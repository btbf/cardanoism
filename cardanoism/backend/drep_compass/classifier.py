"""drep_compass.classifier
Governance Action の Cardanoism独自タグ分類 (AI 完全駆動)。

旧 rule-based 実装は撤去。OpenAI gpt-5.4-mini に直接分類させ、結果を
taxonomy.is_valid_tag() で検証してから DB 保存する。

入力:
  governance_actions row (proposal_id, proposal_type, title, abstract,
  title_ja, abstract_ja, motivation, rationale, withdrawal_total_lovelace)

出力:
  list[ClassifiedTag] = (tag, tag_type, confidence, rationale, source="ai")
  → gov_action_tags テーブルに INSERT
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from cardanoism.backend.ai_client import classify_proposal_tags as _ai_classify
from cardanoism.backend.drep_compass.taxonomy import (
    is_valid_tag,
    tag_type_of,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifiedTag:
    """1 件の分類結果。gov_action_tags へ INSERT する形に対応。"""
    tag: str
    tag_type: str  # "category" | "attribute" | "quality"
    confidence: float  # 0.0〜1.0
    rationale: str  # AI が出力した分類理由
    source: str = "ai"  # 全件 AI 起源


# AI 出力 1 件あたりの最大タグ数 (excessive な分類を防ぐ)
_MAX_TAGS_PER_GA = 8


def classify_governance_action(ga: dict[str, Any]) -> list[ClassifiedTag]:
    """1 GA を OpenAI で分類した結果を返す。

    Args:
      ga: governance_actions テーブルから取った dict
          (proposal_type, title, abstract, motivation, rationale,
           withdrawal_total_lovelace を含む)

    Returns:
      ClassifiedTag のリスト。
      - taxonomy.is_valid_tag() で検証し、未知タグは捨てる
      - 同じタグの重複は最高 confidence のものを採用
      - 全件 source="ai"
      - AI 呼び出しに失敗した場合は空リスト (呼び出し側で no-op になる)
    """
    if not ga:
        return []

    try:
        result = _ai_classify(ga)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "classify_governance_action: AI call failed for %s: %s",
            ga.get("proposal_id"), e,
        )
        return []

    logger.info(
        "classify_governance_action: AI %s → %d raw tags "
        "(tokens in=%d out=%d cost=$%.4f)",
        ga.get("proposal_id"),
        len(result.tags),
        result.tokens_input,
        result.tokens_output,
        result.cost_usd,
    )

    # taxonomy 検証 + 重複除去 (高 confidence 優先)
    by_tag: dict[str, tuple[float, str]] = {}
    for entry in result.tags:
        tag = str(entry.get("tag") or "").strip().lower()
        if not is_valid_tag(tag):
            logger.debug(
                "classify_governance_action: skip unknown tag %r from AI",
                tag,
            )
            continue
        try:
            conf = float(entry.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        rationale = str(entry.get("rationale") or "")[:1000]

        prev = by_tag.get(tag)
        if prev is None or conf > prev[0]:
            by_tag[tag] = (conf, rationale)

    out: list[ClassifiedTag] = []
    for tag, (conf, rationale) in by_tag.items():
        ttype = tag_type_of(tag)
        if ttype is None:
            continue
        out.append(ClassifiedTag(
            tag=tag,
            tag_type=ttype,
            confidence=conf,
            rationale=rationale,
            source="ai",
        ))

    # 上限を超えたら confidence 降順で絞る
    if len(out) > _MAX_TAGS_PER_GA:
        out.sort(key=lambda c: -c.confidence)
        out = out[:_MAX_TAGS_PER_GA]

    # AI から category が 1 つも返らなかった場合は "other" を補う
    if not any(c.tag_type == "category" for c in out):
        out.append(ClassifiedTag(
            tag="other",
            tag_type="category",
            confidence=0.3,
            rationale="AI returned no category tag (fallback)",
            source="ai",
        ))

    return out


def classify_governance_action_ai_stub(ga: dict[str, Any]) -> list[ClassifiedTag]:
    """後方互換のためにシグネチャだけ残す stub。常に空リスト。

    旧設計の rule + ai ハイブリッド構成の名残。現状は全件 classify_governance_action()
    が AI なので、このフォールバックは不要。
    """
    return []
