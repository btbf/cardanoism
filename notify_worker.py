"""
notify_worker.py
通知バッチワーカー - cron で定期実行する独立スクリプト

※ epoch_start / pool_retire / pool_fee_change / drep_new_governance_action / drep_vote は
  ogmios_listener.py（チェーン同期デーモン）が担当するため、このワーカーでは処理しない。

推奨 cron 設定:
  # pool/drep は30分ごと
  */30 * * * *  python /path/to/notify_worker.py --event pool
  */30 * * * *  python /path/to/notify_worker.py --event drep

  # リマインダーは1時間ごとで十分
  0 * * * *     python /path/to/notify_worker.py --event reminder

  # エポック切り替わり時刻確認
  python notify_worker.py --epoch-schedule

全イベント一括実行:
  python notify_worker.py
"""
import os
import sys
import argparse
import json
import logging
import socket
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# シークレットは Infisical CLI (`infisical run -- python notify_worker.py ...`) で注入する。
# .env は fallback としてのみ読み込み、Infisical 注入値を上書きしない。
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cardanoism", ".env"), override=False)

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.koios import (
    _post, _get, get_current_epoch,
    get_pool_apy, batch_account_info,
    batch_account_update_history, batch_account_reward_history,
    batch_account_reward_history_by_type,
    KOIOS_BATCH_SIZE, _chunks,
)
from cardanoism.backend.line_notify import send_line_push, send_line_flex
from cardanoism.backend import line_flex
from cardanoism.backend.mail_notify import send_email, build_html, build_text
from cardanoism.backend.telegram_notify import send_telegram
from cardanoism.backend.stake_rewards_db import bulk_upsert_stake_rewards

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("notify_worker")

CARDANOISM_URL = os.getenv("CARDANOISM_URL", "https://cardanoism.com")

# ============================================================
# Cardano エポック時刻計算
# ============================================================

# ネットワーク別エポック長（秒）
# mainnet / preprod : 5日 = 432,000秒
# preview           : 1日 =  86,400秒
_CARDANO_EPOCH_SECONDS: dict[str, int] = {
    "mainnet": 432_000,
    "preprod": 432_000,
    "preview":  86_400,
}

MAX_WORKERS = 10  # 並列 Koios API コール数


def _koios_network() -> str:
    return os.getenv("KOIOS_NETWORK", "mainnet").lower()


def _epoch_duration() -> timedelta:
    secs = _CARDANO_EPOCH_SECONDS.get(_koios_network(), 432_000)
    return timedelta(seconds=secs)


def _get_tip_epoch_info() -> dict | None:
    """
    Koios /tip からエポック情報を取得する。
    戻り値: {"epoch_no": int, "epoch_slot": int, "block_time": datetime} | None
    epoch_slot はエポック開始からの経過秒数（Shelley 以降 1 slot = 1 秒）。
    """
    from cardanoism.backend.koios import _get
    data = _get("/tip")
    if not data or not isinstance(data, list) or not data[0]:
        return None
    tip = data[0]
    bt = tip.get("block_time", "")
    # Koios は "2024-04-14T21:44:51" 形式（UTC・タイムゾーン表記なし）で返す場合がある
    if bt:
        if bt.endswith("Z"):
            bt = bt[:-1] + "+00:00"
        elif "+" not in bt and len(bt) == 19:
            bt += "+00:00"
        try:
            block_time = datetime.fromisoformat(bt)
        except ValueError:
            block_time = None
    else:
        block_time = None
    return {
        "epoch_no":   tip.get("epoch_no"),
        "epoch_slot": int(tip.get("epoch_slot") or 0),
        "block_time": block_time,
    }


def print_epoch_schedule(count: int = 10):
    """直近のエポック切り替わり時刻（UTC）を表示する。"""
    tip = _get_tip_epoch_info()
    if tip is None:
        print("Koios API からデータを取得できませんでした")
        return

    epoch_no   = tip["epoch_no"]
    epoch_slot = tip["epoch_slot"]
    block_time = tip["block_time"]
    network    = _koios_network()
    ep_dur     = _epoch_duration()
    ep_secs    = int(ep_dur.total_seconds())

    if block_time:
        current_epoch_start = block_time - timedelta(seconds=epoch_slot)
    else:
        print("block_time が取得できませんでした")
        return

    days_str = f"{ep_secs // 86400}日" if ep_secs % 86400 == 0 else f"{ep_secs // 3600}時間"
    print(f"ネットワーク   : {network}")
    print(f"エポック長     : {ep_secs:,}秒 ({days_str})")
    print(f"現在のエポック : {epoch_no}  (開始: {current_epoch_start.strftime('%Y-%m-%d %H:%M:%S UTC')})")
    print()
    print(f"  {'エポック':>8}  切り替わり時刻 (UTC)")
    print("  " + "-" * 42)
    for i in range(count + 1):
        ep = epoch_no + i
        t  = current_epoch_start + i * ep_dur
        marker = "  ← 現在進行中" if i == 0 else ""
        print(f"  {ep:>8}  {t.strftime('%Y-%m-%d %H:%M:%S UTC')}{marker}")

    next_start = current_epoch_start + ep_dur
    print()
    print("推奨 cron 設定 (EPOCH_CHECK_WINDOW_MIN=60):")
    print(f"  {next_start.minute} {next_start.hour} * * *  EPOCH_CHECK_WINDOW_MIN=60 python notify_worker.py --event epoch_start")


POOL_EVENT_TYPES = [
    "pool_saturation",
    "pool_pledge_shortage",
    "pool_reward_received",
]


# ============================================================
# 状態管理
# ============================================================

def _norm_scope_id(scope_id) -> int:
    """global scope (None) を 0 に正規化。
    scope_id は NOT NULL DEFAULT 0 で扱うため、UNIQUE 制約と ON DUPLICATE KEY UPDATE
    が正しく機能する。NULL 許容にすると MySQL は毎回別物扱いして行が増殖する。
    """
    if scope_id is None:
        return 0
    return int(scope_id)


def get_state(scope_type: str, scope_id, key: str) -> str | None:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT last_value FROM notification_check_state "
            "WHERE scope_type = ? AND scope_id = ? AND key_name = ?",
            (scope_type, _norm_scope_id(scope_id), key),
        )
        row = cursor.fetchone()
        return row["last_value"] if row else None


def set_state(scope_type: str, scope_id, key: str, value: str):
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO notification_check_state (scope_type, scope_id, key_name, last_value)
            VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE last_value = ?, checked_at = NOW()
            """,
            (scope_type, _norm_scope_id(scope_id), key, value, value),
        )
        conn.commit()


def bulk_get_state(scope_type: str, scope_ids: list, key: str) -> dict:
    """複数 scope_id の状態を1クエリで一括取得。{scope_id: last_value}"""
    if not scope_ids:
        return {}
    normalized = [_norm_scope_id(s) for s in scope_ids]
    placeholders = ",".join(["?"] * len(normalized))
    with get_db() as (cursor, _):
        cursor.execute(
            f"SELECT scope_id, last_value FROM notification_check_state "
            f"WHERE scope_type = ? AND scope_id IN ({placeholders}) AND key_name = ?",
            [scope_type, *normalized, key],
        )
        return {row["scope_id"]: row["last_value"] for row in cursor.fetchall()}


def bulk_already_sent(dedup_keys: list[str]) -> set[str]:
    """dedup_key のリストを1クエリで一括チェック。送信済み dedup_key のセットを返す。"""
    if not dedup_keys:
        return set()
    placeholders = ",".join(["?"] * len(dedup_keys))
    with get_db() as (cursor, _):
        cursor.execute(
            f"SELECT DISTINCT dedup_key FROM notification_log WHERE dedup_key IN ({placeholders})",
            dedup_keys,
        )
        return {row["dedup_key"] for row in cursor.fetchall()}


def already_sent(user_id: int, event_type: str, dedup_key: str) -> bool:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT 1 FROM notification_log "
            "WHERE user_id = ? AND event_type = ? AND dedup_key = ?",
            (user_id, event_type, dedup_key),
        )
        return cursor.fetchone() is not None


def log_sent(user_id: int, event_type: str, dedup_key: str, channel: str = "line", payload: str = ""):
    with get_db() as (cursor, conn):
        cursor.execute(
            "INSERT INTO notification_log (user_id, event_type, channel, dedup_key, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, event_type, channel, dedup_key, payload),
        )
        conn.commit()


def push_and_log(line_id: str, user_id: int, event_type: str, dedup_key: str, message: str) -> bool:
    """LINE 送信 + ログ記録。成功時 True。"""
    ok = send_line_push(line_id, message)
    if ok:
        log_sent(user_id, event_type, dedup_key, "line", message[:500])
    return ok


def email_and_log(email: str, user_id: int, event_type: str, dedup_key: str,
                  subject: str, html: str, text: str = "") -> bool:
    """メール送信 + ログ記録。成功時 True。"""
    ok = send_email(email, subject, html, text)
    if ok:
        log_sent(user_id, event_type, dedup_key, "email", subject[:500])
    return ok


def get_users_with_email_event(event_type: str) -> list[dict]:
    """指定イベントが有効でメール通知チャンネルを持つユーザー一覧。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT u.id, u.created_at AS user_created_at,
                   nc.channel_value AS email_addr, COALESCE(u.language, 'ja') AS language
            FROM users u
            JOIN notification_settings ns ON u.id = ns.user_id
            JOIN notification_channels nc ON u.id = nc.user_id
              AND nc.channel_type = 'email' AND nc.enabled = 1
            WHERE ns.event_type = ? AND ns.enabled = 1
            """,
            (event_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_stake_addrs_with_email_event(event_type: str) -> list[dict]:
    """指定イベントが有効なステークアドレスとユーザー情報一覧（メールチャンネル）。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT sa.id AS stake_id, sa.address, sa.nickname,
                   sa.role, sa.created_at,
                   sa.delegated_pool_id, sa.delegated_pool_name,
                   sa.delegated_drep_id, sa.delegated_drep_name,
                   sa.spo_pool_id,
                   u.id AS user_id, nc.channel_value AS email_addr,
                   COALESCE(u.language, 'ja') AS language
            FROM stake_addresses sa
            JOIN users u ON sa.user_id = u.id
            JOIN notification_channels nc ON u.id = nc.user_id
              AND nc.channel_type = 'email' AND nc.enabled = 1
            JOIN stake_notification_settings sns ON sa.id = sns.stake_address_id
            WHERE sns.event_type = ? AND sns.enabled = 1
            """,
            (event_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_users_with_telegram_event(event_type: str) -> list[dict]:
    """指定イベントが有効で Telegram 通知チャンネルを持つユーザー一覧。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT u.id, u.created_at AS user_created_at,
                   nc.channel_value AS telegram_chat_id, COALESCE(u.language, 'ja') AS language
            FROM users u
            JOIN notification_settings ns ON u.id = ns.user_id
            JOIN notification_channels nc ON u.id = nc.user_id
              AND nc.channel_type = 'telegram' AND nc.enabled = 1
            WHERE ns.event_type = ? AND ns.enabled = 1
            """,
            (event_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_stake_addrs_with_telegram_event(event_type: str) -> list[dict]:
    """指定イベントが有効なステークアドレスとユーザー情報一覧（Telegramチャンネル）。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT sa.id AS stake_id, sa.address, sa.nickname,
                   sa.role, sa.created_at,
                   sa.delegated_pool_id, sa.delegated_pool_name,
                   sa.delegated_drep_id, sa.delegated_drep_name,
                   sa.spo_pool_id,
                   u.id AS user_id, nc.channel_value AS telegram_chat_id,
                   COALESCE(u.language, 'ja') AS language
            FROM stake_addresses sa
            JOIN users u ON sa.user_id = u.id
            JOIN notification_channels nc ON u.id = nc.user_id
              AND nc.channel_type = 'telegram' AND nc.enabled = 1
            JOIN stake_notification_settings sns ON sa.id = sns.stake_address_id
            WHERE sns.event_type = ? AND sns.enabled = 1
            """,
            (event_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _merge_stake_channels(line_addrs: list[dict], email_addrs: list[dict], telegram_addrs: list[dict] | None = None) -> list[dict]:
    """
    LINE / email / telegram のアドレスリストを stake_id をキーにマージして返す。
    どちらか一方のチャンネルしか持たない場合も含む。
    """
    merged: dict[int, dict] = {}
    for addr in line_addrs:
        sid = addr["stake_id"]
        merged[sid] = {**addr, "email_addr": None, "telegram_chat_id": None}
    for addr in email_addrs:
        sid = addr["stake_id"]
        if sid not in merged:
            merged[sid] = {**addr, "line_notify_id": None, "telegram_chat_id": None}
        else:
            merged[sid]["email_addr"] = addr["email_addr"]
    for addr in (telegram_addrs or []):
        sid = addr["stake_id"]
        if sid not in merged:
            merged[sid] = {**addr, "line_notify_id": None, "email_addr": None}
        else:
            merged[sid]["telegram_chat_id"] = addr["telegram_chat_id"]
    return list(merged.values())


def flex_and_log(line_id: str, user_id: int, event_type: str, dedup_key: str, alt_text: str, contents: dict) -> bool:
    """LINE Flex 送信 + ログ記録。成功時 True。"""
    ok = send_line_flex(line_id, alt_text, contents)
    if ok:
        log_sent(user_id, event_type, dedup_key, "line", alt_text)
    return ok


def telegram_and_log(chat_id: str, user_id: int, event_type: str, dedup_key: str, text: str) -> bool:
    """Telegram 送信 + ログ記録。成功時 True。"""
    ok = send_telegram(chat_id, text)
    if ok:
        log_sent(user_id, event_type, dedup_key, "telegram", text[:500])
    return ok


# ============================================================
# ユーザー・アドレス取得
# ============================================================

def get_users_with_event(event_type: str) -> list[dict]:
    """指定イベントが有効でLINE通知チャンネルを持つユーザー一覧。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT u.id, u.created_at AS user_created_at,
                   nc.channel_value AS line_notify_id, COALESCE(u.language, 'ja') AS language
            FROM users u
            JOIN notification_settings ns ON u.id = ns.user_id
            JOIN notification_channels nc ON u.id = nc.user_id
              AND nc.channel_type = 'line' AND nc.enabled = 1
            WHERE ns.event_type = ? AND ns.enabled = 1
            """,
            (event_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_stake_addrs_with_event(event_type: str) -> list[dict]:
    """指定イベントが有効なステークアドレスとユーザー情報一覧。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT sa.id AS stake_id, sa.address, sa.nickname,
                   sa.role, sa.created_at,
                   sa.delegated_pool_id, sa.delegated_pool_name,
                   sa.delegated_drep_id, sa.delegated_drep_name,
                   sa.spo_pool_id,
                   u.id AS user_id, nc.channel_value AS line_notify_id,
                   COALESCE(u.language, 'ja') AS language
            FROM stake_addresses sa
            JOIN users u ON sa.user_id = u.id
            JOIN notification_channels nc ON u.id = nc.user_id
              AND nc.channel_type = 'line' AND nc.enabled = 1
            JOIN stake_notification_settings sns ON sa.id = sns.stake_address_id
            WHERE sns.event_type = ? AND sns.enabled = 1
            """,
            (event_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# イベント: プール系
# ============================================================

def refresh_stake_delegations():
    """全ステークアドレスの委任先（プール・DRep）を /account_info で一括リフレッシュしDBを更新する。
    1リクエストで全アドレスを処理し、変化があった行のみ UPDATE する。
    委任先が変わった場合は delegated_pool_name / delegated_drep_name も再解決する。
    """
    from cardanoism.backend.koios import get_pool_name, _fetch_drep_name

    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT id, address, delegated_pool_id, delegated_drep_id FROM stake_addresses"
        )
        rows = [dict(r) for r in cursor.fetchall()]

    if not rows:
        return

    addresses = [r["address"] for r in rows]
    account_map = batch_account_info(addresses)
    if not account_map:
        logger.warning("refresh_stake_delegations: /account_info の取得に失敗しました")
        return

    # 同一 pool / drep への名前解決を 1 run 内で重複 Koios コールしないようメモ化
    _pool_name_memo: dict[str, str] = {}
    _drep_name_memo: dict[str, str] = {}

    def _pool_name(pid: str | None) -> str | None:
        if not pid:
            return None
        if pid not in _pool_name_memo:
            try:
                _pool_name_memo[pid] = get_pool_name(pid) or ""
            except Exception as e:  # noqa: BLE001
                logger.warning("pool 名解決失敗 %s: %s", pid, e)
                _pool_name_memo[pid] = ""
        return _pool_name_memo[pid] or None

    def _drep_name(did: str | None) -> str | None:
        if not did:
            return None
        if did not in _drep_name_memo:
            try:
                _drep_name_memo[did] = _fetch_drep_name(did) or ""
            except Exception as e:  # noqa: BLE001
                logger.warning("drep 名解決失敗 %s: %s", did, e)
                _drep_name_memo[did] = ""
        return _drep_name_memo[did] or None

    updated = 0
    for row in rows:
        account = account_map.get(row["address"])
        if not account:
            continue

        new_pool_id = account.get("delegated_pool") or None
        new_drep_id = account.get("delegated_drep") or None

        # 特殊DRep値はNoneとして扱う
        if new_drep_id in ("drep_always_abstain", "drep_always_no_confidence"):
            new_drep_id = None

        if new_pool_id == row["delegated_pool_id"] and new_drep_id == row["delegated_drep_id"]:
            continue  # 変化なし

        # 委任先が変わったので名前も再解決する (旧名がダッシュボードに残る不具合の修正)
        new_pool_name = _pool_name(new_pool_id)
        new_drep_name = _drep_name(new_drep_id)

        with get_db() as (cursor, conn):
            cursor.execute(
                """UPDATE stake_addresses
                   SET delegated_pool_id = ?, delegated_pool_name = ?,
                       delegated_drep_id = ?, delegated_drep_name = ?,
                       role_checked_at = NOW()
                   WHERE id = ?""",
                (new_pool_id, new_pool_name, new_drep_id, new_drep_name, row["id"]),
            )
            conn.commit()

        logger.info(
            "委任先更新: address_id=%d  pool %s→%s (%s)  drep %s→%s (%s)",
            row["id"],
            row["delegated_pool_id"], new_pool_id, new_pool_name,
            row["delegated_drep_id"], new_drep_id, new_drep_name,
        )
        updated += 1

    logger.info("refresh_stake_delegations: %d件更新 / %d件チェック", updated, len(rows))


def _fetch_pool_info(pool_id: str) -> dict | None:
    data = _post("/pool_info", {"_pool_bech32_ids": [pool_id]})
    if not data or not isinstance(data, list) or not data[0]:
        return None
    return data[0]


def _fetch_pool_infos_batch(pool_ids: list[str]) -> dict[str, dict]:
    """複数プールの情報を1リクエストで一括取得。{pool_id_bech32: info} を返す。"""
    if not pool_ids:
        return {}
    data = _post("/pool_info", {"_pool_bech32_ids": pool_ids})
    if not data or not isinstance(data, list):
        return {}
    return {item["pool_id_bech32"]: item for item in data if item.get("pool_id_bech32")}


def check_pool_events():
    logger.info("プールイベント チェック開始")

    # LINE / email / telegram チャンネルを持つアドレスをまとめて収集
    all_addrs: dict[int, dict] = {}
    enabled_events: dict[int, set] = {}

    for event_type in POOL_EVENT_TYPES:
        for addr in get_stake_addrs_with_event(event_type):
            sid = addr["stake_id"]
            if sid not in all_addrs:
                all_addrs[sid] = {**addr, "email_addr": None, "telegram_chat_id": None}
            enabled_events.setdefault(sid, set()).add(event_type)
        for addr in get_stake_addrs_with_email_event(event_type):
            sid = addr["stake_id"]
            if sid not in all_addrs:
                all_addrs[sid] = {**addr, "line_notify_id": None, "telegram_chat_id": None}
            all_addrs[sid]["email_addr"] = addr["email_addr"]
            enabled_events.setdefault(sid, set()).add(event_type)
        for addr in get_stake_addrs_with_telegram_event(event_type):
            sid = addr["stake_id"]
            if sid not in all_addrs:
                all_addrs[sid] = {**addr, "line_notify_id": None, "email_addr": None}
            all_addrs[sid]["telegram_chat_id"] = addr["telegram_chat_id"]
            enabled_events.setdefault(sid, set()).add(event_type)

    # /tip を1回だけ呼んでエポックをキャッシュ
    current_epoch = get_current_epoch()

    # 全プールの pool_info を1リクエストで一括取得
    pool_ids = list({a["delegated_pool_id"] for a in all_addrs.values() if a.get("delegated_pool_id")})
    pool_infos = _fetch_pool_infos_batch(pool_ids)

    # APY を並列取得（プールごとに独立した API コールのため ThreadPoolExecutor で高速化）
    pool_apys: dict[str, float | None] = {}
    if current_epoch is not None:
        apy_epoch = current_epoch - 2
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(get_pool_apy, pid, apy_epoch): pid for pid in pool_ids}
            for f in as_completed(futures):
                pool_apys[futures[f]] = f.result()

    # 各アドレスのイベントをチェック（pool_reward_received は後で一括処理）
    for stake_id, addr in all_addrs.items():
        pool_id = addr.get("delegated_pool_id")
        if not pool_id or pool_id not in pool_infos:
            continue
        pool_info = pool_infos[pool_id]
        apy = pool_apys.get(pool_id)
        for event_type in enabled_events[stake_id]:
            if event_type == "pool_reward_received":
                continue
            _check_pool_event(event_type, addr, pool_info, apy, current_epoch=current_epoch)

    # pool_reward_received を /account_reward_history 一括呼び出しで処理
    _check_pool_reward_received_batch(all_addrs, enabled_events, current_epoch, pool_apys)


def _apy_line(apy: float | None) -> str:
    """APY行を返す。取得できない場合は空文字。"""
    if apy is None:
        return ""
    return f"\nAPY: {apy:.2f}%"


def _check_pool_event(event_type: str, addr: dict, pool_info: dict, apy: float | None = None, current_epoch: int | None = None):
    stake_id = addr["stake_id"]
    user_id = addr["user_id"]
    line_id = addr["line_notify_id"]
    lang = addr.get("language", "ja")
    pool_name = addr.get("delegated_pool_name") or (addr.get("delegated_pool_id") or "")[:12]
    nickname = addr["nickname"]

    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.pool_saturation import context as ctx_sat
    from cardanoism.backend.notify_templates.pool_pledge_shortage import context as ctx_pledge

    if event_type == "pool_saturation":
        saturation = pool_info.get("live_saturation")
        if saturation is None:
            return
        # Koios の live_saturation は既にパーセント値 (例: 53.51 = 53.51%)。× 100 不要。
        # cf. pool_search.py の同フィールドコメント。
        sat_pct = float(saturation)
        is_saturated = sat_pct > 100
        was_saturated = get_state("stake_address", stake_id, "pool_saturated")
        if is_saturated and was_saturated != "1":
            set_state("stake_address", stake_id, "pool_saturated", "1")
            dedup_key = f"pool_saturation_{stake_id}_{int(sat_pct)}"
            ctx = ctx_sat(
                pool_name=pool_name, sat_pct=sat_pct, apy=apy,
                nickname=nickname, base_url=CARDANOISM_URL,
            )
            deliver(addr, event_type, ctx, dedup_base=dedup_key)
        elif not is_saturated and was_saturated == "1":
            set_state("stake_address", stake_id, "pool_saturated", "0")

    elif event_type == "pool_pledge_shortage":
        live_pledge = int(pool_info.get("live_pledge") or 0)
        pledge = int(pool_info.get("pledge") or 0)
        is_short = live_pledge < pledge
        was_short = get_state("stake_address", stake_id, "pool_pledge_short")
        if is_short and was_short != "1":
            set_state("stake_address", stake_id, "pool_pledge_short", "1")
            dedup_key = f"pool_pledge_short_{stake_id}"
            ctx = ctx_pledge(
                pool_name=pool_name,
                pledged_ada=pledge / 1_000_000,
                live_ada=live_pledge / 1_000_000,
                apy=apy, nickname=nickname, base_url=CARDANOISM_URL,
            )
            deliver(addr, event_type, ctx, dedup_base=dedup_key)
        elif not is_short and was_short == "1":
            set_state("stake_address", stake_id, "pool_pledge_short", "0")

    elif event_type == "pool_reward_received":
        pass  # check_pool_events で _check_pool_reward_received_batch に一括委譲


def _check_pool_reward_received_batch(
    all_addrs: dict,
    enabled_events: dict,
    current_epoch: int | None,
    pool_apys: dict,
):
    """
    報酬入金通知を全対象アドレスに対して /account_reward_history 1回で一括処理する。
    Cardanoでは Epoch N のスナップショット → Epoch N+2 で報酬が確定・入金される。

    SPO の場合 (spo_pool_id 設定済み): leader (オペレーター報酬) を「SPO 報酬」として
    通知し、member (ステーク報酬) は混乱を避けるため通知しない (合算は Flex 内で表示)。
    通常委任者の場合: member 報酬を従来どおり通知。
    """
    if current_epoch is None:
        return
    reward_epoch = current_epoch - 2

    def _eligible_for_reward(addr: dict) -> bool:
        """新規ユーザー保護: アドレス登録前にウォレットへ入金済みの報酬は通知しない。

        Cardano 報酬は snapshot(epoch N) → 入金(epoch N+2) で、入金は epoch N+1 終了
        ⇒ epoch N+2 開始 のタイミング。アドレスを epoch R で登録した場合:
          - reward_epoch = R-2 の報酬は epoch R 開始時点で既に入金済み → 通知しない
          - reward_epoch = R-1 の報酬は epoch R+1 開始時点に入金 (登録後) → 通知する
        よって閾値は `reward_epoch >= R - 1`。
        """
        created = addr.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except ValueError:
                return True
        if not created:
            return True
        addr_epoch = _datetime_to_mainnet_epoch(created)
        if addr_epoch is None:
            return True
        return reward_epoch >= addr_epoch - 1

    # dedup 済みでない報酬通知対象アドレスを収集
    reward_addrs = [
        addr for stake_id, addr in all_addrs.items()
        if "pool_reward_received" in enabled_events.get(stake_id, set())
        and _eligible_for_reward(addr)
        and not already_sent(
            addr["user_id"], "pool_reward_received", f"reward_{addr['stake_id']}_{reward_epoch}"
        )
    ]
    if not reward_addrs:
        return

    # type 別に取得 (1 アドレス × 1 epoch で member / leader / other がそれぞれ別行)
    reward_by_type = batch_account_reward_history_by_type(
        [a["address"] for a in reward_addrs], reward_epoch
    )
    if not reward_by_type:
        return

    # ダッシュボード用キャッシュ: type 別に upsert
    addr_to_pool = {
        a["address"]: (a.get("delegated_pool_id") or None)
        for a in reward_addrs
    }
    try:
        bulk_upsert_stake_rewards(
            (sa, reward_epoch, lovelace, addr_to_pool.get(sa), rt)
            for (sa, rt), lovelace in reward_by_type.items()
        )
    except Exception as _e:  # noqa: BLE001
        logger.warning("stake_rewards cache upsert failed: %s", _e)

    # 各アドレスに通知 (notify_templates 経由で 3 チャンネル統合送信)
    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.pool_reward_received import (
        context as build_ctx, EVENT_TYPE,
    )
    for addr in reward_addrs:
        sa = addr["address"]
        member_lov = reward_by_type.get((sa, "member"), 0)
        leader_lov = reward_by_type.get((sa, "leader"), 0)
        is_spo = bool(addr.get("spo_pool_id"))

        # SPO の場合: leader のみ通知。leader=0 なら通知しない。
        # 非 SPO: member 報酬 (通常 leader=0 なので合算でも変わらず) を通知。
        if is_spo:
            primary_lov = leader_lov
        else:
            primary_lov = member_lov + leader_lov
        if primary_lov <= 0:
            continue

        ctx = build_ctx(
            reward_epoch=reward_epoch,
            primary_ada=primary_lov / 1_000_000,
            apy=pool_apys.get(addr.get("delegated_pool_id") or ""),
            nickname=addr["nickname"],
            is_leader=is_spo,
            base_url=CARDANOISM_URL,
            pool_name=addr.get("delegated_pool_name") or "",
        )
        deliver(addr, EVENT_TYPE, ctx, dedup_base=f"reward_{addr['stake_id']}_{reward_epoch}")


# ============================================================
# イベント: DRep系
# ============================================================

REMINDER_MILESTONES = [90, 120, 365]


def check_delegation_reminders():
    logger.info("長期委任リマインダー チェック開始")
    _check_pool_delegation_reminder()
    _check_drep_delegation_reminder()


def _days_since_dt(dt) -> int | None:
    from datetime import datetime, timezone
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def _highest_passed_milestone(days: int) -> int | None:
    """days が到達している最高のマイルストーンを返す。
    例: days=400 → 365、days=121 → 120、days=80 → None。

    365 日以上経過したアドレスを新規登録した場合に 90/120/365 を 3 通同時に
    送らないため、必ず最高 1 件だけを通知対象にする。
    """
    for ms in sorted(REMINDER_MILESTONES, reverse=True):
        if days >= ms:
            return ms
    return None



def _check_pool_delegation_reminder():
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("pool_delegation_reminder"),
        get_stake_addrs_with_email_event("pool_delegation_reminder"),
        get_stake_addrs_with_telegram_event("pool_delegation_reminder"),
    )
    addrs = [a for a in addrs if a.get("delegated_pool_id")]
    if not addrs:
        return

    # キャッシュが未設定のアドレスを /account_update_history で一括取得
    uncached = [a for a in addrs if not get_state("stake_address", a["stake_id"], "pool_delegation_date")]
    if uncached:
        history_map = batch_account_update_history([a["address"] for a in uncached])
        for addr in uncached:
            entries = history_map.get(addr["address"], [])
            pool_entries = [e for e in entries if e.get("action_type") == "delegation_pool"]
            if pool_entries:
                latest = max(pool_entries, key=lambda e: e.get("block_time", 0))
                bt = latest.get("block_time")
                if bt:
                    dt = datetime.fromtimestamp(int(bt), tz=timezone.utc)
                    set_state("stake_address", addr["stake_id"], "pool_delegation_date", dt.isoformat())

    # ユニークプールIDの APY を一括取得
    unique_pool_ids = list({a["delegated_pool_id"] for a in addrs})
    pool_apys: dict[str, float | None] = {pid: get_pool_apy(pid) for pid in unique_pool_ids}

    for addr in addrs:
        cached = get_state("stake_address", addr["stake_id"], "pool_delegation_date")
        if not cached:
            continue
        try:
            dt = datetime.fromisoformat(cached).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        days = _days_since_dt(dt)
        if days is None:
            continue

        pool_id = addr["delegated_pool_id"]
        pool_name = addr.get("delegated_pool_name") or pool_id[:12]
        apy = pool_apys.get(pool_id)
        # 到達済みの最高マイルストーン 1 件だけ通知する (3 通同時送信を防ぐ)
        milestone = _highest_passed_milestone(days)
        if milestone is None:
            continue
        dedup_key = f"pool_remind_{addr['stake_id']}_{milestone}d"
        if already_sent(addr["user_id"], "pool_delegation_reminder", dedup_key):
            continue
        from cardanoism.backend.notify_templates import deliver
        from cardanoism.backend.notify_templates.pool_delegation_reminder import (
            context as ctx_pool_remind,
        )
        ctx = ctx_pool_remind(
            pool_name=pool_name, milestone=milestone, apy=apy,
            nickname=addr["nickname"], base_url=CARDANOISM_URL,
        )
        deliver(addr, "pool_delegation_reminder", ctx, dedup_base=dedup_key)


def _check_drep_delegation_reminder():
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_delegation_reminder"),
        get_stake_addrs_with_email_event("drep_delegation_reminder"),
        get_stake_addrs_with_telegram_event("drep_delegation_reminder"),
    )
    addrs = [a for a in addrs if a.get("delegated_drep_id")]
    if not addrs:
        return

    # キャッシュが未設定のアドレスを /account_update_history で一括取得
    uncached = [a for a in addrs if not get_state("stake_address", a["stake_id"], "drep_delegation_date")]
    if uncached:
        history_map = batch_account_update_history([a["address"] for a in uncached])
        for addr in uncached:
            entries = history_map.get(addr["address"], [])
            drep_entries = [e for e in entries if e.get("action_type") == "delegation_drep"]
            if drep_entries:
                latest = max(drep_entries, key=lambda e: e.get("block_time", 0))
                bt = latest.get("block_time")
                if bt:
                    dt = datetime.fromtimestamp(int(bt), tz=timezone.utc)
                    set_state("stake_address", addr["stake_id"], "drep_delegation_date", dt.isoformat())

    for addr in addrs:
        cached = get_state("stake_address", addr["stake_id"], "drep_delegation_date")
        if not cached:
            continue
        try:
            dt = datetime.fromisoformat(cached).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        days = _days_since_dt(dt)
        if days is None:
            continue

        drep_id = addr["delegated_drep_id"]
        drep_name = addr.get("delegated_drep_name") or drep_id[:12]
        # 到達済みの最高マイルストーン 1 件だけ通知する (3 通同時送信を防ぐ)
        milestone = _highest_passed_milestone(days)
        if milestone is None:
            continue
        dedup_key = f"drep_remind_{addr['stake_id']}_{milestone}d"
        if already_sent(addr["user_id"], "drep_delegation_reminder", dedup_key):
            continue
        from cardanoism.backend.notify_templates import deliver
        from cardanoism.backend.notify_templates.drep_delegation_reminder import (
            context as ctx_drep_remind,
        )
        ctx = ctx_drep_remind(
            drep_name=drep_name, milestone=milestone,
            nickname=addr["nickname"], base_url=CARDANOISM_URL,
        )
        deliver(addr, "drep_delegation_reminder", ctx, dedup_base=dedup_key)


def check_drep_events():
    logger.info("DRepイベント チェック開始")
    _check_drep_status_change()
    _check_drep_unvoted_ga()


def _check_drep_status_change():
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_status_change"),
        get_stake_addrs_with_email_event("drep_status_change"),
        get_stake_addrs_with_telegram_event("drep_status_change"),
    )
    addrs = [a for a in addrs if a.get("delegated_drep_id")]
    if not addrs:
        return

    # ユニーク drep_id を 1,000 件チャンクで一括取得
    unique_drep_ids = list({a["delegated_drep_id"] for a in addrs})
    drep_status_map: dict[str, str] = {}
    for chunk in _chunks(unique_drep_ids, KOIOS_BATCH_SIZE):
        data = _post("/drep_info", {"_drep_ids": chunk})
        if data and isinstance(data, list):
            for item in data:
                if item.get("drep_id"):
                    drep_status_map[item["drep_id"]] = item.get("status") or ""
    if not drep_status_map:
        return

    for addr in addrs:
        drep_id = addr["delegated_drep_id"]
        status = drep_status_map.get(drep_id)
        if status is None:
            continue

        stake_id = addr["stake_id"]
        user_id = addr["user_id"]
        line_id = addr["line_notify_id"]
        lang = addr.get("language", "ja")
        drep_name = addr.get("delegated_drep_name") or drep_id[:12]

        last_status = get_state("stake_address", stake_id, "drep_status")
        if last_status is None:
            set_state("stake_address", stake_id, "drep_status", status)
            continue
        if last_status == status:
            continue

        set_state("stake_address", stake_id, "drep_status", status)
        dedup_key = f"drep_status_{stake_id}_{status}"
        if already_sent(user_id, "drep_status_change", dedup_key):
            continue

        from cardanoism.backend.notify_templates import deliver
        from cardanoism.backend.notify_templates.drep_status_change import (
            context as ctx_status,
        )
        ctx = ctx_status(
            drep_name=drep_name, old_status=last_status, new_status=status,
            nickname=addr["nickname"], base_url=CARDANOISM_URL,
        )
        deliver(addr, "drep_status_change", ctx, dedup_base=dedup_key)


# ============================================================
# DRep 未投票 GA リマインダー（本人向け）
# ============================================================

# DRep 未投票 GA リマインダーの定数
DREP_UNVOTED_PRE_RATIFY_GAP_PT = 10.0   # 批准閾値の何 pt 手前で発火するか
DREP_UNVOTED_NEAR_EXPIRE_EPOCHS = 2     # expiration までこの epoch 以下で発火


def _check_drep_unvoted_ga():
    """DRep 本人 (stake_addresses.role='drep') が未投票の Active な GA を検知し、
    以下のいずれかが先に成立した時点で「1 GA につき 1 通」だけ通知する:

      - "7d"          : block_time から 7 日経過
      - "14d"         : block_time から 14 日経過
      - "pre_ratify"  : drep_yes_pct が批准閾値の 10pt 手前 (例: 67% → 57%) に到達
      - "near_expire" : expiration まで残り 2 epoch 以下

    dedup_key は GA 単位 (`drep_unvoted_{stake_id}_{proposal_id}`) で固定し、
    どのトリガーで発火したかを ctx.trigger に詰めて配信する。
    複数該当時は切迫度の高い順に pre_ratify > near_expire > 14d > 7d を採用。
    """
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_unvoted_ga"),
        get_stake_addrs_with_email_event("drep_unvoted_ga"),
        get_stake_addrs_with_telegram_event("drep_unvoted_ga"),
    )
    # role='drep' かつ自身の drep_id が判明しているアドレスのみ対象
    drep_addrs = [a for a in addrs if a.get("role") == "drep" and a.get("delegated_drep_id")]
    if not drep_addrs:
        return

    # Active な GA を一括取得（block_time / proposal_type / title / expiration 含む）
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, proposal_type, block_time, expiration, title, title_ja
            FROM governance_actions
            WHERE proposal_id IS NOT NULL AND proposal_id <> ''
              AND block_time IS NOT NULL
              AND ratified_epoch IS NULL
              AND enacted_epoch  IS NULL
              AND dropped_epoch  IS NULL
              AND expired_epoch  IS NULL
            """
        )
        active_gas = [dict(r) for r in cursor.fetchall()]

    if not active_gas:
        return

    # プロトコルパラメータと voting summary を 1 回ずつ読み込む
    from cardanoism.backend.params_db import get_protocol_params, thresholds_for_type
    params = get_protocol_params()

    # 現在エポック: params に epoch_no があればそれを使い、なければ Koios で取得
    current_epoch: int | None = None
    if params and params.get("epoch_no") is not None:
        try:
            current_epoch = int(params["epoch_no"])
        except (TypeError, ValueError):
            current_epoch = None
    if current_epoch is None:
        try:
            from cardanoism.backend.koios import get_current_epoch
            current_epoch = get_current_epoch()
        except Exception:
            current_epoch = None

    proposal_ids = [g["proposal_id"] for g in active_gas]
    summary_map: dict[str, float] = {}  # proposal_id → drep_yes_pct (0-100)
    if proposal_ids:
        placeholders = ",".join(["?"] * len(proposal_ids))
        with get_db() as (cursor, _):
            cursor.execute(
                f"SELECT proposal_id, drep_yes_pct FROM proposal_voting_summary "
                f"WHERE proposal_id IN ({placeholders})",
                proposal_ids,
            )
            for r in cursor.fetchall():
                row = dict(r)
                try:
                    summary_map[row["proposal_id"]] = float(row.get("drep_yes_pct") or 0.0)
                except (TypeError, ValueError):
                    summary_map[row["proposal_id"]] = 0.0

    # 各 DRep が既に投票済みの proposal_id 集合を 1 回の問い合わせで取得
    unique_drep_ids = list({a["delegated_drep_id"] for a in drep_addrs})
    voted_pairs: set[tuple[str, str]] = set()  # (drep_id, proposal_id)
    if unique_drep_ids and proposal_ids:
        d_placeholders = ",".join(["?"] * len(unique_drep_ids))
        p_placeholders = ",".join(["?"] * len(proposal_ids))
        with get_db() as (cursor, _):
            cursor.execute(
                f"""
                SELECT DISTINCT voter_id, proposal_id
                FROM proposal_votes
                WHERE voter_role = 'DRep'
                  AND voter_id IN ({d_placeholders})
                  AND proposal_id IN ({p_placeholders})
                """,
                [*unique_drep_ids, *proposal_ids],
            )
            for r in cursor.fetchall():
                row = dict(r)
                voted_pairs.add((row["voter_id"], row["proposal_id"]))

    now = datetime.now(timezone.utc)

    for ga in active_gas:
        pid = ga["proposal_id"]
        ptype = ga.get("proposal_type") or ""
        block_time = ga.get("block_time")
        if not block_time:
            continue
        # block_time は DATETIME (UTC として扱う)
        if isinstance(block_time, str):
            try:
                block_dt = datetime.fromisoformat(block_time)
            except ValueError:
                continue
        else:
            block_dt = block_time
        if block_dt.tzinfo is None:
            block_dt = block_dt.replace(tzinfo=timezone.utc)

        days_elapsed = (now - block_dt).total_seconds() / 86400.0

        # 提案タイプに応じて DRep が voter として有効でないなら通知しない
        from cardanoism.backend.params_db import voters_for_type
        if not voters_for_type(ptype).get("drep"):
            continue

        # 批准閾値 (DRep)。閾値が None / 0 のタイプ (NoConfidence で SPO のみ等) は pre_ratify トリガーなし
        thresholds = thresholds_for_type(ptype, params)
        drep_th = thresholds.get("drep") if thresholds else None
        # "10pt 手前" = (批准閾値 % - 10pt). drep_th=0.67 なら 57.0
        pre_ratify_pct: float | None = None
        if drep_th and drep_th > 0:
            cutoff = drep_th * 100.0 - DREP_UNVOTED_PRE_RATIFY_GAP_PT
            if cutoff > 0:
                pre_ratify_pct = cutoff
        drep_yes_pct = summary_map.get(pid, 0.0)

        # 残エポック数 (expiration が記録されているとき)
        expiration_epoch = ga.get("expiration")
        epochs_left: int | None = None
        if expiration_epoch is not None and current_epoch is not None:
            try:
                epochs_left = int(expiration_epoch) - current_epoch
            except (TypeError, ValueError):
                epochs_left = None

        # トリガー判定: 切迫度の高い順に最初にヒットしたものを採用
        trigger: str | None = None
        if pre_ratify_pct is not None and drep_yes_pct >= pre_ratify_pct:
            trigger = "pre_ratify"
        elif epochs_left is not None and epochs_left <= DREP_UNVOTED_NEAR_EXPIRE_EPOCHS:
            trigger = "near_expire"
        elif days_elapsed >= 14:
            trigger = "14d"
        elif days_elapsed >= 7:
            trigger = "7d"
        else:
            continue

        title = ga.get("title_ja") or ga.get("title") or pid

        for addr in drep_addrs:
            drep_id = addr["delegated_drep_id"]
            if (drep_id, pid) in voted_pairs:
                continue

            # 新規ユーザー保護: ユーザーがこのアドレスを登録するより前に提出された
            # GA は通知しない。これがないと「アドレス登録 + 通知チャンネル連携」と
            # 同時に過去の Active GA すべてを 1 ユーザーに洪水的に通知してしまう。
            addr_created_at = addr.get("created_at")
            if isinstance(addr_created_at, str):
                try:
                    addr_created_at = datetime.fromisoformat(addr_created_at)
                except ValueError:
                    addr_created_at = None
            if addr_created_at and addr_created_at.tzinfo is None:
                addr_created_at = addr_created_at.replace(tzinfo=timezone.utc)
            if addr_created_at and block_dt < addr_created_at:
                continue

            stake_id = addr["stake_id"]
            user_id = addr["user_id"]
            lang = addr.get("language", "ja")
            dedup_key = f"drep_unvoted_{stake_id}_{pid}"
            if already_sent(user_id, "drep_unvoted_ga", dedup_key):
                continue

            from cardanoism.backend.notify_templates import deliver
            from cardanoism.backend.notify_templates.drep_unvoted_ga import (
                context as ctx_unvoted,
            )
            ctx = ctx_unvoted(
                title=title,
                proposal_type_label=ptype or "-",
                trigger=trigger,
                nickname=addr["nickname"],
                proposal_id=pid,
                base_url=CARDANOISM_URL,
            )
            deliver(addr, "drep_unvoted_ga", ctx, dedup_base=dedup_key)


# ============================================================
# プロトコルパラメータ同期
# ============================================================

def check_params_sync():
    """最新エポックのプロトコルパラメータ（投票閾値・デポジット等）と、
    CC の quorum（committee_info）を DB にキャッシュする。"""
    from cardanoism.backend.koios import get_current_epoch, get_epoch_params, get_committee_info
    from cardanoism.backend.params_db import upsert_protocol_params

    logger.info("プロトコルパラメータ同期 開始")
    epoch = get_current_epoch()
    if epoch is None:
        logger.warning("現在のエポック取得失敗")
        return
    params = get_epoch_params(epoch_no=epoch)
    if not params:
        logger.warning("エポックパラメータ取得失敗")
        return

    # CC quorum + メンバーを committee_info から取得
    cc_info = get_committee_info()
    if cc_info:
        params["cc_quorum_numerator"]   = cc_info.get("quorum_numerator")
        params["cc_quorum_denominator"] = cc_info.get("quorum_denominator")
        logger.info("CC quorum: %s / %s", cc_info.get("quorum_numerator"), cc_info.get("quorum_denominator"))
    else:
        logger.warning("committee_info 取得失敗。CC 閾値は更新されません")

    upsert_protocol_params(params)

    # CC メンバーを cc_members テーブルに UPSERT
    if cc_info:
        from cardanoism.backend.params_db import upsert_cc_member
        members = cc_info.get("members") or []
        for m in members:
            try:
                upsert_cc_member(m)
            except Exception as e:
                logger.exception("upsert_cc_member failed: %s", e)
        logger.info("CC メンバー %d 件を同期", len(members))

    logger.info("プロトコルパラメータ同期 完了 (epoch=%s)", epoch)


# ============================================================
# 投票理由（rationale）取得 + 翻訳
# ============================================================

def check_vote_rationale_sync(fetch_limit: int = 500, translate_limit: int = 100):
    """
    proposal_votes.meta_url から投票メタデータ（CIP-100）を取得して body.comment を抽出。
    取得した rationale が英語なら OpenAI で日本語翻訳して rationale_ja に保存。

    fetch_limit:     1 実行あたりのメタデータ取得上限件数（0 で無制限）
    translate_limit: 1 実行あたりの翻訳対象件数（OpenAI API コスト制御。0 で無制限）
    """
    from cardanoism.backend.vote_meta_fetch import (
        fetch_vote_metadata_json, extract_rationale, is_japanese,
    )
    from cardanoism.backend.vote_db import update_rationale

    fetch_label = "無制限" if fetch_limit <= 0 else str(fetch_limit)
    translate_label = "無制限" if translate_limit <= 0 else str(translate_limit)
    logger.info("投票理由同期 開始 (fetch_limit=%s, translate_limit=%s)", fetch_label, translate_label)

    # Step 1: meta_url が有り、rationale 未取得のレコードをフェッチ
    fetch_sql = (
        "SELECT id, meta_url "
        "FROM proposal_votes "
        "WHERE meta_url IS NOT NULL AND meta_url <> '' "
        "  AND meta_fetched_at IS NULL "
        "  AND voter_role = 'DRep' "
        "ORDER BY block_time DESC"
    )
    fetch_params: list = []
    if fetch_limit and fetch_limit > 0:
        fetch_sql += " LIMIT ?"
        fetch_params.append(int(fetch_limit))

    with get_db() as (cursor, _):
        cursor.execute(fetch_sql, fetch_params)
        rows = [dict(r) for r in cursor.fetchall()]

    logger.info("メタデータ取得対象: %d 件", len(rows))
    fetched = 0
    for i, r in enumerate(rows, 1):
        vid = r["id"]
        url = r["meta_url"]
        meta = fetch_vote_metadata_json(url)
        rationale = extract_rationale(meta)
        try:
            # rationale が空でも meta_fetched_at はセットする（再取得を避けるため）
            update_rationale(vid, rationale if rationale else None)
            fetched += 1
        except Exception as e:
            logger.exception("update_rationale failed (id=%s): %s", vid, e)
        if i % 50 == 0:
            logger.info("  フェッチ進捗: %d / %d", i, len(rows))
    logger.info("メタデータ取得完了: %d 件処理", fetched)

    # Step 2: 翻訳対象（英語テキストで rationale_ja が空）を OpenAI で翻訳
    translate_sql = (
        "SELECT id, rationale "
        "FROM proposal_votes "
        "WHERE rationale IS NOT NULL AND rationale <> '' "
        "  AND (rationale_ja IS NULL OR rationale_ja = '') "
        "ORDER BY block_time DESC"
    )
    translate_params: list = []
    if translate_limit and translate_limit > 0:
        translate_sql += " LIMIT ?"
        translate_params.append(int(translate_limit))

    with get_db() as (cursor, _):
        cursor.execute(translate_sql, translate_params)
        translate_rows = [dict(r) for r in cursor.fetchall()]

    # 日本語判定ですでに日本語のものは除外
    english_rows = [r for r in translate_rows if not is_japanese(r["rationale"])]
    logger.info("翻訳対象: %d 件 (全候補 %d / 日本語スキップ %d)",
                len(english_rows), len(translate_rows), len(translate_rows) - len(english_rows))

    if english_rows:
        from cardanoism.backend.governance import build_translator
        translator = build_translator()
        translated_ok = 0
        for i, r in enumerate(english_rows, 1):
            vid = r["id"]
            text = r["rationale"]
            try:
                translated = translator.translate_overview(text)
                if translated:
                    with get_db() as (cursor, conn):
                        cursor.execute(
                            "UPDATE proposal_votes SET rationale_ja = ? WHERE id = ?",
                            (translated, int(vid)),
                        )
                        conn.commit()
                    translated_ok += 1
            except Exception as e:
                logger.exception("translate failed (id=%s): %s", vid, e)
            if i % 10 == 0:
                logger.info("  翻訳進捗: %d / %d", i, len(english_rows))
        logger.info("翻訳完了: %d 件成功 / %d 件試行", translated_ok, len(english_rows))

    logger.info("投票理由同期 完了")


# ============================================================
# 投票同期
# ============================================================

def _dedupe_latest_votes(votes: list[dict]) -> list[dict]:
    """
    Koios レスポンス内で同じ voter が複数回投票している場合、
    block_time が最新のもののみを残す。
    """
    latest: dict[tuple, dict] = {}
    for v in votes:
        key = (v.get("voter_role") or "", v.get("voter_id") or "")
        bt = v.get("block_time") or 0
        try:
            bt_int = int(bt)
        except (TypeError, ValueError):
            bt_int = 0
        cur = latest.get(key)
        if cur is None:
            latest[key] = v
        else:
            cur_bt = cur.get("block_time") or 0
            try:
                cur_bt_int = int(cur_bt)
            except (TypeError, ValueError):
                cur_bt_int = 0
            if bt_int > cur_bt_int:
                latest[key] = v
    return list(latest.values())


def check_vote_sync():
    """
    governance_actions テーブルの全 proposal を対象に、Koios /proposal_votes を取得して
    proposal_votes テーブルにキャッシュする。投票は常に最新トランザクション
    （block_time 最大）を採用。
    投票集計（/proposal_voting_summary）は重いので別バッチ（summary_sync）で行う。
    """
    from cardanoism.backend.koios import get_proposal_votes
    from cardanoism.backend.vote_db import bulk_upsert_votes

    logger.info("投票同期 開始")

    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id
            FROM governance_actions
            WHERE proposal_id IS NOT NULL AND proposal_id <> ''
            ORDER BY block_time DESC
            """
        )
        proposal_ids = [r["proposal_id"] for r in cursor.fetchall() if r.get("proposal_id")]

    logger.info("投票取得対象 proposal: %d 件", len(proposal_ids))
    total_votes = 0
    for i, pid in enumerate(proposal_ids, 1):
        try:
            votes = get_proposal_votes(pid)
            if votes:
                deduped = _dedupe_latest_votes(votes)
                n = bulk_upsert_votes(pid, deduped)
                total_votes += n
            if i % 20 == 0:
                logger.info("  進捗: %d / %d proposal", i, len(proposal_ids))
        except Exception as e:
            logger.exception("vote_sync (proposal_id=%s) failed: %s", pid, e)
    logger.info("投票同期 完了: %d 件 upsert", total_votes)


# ============================================================
# 投票集計同期（重い /proposal_voting_summary 専用）
# ============================================================

def check_summary_sync(max_workers: int = 6):
    """
    /proposal_voting_summary は Koios 側で計算コストが高く 1 件数十秒かかる場合がある。
    ThreadPoolExecutor で並列化（既存のレートリミッタが自動的に 80req/10s で絞る）。

    対象は **Active な GA のみ** (ratified / enacted / dropped / expired を除く)。
    pre_ratify トリガー (drep_yes_pct ≥ 批准値 -10pt) のリアルタイム判定に
    必要な集計値をこの sync で常時最新化する。15 min cron で回す前提。
    過去 GA は ratified 後に集計値が変動しないため定期再取得しない。
    """
    from cardanoism.backend.koios import get_proposal_voting_summary
    from cardanoism.backend.voting_summary_db import upsert_voting_summary

    logger.info("投票集計同期 開始 (workers=%d, active GA のみ)", max_workers)

    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, proposal_type
            FROM governance_actions
            WHERE proposal_id IS NOT NULL AND proposal_id <> ''
              AND ratified_epoch IS NULL
              AND enacted_epoch  IS NULL
              AND dropped_epoch  IS NULL
              AND expired_epoch  IS NULL
            ORDER BY block_time DESC
            """
        )
        proposals = [dict(r) for r in cursor.fetchall() if r.get("proposal_id")]
    logger.info("集計対象: %d 件 (Active)", len(proposals))

    def _one(p: dict) -> int:
        pid = p["proposal_id"]
        ptype = p.get("proposal_type") or ""
        try:
            summary = get_proposal_voting_summary(pid)
            if summary:
                summary["proposal_type"] = ptype
                upsert_voting_summary(pid, summary)
                return 1
        except Exception as e:
            logger.exception("summary_sync %s: %s", pid, e)
        return 0

    total = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_one, p) for p in proposals]
        for i, fut in enumerate(as_completed(futures), 1):
            total += fut.result()
            if i % 10 == 0:
                logger.info("  進捗: %d / %d", i, len(proposals))
    logger.info("投票集計同期 完了: %d 件 upsert", total)


# ============================================================
# DRep 同期
# ============================================================

def _extract_drep_meta(meta_row: dict) -> dict:
    """drep_metadata のレスポンスから CIP-119 body を抽出する。"""
    if not meta_row:
        return {}
    body = ((meta_row.get("meta_json") or {}).get("body") or {}) if isinstance(meta_row.get("meta_json"), dict) else {}
    if not isinstance(body, dict):
        return {}

    import json as _json

    def _s(v):
        if isinstance(v, dict):
            return str(v.get("@value") or "").strip() or None
        if isinstance(v, str):
            return v.strip() or None
        return None

    image = body.get("image")
    image_url = None
    if isinstance(image, dict):
        image_url = image.get("contentUrl") or image.get("@id") or None
    elif isinstance(image, str):
        image_url = image
    # data URI (base64 画像) は巨大になりがちなので保存しない
    if isinstance(image_url, str) and image_url.startswith("data:"):
        image_url = None

    refs = body.get("references") or []
    return {
        "given_name":     _s(body.get("givenName")),
        "image_url":      image_url,
        "payment_address": _s(body.get("paymentAddress")),
        "motivations":    _s(body.get("motivations")),
        "objectives":     _s(body.get("objectives")),
        "qualifications": _s(body.get("qualifications")),
        "references_json": _json.dumps(refs, ensure_ascii=False) if refs else None,
        "meta_is_valid":  meta_row.get("is_valid"),
    }


def _extract_pool_meta(info: dict) -> dict:
    """Koios /pool_info の meta_json から ticker / 名称 / 説明 / homepage を取り出す。
    Koios の meta_json には extended フィールドが含まれないので extended は別途
    meta_url を直接フェッチして抽出する（_fetch_pool_extended_via_meta_url）。
    """
    meta = info.get("meta_json") or {}
    return {
        "ticker":      _extract_str(meta.get("ticker")),
        "pool_name":   _extract_str(meta.get("name")),
        "description": _extract_str(meta.get("description")) or None,
        "homepage":    _extract_str(meta.get("homepage")) or None,
    }


def _coerce_url(value) -> str | None:
    """文字列 / {"@value": "..."} のいずれにも対応して http(s) URL を返す。"""
    if isinstance(value, dict):
        value = value.get("@value")
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v.startswith(("http://", "https://")):
        return None
    return v[:1024]


def _coerce_handle(value, max_len: int = 128) -> str | None:
    """social handle を正規化（先頭の @ を除去、長さ上限）。"""
    if isinstance(value, dict):
        value = value.get("@value")
    if not isinstance(value, str):
        return None
    v = value.strip().lstrip("@").strip()
    if not v:
        return None
    return v[:max_len]


def _coerce_text(value, max_len: int = 4000) -> str | None:
    """テキストフィールドを正規化（空チェック + 長さ上限）。"""
    if isinstance(value, dict):
        value = value.get("@value")
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    return v[:max_len]


def _fetch_pool_extended(extended_url: str | None) -> dict | None:
    """CIP-6 / POM の extended metadata を取得し、UI で使う項目だけ抜き出して返す。

    抽出キー:
      icon_url        : info.url_png_icon_64x64 (なければ info.url_png_logo / body.url_png_icon_64x64)
      logo_url        : info.url_png_logo
      about           : info.about.me
      twitter_handle  : info.social.twitter_handle
      telegram_handle : info.social.telegram_handle
      youtube_handle  : info.social.youtube_handle
      github_handle   : info.social.github_handle
    取得失敗 / 1 つも値が無い場合は None。
    """
    if not extended_url or not isinstance(extended_url, str):
        return None
    if not extended_url.startswith(("http://", "https://")):
        return None
    try:
        resp = requests.get(extended_url, timeout=5)
        if resp.status_code != 200:
            return None
        body = resp.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    info = body.get("info") if isinstance(body.get("info"), dict) else {}
    social = info.get("social") if isinstance(info.get("social"), dict) else {}
    about = info.get("about") if isinstance(info.get("about"), dict) else {}

    icon = (
        _coerce_url(info.get("url_png_icon_64x64"))
        or _coerce_url(info.get("url_png_logo"))
        or _coerce_url(body.get("url_png_icon_64x64"))
    )
    logo = _coerce_url(info.get("url_png_logo"))
    out = {
        "icon_url":        icon,
        "logo_url":        logo,
        "about":           _coerce_text(about.get("me")),
        "twitter_handle":  _coerce_handle(social.get("twitter_handle")),
        "telegram_handle": _coerce_handle(social.get("telegram_handle")),
        "youtube_handle":  _coerce_handle(social.get("youtube_handle"), max_len=255),
        "github_handle":   _coerce_handle(social.get("github_handle")),
    }
    # すべて None なら呼び出し側で判定しやすいように None を返す
    if not any(v for v in out.values()):
        return None
    return out


def _fetch_pool_extended_via_meta_url(meta_url: str | None) -> dict | None:
    """meta_url を直接フェッチし、basic metadata に extended URL があればそれも辿って
    アイコン/ロゴ/about/social を抽出した dict を返す。
    extended が無い、もしくは取得失敗時は None。
    """
    if not meta_url or not isinstance(meta_url, str):
        return None
    if not meta_url.startswith(("http://", "https://")):
        return None
    try:
        resp = requests.get(meta_url, timeout=5)
        if resp.status_code != 200:
            return None
        body = resp.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    ext = body.get("extended")
    if isinstance(ext, dict):
        ext = ext.get("@value")
    if not isinstance(ext, str):
        return None
    ext = ext.strip()
    if not ext.startswith(("http://", "https://")):
        return None
    return _fetch_pool_extended(ext[:1024])


def _fetch_extended_data_parallel(meta_urls: dict[str, str], workers: int = 16) -> dict[str, dict]:
    """{pool_id: meta_url} を並列でフェッチ。各タスクは meta_url → extended URL → 抽出 を連続実行する。
    返り値: {pool_id: extracted_dict}（icon_url / logo_url / about / *_handle）。
    """
    if not meta_urls:
        return {}
    out: dict[str, dict] = {}
    logger.info("extended metadata フェッチ開始: %d 件 (workers=%d) — meta_url 直叩き", len(meta_urls), workers)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_pool_extended_via_meta_url, url): pid for pid, url in meta_urls.items()}
        done = 0
        for fut in as_completed(futs):
            pid = futs[fut]
            try:
                data = fut.result()
            except Exception:
                data = None
            if data:
                out[pid] = data
            done += 1
            if done % 500 == 0:
                logger.info("extended metadata: %d / %d 完了 (回収 %d)", done, len(meta_urls), len(out))
    icon_count = sum(1 for d in out.values() if d.get("icon_url"))
    social_count = sum(1 for d in out.values() if any(d.get(k) for k in ("twitter_handle", "telegram_handle", "youtube_handle", "github_handle")))
    logger.info("extended metadata フェッチ完了: %d 件 (icons=%d, social=%d)", len(out), icon_count, social_count)
    return out


def _extract_str(value) -> str:
    """{"@value": "..."} 形式と文字列の両方に対応して文字列を返す。"""
    if isinstance(value, dict):
        return str(value.get("@value") or "").strip()
    return str(value or "").strip()


# ============================================================
# リレー疎通確認 (TCP connect)
# ============================================================

def _tcp_check(host: str, port: int, timeout: float = 3.0) -> bool:
    """指定ホスト:ポートへ TCP コネクトを試みて成功すれば True。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _check_single_relay(relay: dict, timeout: float = 3.0) -> bool:
    """単一リレーへの疎通確認。ipv4 / ipv6 / dns に対応。SRV のみ等は False（確認不能=OFF）。"""
    if not isinstance(relay, dict):
        return False
    port = relay.get("port")
    try:
        port = int(port) if port is not None else None
    except (TypeError, ValueError):
        return False
    if not port or not (0 < port < 65536):
        return False
    raw_host = relay.get("ipv4") or relay.get("ipv6") or relay.get("dns")
    if not isinstance(raw_host, str):
        return False
    host = raw_host.strip()
    if not host:
        return False
    return _tcp_check(host, port, timeout=timeout)


def _check_pool_relays(relays_value, timeout: float = 3.0) -> bool:
    """プールのリレー疎通確認。1件でも疎通成功で True を返す（複数リレーは冗長構成のため）。
    relays が空 / 取得失敗 / 全リレー疎通NG は False。
    """
    if relays_value is None:
        return False
    if isinstance(relays_value, str):
        try:
            relays = json.loads(relays_value)
        except (TypeError, ValueError):
            return False
    else:
        relays = relays_value
    if not isinstance(relays, list) or not relays:
        return False
    for relay in relays:
        if _check_single_relay(relay, timeout=timeout):
            return True
    return False


def check_pool_relay_alive(workers: int = 32, timeout: float = 3.0):
    """全 active プールのリレーに TCP 疎通確認を行い、relay_alive を一括更新する。"""
    from cardanoism.backend.pool_db import get_pools_with_relays, bulk_update_relay_alive

    pools = get_pools_with_relays(only_active=True)
    if not pools:
        logger.warning("リレー疎通確認: 対象プールがありません")
        return
    logger.info("リレー疎通確認 開始: %d 件 (workers=%d, timeout=%.1fs)", len(pools), workers, timeout)

    results: list[tuple] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_check_pool_relays, p.get("relays"), timeout): p["pool_id_bech32"]
            for p in pools
        }
        done = 0
        for fut in as_completed(futs):
            pid = futs[fut]
            try:
                alive = fut.result()
            except Exception:
                alive = False
            results.append((pid, bool(alive)))
            done += 1
            if done % 500 == 0:
                alive_so_far = sum(1 for _, a in results if a)
                logger.info("リレー疎通確認: %d / %d 完了 (alive=%d)", done, len(pools), alive_so_far)

    bulk_update_relay_alive(results)
    alive_count = sum(1 for _, a in results if a)
    logger.info("リレー疎通確認 完了: %d / %d 件 ALIVE", alive_count, len(results))


# ============================================================
# プール ブロック履歴 同期 (直近 5 エポック)
# ============================================================

def check_pool_block_history(epochs: int = 5):
    """全 active プールの直近 N エポックのブロック生成数 + 直近 7 エポックの APY 平均を取得。
    /pool_history は 1 コールで block_cnt も epoch_ros も返すため、limit=7 で叩き、
    epoch_ros の値が入っている行の平均を pools.apy に保存する（API コール数ゼロ追加）。
    block_history_5ep には先頭 epochs 件（デフォルト 5）を従来通り保存。
    """
    from cardanoism.backend.koios import get_pool_history
    from cardanoism.backend.pool_db import get_pool_ids_for_block_history, bulk_update_block_history

    APY_WINDOW = 7
    fetch_limit = max(epochs, APY_WINDOW)

    pool_ids = get_pool_ids_for_block_history(only_active=True)
    if not pool_ids:
        logger.warning("プールブロック履歴: 対象プールがありません")
        return
    logger.info("プールブロック履歴 同期 開始: %d 件 (block_window=%d, apy_window=%d)",
                len(pool_ids), epochs, APY_WINDOW)

    updates: list[tuple] = []
    fetched = 0
    apy_captured = 0
    for pid in pool_ids:
        try:
            history = get_pool_history(pid, limit=fetch_limit)
        except Exception as e:
            logger.debug("get_pool_history 失敗 pool=%s: %s", pid, e)
            history = []
        # block_cnt を newest 順で抽出（足りない分は 0 でパディング）
        counts: list[int] = []
        for row in history[:epochs]:
            try:
                counts.append(int(row.get("block_cnt") or 0))
            except (TypeError, ValueError):
                counts.append(0)
        while len(counts) < epochs:
            counts.append(0)

        # 直近 APY_WINDOW エポック分のうち epoch_ros が確定している値だけを配列化。
        # 完了直後のエポックでは epoch_ros が NULL のことがあるので skip。
        # 平均は表示時に Python 側で算出する (block_history_5ep と同じ流儀)。
        ros_values: list[float] = []
        for row in history[:APY_WINDOW]:
            ros = row.get("epoch_ros")
            if ros is None:
                continue
            try:
                ros_values.append(round(float(ros), 4))
            except (TypeError, ValueError):
                continue

        apy_json = json.dumps(ros_values) if ros_values else None
        if ros_values:
            apy_captured += 1

        updates.append((pid, json.dumps(counts), apy_json))
        fetched += 1
        if fetched % 200 == 0:
            logger.info("プールブロック履歴: %d / %d フェッチ済み (APY 取得=%d)", fetched, len(pool_ids), apy_captured)

    inserted = bulk_update_block_history(updates)
    logger.info("プールブロック履歴 同期 完了: %d / %d 件 update (APY 取得=%d, window=%d)",
                inserted, len(pool_ids), apy_captured, APY_WINDOW)


# ============================================================
# DRep マッチング診断 (委任コンパス MVP)
# ============================================================
# 旧 5 軸派閥モデル (axis_*) と旧 9 トピックモデル (topic_*) は削除済み。
# 新しい 11 axis 価値観モデルは cardanoism.backend.drep_compass パッケージ
# に集約され、本ワーカーからは下記 2 つの CLI イベントで起動する:
#
#   --event compass_classify_all : 全 GA を rule-based 分類して
#                                  gov_action_tags に書き込む
#   --event compass_profile_all  : 全 registered DRep の axis profile を
#                                  計算して drep_profiles に書き込む

def check_drep_compass_classify_all() -> int:
    """全 governance_actions を rule-based 分類して gov_action_tags へ反映する。

    既存タグ (source='rule') は preserve しつつ INSERT IGNORE で新規分だけ追加。
    完全再生成したい場合は reclassify_governance_action() を 1 件ずつ呼ぶ。
    """
    from cardanoism.backend.drep_compass.api import classify_governance_action
    logger.info("=== Compass GA 分類: 全件 開始 ===")
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT proposal_id FROM governance_actions "
            "WHERE proposal_id IS NOT NULL AND proposal_id <> ''"
        )
        ids = [r["proposal_id"] for r in cursor.fetchall()]
    logger.info("対象 GA: %d 件", len(ids))
    total_inserted = 0
    for pid in ids:
        try:
            total_inserted += classify_governance_action(str(pid))
        except Exception as e:  # noqa: BLE001
            logger.warning("classify failed for %s: %s", pid, e)
    logger.info("=== Compass GA 分類: 完了 (%d tags inserted) ===", total_inserted)
    return total_inserted


def check_drep_compass_profile_all() -> int:
    """全 registered DRep の compass プロファイルを再計算する。"""
    from cardanoism.backend.drep_compass.api import recalculate_all_drep_profiles
    logger.info("=== Compass DRep プロファイル: 全件 開始 ===")
    n = recalculate_all_drep_profiles()
    logger.info("=== Compass DRep プロファイル: 完了 (%d DReps) ===", n)
    return n


def check_drep_compass_status() -> None:
    """委任コンパスのデータ状況を診断 (件数 + 分布)。

    マッチング候補が出ないときの切り分け用。
      - governance_actions / gov_action_tags / drep_profiles の件数
      - source 別 tag 件数 (rule / ai / manual)
      - tag_type 別 tag 件数
      - analyzed_vote_count 分布 (>=3, >=5, >=10)
      - 上位 5 DRep の analyzed_vote_count
    """
    logger.info("=== Compass Status 診断 開始 ===")
    with get_db() as (cursor, _):
        cursor.execute("SELECT COUNT(*) AS n FROM governance_actions")
        ga_count = int(cursor.fetchone()["n"])
        cursor.execute("SELECT COUNT(*) AS n FROM gov_action_tags")
        tag_count = int(cursor.fetchone()["n"])
        cursor.execute("SELECT COUNT(*) AS n FROM drep_profiles")
        profile_count = int(cursor.fetchone()["n"])

        cursor.execute(
            "SELECT source, COUNT(*) AS n FROM gov_action_tags GROUP BY source"
        )
        by_source = {r["source"]: int(r["n"]) for r in cursor.fetchall()}

        cursor.execute(
            "SELECT tag_type, COUNT(*) AS n FROM gov_action_tags GROUP BY tag_type"
        )
        by_type = {r["tag_type"]: int(r["n"]) for r in cursor.fetchall()}

        cursor.execute(
            "SELECT tag, COUNT(*) AS n FROM gov_action_tags "
            "GROUP BY tag ORDER BY n DESC LIMIT 20"
        )
        top_tags = [(r["tag"], int(r["n"])) for r in cursor.fetchall()]

        # analyzed_vote_count 分布
        cursor.execute(
            "SELECT COUNT(*) AS n FROM drep_profiles WHERE analyzed_vote_count >= 1"
        )
        gte_1 = int(cursor.fetchone()["n"])
        cursor.execute(
            "SELECT COUNT(*) AS n FROM drep_profiles WHERE analyzed_vote_count >= 3"
        )
        gte_3 = int(cursor.fetchone()["n"])
        cursor.execute(
            "SELECT COUNT(*) AS n FROM drep_profiles WHERE analyzed_vote_count >= 5"
        )
        gte_5 = int(cursor.fetchone()["n"])
        cursor.execute(
            "SELECT COUNT(*) AS n FROM drep_profiles WHERE analyzed_vote_count >= 10"
        )
        gte_10 = int(cursor.fetchone()["n"])

        # マッチング候補に残る DRep 数 (registered=1 と JOIN)
        cursor.execute(
            "SELECT COUNT(*) AS n FROM drep_profiles dp "
            "JOIN dreps d ON d.drep_id = dp.drep_id "
            "WHERE d.registered = 1 AND dp.analyzed_vote_count >= 3"
        )
        candidates = int(cursor.fetchone()["n"])

        # 上位 5 DRep
        cursor.execute(
            "SELECT drep_id, analyzed_vote_count, eligible_action_count, "
            "       participation_rate, reasoning_disclosure_rate "
            "FROM drep_profiles "
            "ORDER BY analyzed_vote_count DESC LIMIT 5"
        )
        top_dreps = [dict(r) for r in cursor.fetchall()]

    logger.info("─── テーブル件数 ───")
    logger.info("  governance_actions: %d 件", ga_count)
    logger.info("  gov_action_tags:    %d 件", tag_count)
    logger.info("  drep_profiles:      %d 件", profile_count)
    logger.info("─── gov_action_tags source 別 ───")
    for s in ("rule", "ai", "manual"):
        logger.info("  %-7s: %d 件", s, by_source.get(s, 0))
    logger.info("─── gov_action_tags tag_type 別 ───")
    for t in ("category", "attribute", "quality"):
        logger.info("  %-10s: %d 件", t, by_type.get(t, 0))
    logger.info("─── 上位 20 タグ ───")
    for tag, n in top_tags:
        logger.info("  %-25s: %d 件", tag, n)
    logger.info("─── drep_profiles 分布 ───")
    logger.info("  analyzed_vote_count >= 1 : %d 件", gte_1)
    logger.info("  analyzed_vote_count >= 3 : %d 件", gte_3)
    logger.info("  analyzed_vote_count >= 5 : %d 件", gte_5)
    logger.info("  analyzed_vote_count >= 10: %d 件", gte_10)
    logger.info("─── マッチング候補数 (registered=1 AND analyzed>=3) ───")
    logger.info("  %d 件", candidates)
    if candidates == 0:
        logger.warning("⚠ マッチング候補が 0 件です。以下を確認してください:")
        if tag_count == 0:
            logger.warning("  - gov_action_tags が空: compass_classify_all を実行")
        elif profile_count == 0:
            logger.warning("  - drep_profiles が空: compass_profile_all を実行")
        elif gte_3 == 0:
            logger.warning("  - analyzed_vote_count >= 3 が 0: "
                           "DRep の Yes/No 投票が gov_action_tags 付き GA に "
                           "まだ届いていない可能性。タグ分布を確認")
        else:
            logger.warning("  - registered=1 と JOIN すると 0: dreps テーブルの "
                           "registered フラグを確認")
    logger.info("─── 上位 5 DRep ───")
    for d in top_dreps:
        logger.info(
            "  %s : analyzed=%d eligible=%d participation=%.2f rationale=%.2f",
            d["drep_id"][:32] + "..." if len(d["drep_id"]) > 32 else d["drep_id"],
            int(d["analyzed_vote_count"] or 0),
            int(d["eligible_action_count"] or 0),
            float(d["participation_rate"] or 0),
            float(d["reasoning_disclosure_rate"] or 0),
        )
    logger.info("=== Compass Status 診断 完了 ===")


def _split_pool_updates(updates: list[dict], current_epoch: int) -> tuple[dict | None, dict | None]:
    """/pool_updates の一覧から (active 更新, pending 更新) を抽出する。

    Koios `/pool_updates` は提出された cert ごとの履歴を返す。フィールド:
      active_epoch_no : この cert の値が active になる epoch
      pledge / margin / fixed_cost : cert の値 (deregistration では NULL)

    判定:
      active  : active_epoch_no <= current_epoch のうち active_epoch_no 最大
      pending : active_epoch_no >  current_epoch のうち active_epoch_no 最大 (= 最新の予告)
                ※ 更に未来の予告がある場合も「直近の反映予告」を表示したいので最大を採る

    deregistration entry (= update_type == "deregistration") は pledge/margin が
    NULL のため除外して扱う。
    """
    if not updates:
        return None, None
    # registration / re-registration のみ (deregistration は除外)
    regs = [
        u for u in updates
        if u.get("update_type") != "deregistration"
        and u.get("pledge") is not None
        and u.get("margin") is not None
    ]
    if not regs:
        return None, None

    active_candidates = [
        u for u in regs
        if u.get("active_epoch_no") is not None and int(u["active_epoch_no"]) <= int(current_epoch)
    ]
    pending_candidates = [
        u for u in regs
        if u.get("active_epoch_no") is not None and int(u["active_epoch_no"]) > int(current_epoch)
    ]

    active = max(active_candidates, key=lambda u: int(u["active_epoch_no"])) if active_candidates else None
    pending = max(pending_candidates, key=lambda u: int(u["active_epoch_no"])) if pending_candidates else None

    # pending が active と完全一致する場合 (= 同じ値で再登録された予告) は表示不要
    if active and pending:
        same = (
            int(active.get("pledge") or 0) == int(pending.get("pledge") or 0)
            and float(active.get("margin") or 0) == float(pending.get("margin") or 0)
            and int(active.get("fixed_cost") or 0) == int(pending.get("fixed_cost") or 0)
        )
        if same:
            pending = None
    return active, pending


def check_pool_sync():
    """
    Koios から全プールの情報を取得して DB にキャッシュする。
    - /pool_list   : 全プールの最小情報（status / ticker / retiring_epoch 等）
    - /pool_info   : ライブ系 (active_stake / live_stake / saturation / blocks / メタデータ)
    - /pool_updates: cert 履歴 (pledge / margin / fixed_cost を active / pending に分離)

    /pool_info は最新 cert の pledge/margin/fixed_cost をそのまま返してしまうので、
    「未来エポックで反映予定の値」と「現在 active な値」が区別できない。
    /pool_updates の active_epoch_no を使って正しく振り分ける。
    """
    from cardanoism.backend.koios import (
        KOIOS_BASE_URL, get_pool_list, get_pool_info_batch,
        get_recent_pool_updates, get_current_epoch,
    )
    from cardanoism.backend.pool_db import bulk_upsert_pools

    logger.info("プール同期 開始 (network=%s, url=%s)", _koios_network(), KOIOS_BASE_URL)

    pools = get_pool_list()
    if not pools:
        logger.warning("プール一覧が取得できませんでした")
        return
    logger.info("プール一覧: %d 件", len(pools))

    # retired はメタデータが薄い & 同期コスト高なので /pool_info の対象から外す。
    # ただし pool_list 由来の最小情報（status / retiring_epoch）は upsert しておく。
    target_ids = [
        p["pool_id_bech32"]
        for p in pools
        if p.get("pool_id_bech32") and p.get("pool_status") != "retired"
    ]
    logger.info("/pool_info 対象: %d 件", len(target_ids))

    info_map = {i["pool_id_bech32"]: i for i in get_pool_info_batch(target_ids)}

    # /pool_updates を直近 2 エポック分だけ全プール横断で 1 リクエスト取得。
    # それより古い変更しかないプール ("ここ最近静か") は /pool_info の値を
    # そのまま active として採用すれば足りる。
    current_epoch = get_current_epoch() or 0
    updates_map = get_recent_pool_updates(max(0, current_epoch - 1))
    logger.info("/pool_updates 直近変更: %d プール", len(updates_map))

    # 各プールの基本フィールド (ticker / name / homepage 等) を抽出。
    # extended は Koios meta_json には乗らないので、meta_url を直叩きするための URL も集める。
    pool_meta_cache: dict[str, dict] = {}
    meta_url_targets: dict[str, str] = {}
    for p in pools:
        pid = p.get("pool_id_bech32")
        if not pid:
            continue
        info = info_map.get(pid, {})
        pool_meta_cache[pid] = _extract_pool_meta(info)
        url = info.get("meta_url") or p.get("meta_url")
        if url:
            meta_url_targets[pid] = url
    logger.info("meta_url 対象: %d 件 (extended は meta_url を直接フェッチして抽出)", len(meta_url_targets))

    # meta_url → (extended があれば) extended URL → icon/logo/about/social を1タスクで連続取得
    extended_map = _fetch_extended_data_parallel(meta_url_targets)

    records: list[dict] = []
    for p in pools:
        pid = p.get("pool_id_bech32")
        if not pid:
            continue
        info = info_map.get(pid, {})
        meta = pool_meta_cache.get(pid) or _extract_pool_meta(info)
        ext = extended_map.get(pid) or {}
        # /pool_updates から active / pending を判定。fallback として /pool_info の値を使う。
        active_upd, pending_upd = _split_pool_updates(updates_map.get(pid, []), current_epoch)
        active_pledge = active_upd.get("pledge") if active_upd else info.get("pledge")
        active_margin = active_upd.get("margin") if active_upd else info.get("margin")
        active_fixed_cost = active_upd.get("fixed_cost") if active_upd else info.get("fixed_cost")
        pending_pledge = pending_upd.get("pledge") if pending_upd else None
        pending_margin = pending_upd.get("margin") if pending_upd else None
        pending_fixed_cost = pending_upd.get("fixed_cost") if pending_upd else None
        pending_effective_epoch = pending_upd.get("active_epoch_no") if pending_upd else None

        records.append({
            "pool_id_bech32":   pid,
            "pool_id_hex":      info.get("pool_id_hex") or p.get("pool_id_hex"),
            "pool_status":      p.get("pool_status") or info.get("pool_status"),
            "active_epoch_no":  info.get("active_epoch_no"),
            "retiring_epoch":   p.get("retiring_epoch") or info.get("retiring_epoch"),
            "op_cert":          info.get("op_cert"),
            "op_cert_counter": info.get("op_cert_counter"),
            "vrf_key_hash":     info.get("vrf_key_hash"),
            "pledge":           active_pledge,
            "margin":           active_margin,
            "fixed_cost":       active_fixed_cost,
            "pending_pledge":          pending_pledge,
            "pending_margin":          pending_margin,
            "pending_fixed_cost":      pending_fixed_cost,
            "pending_effective_epoch": pending_effective_epoch,
            "active_stake":     info.get("active_stake"),
            "live_stake":       info.get("live_stake"),
            "live_pledge":      info.get("live_pledge"),
            "live_delegators":  info.get("live_delegators"),
            "live_saturation":  info.get("live_saturation"),
            "sigma":            info.get("sigma"),
            "block_count":      info.get("block_count"),
            "reward_addr":      info.get("reward_addr"),
            "owners":           info.get("owners"),
            "relays":           info.get("relays"),
            "meta_url":         info.get("meta_url") or p.get("meta_url"),
            "meta_hash":        info.get("meta_hash") or p.get("meta_hash"),
            "pool_icon_url":    ext.get("icon_url"),
            "pool_logo_url":    ext.get("logo_url"),
            "extended_about":   ext.get("about"),
            "twitter_handle":   ext.get("twitter_handle"),
            "telegram_handle":  ext.get("telegram_handle"),
            "youtube_handle":   ext.get("youtube_handle"),
            "github_handle":    ext.get("github_handle"),
            **meta,
        })

    inserted = bulk_upsert_pools(records)
    logger.info("プール同期 完了: %d / %d 件 upsert (extended=%d)", inserted, len(records), len(extended_map))

    # SPO 判定の再 sync (24h fallback)。pools.reward_addr / owners が更新された後に走る。
    try:
        from cardanoism.backend.auth_db import refresh_all_spo_roles
        checked, updated = refresh_all_spo_roles()
        logger.info("SPO 判定 再 sync 完了: %d 件チェック / %d 件更新", checked, updated)
    except Exception as e:  # noqa: BLE001
        logger.warning("SPO 判定 再 sync 失敗 (継続): %s", e)


def check_spo_role_initial_sync():
    """初期セットアップ用: 全 stake_addresses の spo_pool_id を一括で再判定する。

    pool_sync が完了している前提。新規 VPS デプロイ時の手順に組み込む。
    """
    logger.info("SPO 判定 初期投入 開始")
    try:
        from cardanoism.backend.auth_db import refresh_all_spo_roles
        checked, updated = refresh_all_spo_roles()
        logger.info("SPO 判定 初期投入 完了: %d 件チェック / %d 件更新", checked, updated)
    except Exception as e:  # noqa: BLE001
        logger.exception("SPO 判定 初期投入 失敗: %s", e)


def check_drep_sync():
    """
    Koios から全 DRep の情報を取得して DB にキャッシュする。
    - /drep_list: 全 DRep の最小情報
    - /drep_info: 登録状態 + 委任量
    - /drep_metadata: CIP-119 メタデータ（画像・表示名等）
    """
    from cardanoism.backend.koios import (
        KOIOS_BASE_URL, get_drep_list, get_drep_info_batch, get_drep_metadata_batch,
    )
    from cardanoism.backend.drep_db import bulk_upsert_dreps

    logger.info("DRep 同期 開始 (network=%s, url=%s)", _koios_network(), KOIOS_BASE_URL)

    dreps = get_drep_list()
    if not dreps:
        logger.warning("DRep 一覧が取得できませんでした")
        return
    logger.info("DRep 一覧: %d 件", len(dreps))

    # 登録済みのみ詳細フェッチ対象にする（リソース節約）
    registered_ids = [d["drep_id"] for d in dreps if d.get("registered") and d.get("drep_id")]
    logger.info("registered DRep: %d 件", len(registered_ids))

    info_map = {i["drep_id"]: i for i in get_drep_info_batch(registered_ids)}
    meta_map = {m["drep_id"]: m for m in get_drep_metadata_batch(registered_ids)}

    records: list[dict] = []
    for d in dreps:
        did = d.get("drep_id")
        if not did:
            continue
        info = info_map.get(did, {})
        meta_row = meta_map.get(did, {})
        meta = _extract_drep_meta(meta_row)

        records.append({
            "drep_id":          did,
            "hex":              d.get("hex"),
            "has_script":       d.get("has_script"),
            "registered":       d.get("registered"),
            "drep_status":      info.get("drep_status"),
            "active":           info.get("active"),
            "deposit":          info.get("deposit"),
            "expires_epoch_no": info.get("expires_epoch_no"),
            "amount":           info.get("amount") or 0,
            "meta_url":         info.get("meta_url"),
            "meta_hash":        info.get("meta_hash"),
            **meta,
        })

    inserted = bulk_upsert_dreps(records)
    logger.info("DRep 同期 完了: %d / %d 件 upsert", inserted, len(records))


# ============================================================
# 法定通貨レート同期
# ============================================================

def check_fiat_sync():
    """
    CoinGecko から ADA/JPY・ADA/USD を取得して fiat_rate テーブルに保存。
    cron 推奨: */15 * * * *
    """
    from cardanoism.backend.price import fetch_ada_rates
    from cardanoism.backend.fiat_db import upsert_fiat_rate

    logger.info("法定通貨レート同期 開始")
    rates = fetch_ada_rates()
    if not rates:
        logger.warning("レート取得失敗")
        return
    upsert_fiat_rate(rates["ada_jpy"], rates["ada_usd"], source="coingecko")
    logger.info("fiat_rate 更新: ADA/JPY=%.4f ADA/USD=%.6f",
                rates["ada_jpy"], rates["ada_usd"])


# ============================================================
# トレジャリー同期（DBキャッシュ更新）
# ============================================================

def check_treasury_sync():
    """
    Koios から DB にトレジャリー関連データを同期する。
      - treasury_snapshot: 最新エポックの /totals を UPSERT
      - treasury_withdrawal: /treasury_withdrawals を INSERT IGNORE
      - ncl_active: DRep過半数賛成の最新 NCL 提案を UPSERT

    cron 推奨: エポック境界後1回（5日に1回）。日次でも問題ない。
    """
    from cardanoism.backend.koios import (
        get_totals, get_treasury_withdrawals, fetch_active_ncl,
        get_current_epoch, KOIOS_BASE_URL,
    )
    from cardanoism.backend.treasury_db import (
        upsert_treasury_snapshot,
        upsert_treasury_history,
        get_existing_history_epochs,
        insert_treasury_withdrawals,
        upsert_active_ncl,
    )
    logger.info("トレジャリー同期 開始 (network=%s, url=%s)", _koios_network(), KOIOS_BASE_URL)

    # 1) トレジャリー残高（最新スナップショット + 履歴）
    epoch = None
    try:
        epoch = get_current_epoch()
        totals = get_totals(epoch_no=epoch) if epoch else get_totals()
        if totals and totals.get("treasury") is not None:
            epoch_no = int(totals.get("epoch_no") or epoch or 0)
            upsert_treasury_snapshot(
                epoch_no=epoch_no,
                treasury=int(totals["treasury"]),
                reserves=int(totals["reserves"]) if totals.get("reserves") is not None else None,
                supply=int(totals["supply"]) if totals.get("supply") is not None else None,
            )
            logger.info("treasury_snapshot 更新: Ep.%d treasury=%s", epoch_no, totals["treasury"])
        else:
            logger.warning("totals 取得失敗")
    except Exception as e:
        logger.exception("treasury_snapshot 同期失敗: %s", e)

    # 1.5) treasury_history は NCL 期間に基づき同期（後段の NCL fetch 後に実行）。
    # ここでは仮に直近 12 エポックを最低限同期してフォールバック用データを確保する。
    try:
        if epoch:
            fallback_start = max(0, int(epoch) - 11)
            fallback_end = int(epoch)
            existing = get_existing_history_epochs(fallback_start, fallback_end)
            synced = 0
            for ep in range(fallback_start, fallback_end + 1):
                if ep in existing:
                    continue
                t = get_totals(epoch_no=ep)
                if t and t.get("treasury") is not None:
                    upsert_treasury_history(
                        epoch_no=int(t.get("epoch_no") or ep),
                        treasury=int(t["treasury"]),
                        reserves=int(t["reserves"]) if t.get("reserves") is not None else None,
                        supply=int(t["supply"]) if t.get("supply") is not None else None,
                    )
                    synced += 1
            logger.info("treasury_history (fallback): 直近 12 エポックのうち %d 件を新規取得", synced)
    except Exception as e:
        logger.exception("treasury_history fallback 同期失敗: %s", e)

    # 2) 引き出し履歴
    try:
        withdrawals = get_treasury_withdrawals(limit=1000)
        records = []
        for w in withdrawals:
            if not w.get("stake_address"):
                continue
            try:
                records.append({
                    "stake_address": w["stake_address"],
                    "amount_lovelace": int(w.get("amount") or 0),
                    "earned_epoch": int(w.get("earned_epoch") or 0),
                    "spendable_epoch": int(w.get("spendable_epoch") or 0),
                })
            except (TypeError, ValueError):
                continue
        inserted = insert_treasury_withdrawals(records)
        logger.info("treasury_withdrawal: 新規 %d 件追加（全 %d 件チェック）", inserted, len(records))
    except Exception as e:
        logger.exception("treasury_withdrawal 同期失敗: %s", e)

    # 3) NCL
    ncl_start = None
    ncl_end = None
    try:
        ncl = fetch_active_ncl(use_cache=False)
        if ncl:
            upsert_active_ncl(ncl)
            ncl_start = int(ncl["start_epoch"])
            ncl_end = int(ncl["end_epoch"])
            logger.info(
                "ncl_active 更新: %s (%d ADA, Ep.%d-%d, DRep %.2f%%)",
                ncl["title"], ncl["limit_ada"], ncl_start, ncl_end, ncl["drep_yes_pct"],
            )
        else:
            logger.warning("DRep過半数賛成のNCL提案が見つかりません（既存の ncl_active はそのまま）")
    except Exception as e:
        logger.exception("ncl_active 同期失敗: %s", e)

    # 4) NCL 期間の履歴（折れ線グラフ用）。NCL start から現在エポックまでを埋める。
    # ON DUPLICATE KEY UPDATE で全件更新せず、未取得分だけ Koios call する設計。
    try:
        if ncl_start is not None and epoch:
            range_start = max(0, ncl_start)
            # 現在エポックを上限。NCL end が未来でも現在以降の履歴は取れない
            range_end = min(int(epoch), ncl_end if ncl_end is not None else int(epoch))
            existing = get_existing_history_epochs(range_start, range_end)
            missing = [ep for ep in range(range_start, range_end + 1) if ep not in existing]
            # 暴走防止: 1 サイクルで最大 80 件まで
            CAP = 80
            if len(missing) > CAP:
                logger.info(
                    "treasury_history (NCL範囲): 未取得 %d 件のうち最新 %d 件のみ今回同期",
                    len(missing), CAP,
                )
                missing = missing[-CAP:]
            synced = 0
            for ep in missing:
                t = get_totals(epoch_no=ep)
                if t and t.get("treasury") is not None:
                    upsert_treasury_history(
                        epoch_no=int(t.get("epoch_no") or ep),
                        treasury=int(t["treasury"]),
                        reserves=int(t["reserves"]) if t.get("reserves") is not None else None,
                        supply=int(t["supply"]) if t.get("supply") is not None else None,
                    )
                    synced += 1
            logger.info(
                "treasury_history (NCL Ep.%d-%d): 新規 %d 件取得（既存 %d 件はスキップ）",
                range_start, range_end, synced, len(existing),
            )
    except Exception as e:
        logger.exception("treasury_history (NCL範囲) 同期失敗: %s", e)

    # 5) TreasuryWithdrawals GA の受取先ごとの出金状況を /account_reward_history で照合
    try:
        _sync_ga_withdrawal_payouts()
    except Exception as e:
        logger.exception("ga_withdrawal_payout 同期失敗: %s", e)

    logger.info("トレジャリー同期 完了")


def _sync_ga_withdrawal_payouts():
    """ratified 済み TreasuryWithdrawals GA の受取先ごとの出金を照合する。

    1. ratified 済み GA の withdrawal_json を受取先単位に展開して
       ga_withdrawal_payout に登録 (既存エントリの paid 状態は保護)
    2. 未確認 (paid=0) エントリを GA の ratified_epoch ごとにまとめて
       /account_reward_history を叩く (paid=1 は再チェックしない = Koios コール最小化)
    3. type=treasury / earned_epoch=ratified_epoch / amount 一致のエントリを paid=1 に
    """
    from cardanoism.backend.koios import fetch_treasury_rewards_by_epoch
    from cardanoism.backend.treasury_db import (
        get_ratified_treasury_withdrawal_gas,
        upsert_payout_entries,
        get_unpaid_payout_entries,
        mark_payouts_paid,
    )

    # (1) ratified GA の withdrawal_json を受取先単位に展開して登録
    entries = []
    for ga in get_ratified_treasury_withdrawal_gas():
        try:
            items = json.loads(ga["withdrawal_json"]) or []
        except (TypeError, ValueError):
            continue
        for w in items if isinstance(items, list) else []:
            sa = w.get("stake_address")
            amt = w.get("amount")
            if not sa or amt is None:
                continue
            try:
                entries.append({
                    "proposal_id": ga["proposal_id"],
                    "stake_address": sa,
                    "amount_lovelace": int(amt),
                })
            except (TypeError, ValueError):
                continue
    registered = upsert_payout_entries(entries)
    logger.info("ga_withdrawal_payout: 新規エントリ %d 件登録", registered)

    # (2) 未確認エントリを ratified_epoch ごとにグルーピング
    unpaid = get_unpaid_payout_entries()
    if not unpaid:
        logger.info("ga_withdrawal_payout: 未確認エントリなし")
        return
    by_epoch: dict[int, list[dict]] = {}
    for e in unpaid:
        try:
            ep = int(e["ratified_epoch"])
        except (TypeError, ValueError):
            continue
        by_epoch.setdefault(ep, []).append(e)

    # (3) epoch ごとに /account_reward_history を叩いて照合
    paid_updates = []
    for epoch, ents in by_epoch.items():
        stake_addrs = list({e["stake_address"] for e in ents})
        rewards = fetch_treasury_rewards_by_epoch(stake_addrs, epoch)
        # (stake_address, earned_epoch, amount) の集合に正規化して O(1) 照合
        reward_set = set()
        for r in rewards:
            try:
                reward_set.add((
                    r.get("stake_address"),
                    int(r.get("earned_epoch")),
                    int(r.get("amount") or 0),
                ))
            except (TypeError, ValueError):
                continue
        for e in ents:
            key = (e["stake_address"], epoch, int(e["amount_lovelace"]))
            if key in reward_set:
                paid_updates.append({"id": e["id"], "paid_epoch": epoch})

    updated = mark_payouts_paid(paid_updates)
    logger.info("ga_withdrawal_payout: 出金確認 %d 件 (未確認 %d 件中)", updated, len(unpaid))


# ============================================================
# トレジャリーイベント
# ============================================================

def _datetime_to_mainnet_epoch(dt: datetime) -> int | None:
    """datetime を Cardano mainnet のエポック番号に変換する。Shelley 以前 (epoch < 208)
    は 0 を返す。preprod / preview ではずれるが、treasury withdrawals は mainnet 主体。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    SHELLEY_UNIX = 1596059091   # 2020-07-29 21:44:51Z = epoch 208 start
    SHELLEY_EPOCH = 208
    EPOCH_SECONDS = 432000
    t = dt.timestamp()
    if t < SHELLEY_UNIX:
        return 0
    return SHELLEY_EPOCH + int((t - SHELLEY_UNIX) // EPOCH_SECONDS)


def check_treasury_events():
    """TreasuryWithdrawals ガバナンスアクションが enacted（施行）されたのを検知して全ユーザーへ通知。"""
    logger.info("トレジャリーイベント チェック開始")
    from cardanoism.backend.koios import get_treasury_proposals

    proposals = get_treasury_proposals()
    enacted = [p for p in proposals if p.get("enacted_epoch") is not None]
    if not enacted:
        logger.info("施行済みのトレジャリー引き出しはありません")
        return

    from cardanoism.backend.notify_templates import deliver, merge_user_channels
    from cardanoism.backend.notify_templates.treasury_withdrawal_enacted import (
        context as build_ctx, EVENT_TYPE,
    )

    line_users = get_users_with_event("treasury_withdrawal_enacted")
    email_users = get_users_with_email_event("treasury_withdrawal_enacted")
    tg_users = get_users_with_telegram_event("treasury_withdrawal_enacted")
    addrs = merge_user_channels(line_users, email_users, tg_users)
    if not addrs:
        logger.info("通知対象ユーザーがいません")
        return

    # 新規ユーザー保護: ユーザー登録より前に施行された GA はスキップする。
    # ユーザーの users.created_at を mainnet エポック番号に換算してキャッシュ。
    user_signup_epoch: dict[int, int | None] = {}
    for a in addrs:
        uid = a.get("user_id")
        if uid is None:
            continue
        created = a.get("user_created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except ValueError:
                created = None
        user_signup_epoch[uid] = _datetime_to_mainnet_epoch(created) if created else None

    # 同一エポックで施行された複数の GA は 1 通の集約通知にまとめる。
    # 単発時は従来通り提案タイトルと個別 URL を表示。
    def _extract_title(p: dict) -> str:
        meta_body = ((p.get("meta_json") or {}).get("body") or {}) if isinstance(p.get("meta_json"), dict) else {}
        title = ""
        if isinstance(meta_body, dict):
            raw_title = meta_body.get("title")
            if isinstance(raw_title, dict):
                title = str(raw_title.get("@value") or "").strip()
            elif isinstance(raw_title, str):
                title = raw_title.strip()
        return title or (p.get("proposal_id") or "")[:24] + "..."

    # enacted_epoch でグルーピング
    by_epoch: dict[int, list[dict]] = {}
    for p in enacted:
        ep = p.get("enacted_epoch")
        if ep is None:
            continue
        try:
            ep_int = int(ep)
        except (TypeError, ValueError):
            continue
        by_epoch.setdefault(ep_int, []).append(p)

    governance_url = f"{CARDANOISM_URL}/governance"

    for enacted_epoch, props in by_epoch.items():
        count = len(props)
        if count >= 2:
            # 集約通知: タイトルは使わず件数と epoch だけ。URL は一覧ページ。
            dedup_base = f"treasury_enacted_epoch:{enacted_epoch}"
            ctx = build_ctx(
                enacted_epoch=enacted_epoch,
                proposal_url=governance_url,
                proposal_count=count,
            )
        else:
            # 単発: 従来通り提案個別の URL とタイトル
            p = props[0]
            proposal_id = p.get("proposal_id") or ""
            dedup_base = f"treasury_enacted:{proposal_id}"
            ctx = build_ctx(
                proposal_title=_extract_title(p),
                enacted_epoch=enacted_epoch,
                proposal_url=f"{CARDANOISM_URL}/governance/{proposal_id}",
            )

        for addr in addrs:
            # 登録より前のエポックはスキップ
            signup_epoch = user_signup_epoch.get(addr.get("user_id"))
            if signup_epoch is not None and enacted_epoch < signup_epoch:
                continue
            deliver(addr, EVENT_TYPE, ctx, dedup_base=dedup_base)



# ============================================================
# GA AI 分析: 初回同期バッチ
# ============================================================

def check_ga_ai_initial_sync(include_all: bool = False) -> None:
    """既存 GA に対して AI 分析キューを初期化するバッチ。

    通常対象（OR 条件で union）:
      - Active（ratified/enacted/dropped/expired すべて NULL）
      - Ratified（ratified_epoch IS NOT NULL）
      - Enacted（enacted_epoch IS NOT NULL）
      - expiration >= 現在エポック - 6（最近 Expired / Dropped した GA も含める）

    include_all=True の場合:
      - proposal_id がある GA 全件を対象（過去の Dropped / Expired も含む）
      - DRep マッチング診断のサンプルサイズを拡大したいときに使う

    INSERT IGNORE で投入するため、既に行があれば何もしない（再実行安全）。
    実際の分析は ga_ai_worker.py が pending を拾って進める。
    """
    logger.info("=== GA AI 分析 初回同期バッチ 開始 (include_all=%s) ===", include_all)

    params: list = []
    if include_all:
        sql = (
            "SELECT proposal_id FROM governance_actions "
            "WHERE proposal_id IS NOT NULL AND proposal_id <> ''"
        )
        current_epoch = None
        epoch_threshold = None
    else:
        try:
            current_epoch = get_current_epoch()
        except Exception as e:
            logger.warning("現在エポック取得失敗 (continue with None): %s", e)
            current_epoch = None

        epoch_threshold = None
        if current_epoch is not None:
            epoch_threshold = max(0, int(current_epoch) - 6)

        sql = (
            "SELECT proposal_id FROM governance_actions "
            "WHERE proposal_id IS NOT NULL AND proposal_id <> '' AND ("
            "  (ratified_epoch IS NULL AND enacted_epoch IS NULL "
            "   AND dropped_epoch IS NULL AND expired_epoch IS NULL)"
            "  OR ratified_epoch IS NOT NULL"
            "  OR enacted_epoch IS NOT NULL"
        )
        if epoch_threshold is not None:
            sql += "  OR expiration >= ?"
            params.append(epoch_threshold)
        sql += ")"

    with get_db() as (cursor, _):
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    proposal_ids = [str(r["proposal_id"]) for r in rows]
    logger.info("対象 GA: %d 件 (include_all=%s, current_epoch=%s, threshold=%s)",
                len(proposal_ids), include_all, current_epoch, epoch_threshold)

    if not proposal_ids:
        logger.info("対象 GA なし。終了。")
        return

    try:
        from cardanoism.backend.governance_ai_db import bulk_enqueue
        queued = bulk_enqueue(proposal_ids)
    except Exception as e:
        logger.exception("bulk_enqueue 失敗: %s", e)
        return

    logger.info("AI 分析キューに新規 enqueue: %d 件 (既存をスキップ: %d 件)",
                queued, len(proposal_ids) - queued)
    logger.info("=== GA AI 分析 初回同期バッチ 完了 ===")


def check_constitution_sync() -> None:
    """最新 enacted NewConstitution の本文を IPFS から取得し、Catalyst でも使われる
    Translator で日本語訳して constitution_cache に保存する。

    既に同じ proposal_id で翻訳済みなら skip（強制再翻訳したい場合は constitution_cache
    の id=1 行を削除してから再実行）。
    """
    logger.info("=== Constitution sync 開始 ===")

    from cardanoism.backend.constitution_fetcher import fetch_constitution_text
    from cardanoism.backend.constitution_db import get_constitution, upsert_constitution
    from cardanoism.backend.governance import build_translator

    # 最新 enacted を引く
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, enacted_epoch
            FROM governance_actions
            WHERE proposal_type = 'NewConstitution'
              AND enacted_epoch IS NOT NULL
            ORDER BY enacted_epoch DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    if not row:
        logger.warning("enacted NewConstitution が DB に見つかりません")
        return

    proposal_id = str(row.get("proposal_id") or "")
    enacted_epoch = row.get("enacted_epoch")

    cached = get_constitution()
    if (
        cached
        and cached.get("proposal_id") == proposal_id
        and cached.get("translated_text")
    ):
        logger.info(
            "constitution_cache に同じ proposal_id (%s) が既に翻訳済みのためスキップ",
            proposal_id,
        )
        return

    logger.info("憲法本文取得中: proposal_id=%s, enacted_epoch=%s", proposal_id, enacted_epoch)
    text, source_url = fetch_constitution_text()
    if not text:
        logger.error("憲法本文の取得に失敗。IPFS gateway / pymupdf / GPT_API_KEY / action_anchor_url を確認してください")
        return
    logger.info("取得 OK: %d 文字 (url=%s)", len(text), source_url)

    # まず原文だけ保存しておく（翻訳が長時間 / 失敗してもキャッシュは残る）
    upsert_constitution(
        proposal_id=proposal_id,
        enacted_epoch=enacted_epoch,
        source_url=source_url,
        original_text=text,
        update_translation=False,
    )

    # 翻訳（chunk して連続翻訳）
    logger.info("翻訳開始 (Translator はカタリスト同等エンジン)")
    translator = build_translator()
    translated = _translate_constitution_text(translator, text)
    logger.info("翻訳完了: %d 文字", len(translated))

    upsert_constitution(
        proposal_id=proposal_id,
        enacted_epoch=enacted_epoch,
        source_url=source_url,
        original_text=text,
        translated_text=translated,
        update_translation=True,
    )
    logger.info("=== Constitution sync 完了 ===")


def _translate_constitution_text(translator, text: str, chunk_chars: int = 4000) -> str:
    """段落単位で chunk して翻訳する（長文一括は token 制限・失敗時の再試行が辛いため）。
    chunk_chars 文字程度ごとに区切る。
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in paragraphs:
        if cur_len + len(p) > chunk_chars and cur:
            chunks.append("\n\n".join(cur))
            cur = []
            cur_len = 0
        cur.append(p)
        cur_len += len(p) + 2
    if cur:
        chunks.append("\n\n".join(cur))

    out: list[str] = []
    for i, c in enumerate(chunks, 1):
        if not c.strip():
            out.append(c)
            continue
        logger.info("  chunk %d/%d (%d chars)", i, len(chunks), len(c))
        try:
            translated = translator.translate_overview(c)
        except Exception as exc:
            logger.warning("  chunk %d 翻訳失敗 (continue 原文): %s", i, exc)
            translated = c
        out.append(translated)
    return "\n\n".join(out)


def check_ga_ai_reanalyze(
    proposal_id: str | None = None,
    all_flag: bool = False,
    include_old: bool = False,
) -> None:
    """既に analyzed の GA を pending に戻して再分析対象にする。

    Args:
        proposal_id: 単一 GA を対象に再分析する場合に指定。
        all_flag:    True なら status='analyzed' の全行を再分析対象にする。
        include_old: --all と組み合わせて指定すると Ratified / Enacted /
                     Dropped / Expired も含めて再分析する（トピック分類の
                     体系を変更したときなど、過去 GA も含めて再分類したい
                     ケース向け）。

    どちらも指定しなかった / 両方指定した場合は何もしない。
    """
    if proposal_id and all_flag:
        logger.error("--proposal-id と --all は同時指定できません")
        return
    if not proposal_id and not all_flag:
        logger.error("--proposal-id <id> または --all のどちらかを指定してください")
        return

    from cardanoism.backend.governance_ai_db import requeue, requeue_all

    if proposal_id:
        logger.info("=== GA AI 再分析: %s ===", proposal_id)
        ok = requeue(proposal_id)
        if ok:
            logger.info("pending に戻しました。ga_ai_worker が次サイクルで再分析します。")
        else:
            logger.warning("再分析対象に変更できませんでした (proposal_id 確認してください)")
        return

    if include_old:
        logger.info("=== GA AI 再分析: 全 analyzed (Ratified / Enacted / Dropped / Expired 含む) ===")
        n = requeue_all(only_analyzed=True, active_only=False)
        logger.info("%d 件を pending に戻しました（過去 GA 含む全件）。"
                    " ga_ai_worker が順次再分析します。", n)
    else:
        logger.info("=== GA AI 再分析: Active な analyzed 全件 ===")
        n = requeue_all(only_analyzed=True, active_only=True)
        logger.info("%d 件を pending に戻しました（Active な GA のみ対象）。"
                    " ga_ai_worker が順次再分析します。", n)


# ============================================================
# エントリポイント
# ============================================================

# ============================================================
# 管理者用: 通知疎通テスト
# ============================================================

def check_notify_test():
    """管理者用の通知疎通テスト。

    環境変数 ADMIN_USER_ID で指定したユーザーの notification_channels に登録された
    LINE / Telegram / email へ、本番と同じ送信ヘルパー (flex_and_log /
    telegram_and_log / email_and_log) を通してテストメッセージを送る。
    notification_log にも記録され、本番経路の疎通確認となる。
    enabled の ON/OFF は問わない。dedup_key はタイムスタンプ込みで毎回ユニーク。
    """
    from datetime import datetime, timezone

    admin_user_id = os.getenv("ADMIN_USER_ID", "").strip()
    if not admin_user_id:
        logger.warning("notify_test: ADMIN_USER_ID が未設定です")
        return
    try:
        uid = int(admin_user_id)
    except ValueError:
        logger.warning("notify_test: ADMIN_USER_ID が数値ではありません: %s", admin_user_id)
        return

    from cardanoism.backend.auth_db import get_notification_channels
    channels = get_notification_channels(uid)
    if not channels:
        logger.warning("notify_test: user_id=%s に登録チャンネルがありません", uid)
        return

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = f"Cardanoism 通知疎通テスト ({ts})"
    event_type = "notify_test"
    dedup_key = f"notify_test_{int(now.timestamp())}"
    logger.info("通知疎通テスト 開始 (user_id=%s, %d チャンネル)", uid, len(channels))

    # LINE 用の最小 Flex bubble (本番と同じ flex_and_log を通すため)
    flex_contents = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "Cardanoism 通知疎通テスト",
                 "weight": "bold", "size": "md"},
                {"type": "text", "text": ts,
                 "size": "sm", "color": "#888888", "wrap": True, "margin": "md"},
            ],
        },
    }

    for ch in channels:
        ctype = str(ch.get("channel_type") or "")
        cvalue = str(ch.get("channel_value") or "")
        if not cvalue:
            logger.info("notify_test %s: skip (channel_value 空)", ctype)
            continue
        try:
            if ctype == "line":
                ok = flex_and_log(cvalue, uid, event_type, dedup_key, msg, flex_contents)
            elif ctype == "telegram":
                ok = telegram_and_log(cvalue, uid, event_type, dedup_key, msg)
            elif ctype == "email":
                ok = email_and_log(
                    cvalue, uid, event_type, dedup_key,
                    "Cardanoism 通知疎通テスト", f"<p>{msg}</p>", msg,
                )
            else:
                logger.info("notify_test %s: skip (未対応チャンネル)", ctype)
                continue
            logger.info("notify_test %s: %s", ctype, "OK" if ok else "FAILED")
        except Exception as e:  # noqa: BLE001
            logger.exception("notify_test %s 失敗: %s", ctype, e)

    logger.info("通知疎通テスト 完了")


def main():
    parser = argparse.ArgumentParser(description="Cardanoism 通知バッチワーカー")
    parser.add_argument(
        "--event",
        default="all",
        choices=["all", "pool", "drep", "drep_unvoted", "reminder", "treasury", "treasury_sync", "fiat_sync", "drep_sync", "pool_sync", "pool_block_history_sync", "relay_check", "vote_sync", "summary_sync", "params_sync", "vote_rationale_sync", "ga_ai_initial_sync", "ga_ai_reanalyze", "constitution_sync", "spo_role_initial_sync", "compass_classify_all", "compass_profile_all", "compass_status", "notify_test"],
        help="実行するイベントグループ",
    )
    parser.add_argument(
        "--epoch-schedule",
        action="store_true",
        help="直近のエポック切り替わり時刻（UTC）を表示して終了する",
    )
    parser.add_argument(
        "--fetch-limit",
        type=int,
        default=500,
        help="vote_rationale_sync でメタデータ取得する最大件数（0 で無制限）",
    )
    parser.add_argument(
        "--translate-limit",
        type=int,
        default=100,
        help="vote_rationale_sync で OpenAI 翻訳する最大件数（0 で無制限）",
    )
    parser.add_argument(
        "--proposal-id",
        metavar="PROPOSAL_ID",
        help="ga_ai_reanalyze で対象を 1 件に絞るときに指定する proposal_id",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "ga_ai_reanalyze: Active かつ analyzed の GA 全件を再分析対象にする"
            "（Ratified / Enacted / Dropped / Expired は対象外）。"
            "ga_ai_initial_sync: 期間制限を外し過去 Dropped / Expired も含む全 GA を投入対象にする。"
        ),
    )
    parser.add_argument(
        "--include-old",
        action="store_true",
        help=(
            "ga_ai_reanalyze --all と組み合わせて、Ratified / Enacted / Dropped /"
            " Expired も含む全 analyzed GA を再分析対象にする"
            "（トピック分類体系の変更時など、過去 GA も再分類したいケース向け）。"
        ),
    )
    args = parser.parse_args()

    if args.epoch_schedule:
        print_epoch_schedule()
        return

    # Phase 4 (Ogmios listener) で stake_addresses.delegated_pool_id / delegated_drep_id を
    # 即時更新するようになったため、cron 側のリフレッシュは reminder の 1 時間ごとだけで十分。
    # listener が落ちている時のフォールバックを兼ねる。
    if args.event in ("all", "reminder"):
        refresh_stake_delegations()
    if args.event in ("all", "pool"):
        check_pool_events()
    if args.event in ("all", "drep"):
        check_drep_events()
    elif args.event == "drep_unvoted":
        # drep_unvoted 単独実行: status_change はスキップして未投票通知のみ走らせる
        _check_drep_unvoted_ga()
    if args.event in ("all", "reminder"):
        check_delegation_reminders()
    if args.event in ("all", "treasury"):
        check_treasury_events()
    if args.event in ("all", "treasury_sync"):
        check_treasury_sync()
    if args.event in ("all", "fiat_sync"):
        check_fiat_sync()
    if args.event in ("all", "drep_sync"):
        check_drep_sync()
    if args.event in ("all", "pool_sync"):
        check_pool_sync()
    if args.event in ("all", "pool_block_history_sync"):
        check_pool_block_history()
    if args.event in ("all", "relay_check"):
        check_pool_relay_alive()
    if args.event in ("all", "vote_sync"):
        check_vote_sync()
    if args.event in ("all", "summary_sync"):
        check_summary_sync()
    if args.event in ("all", "params_sync"):
        check_params_sync()
    if args.event in ("all", "vote_rationale_sync"):
        check_vote_rationale_sync(
            fetch_limit=args.fetch_limit,
            translate_limit=args.translate_limit,
        )
    # GA AI 初回同期は --event ga_ai_initial_sync で明示指定したときのみ実行する
    # （"all" には含めない: 通常は governance.py 側 enqueue で自動投入されるため）
    if args.event == "ga_ai_initial_sync":
        check_ga_ai_initial_sync(include_all=args.all)

    # GA AI 再分析: --event ga_ai_reanalyze で明示指定（"all" には含めない）
    if args.event == "ga_ai_reanalyze":
        check_ga_ai_reanalyze(
            proposal_id=args.proposal_id,
            all_flag=args.all,
            include_old=args.include_old,
        )

    # 憲法同期 + 翻訳: --event constitution_sync で明示指定（"all" には含めない）
    if args.event == "constitution_sync":
        check_constitution_sync()

    # SPO 判定 初期投入: --event spo_role_initial_sync で明示指定（"all" には含めない）
    if args.event == "spo_role_initial_sync":
        check_spo_role_initial_sync()

    # DRep マッチング診断用トピックプロフィール: 明示指定 or cron 経由（"all" には含めない）
    # DRep委任コンパス (11 axis MVP): rule-based GA 分類 / DRep プロファイル再計算
    if args.event == "compass_classify_all":
        check_drep_compass_classify_all()
    if args.event == "compass_profile_all":
        check_drep_compass_profile_all()
    if args.event == "compass_status":
        check_drep_compass_status()

    # 管理者用 通知疎通テスト: --event notify_test で明示指定（"all" には含めない）
    if args.event == "notify_test":
        check_notify_test()

    logger.info("完了")


if __name__ == "__main__":
    main()
