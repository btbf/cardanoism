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

# .env を明示的にロード（他モジュールの import より先に実行する必要がある）
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cardanoism", ".env"), override=True)

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.koios import (
    _post, _get, get_current_epoch,
    get_pool_apy, batch_account_info,
    batch_account_update_history, batch_account_reward_history,
    KOIOS_BATCH_SIZE, _chunks,
)
from cardanoism.backend.line_notify import send_line_push, send_line_flex
from cardanoism.backend import line_flex
from cardanoism.backend.mail_notify import send_email, build_html, build_text
from cardanoism.backend.telegram_notify import send_telegram

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

def get_state(scope_type: str, scope_id, key: str) -> str | None:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT last_value FROM notification_check_state "
            "WHERE scope_type = ? AND scope_id <=> ? AND key_name = ?",
            (scope_type, scope_id, key),
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
            (scope_type, scope_id, key, value, value),
        )
        conn.commit()


def bulk_get_state(scope_type: str, scope_ids: list, key: str) -> dict:
    """複数 scope_id の状態を1クエリで一括取得。{scope_id: last_value}"""
    if not scope_ids:
        return {}
    placeholders = ",".join(["?"] * len(scope_ids))
    with get_db() as (cursor, _):
        cursor.execute(
            f"SELECT scope_id, last_value FROM notification_check_state "
            f"WHERE scope_type = ? AND scope_id IN ({placeholders}) AND key_name = ?",
            [scope_type, *scope_ids, key],
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
            SELECT u.id, nc.channel_value AS email_addr, COALESCE(u.language, 'ja') AS language
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
            SELECT u.id, nc.channel_value AS telegram_chat_id, COALESCE(u.language, 'ja') AS language
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
            SELECT u.id, nc.channel_value AS line_notify_id, COALESCE(u.language, 'ja') AS language
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
    """
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

        with get_db() as (cursor, conn):
            cursor.execute(
                """UPDATE stake_addresses
                   SET delegated_pool_id = ?, delegated_drep_id = ?, role_checked_at = NOW()
                   WHERE id = ?""",
                (new_pool_id, new_drep_id, row["id"]),
            )
            conn.commit()

        logger.info(
            "委任先更新: address_id=%d  pool %s→%s  drep %s→%s",
            row["id"],
            row["delegated_pool_id"], new_pool_id,
            row["delegated_drep_id"], new_drep_id,
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

    if event_type == "pool_saturation":
        saturation = pool_info.get("live_saturation")
        if saturation is None:
            return
        sat_pct = float(saturation) * 100
        is_saturated = sat_pct > 100
        was_saturated = get_state("stake_address", stake_id, "pool_saturated")
        if is_saturated and was_saturated != "1":
            set_state("stake_address", stake_id, "pool_saturated", "1")
            dedup_key = f"pool_saturation_{stake_id}_{int(sat_pct)}"
            if already_sent(user_id, event_type, dedup_key):
                return
            alt_text = f"【Cardanoism】委任先プール「{pool_name}」が飽和ラインを超えました（{sat_pct:.1f}%）" if lang == "ja" else f"[Cardanoism] Pool '{pool_name}' exceeded saturation ({sat_pct:.1f}%)"
            contents = line_flex.pool_saturation(pool_name, sat_pct, apy, nickname, CARDANOISM_URL, lang=lang)
            flex_and_log(line_id, user_id, event_type, dedup_key, alt_text, contents)
            if addr.get("email_addr"):
                dk = dedup_key + "_email"
                if not already_sent(user_id, event_type, dk):
                    subj = f"委任先プール「{pool_name}」が飽和ラインを超えました（{sat_pct:.1f}%）" if lang == "ja" else f"Pool '{pool_name}' exceeded saturation ({sat_pct:.1f}%)"
                    ls = ([f"ウォレット: {nickname}", f"プール「{pool_name}」の飽和度が {sat_pct:.1f}% になっています。", "委任先の変更をご検討ください。"]
                          if lang == "ja" else
                          [f"Wallet: {nickname}", f"Pool '{pool_name}' saturation is {sat_pct:.1f}%.", "Please consider changing your delegation."])
                    email_and_log(addr["email_addr"], user_id, event_type, dk, subj,
                                  build_html(subj, ls, CARDANOISM_URL, "マイページを開く" if lang == "ja" else "Open MyPage", lang),
                                  build_text(subj, ls, CARDANOISM_URL, lang))
            if addr.get("telegram_chat_id"):
                dk = dedup_key + "_telegram"
                if not already_sent(user_id, event_type, dk):
                    tg_text = (f"⚠️ <b>委任先プール飽和アラート</b>\nウォレット: {nickname}\nプール: {pool_name}\n飽和度: {sat_pct:.1f}%\n委任先の変更をご検討ください。"
                               if lang == "ja" else
                               f"⚠️ <b>Pool Saturation Alert</b>\nWallet: {nickname}\nPool: {pool_name}\nSaturation: {sat_pct:.1f}%\nPlease consider changing your delegation.")
                    telegram_and_log(addr["telegram_chat_id"], user_id, event_type, dk, tg_text)
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
            if already_sent(user_id, event_type, dedup_key):
                return
            live_ada = live_pledge / 1_000_000
            pledged_ada = pledge / 1_000_000
            alt_text = f"【Cardanoism】委任先プール「{pool_name}」の誓約が不足しています" if lang == "ja" else f"[Cardanoism] Pool '{pool_name}' has insufficient pledge"
            contents = line_flex.pool_pledge_shortage(pool_name, pledged_ada, live_ada, apy, nickname, CARDANOISM_URL, lang=lang)
            flex_and_log(line_id, user_id, event_type, dedup_key, alt_text, contents)
            if addr.get("email_addr"):
                dk = dedup_key + "_email"
                if not already_sent(user_id, event_type, dk):
                    subj = f"委任先プール「{pool_name}」の誓約が不足しています" if lang == "ja" else f"Pool '{pool_name}' has insufficient pledge"
                    ls = ([f"ウォレット: {nickname}", f"誓約金額: {pledged_ada:,.0f} ADA", f"現在の実績: {live_ada:,.0f} ADA", "誓約不足のプールは報酬が減少する場合があります。"]
                          if lang == "ja" else
                          [f"Wallet: {nickname}", f"Pledge: {pledged_ada:,.0f} ADA", f"Live pledge: {live_ada:,.0f} ADA", "Pools with insufficient pledge may have reduced rewards."])
                    email_and_log(addr["email_addr"], user_id, event_type, dk, subj,
                                  build_html(subj, ls, CARDANOISM_URL, "マイページを開く" if lang == "ja" else "Open MyPage", lang),
                                  build_text(subj, ls, CARDANOISM_URL, lang))
            if addr.get("telegram_chat_id"):
                dk = dedup_key + "_telegram"
                if not already_sent(user_id, event_type, dk):
                    tg_text = (f"⚠️ <b>誓約不足アラート</b>\nウォレット: {nickname}\nプール: {pool_name}\n誓約: {pledged_ada:,.0f} ADA / 実績: {live_ada:,.0f} ADA"
                               if lang == "ja" else
                               f"⚠️ <b>Pledge Shortage Alert</b>\nWallet: {nickname}\nPool: {pool_name}\nPledge: {pledged_ada:,.0f} ADA / Live: {live_ada:,.0f} ADA")
                    telegram_and_log(addr["telegram_chat_id"], user_id, event_type, dk, tg_text)
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
    """
    if current_epoch is None:
        return
    reward_epoch = current_epoch - 2

    # dedup 済みでない報酬通知対象アドレスを収集
    reward_addrs = [
        addr for stake_id, addr in all_addrs.items()
        if "pool_reward_received" in enabled_events.get(stake_id, set())
        and not already_sent(
            addr["user_id"], "pool_reward_received", f"reward_{addr['stake_id']}_{reward_epoch}"
        )
    ]
    if not reward_addrs:
        return

    # 1,000件チャンクで一括取得
    reward_map = batch_account_reward_history(
        [a["address"] for a in reward_addrs], reward_epoch
    )
    if not reward_map:
        return

    # 各アドレスに通知
    for addr in reward_addrs:
        total_lovelace = reward_map.get(addr["address"], 0)
        if total_lovelace <= 0:
            continue

        amount_ada = total_lovelace / 1_000_000
        stake_id = addr["stake_id"]
        user_id = addr["user_id"]
        line_id = addr["line_notify_id"]
        lang = addr.get("language", "ja")
        pool_name = addr.get("delegated_pool_name") or (addr.get("delegated_pool_id") or "")[:12]
        nickname = addr["nickname"]
        apy = pool_apys.get(addr.get("delegated_pool_id") or "")

        dedup_key = f"reward_{stake_id}_{reward_epoch}"
        alt_text = (
            f"【Cardanoism】Epoch {reward_epoch} 分の報酬が入金されました"
            if lang == "ja" else
            f"[Cardanoism] Rewards for Epoch {reward_epoch} have arrived"
        )
        contents = line_flex.pool_reward_received(reward_epoch, amount_ada, apy, nickname, CARDANOISM_URL, lang=lang)
        flex_and_log(line_id, user_id, "pool_reward_received", dedup_key, alt_text, contents)
        if addr.get("email_addr"):
            dk = dedup_key + "_email"
            if not already_sent(user_id, "pool_reward_received", dk):
                subj = (
                    f"Epoch {reward_epoch} 分の報酬が入金されました"
                    if lang == "ja" else
                    f"Rewards for Epoch {reward_epoch} have arrived"
                )
                ls = (
                    [f"ウォレット: {nickname}", f"Epoch {reward_epoch} の報酬: {amount_ada:.6f} ADA"]
                    if lang == "ja" else
                    [f"Wallet: {nickname}", f"Epoch {reward_epoch} reward: {amount_ada:.6f} ADA"]
                )
                email_and_log(
                    addr["email_addr"], user_id, "pool_reward_received", dk, subj,
                    build_html(subj, ls, CARDANOISM_URL, "マイページを開く" if lang == "ja" else "Open MyPage", lang),
                    build_text(subj, ls, CARDANOISM_URL, lang),
                )
        if addr.get("telegram_chat_id"):
            dk = dedup_key + "_telegram"
            if not already_sent(user_id, "pool_reward_received", dk):
                tg_text = (f"💰 <b>ステーキング報酬入金</b>\nウォレット: {nickname}\nEpoch {reward_epoch} 報酬: {amount_ada:.6f} ADA"
                           if lang == "ja" else
                           f"💰 <b>Staking Reward Received</b>\nWallet: {nickname}\nEpoch {reward_epoch} reward: {amount_ada:.6f} ADA")
                telegram_and_log(addr["telegram_chat_id"], user_id, "pool_reward_received", dk, tg_text)


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
        lang = addr.get("language", "ja")
        for milestone in REMINDER_MILESTONES:
            if days < milestone:
                continue
            dedup_key = f"pool_remind_{addr['stake_id']}_{milestone}d"
            if already_sent(addr["user_id"], "pool_delegation_reminder", dedup_key):
                continue
            alt_text = f"【Cardanoism】委任から{milestone}日が経過しました。委任先プールを確認しましょう" if lang == "ja" else f"[Cardanoism] {milestone} days since delegation. Please check your pool."
            contents = line_flex.pool_delegation_reminder(pool_name, milestone, apy, addr["nickname"], CARDANOISM_URL, lang=lang)
            flex_and_log(addr["line_notify_id"], addr["user_id"], "pool_delegation_reminder", dedup_key, alt_text, contents)
            if addr.get("email_addr"):
                dk = dedup_key + "_email"
                if not already_sent(addr["user_id"], "pool_delegation_reminder", dk):
                    subj = f"委任から{milestone}日が経過しました。委任先プールを確認しましょう" if lang == "ja" else f"{milestone} days since delegation. Please check your pool."
                    ls = ([f"ウォレット: {addr['nickname']}", f"委任先プール: {pool_name}", f"委任から {milestone} 日が経過しました。委任先プールの状態を確認することをお勧めします。"]
                          if lang == "ja" else
                          [f"Wallet: {addr['nickname']}", f"Pool: {pool_name}", f"{milestone} days have passed since delegation. We recommend reviewing your pool."])
                    email_and_log(addr["email_addr"], addr["user_id"], "pool_delegation_reminder", dk, subj,
                                  build_html(subj, ls, CARDANOISM_URL, "マイページを開く" if lang == "ja" else "Open MyPage", lang),
                                  build_text(subj, ls, CARDANOISM_URL, lang))
            if addr.get("telegram_chat_id"):
                dk = dedup_key + "_telegram"
                if not already_sent(addr["user_id"], "pool_delegation_reminder", dk):
                    tg_text = (f"🔔 <b>委任リマインダー</b>\nウォレット: {addr['nickname']}\nプール: {pool_name}\n委任から {milestone} 日が経過しました。委任先を確認しましょう。"
                               if lang == "ja" else
                               f"🔔 <b>Delegation Reminder</b>\nWallet: {addr['nickname']}\nPool: {pool_name}\n{milestone} days since delegation. Please review your pool.")
                    telegram_and_log(addr["telegram_chat_id"], addr["user_id"], "pool_delegation_reminder", dk, tg_text)


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
        lang = addr.get("language", "ja")
        for milestone in REMINDER_MILESTONES:
            if days < milestone:
                continue
            dedup_key = f"drep_remind_{addr['stake_id']}_{milestone}d"
            if already_sent(addr["user_id"], "drep_delegation_reminder", dedup_key):
                continue
            alt_text = f"【Cardanoism】委任から{milestone}日が経過しました。委任先DRepを確認しましょう" if lang == "ja" else f"[Cardanoism] {milestone} days since delegation. Please check your DRep."
            contents = line_flex.drep_delegation_reminder(drep_name, milestone, addr["nickname"], f"{CARDANOISM_URL}/governance", lang=lang)
            flex_and_log(addr["line_notify_id"], addr["user_id"], "drep_delegation_reminder", dedup_key, alt_text, contents)
            if addr.get("email_addr"):
                dk = dedup_key + "_email"
                if not already_sent(addr["user_id"], "drep_delegation_reminder", dk):
                    subj = f"委任から{milestone}日が経過しました。委任先DRepを確認しましょう" if lang == "ja" else f"{milestone} days since delegation. Please check your DRep."
                    ls = ([f"ウォレット: {addr['nickname']}", f"委任先DRep: {drep_name}", f"委任から {milestone} 日が経過しました。委任先DRepの活動を確認することをお勧めします。"]
                          if lang == "ja" else
                          [f"Wallet: {addr['nickname']}", f"DRep: {drep_name}", f"{milestone} days have passed since delegation. We recommend reviewing your DRep's activity."])
                    gov_url = f"{CARDANOISM_URL}/governance"
                    email_and_log(addr["email_addr"], addr["user_id"], "drep_delegation_reminder", dk, subj,
                                  build_html(subj, ls, gov_url, "ガバナンスを確認" if lang == "ja" else "Check Governance", lang),
                                  build_text(subj, ls, gov_url, lang))
            if addr.get("telegram_chat_id"):
                dk = dedup_key + "_telegram"
                if not already_sent(addr["user_id"], "drep_delegation_reminder", dk):
                    tg_text = (f"🗳️ <b>DRep委任リマインダー</b>\nウォレット: {addr['nickname']}\nDRep: {drep_name}\n委任から {milestone} 日が経過しました。DRepの活動を確認しましょう。"
                               if lang == "ja" else
                               f"🗳️ <b>DRep Delegation Reminder</b>\nWallet: {addr['nickname']}\nDRep: {drep_name}\n{milestone} days since delegation. Please review your DRep's activity.")
                    telegram_and_log(addr["telegram_chat_id"], addr["user_id"], "drep_delegation_reminder", dk, tg_text)


def check_drep_events():
    logger.info("DRepイベント チェック開始")
    _check_drep_status_change()


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

        alt_text = f"【Cardanoism】委任先DRep「{drep_name}」のステータスが変わりました" if lang == "ja" else f"[Cardanoism] Delegated DRep '{drep_name}' status changed"
        contents = line_flex.drep_status_change(drep_name, last_status, status, addr["nickname"], CARDANOISM_URL, lang=lang)
        flex_and_log(line_id, user_id, "drep_status_change", dedup_key, alt_text, contents)
        if addr.get("email_addr"):
            dk = dedup_key + "_email"
            if not already_sent(user_id, "drep_status_change", dk):
                subj = f"委任先DRep「{drep_name}」のステータスが変わりました" if lang == "ja" else f"Delegated DRep '{drep_name}' status changed"
                ls = ([f"ウォレット: {addr['nickname']}", f"DRep: {drep_name}", f"ステータス: {last_status} → {status}"]
                      if lang == "ja" else
                      [f"Wallet: {addr['nickname']}", f"DRep: {drep_name}", f"Status: {last_status} → {status}"])
                email_and_log(addr["email_addr"], user_id, "drep_status_change", dk, subj,
                              build_html(subj, ls, CARDANOISM_URL, "ガバナンスを確認" if lang == "ja" else "Check Governance", lang),
                              build_text(subj, ls, CARDANOISM_URL, lang))
        if addr.get("telegram_chat_id"):
            dk = dedup_key + "_telegram"
            if not already_sent(user_id, "drep_status_change", dk):
                tg_text = (f"📋 <b>DRepステータス変更</b>\nウォレット: {addr['nickname']}\nDRep: {drep_name}\nステータス: {last_status} → {status}"
                           if lang == "ja" else
                           f"📋 <b>DRep Status Changed</b>\nWallet: {addr['nickname']}\nDRep: {drep_name}\nStatus: {last_status} → {status}")
                telegram_and_log(addr["telegram_chat_id"], user_id, "drep_status_change", dk, tg_text)


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
    """
    from cardanoism.backend.koios import get_proposal_voting_summary
    from cardanoism.backend.voting_summary_db import upsert_voting_summary

    logger.info("投票集計同期 開始 (workers=%d)", max_workers)

    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, proposal_type
            FROM governance_actions
            WHERE proposal_id IS NOT NULL AND proposal_id <> ''
            ORDER BY block_time DESC
            """
        )
        proposals = [dict(r) for r in cursor.fetchall() if r.get("proposal_id")]
    logger.info("集計対象: %d 件", len(proposals))

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


def check_pool_sync():
    """
    Koios から全プールの情報を取得して DB にキャッシュする。
    - /pool_list: 全プールの最小情報（status / ticker / retiring_epoch 等）
    - /pool_info: 詳細（pledge / margin / live_stake / saturation / blocks / メタデータ）
    """
    from cardanoism.backend.koios import (
        KOIOS_BASE_URL, get_pool_list, get_pool_info_batch,
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

        records.append({
            "pool_id_bech32":   pid,
            "pool_id_hex":      info.get("pool_id_hex") or p.get("pool_id_hex"),
            "pool_status":      p.get("pool_status") or info.get("pool_status"),
            "active_epoch_no":  info.get("active_epoch_no"),
            "retiring_epoch":   p.get("retiring_epoch") or info.get("retiring_epoch"),
            "op_cert":          info.get("op_cert"),
            "op_cert_counter": info.get("op_cert_counter"),
            "vrf_key_hash":     info.get("vrf_key_hash"),
            "pledge":           info.get("pledge"),
            "margin":           info.get("margin"),
            "fixed_cost":       info.get("fixed_cost"),
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
        insert_treasury_withdrawals,
        upsert_active_ncl,
    )
    logger.info("トレジャリー同期 開始 (network=%s, url=%s)", _koios_network(), KOIOS_BASE_URL)

    # 1) トレジャリー残高
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
    try:
        ncl = fetch_active_ncl(use_cache=False)
        if ncl:
            upsert_active_ncl(ncl)
            logger.info(
                "ncl_active 更新: %s (%d ADA, Ep.%d-%d, DRep %.2f%%)",
                ncl["title"], ncl["limit_ada"], ncl["start_epoch"], ncl["end_epoch"], ncl["drep_yes_pct"],
            )
        else:
            logger.warning("DRep過半数賛成のNCL提案が見つかりません（既存の ncl_active はそのまま）")
    except Exception as e:
        logger.exception("ncl_active 同期失敗: %s", e)

    logger.info("トレジャリー同期 完了")


# ============================================================
# トレジャリーイベント
# ============================================================

def check_treasury_events():
    """TreasuryWithdrawals ガバナンスアクションが enacted（施行）されたのを検知して全ユーザーへ通知。"""
    logger.info("トレジャリーイベント チェック開始")
    from cardanoism.backend.koios import get_treasury_proposals

    proposals = get_treasury_proposals()
    enacted = [p for p in proposals if p.get("enacted_epoch") is not None]
    if not enacted:
        logger.info("施行済みのトレジャリー引き出しはありません")
        return

    line_users = get_users_with_event("treasury_withdrawal_enacted")
    email_users = get_users_with_email_event("treasury_withdrawal_enacted")
    tg_users = get_users_with_telegram_event("treasury_withdrawal_enacted")

    if not (line_users or email_users or tg_users):
        logger.info("通知対象ユーザーがいません")
        return

    for p in enacted:
        proposal_id = p.get("proposal_id") or ""
        enacted_epoch = p.get("enacted_epoch")
        dedup_base = f"treasury_enacted:{proposal_id}"

        meta_body = ((p.get("meta_json") or {}).get("body") or {}) if isinstance(p.get("meta_json"), dict) else {}
        title = ""
        if isinstance(meta_body, dict):
            raw_title = meta_body.get("title")
            if isinstance(raw_title, dict):
                title = str(raw_title.get("@value") or "").strip()
            elif isinstance(raw_title, str):
                title = raw_title.strip()
        if not title:
            title = proposal_id[:24] + "..."

        proposal_url = f"{CARDANOISM_URL}/governance/{proposal_id}"

        for u in line_users:
            dk = dedup_base + "_line"
            if already_sent(u["id"], "treasury_withdrawal_enacted", dk):
                continue
            lang = u.get("language", "ja")
            msg = (
                f"🏛️ 【トレジャリー引き出しが施行されました】\n"
                f"タイトル: {title}\n"
                f"施行エポック: {enacted_epoch}\n"
                f"詳細: {proposal_url}"
                if lang == "ja" else
                f"🏛️ [Treasury Withdrawal Enacted]\n"
                f"Title: {title}\n"
                f"Enacted Epoch: {enacted_epoch}\n"
                f"Details: {proposal_url}"
            )
            push_and_log(u["line_notify_id"], u["id"], "treasury_withdrawal_enacted", dk, msg)

        for u in email_users:
            dk = dedup_base + "_email"
            if already_sent(u["id"], "treasury_withdrawal_enacted", dk):
                continue
            lang = u.get("language", "ja")
            subj = "トレジャリー引き出しが施行されました" if lang == "ja" else "Treasury Withdrawal Enacted"
            lines = (
                [f"タイトル: {title}", f"施行エポック: {enacted_epoch}"]
                if lang == "ja" else
                [f"Title: {title}", f"Enacted Epoch: {enacted_epoch}"]
            )
            cta = "提案を開く" if lang == "ja" else "Open Proposal"
            email_and_log(
                u["email_addr"], u["id"], "treasury_withdrawal_enacted", dk, subj,
                build_html(subj, lines, proposal_url, cta, lang),
                build_text(subj, lines, proposal_url, lang),
            )

        for u in tg_users:
            dk = dedup_base + "_telegram"
            if already_sent(u["id"], "treasury_withdrawal_enacted", dk):
                continue
            lang = u.get("language", "ja")
            tg_text = (
                f"🏛️ <b>トレジャリー引き出しが施行されました</b>\n"
                f"タイトル: {title}\n施行エポック: {enacted_epoch}\n{proposal_url}"
                if lang == "ja" else
                f"🏛️ <b>Treasury Withdrawal Enacted</b>\n"
                f"Title: {title}\nEnacted Epoch: {enacted_epoch}\n{proposal_url}"
            )
            telegram_and_log(u["telegram_chat_id"], u["id"], "treasury_withdrawal_enacted", dk, tg_text)


# ============================================================
# テスト送信
# ============================================================

def list_users():
    """LINE 通知チャンネルが設定されているユーザー一覧を表示する。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT u.id, u.username, u.email, nc.channel_value AS line_notify_id
            FROM users u
            JOIN notification_channels nc ON u.id = nc.user_id AND nc.channel_type = 'line'
            ORDER BY u.id
            """
        )
        rows = cursor.fetchall()
    if not rows:
        print("LINE 通知チャンネルが設定されているユーザーはいません")
        return
    print(f"{'ID':>4}  {'ユーザー名':<20}  {'メール':<30}  LINE ID")
    print("-" * 80)
    for row in rows:
        line_id_masked = row["line_notify_id"][:6] + "..." if row["line_notify_id"] else "-"
        print(f"{row['id']:>4}  {(row['username'] or ''):<20}  {(row['email'] or ''):<30}  {line_id_masked}")


def _get_user_info(user_id: int) -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT nc.channel_value AS line_notify_id, COALESCE(u.language, 'ja') AS language
            FROM users u
            LEFT JOIN notification_channels nc ON u.id = nc.user_id AND nc.channel_type = 'line' AND nc.enabled = 1
            WHERE u.id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def _get_line_id_for_user(user_id: int) -> str | None:
    info = _get_user_info(user_id)
    return info["line_notify_id"] if info else None


def _get_user_enabled_events(user_id: int) -> dict[str, list]:
    """
    ユーザーの ON イベントを返す。
    {
      "user": ["epoch_start", ...],          # notification_settings が enabled=1
      "stakes": {stake_id: {"nickname": ..., "events": [...]}},  # stake_notification_settings が enabled=1
    }
    """
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT event_type FROM notification_settings WHERE user_id = ? AND enabled = 1",
            (user_id,),
        )
        user_events = [row["event_type"] for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT sa.id, sa.nickname,
                   sa.delegated_pool_id, sa.delegated_pool_name,
                   sa.delegated_drep_id, sa.delegated_drep_name,
                   sns.event_type
            FROM stake_addresses sa
            JOIN stake_notification_settings sns ON sa.id = sns.stake_address_id
            WHERE sa.user_id = ? AND sns.enabled = 1
            ORDER BY sa.id
            """,
            (user_id,),
        )
        stakes: dict[int, dict] = {}
        for row in cursor.fetchall():
            sid = row["id"]
            if sid not in stakes:
                stakes[sid] = {
                    "nickname": row["nickname"],
                    "pool_id": row["delegated_pool_id"] or "",
                    "pool_name": row["delegated_pool_name"] or "",
                    "drep_id": row["delegated_drep_id"] or "",
                    "drep_name": row["delegated_drep_name"] or "",
                    "events": [],
                }
            stakes[sid]["events"].append(row["event_type"])

    return {"user": user_events, "stakes": stakes}


def send_test_enabled(user_id: int):
    """ユーザーの ON イベントをすべてダミーデータでテスト送信する。"""
    user_info = _get_user_info(user_id)
    if not user_info or not user_info.get("line_notify_id"):
        logger.error("ユーザー %d が見つからないか LINE 通知チャンネルが未設定です", user_id)
        return
    line_id = user_info["line_notify_id"]
    _DUMMY["_lang"] = user_info.get("language", "ja")

    enabled = _get_user_enabled_events(user_id)

    # ユーザーレベルイベント（epoch_start など）
    for event_type in enabled["user"]:
        result = _build_dummy_flex(event_type)
        if result is None:
            continue
        alt_text, contents = result
        ok = send_line_flex(line_id, alt_text, contents)
        logger.info("[%s] %s (user)", "OK" if ok else "失敗", event_type)

    # ステークアドレスレベルイベント
    drep_events = {"drep_status_change", "drep_delegation_reminder"}
    pool_events = {"pool_saturation", "pool_pledge_shortage",
                   "pool_reward_received", "pool_delegation_reminder"}

    for sid, info in enabled["stakes"].items():
        for event_type in info["events"]:
            # 委任していない場合はスキップ
            if event_type in drep_events and not info["drep_id"]:
                logger.info("[スキップ] %s — DRep未委任 (stake_id=%d / %s)", event_type, sid, info["nickname"])
                continue
            if event_type in pool_events and not info["pool_id"]:
                logger.info("[スキップ] %s — プール未委任 (stake_id=%d / %s)", event_type, sid, info["nickname"])
                continue

            # ダミーデータのニックネーム・プール名・DRep名をアドレスの実値で上書き
            saved_nickname = _DUMMY["nickname"]
            saved_pool = _DUMMY["pool_name"]
            saved_drep = _DUMMY["drep_name"]
            _DUMMY["nickname"] = info["nickname"] or saved_nickname
            _DUMMY["pool_name"] = info["pool_name"] or saved_pool
            _DUMMY["drep_name"] = info["drep_name"] or saved_drep

            result = _build_dummy_flex(event_type)

            _DUMMY["nickname"] = saved_nickname
            _DUMMY["pool_name"] = saved_pool
            _DUMMY["drep_name"] = saved_drep

            if result is None:
                continue
            alt_text, contents = result
            ok = send_line_flex(line_id, alt_text, contents)
            logger.info("[%s] %s (stake_id=%d / %s)", "OK" if ok else "失敗", event_type, sid, info["nickname"])


def send_test(user_id: int):
    """指定ユーザーIDに接続確認テストメッセージを送信する。"""
    line_id = _get_line_id_for_user(user_id)
    if not line_id:
        logger.error("ユーザー %d が見つからないか LINE ID が未設定です", user_id)
        return
    msg = (
        f"【Cardanoism テスト通知】\n"
        f"LINE通知の接続確認です。\n"
        f"このメッセージが届いていれば通知の設定は完了です。"
    )
    ok = send_line_push(line_id, msg)
    if ok:
        logger.info("テスト通知を送信しました (user_id=%d)", user_id)
    else:
        logger.error("テスト通知の送信に失敗しました (user_id=%d)", user_id)


# ダミーデータ
_DUMMY = {
    "pool_name": "DUMMY Pool",
    "pool_id": "pool1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "drep_name": "テストDRep",
    "drep_id": "drep1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "nickname": "メインウォレット",
    "epoch": 624,
    "reward_epoch": 622,
    "amount_ada": 12.345678,
    "apy": 3.45,
    "_lang": "ja",  # テスト送信時の言語（_get_user_info で上書きされる）
}

_ALL_TEST_EVENTS = [
    "epoch_start",
    "pool_saturation",
    "pool_pledge_shortage",
    "pool_reward_received",
    "pool_epoch_performance",
    "pool_delegation_reminder",
    "drep_status_change",
    "drep_delegation_reminder",
]


def _build_dummy_flex(ev: str) -> tuple[str, dict] | None:
    """ダミーデータで (alt_text, contents) を返す。不明なイベントは None。"""
    d = _DUMMY
    lang = d.get("_lang", "ja")
    ja = lang == "ja"
    if ev == "pool_saturation":
        return (
            f"【Cardanoism】委任先プール「{d['pool_name']}」が飽和ラインを超えました（108.3%）" if ja else f"[Cardanoism] Pool '{d['pool_name']}' exceeded saturation (108.3%)",
            line_flex.pool_saturation(d["pool_name"], 108.3, d["apy"], d["nickname"], CARDANOISM_URL, lang=lang),
        )
    if ev == "pool_pledge_shortage":
        return (
            f"【Cardanoism】委任先プール「{d['pool_name']}」の誓約が不足しています" if ja else f"[Cardanoism] Pool '{d['pool_name']}' has insufficient pledge",
            line_flex.pool_pledge_shortage(d["pool_name"], 500_000, 480_000, d["apy"], d["nickname"], CARDANOISM_URL, lang=lang),
        )
    if ev == "pool_reward_received":
        return (
            f"【Cardanoism】Epoch {d['reward_epoch']} 分の報酬が入金されました" if ja else f"[Cardanoism] Rewards for Epoch {d['reward_epoch']} have arrived",
            line_flex.pool_reward_received(d["reward_epoch"], d["amount_ada"], d["apy"], d["nickname"], CARDANOISM_URL, lang=lang),
        )
    if ev == "pool_delegation_reminder":
        return (
            "【Cardanoism】委任から90日が経過しました。委任先プールを確認しましょう" if ja else "[Cardanoism] 90 days since delegation. Please check your pool.",
            line_flex.pool_delegation_reminder(d["pool_name"], 90, d["apy"], d["nickname"], CARDANOISM_URL, lang=lang),
        )
    if ev == "drep_status_change":
        return (
            f"【Cardanoism】委任先DRep「{d['drep_name']}」のステータスが変わりました" if ja else f"[Cardanoism] Delegated DRep '{d['drep_name']}' status changed",
            line_flex.drep_status_change(d["drep_name"], "active", "inactive", d["nickname"], CARDANOISM_URL, lang=lang),
        )
    if ev == "drep_delegation_reminder":
        return (
            "【Cardanoism】委任から90日が経過しました。委任先DRepを確認しましょう" if ja else "[Cardanoism] 90 days since delegation. Please check your DRep.",
            line_flex.drep_delegation_reminder(d["drep_name"], 90, d["nickname"], f"{CARDANOISM_URL}/governance", lang=lang),
        )
    return None


def send_test_event(user_id: int, event: str):
    """指定イベントのダミー通知を Flex で送信する。"""
    user_info = _get_user_info(user_id)
    if not user_info or not user_info.get("line_notify_id"):
        logger.error("ユーザー %d が見つからないか LINE 通知チャンネルが未設定です", user_id)
        return
    line_id = user_info["line_notify_id"]
    _DUMMY["_lang"] = user_info.get("language", "ja")

    targets = _ALL_TEST_EVENTS if event == "all" else [event]
    for ev in targets:
        result = _build_dummy_flex(ev)
        if result is None:
            logger.warning("不明なイベント: %s", ev)
            continue
        alt_text, contents = result
        ok = send_line_flex(line_id, alt_text, contents)
        logger.info("[%s] %s", "OK" if ok else "失敗", ev)


# ============================================================
# エントリポイント
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Cardanoism 通知バッチワーカー")
    parser.add_argument(
        "--event",
        default="all",
        choices=["all", "pool", "drep", "reminder", "treasury", "treasury_sync", "fiat_sync", "drep_sync", "pool_sync", "relay_check", "vote_sync", "summary_sync", "params_sync", "vote_rationale_sync"],
        help="実行するイベントグループ",
    )
    parser.add_argument(
        "--test",
        type=int,
        metavar="USER_ID",
        help="指定したユーザーIDにテスト通知を送信して終了する",
    )
    parser.add_argument(
        "--list-users",
        action="store_true",
        help="LINE ID が設定されているユーザー一覧を表示して終了する",
    )
    parser.add_argument(
        "--test-event",
        metavar="EVENT",
        help=f"ダミーデータで通知テスト。--test と組み合わせて使う。all または {_ALL_TEST_EVENTS}",
    )
    parser.add_argument(
        "--test-enabled",
        action="store_true",
        help="--test と組み合わせて使う。ユーザーの ON イベントのみダミーテスト送信する",
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
    args = parser.parse_args()

    if args.epoch_schedule:
        print_epoch_schedule()
        return

    if args.list_users:
        list_users()
        return

    if args.test is not None:
        if args.test_enabled:
            send_test_enabled(args.test)
        elif args.test_event:
            send_test_event(args.test, args.test_event)
        else:
            send_test(args.test)
        return

    if args.event in ("all", "pool", "drep", "reminder"):
        refresh_stake_delegations()
    if args.event in ("all", "pool"):
        check_pool_events()
    if args.event in ("all", "drep"):
        check_drep_events()
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

    logger.info("完了")


if __name__ == "__main__":
    main()
