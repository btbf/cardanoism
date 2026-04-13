"""
notify_worker.py
通知バッチワーカー - cron で定期実行する独立スクリプト

推奨実行間隔:
  */60 * * * *  python notify_worker.py --event epoch_start
  */30 * * * *  python notify_worker.py --event pool
  */30 * * * *  python notify_worker.py --event drep

全イベント一括実行:
  python notify_worker.py
"""
import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.koios import (
    _post, _get, get_current_epoch,
    get_pool_delegation_date, get_drep_delegation_date,
    get_pool_apy, get_proposal_title,
)
from cardanoism.backend.line_notify import send_line_push, send_line_flex
from cardanoism.backend import line_flex

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("notify_worker")

CARDANOISM_URL = os.getenv("CARDANOISM_URL", "https://cardanoism.app")

POOL_EVENT_TYPES = [
    "pool_retire",
    "pool_fee_change",
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
    """指定イベントが有効でLINE IDを持つユーザー一覧。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT u.id, u.line_id, COALESCE(u.language, 'ja') AS language
            FROM users u
            JOIN notification_settings ns ON u.id = ns.user_id
            WHERE ns.event_type = ? AND ns.enabled = 1 AND u.line_id IS NOT NULL
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
                   u.id AS user_id, u.line_id, COALESCE(u.language, 'ja') AS language
            FROM stake_addresses sa
            JOIN users u ON sa.user_id = u.id
            JOIN stake_notification_settings sns ON sa.id = sns.stake_address_id
            WHERE sns.event_type = ? AND sns.enabled = 1 AND u.line_id IS NOT NULL
            """,
            (event_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# イベント: epoch_start
# ============================================================

def check_epoch_start():
    logger.info("epoch_start チェック開始")
    epoch = get_current_epoch()
    if epoch is None:
        logger.warning("epoch_start: エポック取得失敗")
        return

    epoch_str = str(epoch)
    last = get_state("global", None, "current_epoch")

    if last == epoch_str:
        logger.info("epoch_start: 変化なし (epoch %s)", epoch)
        return

    logger.info("epoch_start: 新エポック %s (前回: %s)", epoch, last)
    set_state("global", None, "current_epoch", epoch_str)

    if last is None:
        logger.info("epoch_start: 初回起動のため送信スキップ")
        return

    users = get_users_with_event("epoch_start")
    logger.info("epoch_start: %d ユーザーに送信", len(users))
    for user in users:
        dedup_key = f"epoch_{epoch}"
        if already_sent(user["id"], "epoch_start", dedup_key):
            continue
        lang = user.get("language", "ja")
        alt_text = f"【Cardanoism】新しいエポック（Epoch {epoch}）が始まりました" if lang == "ja" else f"[Cardanoism] New epoch started (Epoch {epoch})"
        contents = line_flex.epoch_start(epoch, CARDANOISM_URL, lang=lang)
        flex_and_log(user["line_id"], user["id"], "epoch_start", dedup_key, alt_text, contents)


# ============================================================
# イベント: プール系
# ============================================================

def _fetch_pool_info(pool_id: str) -> dict | None:
    data = _post("/pool_info", {"_pool_bech32_ids": [pool_id]})
    if not data or not isinstance(data, list) or not data[0]:
        return None
    return data[0]


def check_pool_events():
    logger.info("プールイベント チェック開始")

    # 全プールイベントに対して有効なアドレスを収集
    all_addrs: dict[int, dict] = {}
    enabled_events: dict[int, set] = {}
    for event_type in POOL_EVENT_TYPES:
        for addr in get_stake_addrs_with_event(event_type):
            sid = addr["stake_id"]
            all_addrs[sid] = addr
            enabled_events.setdefault(sid, set()).add(event_type)

    # pool_id ごとに pool_info と APY を一括取得
    pool_ids = {a["delegated_pool_id"] for a in all_addrs.values() if a.get("delegated_pool_id")}
    pool_infos: dict[str, dict] = {}
    pool_apys: dict[str, float | None] = {}
    for pool_id in pool_ids:
        info = _fetch_pool_info(pool_id)
        if info:
            pool_infos[pool_id] = info
        pool_apys[pool_id] = get_pool_apy(pool_id)

    # 各アドレスのイベントをチェック
    for stake_id, addr in all_addrs.items():
        pool_id = addr.get("delegated_pool_id")
        if not pool_id or pool_id not in pool_infos:
            continue
        pool_info = pool_infos[pool_id]
        apy = pool_apys.get(pool_id)
        for event_type in enabled_events[stake_id]:
            _check_pool_event(event_type, addr, pool_info, apy)


def _apy_line(apy: float | None) -> str:
    """APY行を返す。取得できない場合は空文字。"""
    if apy is None:
        return ""
    return f"\nAPY: {apy:.2f}%"


def _check_pool_event(event_type: str, addr: dict, pool_info: dict, apy: float | None = None):
    stake_id = addr["stake_id"]
    user_id = addr["user_id"]
    line_id = addr["line_id"]
    lang = addr.get("language", "ja")
    pool_name = addr.get("delegated_pool_name") or (addr.get("delegated_pool_id") or "")[:12]
    nickname = addr["nickname"]

    if event_type == "pool_retire":
        retiring_epoch = pool_info.get("retiring_epoch")
        if not retiring_epoch:
            return
        dedup_key = f"pool_retire_{stake_id}_{retiring_epoch}"
        if already_sent(user_id, event_type, dedup_key):
            return
        alt_text = f"【Cardanoism】委任先プール「{pool_name}」が Epoch {retiring_epoch} にリタイアします" if lang == "ja" else f"[Cardanoism] Pool '{pool_name}' will retire at Epoch {retiring_epoch}"
        contents = line_flex.pool_retire(pool_name, retiring_epoch, nickname, CARDANOISM_URL, lang=lang)
        flex_and_log(line_id, user_id, event_type, dedup_key, alt_text, contents)

    elif event_type == "pool_fee_change":
        margin = str(pool_info.get("margin") or "")
        fixed = str(pool_info.get("fixed_cost") or "")
        current_val = f"{margin}:{fixed}"
        stored = get_state("stake_address", stake_id, "pool_fee")
        if stored is None:
            set_state("stake_address", stake_id, "pool_fee", current_val)
            return
        if stored == current_val:
            return
        set_state("stake_address", stake_id, "pool_fee", current_val)
        dedup_key = f"pool_fee_change_{stake_id}_{current_val}"
        if already_sent(user_id, event_type, dedup_key):
            return
        old_margin, old_fixed = stored.split(":", 1)
        margin_pct = float(margin) * 100 if margin else 0
        old_margin_pct = float(old_margin) * 100 if old_margin else 0
        fixed_ada = int(fixed) / 1_000_000 if fixed else 0
        old_fixed_ada = int(old_fixed) / 1_000_000 if old_fixed else 0
        alt_text = f"【Cardanoism】委任先プール「{pool_name}」の手数料が変更されました" if lang == "ja" else f"[Cardanoism] Pool '{pool_name}' fee has changed"
        contents = line_flex.pool_fee_change(
            pool_name=pool_name,
            old_margin_pct=old_margin_pct,
            new_margin_pct=margin_pct,
            old_fixed_ada=old_fixed_ada,
            new_fixed_ada=fixed_ada,
            apy=apy,
            nickname=nickname,
            url=CARDANOISM_URL,
            lang=lang,
        )
        ok = send_line_flex(line_id, alt_text, contents)
        if ok:
            log_sent(user_id, event_type, dedup_key, "line", alt_text)

    elif event_type == "pool_saturation":
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
        elif not is_short and was_short == "1":
            set_state("stake_address", stake_id, "pool_pledge_short", "0")

    elif event_type == "pool_reward_received":
        _check_pool_reward_received(addr)


def _check_pool_reward_received(addr: dict):
    """
    報酬入金通知。
    Cardanoでは Epoch N のスナップショット → Epoch N+2 で報酬が確定・入金される。
    現在エポック-2 を対象に /account_reward_history で取得する。
    """
    stake_id = addr["stake_id"]
    user_id = addr["user_id"]
    line_id = addr["line_id"]
    lang = addr.get("language", "ja")
    pool_name = addr.get("delegated_pool_name") or (addr.get("delegated_pool_id") or "")[:12]
    nickname = addr["nickname"]

    current_epoch = get_current_epoch()
    if current_epoch is None:
        return
    reward_epoch = current_epoch - 2  # 報酬が確定するエポック

    dedup_key = f"reward_{stake_id}_{reward_epoch}"
    if already_sent(user_id, "pool_reward_received", dedup_key):
        return

    data = _post(
        "/account_reward_history",
        {"_stake_addresses": [addr["address"]], "_epoch_no": reward_epoch},
    )
    # レスポンスはフラットな配列: [{"stake_address":..., "earned_epoch":..., "amount":"...", ...}]
    if not data or not isinstance(data, list):
        return

    amount_ada = sum(int(r.get("amount", 0)) for r in data) / 1_000_000
    if amount_ada <= 0:
        return

    apy = get_pool_apy(addr.get("delegated_pool_id") or "", reward_epoch)
    alt_text = f"【Cardanoism】Epoch {reward_epoch} 分の報酬が入金されました" if lang == "ja" else f"[Cardanoism] Rewards for Epoch {reward_epoch} have arrived"
    contents = line_flex.pool_reward_received(reward_epoch, amount_ada, apy, nickname, CARDANOISM_URL, lang=lang)
    flex_and_log(line_id, user_id, "pool_reward_received", dedup_key, alt_text, contents)


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


def _get_delegation_days(stake_id: int, address: str, cache_key: str, fetch_fn) -> int | None:
    """
    委任基準日をキャッシュから取得するか API で取得してキャッシュに保存する。
    戻り値: 委任からの経過日数（取得できない場合 None）
    """
    from datetime import datetime, timezone
    cached = get_state("stake_address", stake_id, cache_key)
    if cached:
        try:
            dt = datetime.fromisoformat(cached).replace(tzinfo=timezone.utc)
            return _days_since_dt(dt)
        except ValueError:
            pass

    dt = fetch_fn()
    if dt is None:
        return None
    set_state("stake_address", stake_id, cache_key, dt.isoformat())
    return _days_since_dt(dt)


def _check_pool_delegation_reminder():
    for addr in get_stake_addrs_with_event("pool_delegation_reminder"):
        pool_id = addr.get("delegated_pool_id")
        if not pool_id:
            continue

        days = _get_delegation_days(
            addr["stake_id"],
            addr["address"],
            "pool_delegation_date",
            lambda: get_pool_delegation_date(addr["address"], pool_id),
        )
        if days is None:
            continue

        pool_name = addr.get("delegated_pool_name") or pool_id[:12]
        apy = get_pool_apy(pool_id)
        lang = addr.get("language", "ja")
        for milestone in REMINDER_MILESTONES:
            if days < milestone:
                continue
            dedup_key = f"pool_remind_{addr['stake_id']}_{milestone}d"
            if already_sent(addr["user_id"], "pool_delegation_reminder", dedup_key):
                continue
            alt_text = f"【Cardanoism】委任から{milestone}日が経過しました。委任先プールを確認しましょう" if lang == "ja" else f"[Cardanoism] {milestone} days since delegation. Please check your pool."
            contents = line_flex.pool_delegation_reminder(pool_name, milestone, apy, addr["nickname"], CARDANOISM_URL, lang=lang)
            flex_and_log(addr["line_id"], addr["user_id"], "pool_delegation_reminder", dedup_key, alt_text, contents)


def _check_drep_delegation_reminder():
    for addr in get_stake_addrs_with_event("drep_delegation_reminder"):
        drep_id = addr.get("delegated_drep_id")
        if not drep_id:
            continue

        days = _get_delegation_days(
            addr["stake_id"],
            addr["address"],
            "drep_delegation_date",
            lambda: get_drep_delegation_date(addr["address"], drep_id),
        )
        if days is None:
            continue

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
            flex_and_log(addr["line_id"], addr["user_id"], "drep_delegation_reminder", dedup_key, alt_text, contents)


def check_drep_events():
    logger.info("DRepイベント チェック開始")
    _check_drep_new_governance_action()
    _check_drep_vote()
    _check_drep_status_change()


def _check_drep_new_governance_action():
    data = _post("/proposal_list", {})
    if not data or not isinstance(data, list) or not data:
        return

    latest = data[0]
    latest_key = latest.get("proposal_tx_hash") or latest.get("tx_hash") or ""
    if not latest_key:
        return

    last_key = get_state("global", None, "latest_proposal_tx")
    if last_key == latest_key:
        return

    set_state("global", None, "latest_proposal_tx", latest_key)
    if last_key is None:
        return  # 初回

    proposal_type = latest.get("proposal_type") or "ガバナンスアクション"

    for addr in get_stake_addrs_with_event("drep_new_governance_action"):
        user_id = addr["user_id"]
        line_id = addr["line_id"]
        lang = addr.get("language", "ja")
        dedup_key = f"new_gov_{latest_key}_{addr['stake_id']}"
        if already_sent(user_id, "drep_new_governance_action", dedup_key):
            continue
        alt_text = f"【Cardanoism】新しいガバナンスアクションが提出されました: {proposal_type}" if lang == "ja" else f"[Cardanoism] New governance action submitted: {proposal_type}"
        contents = line_flex.drep_new_governance_action(proposal_type, f"{CARDANOISM_URL}/governance", lang=lang)
        flex_and_log(line_id, user_id, "drep_new_governance_action", dedup_key, alt_text, contents)


def _check_drep_vote():
    for addr in get_stake_addrs_with_event("drep_vote"):
        drep_id = addr.get("delegated_drep_id")
        if not drep_id:
            continue
        stake_id = addr["stake_id"]
        user_id = addr["user_id"]
        line_id = addr["line_id"]
        lang = addr.get("language", "ja")
        drep_name = addr.get("delegated_drep_name") or drep_id[:12]

        data = _post("/drep_votes", {"_drep_id": drep_id})
        if not data or not isinstance(data, list):
            continue

        latest = data[0]
        vote_tx = latest.get("tx_hash") or ""
        if not vote_tx:
            continue

        last_tx = get_state("stake_address", stake_id, "last_drep_vote_tx")
        if last_tx == vote_tx:
            continue

        set_state("stake_address", stake_id, "last_drep_vote_tx", vote_tx)
        if last_tx is None:
            continue  # 初回

        dedup_key = f"drep_vote_{stake_id}_{vote_tx}"
        if already_sent(user_id, "drep_vote", dedup_key):
            continue

        vote = (latest.get("vote") or "").lower()
        proposal_tx_hash = latest.get("proposal_tx_hash") or ""
        proposal_index = latest.get("proposal_index") or 0
        proposal_title = get_proposal_title(proposal_tx_hash, proposal_index) if proposal_tx_hash else None
        vote_label_ja = {"yes": "賛成", "no": "反対", "abstain": "棄権"}.get(vote, vote)
        vote_label_en = {"yes": "Yes", "no": "No", "abstain": "Abstain"}.get(vote, vote)
        alt_text = f"【Cardanoism】委任先DRep「{drep_name}」が投票しました（{vote_label_ja}）" if lang == "ja" else f"[Cardanoism] Delegated DRep '{drep_name}' voted ({vote_label_en})"
        contents = line_flex.drep_vote(drep_name, vote, proposal_title, addr["nickname"], f"{CARDANOISM_URL}/governance", lang=lang)
        flex_and_log(line_id, user_id, "drep_vote", dedup_key, alt_text, contents)


def _check_drep_status_change():
    for addr in get_stake_addrs_with_event("drep_status_change"):
        drep_id = addr.get("delegated_drep_id")
        if not drep_id:
            continue
        stake_id = addr["stake_id"]
        user_id = addr["user_id"]
        line_id = addr["line_id"]
        lang = addr.get("language", "ja")
        drep_name = addr.get("delegated_drep_name") or drep_id[:12]

        data = _post("/drep_info", {"_drep_ids": [drep_id]})
        if not data or not isinstance(data, list) or not data[0]:
            continue

        status = data[0].get("status") or ""
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


# ============================================================
# テスト送信
# ============================================================

def list_users():
    """LINE ID が設定されているユーザー一覧を表示する。"""
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT id, username, email, line_id FROM users WHERE line_id IS NOT NULL ORDER BY id"
        )
        rows = cursor.fetchall()
    if not rows:
        print("LINE ID が設定されているユーザーはいません")
        return
    print(f"{'ID':>4}  {'ユーザー名':<20}  {'メール':<30}  LINE ID")
    print("-" * 80)
    for row in rows:
        line_id_masked = row["line_id"][:6] + "..." if row["line_id"] else "-"
        print(f"{row['id']:>4}  {(row['username'] or ''):<20}  {(row['email'] or ''):<30}  {line_id_masked}")


def _get_user_info(user_id: int) -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute("SELECT line_id, COALESCE(language, 'ja') AS language FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def _get_line_id_for_user(user_id: int) -> str | None:
    info = _get_user_info(user_id)
    return info["line_id"] if info else None


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
    if not user_info or not user_info.get("line_id"):
        logger.error("ユーザー %d が見つからないか LINE ID が未設定です", user_id)
        return
    line_id = user_info["line_id"]
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
    drep_events = {"drep_new_governance_action", "drep_vote", "drep_status_change", "drep_delegation_reminder"}
    pool_events = {"pool_retire", "pool_fee_change", "pool_saturation", "pool_pledge_shortage",
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
    "pool_retire",
    "pool_fee_change",
    "pool_saturation",
    "pool_pledge_shortage",
    "pool_reward_received",
    "pool_delegation_reminder",
    "drep_new_governance_action",
    "drep_vote",
    "drep_status_change",
    "drep_delegation_reminder",
]


def _build_dummy_flex(ev: str) -> tuple[str, dict] | None:
    """ダミーデータで (alt_text, contents) を返す。不明なイベントは None。"""
    d = _DUMMY
    lang = d.get("_lang", "ja")
    ja = lang == "ja"
    if ev == "epoch_start":
        return (
            f"【Cardanoism】新しいエポック（Epoch {d['epoch']}）が始まりました" if ja else f"[Cardanoism] New epoch started (Epoch {d['epoch']})",
            line_flex.epoch_start(d["epoch"], CARDANOISM_URL, lang=lang),
        )
    if ev == "pool_retire":
        return (
            f"【Cardanoism】委任先プール「{d['pool_name']}」が Epoch {d['epoch'] + 10} にリタイアします" if ja else f"[Cardanoism] Pool '{d['pool_name']}' will retire at Epoch {d['epoch'] + 10}",
            line_flex.pool_retire(d["pool_name"], d["epoch"] + 10, d["nickname"], CARDANOISM_URL, lang=lang),
        )
    if ev == "pool_fee_change":
        return (
            f"【Cardanoism】委任先プール「{d['pool_name']}」の手数料が変更されました" if ja else f"[Cardanoism] Pool '{d['pool_name']}' fee has changed",
            line_flex.pool_fee_change(d["pool_name"], 1.0, 2.0, 340, 400, d["apy"], d["nickname"], CARDANOISM_URL, lang=lang),
        )
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
    if ev == "drep_new_governance_action":
        return (
            "【Cardanoism】新しいガバナンスアクションが提出されました: TreasuryWithdrawals" if ja else "[Cardanoism] New governance action submitted: TreasuryWithdrawals",
            line_flex.drep_new_governance_action("TreasuryWithdrawals", f"{CARDANOISM_URL}/governance", lang=lang),
        )
    if ev == "drep_vote":
        return (
            f"【Cardanoism】委任先DRep「{d['drep_name']}」が投票しました（賛成）" if ja else f"[Cardanoism] Delegated DRep '{d['drep_name']}' voted (Yes)",
            line_flex.drep_vote(d["drep_name"], "yes", "Treasury Withdrawal Test", d["nickname"], f"{CARDANOISM_URL}/governance", lang=lang),
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
    if not user_info or not user_info.get("line_id"):
        logger.error("ユーザー %d が見つからないか LINE ID が未設定です", user_id)
        return
    line_id = user_info["line_id"]
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
        choices=["all", "epoch_start", "pool", "drep", "reminder"],
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
    args = parser.parse_args()

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

    if args.event in ("all", "epoch_start"):
        check_epoch_start()
    if args.event in ("all", "pool"):
        check_pool_events()
    if args.event in ("all", "drep"):
        check_drep_events()
    if args.event in ("all", "reminder"):
        check_delegation_reminders()

    logger.info("完了")


if __name__ == "__main__":
    main()
