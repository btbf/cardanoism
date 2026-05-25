"""drep_compass.taxonomy
Cardanoism独自タグの taxonomy 定義。

spec 第 2 節「タグ体系」と完全一致させる。3 系統 (category / attribute / quality)。
価値判断を含むタグ名は禁止 (bad_proposal / wasteful / centralized_bad など)。

公開 API:
  - is_valid_tag(tag) -> bool
  - tag_type_of(tag) -> "category" | "attribute" | "quality" | None
  - all_tags() -> set[str]
  - CATEGORY_TAGS / ATTRIBUTE_TAGS / QUALITY_TAGS (frozenset)
"""
from __future__ import annotations

# ── category : GA が何を扱うか ──────────────────────────────
CATEGORY_TAGS: frozenset[str] = frozenset({
    "treasury",
    "protocol",
    "governance",
    "constitution",
    "core_development",
    "infrastructure",
    "ecosystem",
    "marketing",
    "community",
    "education",
    "event",
    "dapp",
    "wallet",
    "defi",
    "other",
})

# ── attribute : GA の性質 (規模・対象・主体・領域) ─────────
ATTRIBUTE_TAGS: frozenset[str] = frozenset({
    "large_budget",
    "recurring_budget",
    "operational_budget",
    "existing_entity",
    "new_team",
    "individual_contributor",
    "regional_focus",
    "global_focus",
    "open_source",
    "closed_source",
    "public_goods",
    "commercial_product",
    "developer_experience",
    "user_adoption",
    "awareness",
    "long_term_research",
    "security_related",
    "parameter_change",
    "hard_fork",
    "urgent",
    "high_risk",
})

# ── quality : GA の品質 (KPI / マイルストーン / 透明性 / 説明責任) ─
QUALITY_TAGS: frozenset[str] = frozenset({
    "kpi_defined",
    "kpi_unclear",
    "milestone_based",
    "milestone_unclear",
    "budget_reasonable",
    "budget_unclear",
    "budget_excessive",
    "track_record_strong",
    "track_record_unknown",
    "transparency_high",
    "transparency_low",
    "accountability_defined",
    "accountability_unclear",
    "conflict_of_interest_possible",
})

# 全タグ
_ALL: frozenset[str] = CATEGORY_TAGS | ATTRIBUTE_TAGS | QUALITY_TAGS

_TYPE_OF: dict[str, str] = {}
for _t in CATEGORY_TAGS:
    _TYPE_OF[_t] = "category"
for _t in ATTRIBUTE_TAGS:
    _TYPE_OF[_t] = "attribute"
for _t in QUALITY_TAGS:
    _TYPE_OF[_t] = "quality"


def all_tags() -> frozenset[str]:
    """全タグ (category + attribute + quality)。"""
    return _ALL


def is_valid_tag(tag: str) -> bool:
    """taxonomy 定義済みのタグキーか?"""
    return tag in _ALL


def tag_type_of(tag: str) -> str | None:
    """タグの type を返す。未知タグなら None。"""
    return _TYPE_OF.get(tag)


# ── DRep プロファイル 11 axis 定義 ───────────────────────────
# spec 第 1 節「drep_profiles / profile_json axes」と完全一致。
AXES: tuple[str, ...] = (
    "treasury_discipline",
    "growth_investment",
    "technical_foundation",
    "ecosystem_expansion",
    "institutional_continuity",
    "decentralized_allocation",
    "marketing_support",
    "protocol_conservatism",
    "protocol_innovation",
    "transparency_focus",
    "reasoning_disclosure",
)
AXES_SET: frozenset[str] = frozenset(AXES)


def is_valid_axis(axis: str) -> bool:
    return axis in AXES_SET


# ── UI 表示用: 対立軸 + 独立軸 ──────────────────────────────
# 4 つの対立軸ペア (左右に振れる中央バーで表現)
# (key, pos_axis, neg_axis)
#   pos_axis = 右側 (+) 寄りに表示される axis
#   neg_axis = 左側 (-) 寄りに表示される axis
# ※ 表記の慣習に合わせて、より「慎重 / 保守的」な側を pos に置く
BALANCE_AXES: tuple[tuple[str, str, str], ...] = (
    ("treasury",  "treasury_discipline",      "growth_investment"),
    ("ecosystem", "technical_foundation",     "ecosystem_expansion"),
    ("org",       "institutional_continuity", "decentralized_allocation"),
    ("protocol",  "protocol_conservatism",    "protocol_innovation"),
)

# 単独軸 (0〜100% の単純なバーで表現)
SINGLE_AXES: tuple[str, ...] = (
    "marketing_support",
    "transparency_focus",
    "reasoning_disclosure",
)

# 対立軸を構成する全 axis (matched/mismatched 表示時の重複検出に使う)
BALANCE_AXIS_MEMBERS: frozenset[str] = frozenset(
    a for _, pos, neg in BALANCE_AXES for a in (pos, neg)
)

# 対立軸 key から (pos_axis, neg_axis) を取るマップ
BALANCE_BY_KEY: dict[str, tuple[str, str]] = {
    key: (pos, neg) for key, pos, neg in BALANCE_AXES
}

# axis 名 → どの対立軸 key に属するか (None なら単独軸)
AXIS_TO_BALANCE_KEY: dict[str, str] = {
    pos: key for key, pos, _ in BALANCE_AXES
}
AXIS_TO_BALANCE_KEY.update({
    neg: key for key, _, neg in BALANCE_AXES
})
