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
