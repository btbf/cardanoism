"""drep_compass.classifier (廃止)

旧設計の GA タグ付け (rule-based + AI) は新設計で不要になった。
DRep プロファイルは AI が rationale を直接読んで生成する形に統一されたため、
gov_action_tags テーブルへの書き込み処理は撤廃した。

後方互換のため空のシンボルを残しているが、新コードは何も import しないこと。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassifiedTag:
    """旧 API 互換用の空 stub。新設計では使われない。"""
    tag: str
    tag_type: str
    confidence: float
    rationale: str
    source: str = "ai"


def classify_governance_action(ga):  # type: ignore[no-untyped-def]
    """新設計では no-op。常に空リスト。"""
    return []


def classify_governance_action_rule_fallback(ga):  # type: ignore[no-untyped-def]
    return []
