"""plan_config.py
プラン (tier) の表示用メタデータを集中管理する (Phase 2)。

価格・機能配分・色テーマなどの **表示** に関わる設定を 1 箇所に集約。
tier ↔ 機能の論理は feature_gates.py 側にあるので、ここは UI 用の補助情報。

tier 名や価格を変える時はこの 1 ファイルだけ編集すればよい。
"""
from __future__ import annotations

from typing import TypedDict


class PlanDetails(TypedDict):
    tier: str               # feature_gates の tier 識別子と一致
    name_key: str           # i18n key (表示名)
    tagline_key: str        # i18n key (1 行キャッチ)
    price_jpy_monthly: int  # 月額 (円)
    price_usd_monthly: float
    price_jpy_yearly: int   # 年額 (円, 17% off 想定)
    price_usd_yearly: float
    color: str              # アクセントカラー (hex)
    popular: bool           # "おすすめ" バッジ表示
    # ハイライト機能。プラン比較カードの本文に箇条書きで出す i18n keys。
    feature_keys: tuple[str, ...]


# 価格は v0.7 の B 案 (¥330 / ¥880 / ¥1,580 / ¥2,980) を初期値に設定。
# 年額は月額 × 10 (= 2 ヶ月分割引、約 17% off)。USD は JPY ÷ 100 × 1.5 で .99 丸め。
PLANS: list[PlanDetails] = [
    {
        "tier":              "free",
        "name_key":          "plan_free_name",
        "tagline_key":       "plan_free_tagline",
        "price_jpy_monthly": 0,
        "price_usd_monthly": 0,
        "price_jpy_yearly":  0,
        "price_usd_yearly":  0,
        "color":             "#94a3b8",  # slate
        "popular":           False,
        "feature_keys":      (
            "plan_feat_view_governance",
            "plan_feat_notify_epoch",
            "plan_feat_notify_reward_member",
        ),
    },
    {
        "tier":              "light",
        "name_key":          "plan_light_name",
        "tagline_key":       "plan_light_tagline",
        "price_jpy_monthly": 330,
        "price_usd_monthly": 4.99,
        "price_jpy_yearly":  3300,    # 月額 × 10 (2 ヶ月分割引)
        "price_usd_yearly":  49.99,
        "color":             "#f59e0b",  # amber
        "popular":           False,
        "feature_keys":      (
            "plan_feat_notify_pool_retire",
            "plan_feat_notify_pool_fee",
            "plan_feat_notify_pool_perf",
            "plan_feat_addresses_3",
        ),
    },
    {
        "tier":              "standard",
        "name_key":          "plan_standard_name",
        "tagline_key":       "plan_standard_tagline",
        "price_jpy_monthly": 880,
        "price_usd_monthly": 12.99,
        "price_jpy_yearly":  8800,    # 月額 × 10
        "price_usd_yearly":  129.99,
        "color":             "#3b82f6",  # blue
        "popular":           True,        # おすすめバッジ
        "feature_keys":      (
            "plan_feat_notify_drep_vote",
            "plan_feat_notify_new_ga",
            "plan_feat_notify_treasury",
            "plan_feat_addresses_5",
        ),
    },
    {
        "tier":              "plus",
        "name_key":          "plan_plus_name",
        "tagline_key":       "plan_plus_tagline",
        "price_jpy_monthly": 1580,
        "price_usd_monthly": 23.99,
        "price_jpy_yearly":  15800,   # 月額 × 10
        "price_usd_yearly":  239.99,
        "color":             "#7c5cff",  # violet
        "popular":           False,
        "feature_keys":      (
            "plan_feat_csv_export",
            "plan_feat_drep_metadata",
            "plan_feat_addresses_10",
        ),
    },
    {
        "tier":              "pro",
        "name_key":          "plan_pro_name",
        "tagline_key":       "plan_pro_tagline",
        "price_jpy_monthly": 2980,
        "price_usd_monthly": 44.99,
        "price_jpy_yearly":  29800,   # 月額 × 10
        "price_usd_yearly":  449.99,
        "color":             "#0ea5e9",  # sky
        "popular":           False,
        "feature_keys":      (
            "plan_feat_notify_reward_leader",
            "plan_feat_notify_spo_pending",
            "plan_feat_addresses_unlimited",
        ),
    },
]


def get_plan(tier: str) -> PlanDetails | None:
    """tier 識別子からプラン情報を取得。"""
    for p in PLANS:
        if p["tier"] == tier:
            return p
    return None


# ベータ期間中フラグ。True の間は全プランで Standard 機能を解放しているメッセージを出す。
BETA_MODE = True


# ── 機能比較表 (/pricing 下部に表示) ────────────────────────────
# セクション (= カテゴリ) と各機能行を並べる。
# 各行: (label_i18n_key, [free, light, standard, plus, pro] のセル値)
# セル値は:
#   "check" → ✓ アイコン
#   "—"     → 利用不可 (グレー)
#   それ以外の文字列 → そのまま表示 (例: 数値、∞)
COMPARISON_SECTIONS: list[tuple[str, list[tuple[str, list[str]]]]] = [
    # 1. 基本機能 (全 tier 標準)
    ("plan_cat_basic", [
        ("plan_feat_view_governance",       ["check", "check", "check", "check", "check"]),
        ("plan_feat_view_catalyst",         ["check", "check", "check", "check", "check"]),
        ("plan_feat_delegate_pool",         ["check", "check", "check", "check", "check"]),
        ("plan_feat_delegate_drep",         ["check", "check", "check", "check", "check"]),
    ]),
    # 2. アドレス・お気に入り (数値で差別化)
    ("plan_cat_addresses", [
        ("plan_feat_stake_address_count",   ["1",     "3",     "5",     "10",    "∞"]),
        ("plan_feat_favorite_count",        ["5",     "∞",     "∞",     "∞",     "∞"]),
    ]),
    # 3. AI 要約 (Standard 以上)
    ("plan_cat_ai_summary", [
        ("plan_feat_ai_summary_governance", ["—",     "—",     "check", "check", "check"]),
        ("plan_feat_ai_summary_catalyst",   ["—",     "—",     "check", "check", "check"]),
    ]),
    # 3. 通知イベント (tier 別解放、実装済み 14 種)
    ("plan_cat_notify_events", [
        ("plan_feat_notify_epoch",          ["check", "check", "check", "check", "check"]),
        ("plan_feat_notify_reward_member",  ["check", "check", "check", "check", "check"]),
        ("plan_feat_notify_pool_retire",    ["—",     "check", "check", "check", "check"]),
        ("plan_feat_notify_pool_fee",       ["—",     "check", "check", "check", "check"]),
        ("plan_feat_notify_pool_perf",      ["—",     "check", "check", "check", "check"]),
        ("plan_feat_notify_pool_remind",    ["—",     "check", "check", "check", "check"]),
        ("plan_feat_notify_pool_saturation", ["—",    "—",     "check", "check", "check"]),
        ("plan_feat_notify_pool_pledge",    ["—",     "—",     "check", "check", "check"]),
        ("plan_feat_notify_new_ga",         ["—",     "—",     "check", "check", "check"]),
        ("plan_feat_notify_drep_vote",      ["—",     "—",     "check", "check", "check"]),
        ("plan_feat_notify_drep_status",    ["—",     "—",     "check", "check", "check"]),
        ("plan_feat_notify_drep_remind",    ["—",     "—",     "check", "check", "check"]),
        ("plan_feat_notify_treasury",       ["—",     "—",     "check", "check", "check"]),
        ("plan_feat_notify_reward_leader",  ["—",     "—",     "—",     "—",     "check"]),
        ("plan_feat_notify_spo_pending",    ["—",     "—",     "—",     "—",     "check"]),
        ("plan_feat_notify_unvoted",        ["—",     "—",     "—",     "check", "check"]),
    ]),
    # 4. レポート
    ("plan_cat_reports", [
        ("plan_feat_csv_export",            ["—",     "—",     "—",     "check", "check"]),
    ]),
    # 5. DRep ツール
    ("plan_cat_drep_tools", [
        ("plan_feat_drep_metadata",         ["—",     "—",     "—",     "check", "check"]),
    ]),
    # 6. 特典
    ("plan_cat_perks", [
        ("plan_feat_sjg_pro_membership",    ["—",     "—",     "—",     "—",     "check"]),
    ]),
]
