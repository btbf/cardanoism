"""通知の鮮度判定。

チェーンや外部 API の同期が遅れても、DB は最後まで追いつかせる。一方で通知は
「本来届くべき時刻」から一定時間を過ぎたら送らない。この判定を listener と
polling worker で共有する。
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone


def _positive_env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# Shelley 以降の対応ネットワークは 1 slot = 1 second。
REALTIME_MAX_LAG_SLOTS = _positive_env_int(
    "NOTIFICATION_REALTIME_MAX_LAG_SLOTS",
    30 * 60,
)
EPOCH_MAX_LAG_SLOTS = _positive_env_int(
    "NOTIFICATION_EPOCH_MAX_LAG_SLOTS",
    2 * 60 * 60,
)
REWARD_WINDOW_SECONDS = _positive_env_int(
    "NOTIFICATION_REWARD_WINDOW_SECONDS",
    12 * 60 * 60,
)
TREASURY_WINDOW_SECONDS = _positive_env_int(
    "NOTIFICATION_TREASURY_WINDOW_SECONDS",
    12 * 60 * 60,
)
STATE_RECOVERY_GAP_SECONDS = _positive_env_int(
    "NOTIFICATION_STATE_RECOVERY_GAP_SECONDS",
    30 * 60,
)


def is_chain_event_fresh(
    event_slot: int | str | None,
    tip_slot: int | str | None,
    *,
    max_lag_slots: int = REALTIME_MAX_LAG_SLOTS,
) -> bool:
    """event が chain tip から許容slot以内なら True。

    tip が不明な場合は古いイベントを誤送信しないよう fail closed にする。
    tip よりeventが先に見える場合は、tip情報の僅かな遅延として lag=0 扱いにする。
    """
    try:
        event = int(event_slot)  # type: ignore[arg-type]
        tip = int(tip_slot)  # type: ignore[arg-type]
        limit = int(max_lag_slots)
    except (TypeError, ValueError):
        return False
    if event < 0 or tip < 0 or limit < 0:
        return False
    return max(0, tip - event) <= limit


def chain_notification_deadline(
    event_slot: int | str | None,
    tip_slot: int | str | None,
    *,
    max_lag_slots: int = REALTIME_MAX_LAG_SLOTS,
    now_monotonic: float | None = None,
) -> float | None:
    """現在のchain lagを差し引いた配送期限をmonotonic時刻で返す。

    catch-upですでに期限切れ、またはslotを検証できない場合はNone。Cardanoの
    Shelley以降では1 slot = 1秒なので、残りslot数をそのまま残り秒数に使う。
    """
    try:
        event = int(event_slot)  # type: ignore[arg-type]
        tip = int(tip_slot)  # type: ignore[arg-type]
        limit = int(max_lag_slots)
    except (TypeError, ValueError):
        return None
    if event < 0 or tip < 0 or limit < 0:
        return None
    remaining_seconds = limit - max(0, tip - event)
    if remaining_seconds < 0:
        return None
    current = time.monotonic() if now_monotonic is None else float(now_monotonic)
    return current + remaining_seconds


def is_delivery_deadline_open(
    notifications_enabled: bool,
    deadline_monotonic: float | None,
    *,
    now_monotonic: float | None = None,
) -> bool:
    """配送元の鮮度判定と、非同期処理後の期限をまとめて確認する。

    deadline=Noneは既存の直接呼び出しとの互換用に、notifications_enabled=Trueなら
    期限指定なしとして扱う。本番listenerは常に具体的なdeadlineを渡す。
    """
    if not notifications_enabled:
        return False
    if deadline_monotonic is None:
        return True
    current = time.monotonic() if now_monotonic is None else float(now_monotonic)
    return current <= float(deadline_monotonic)


def is_epoch_window_open(
    epoch_slot: int | str | None,
    *,
    window_seconds: int,
) -> bool:
    """現在epoch開始からの経過秒数が通知window内なら True。"""
    try:
        elapsed = int(epoch_slot)  # type: ignore[arg-type]
        limit = int(window_seconds)
    except (TypeError, ValueError):
        return False
    return elapsed >= 0 and limit >= 0 and elapsed <= limit


def is_current_epoch_event_fresh(
    event_epoch: int | str | None,
    current_epoch: int | str | None,
    current_epoch_slot: int | str | None,
    *,
    window_seconds: int,
) -> bool:
    """eventが現在epochのもので、かつepoch開始後のwindow内なら True。"""
    try:
        if int(event_epoch) != int(current_epoch):  # type: ignore[arg-type]
            return False
    except (TypeError, ValueError):
        return False
    return is_epoch_window_open(
        current_epoch_slot,
        window_seconds=window_seconds,
    )


def utc_now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def should_rebaseline_state(
    last_success_at: str | None,
    *,
    now: datetime | None = None,
    max_gap_seconds: int = STATE_RECOVERY_GAP_SECONDS,
) -> bool:
    """初回または長時間停止後なら、状態通知を送らずbaseline化する。"""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    previous = _parse_utc(last_success_at)
    if previous is None:
        return True
    gap = (current - previous).total_seconds()
    # 時計が大きく逆行した状態も比較基準として信用しない。
    if gap < -60:
        return True
    return gap > int(max_gap_seconds)
