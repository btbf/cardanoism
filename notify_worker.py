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
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("notify_worker")

CARDANOISM_URL = os.getenv("CARDANOISM_URL", "https://cardanoism.app")

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


def _merge_stake_channels(line_addrs: list[dict], email_addrs: list[dict]) -> list[dict]:
    """
    LINE と email のアドレスリストを stake_id をキーにマージして返す。
    どちらか一方のチャンネルしか持たない場合も含む。
    """
    merged: dict[int, dict] = {}
    for addr in line_addrs:
        sid = addr["stake_id"]
        merged[sid] = {**addr, "email_addr": None}
    for addr in email_addrs:
        sid = addr["stake_id"]
        if sid not in merged:
            merged[sid] = {**addr, "line_notify_id": None}
        else:
            merged[sid]["email_addr"] = addr["email_addr"]
    return list(merged.values())


def flex_and_log(line_id: str, user_id: int, event_type: str, dedup_key: str, alt_text: str, contents: dict) -> bool:
    """LINE Flex 送信 + ログ記録。成功時 True。"""
    ok = send_line_flex(line_id, alt_text, contents)
    if ok:
        log_sent(user_id, event_type, dedup_key, "line", alt_text)
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

    # LINE と email チャンネルを持つアドレスをまとめて収集
    all_addrs: dict[int, dict] = {}
    enabled_events: dict[int, set] = {}

    for event_type in POOL_EVENT_TYPES:
        for addr in get_stake_addrs_with_event(event_type):
            sid = addr["stake_id"]
            if sid not in all_addrs:
                all_addrs[sid] = {**addr, "email_addr": None}
            enabled_events.setdefault(sid, set()).add(event_type)
        for addr in get_stake_addrs_with_email_event(event_type):
            sid = addr["stake_id"]
            if sid not in all_addrs:
                all_addrs[sid] = {**addr, "line_notify_id": None}
            all_addrs[sid]["email_addr"] = addr["email_addr"]
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


def _check_drep_delegation_reminder():
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_delegation_reminder"),
        get_stake_addrs_with_email_event("drep_delegation_reminder"),
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


def check_drep_events():
    logger.info("DRepイベント チェック開始")
    _check_drep_status_change()


def _check_drep_status_change():
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_status_change"),
        get_stake_addrs_with_email_event("drep_status_change"),
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
        choices=["all", "pool", "drep", "reminder"],
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

    logger.info("完了")


if __name__ == "__main__":
    main()
