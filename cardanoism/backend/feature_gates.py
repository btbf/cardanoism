"""feature_gates.py
機能 ↔ tier マッピングの単一ソース (Phase 0)。

設計方針:
  - tier 名は文字列。新 tier を増やす時は TIER_RANK に追加するだけ。
  - 機能は文字列キー (FeatureKey) で識別。配分変更は FEATURE_TIERS の編集だけ。
  - 上位 tier は下位 tier の機能をすべて使える (ranking ベースの判定)。
  - tier 名が未確定なベータ期間でも機能ゲートのコードは固まる。

使い方:
    from cardanoism.backend.feature_gates import can_use

    if can_use(user_id, "csv_export"):
        ...

ゲート無効 (= 全員許可) の機能は単に FEATURE_TIERS に登録しなければよい。
"""
from __future__ import annotations

import logging
from typing import Iterable

from cardanoism.backend.subscription_db import get_user_tier

logger = logging.getLogger(__name__)


# ── tier ランキング ─────────────────────────────────────────────────
# 数字が大きいほど上位 tier。同 rank 同士の比較は = で True を返す。
# tier 名が固まったら値だけ調整すれば良い。
TIER_RANK: dict[str, int] = {
    "free":     0,
    "light":    1,
    "standard": 2,
    "plus":     3,
    "pro":      4,
}


def tier_rank(tier: str) -> int:
    """tier 名 → ランク。未知の tier は 0 (= free 相当) として安全側に倒す。"""
    return TIER_RANK.get((tier or "").lower(), 0)


def tier_at_least(user_tier: str, required_tier: str) -> bool:
    """user_tier が required_tier 以上か判定 (上位 tier は下位機能を使える)。"""
    return tier_rank(user_tier) >= tier_rank(required_tier)


# ── 機能 ↔ 必要 tier マッピング ────────────────────────────────────
# キー: 機能識別子 (任意の文字列だが命名規則は snake_case 推奨)
# 値:   その機能を使うのに必要な最低 tier
#
# ここに登録されていない機能は「ゲートなし (全員許可)」扱い。
# tier 配分が変わった時はこの dict を編集するだけで済むようにする。
FEATURE_TIERS: dict[str, str] = {
    # ── 基本機能 (全 tier 標準装備) ──
    "view_governance":           "free",
    "view_catalyst":             "free",
    "delegate_pool":             "free",
    "delegate_drep":             "free",
    "ga_vote_matrix":            "free",

    # ── 通知チャンネル (全 tier 標準装備) ──
    "notify_email":              "free",
    "notify_line":               "free",
    "notify_telegram":           "free",

    # ── 通知イベント: Free ──
    "notify_epoch_start":             "free",   # epoch_start
    "notify_pool_reward_member":      "free",   # pool_reward_received (member)

    # ── 通知イベント: Light ──
    "notify_pool_retire":             "light",  # pool_retire
    "notify_pool_fee_change":         "light",  # pool_fee_change
    "notify_pool_epoch_performance":  "light",  # pool_epoch_performance
    "notify_pool_delegation_reminder": "light", # pool_delegation_reminder

    # ── 通知イベント: Standard ──
    "notify_pool_saturation":         "standard",  # pool_saturation
    "notify_pool_pledge_shortage":    "standard",  # pool_pledge_shortage
    "notify_drep_new_governance_action": "standard",  # drep_new_governance_action
    "notify_drep_vote":               "standard",  # drep_vote
    "notify_drep_status_change":      "standard",  # drep_status_change
    "notify_drep_delegation_reminder": "standard",  # drep_delegation_reminder
    "notify_treasury_withdrawal":     "standard",  # treasury_withdrawal_enacted

    # ── 通知イベント: Pro (SPO 専用 + DRep 高度通知) ──
    "notify_pool_reward_leader":      "pro",    # pool_reward_received (leader)
    "notify_spo_pending_vote":        "pro",    # spo_pending_vote
    "notify_unvoted_reminder":        "plus",   # 未投票 GA リマインダー (Plus / Pro = DRep 委任者・SPO 向け、近日実装)

    # ── ステークアドレス上限 ──
    "stake_addresses_1":         "free",
    "stake_addresses_3":         "light",
    "stake_addresses_5":         "standard",
    "stake_addresses_10":        "plus",
    "stake_addresses_unlimited": "pro",

    # ── お気に入り ──
    "favorites_5":               "free",
    "favorites_unlimited":       "light",

    # ── 報酬 / レポート ──
    "csv_export_rewards":        "plus",

    # ── ガバナンス AI ──
    "ga_ai_summary":             "standard",   # GA AI まとめ

    # ── DRep ツール ──
    "drep_metadata_manager":     "plus",
}


def can_use(user_id: int, feature_key: str) -> bool:
    """ユーザーが指定機能を使えるか判定する。

    - feature_key が FEATURE_TIERS に無い → ゲートなし → True
    - DB エラー等で tier 取得失敗 → 安全側で False
    """
    required = FEATURE_TIERS.get(feature_key)
    if required is None:
        # ゲート未登録の機能は全員に許可 (まだサブスク化されていない)
        return True
    try:
        user_tier = get_user_tier(int(user_id)) if user_id else "free"
    except Exception as e:
        logger.warning("can_use: get_user_tier failed user=%s feature=%s: %s",
                       user_id, feature_key, e)
        return False
    return tier_at_least(user_tier, required)


def required_tier_for(feature_key: str) -> str | None:
    """機能を使うのに必要な tier 名を返す。ゲート無しなら None。"""
    return FEATURE_TIERS.get(feature_key)


def all_features_for_tier(tier: str) -> list[str]:
    """指定 tier (とそれ以下) で使えるすべての機能キーを返す。

    プラン比較ページなどで「このプランで使える機能」を列挙する用途。
    """
    user_rank = tier_rank(tier)
    return sorted(
        key for key, req in FEATURE_TIERS.items()
        if tier_rank(req) <= user_rank
    )


def feature_diff(higher_tier: str, lower_tier: str) -> list[str]:
    """higher_tier で使えて lower_tier では使えない機能の差分を返す。

    アップグレードの訴求文言生成等に使う。
    """
    higher = set(all_features_for_tier(higher_tier))
    lower = set(all_features_for_tier(lower_tier))
    return sorted(higher - lower)


__all__: Iterable[str] = (
    "TIER_RANK",
    "FEATURE_TIERS",
    "tier_rank",
    "tier_at_least",
    "can_use",
    "required_tier_for",
    "all_features_for_tier",
    "feature_diff",
)
