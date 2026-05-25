"""AI-first Governance Action tagging for the DRep compass."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from cardanoism.backend.ai_client import classify_proposal_tags as _ai_classify
from cardanoism.backend.drep_compass import config
from cardanoism.backend.drep_compass.taxonomy import is_valid_tag, tag_type_of

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifiedTag:
    """One Cardanoism-owned tag to persist in gov_action_tags."""
    tag: str
    tag_type: str
    confidence: float
    rationale: str
    source: str = "ai"


_MAX_TAGS_PER_GA = 8


def _make_tag(tag: str, confidence: float, rationale: str, source: str) -> ClassifiedTag | None:
    tag = str(tag or "").strip().lower()
    if not is_valid_tag(tag):
        return None
    tag_type = tag_type_of(tag)
    if tag_type is None:
        return None
    return ClassifiedTag(
        tag=tag,
        tag_type=tag_type,
        confidence=max(0.0, min(1.0, float(confidence))),
        rationale=str(rationale or "")[:1000],
        source=source,
    )


def _dedupe(tags: list[ClassifiedTag]) -> list[ClassifiedTag]:
    by_tag: dict[str, ClassifiedTag] = {}
    for item in tags:
        prev = by_tag.get(item.tag)
        if prev is None or item.confidence > prev.confidence:
            by_tag[item.tag] = item
    out = list(by_tag.values())
    out.sort(key=lambda t: -t.confidence)
    return out[:_MAX_TAGS_PER_GA]


def _text_blob(ga: dict[str, Any]) -> str:
    return "\n".join(str(ga.get(k) or "") for k in (
        "proposal_type", "title", "title_ja", "abstract", "abstract_ja",
        "motivation", "motivation_ja", "rationale", "rationale_ja",
    )).lower()


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def _requested_lovelace(ga: dict[str, Any]) -> int:
    for key in ("requested_amount_lovelace", "withdrawal_total_lovelace"):
        try:
            value = int(ga.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def classify_governance_action_rule_fallback(ga: dict[str, Any]) -> list[ClassifiedTag]:
    """Deterministic fallback for clear proposal types and obvious keywords."""
    if not ga:
        return []

    raw: list[ClassifiedTag] = []

    def add(tag: str, confidence: float, rationale: str) -> None:
        item = _make_tag(tag, confidence, rationale, "rule")
        if item:
            raw.append(item)

    ptype = str(ga.get("proposal_type") or "").strip().lower()
    text = _text_blob(ga)

    if ptype == "treasurywithdrawals":
        add("treasury", 1.0, "proposal_type is TreasuryWithdrawals")
    elif ptype == "parameterchange":
        add("protocol", 1.0, "proposal_type is ParameterChange")
        add("parameter_change", 1.0, "proposal_type is ParameterChange")
    elif ptype == "hardforkinitiation":
        add("protocol", 1.0, "proposal_type is HardForkInitiation")
        add("hard_fork", 1.0, "proposal_type is HardForkInitiation")
    elif ptype in {"newconstitution", "constitutionupdate", "updateconstitution"}:
        add("governance", 1.0, "proposal_type is constitution-related")
        add("constitution", 1.0, "proposal_type is constitution-related")
    elif ptype in {"infoaction", "newcommittee", "noconfidence"}:
        add("governance", 0.9, "proposal_type is governance-related")

    if _has(text, r"\b(marketing|pr|public relations|awareness|campaign)\b"):
        add("marketing", 0.75, "marketing / PR / awareness keyword matched")
        add("awareness", 0.75, "marketing / PR / awareness keyword matched")
    if _has(text, r"\b(conference|event|booth|summit|workshop|meetup)\b"):
        add("event", 0.75, "event keyword matched")
        add("community", 0.55, "event keyword may involve community activity")
    if _has(text, r"\bwallets?\b"):
        add("wallet", 0.75, "wallet keyword matched")
    if _has(text, r"\bdefi\b|decentralized finance"):
        add("defi", 0.75, "DeFi keyword matched")
    if _has(text, r"\bdapps?\b|\bapplications?\b"):
        add("dapp", 0.7, "dApp / application keyword matched")
        add("ecosystem", 0.65, "dApp / application keyword matched")
    if _has(text, r"\b(infrastructure|nodes?|tooling|indexers?|explorers?)\b"):
        add("infrastructure", 0.75, "infrastructure / tooling keyword matched")
        add("developer_experience", 0.65, "tooling keyword matched")
    if _has(text, r"\b(research|cryptography|formal methods?)\b"):
        add("long_term_research", 0.75, "research / cryptography keyword matched")
        add("core_development", 0.65, "research / formal methods keyword matched")
    if _has(text, r"\b(kpi|kpis|metrics?|measurable)\b"):
        add("kpi_defined", 0.65, "KPI / metrics keyword matched")
    if _has(text, r"\bmilestones?\b"):
        add("milestone_based", 0.65, "milestone keyword matched")
    if _has(text, r"\b(open source|github|repository|repositories)\b"):
        add("open_source", 0.65, "open source / repository keyword matched")
    if _has(text, r"\b(operational budget|maintenance|recurring)\b"):
        add("operational_budget", 0.65, "operational budget / maintenance keyword matched")
        add("recurring_budget", 0.6, "recurring / maintenance keyword matched")

    requested = _requested_lovelace(ga)
    if requested >= config.LARGE_BUDGET_LOVELACE:
        add("large_budget", 0.85, f"requested amount >= {config.LARGE_BUDGET_LOVELACE} lovelace")
    if requested >= config.HIGH_RISK_LOVELACE:
        add("high_risk", 0.7, f"requested amount >= {config.HIGH_RISK_LOVELACE} lovelace")

    if not any(t.tag_type == "category" for t in raw):
        add("other", 0.3, "no category rule matched")
    return _dedupe(raw)


def _type_guardrail_tags(ga: dict[str, Any]) -> list[ClassifiedTag]:
    """Always add official-type-derived tags as low-risk AI supplements."""
    return classify_governance_action_rule_fallback({
        "proposal_type": ga.get("proposal_type"),
    })


def classify_governance_action(ga: dict[str, Any]) -> list[ClassifiedTag]:
    """Classify one GA with AI, falling back to deterministic rules on failure."""
    if not ga:
        return []

    try:
        result = _ai_classify(ga)
        raw: list[ClassifiedTag] = []
        for entry in result.tags:
            item = _make_tag(
                entry.get("tag"),
                float(entry.get("confidence") or 0.0),
                entry.get("rationale"),
                "ai",
            )
            if item:
                raw.append(item)

        # Official proposal_type tags are not subjective; keep them even if AI omits them.
        raw.extend(_type_guardrail_tags(ga))
        out = _dedupe(raw)
        if not any(t.tag_type == "category" for t in out):
            other = _make_tag("other", 0.3, "AI returned no category tag", "ai")
            if other:
                out.append(other)
        logger.info(
            "classify_governance_action: AI %s -> %d tags "
            "(tokens in=%d out=%d cost=$%.4f)",
            ga.get("proposal_id"),
            len(out),
            result.tokens_input,
            result.tokens_output,
            result.cost_usd,
        )
        return out[:_MAX_TAGS_PER_GA]
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "classify_governance_action: AI failed for %s, using rule fallback: %s",
            ga.get("proposal_id"), e,
        )
        return classify_governance_action_rule_fallback(ga)


def classify_governance_action_ai_stub(ga: dict[str, Any]) -> list[ClassifiedTag]:
    """Backward-compatible alias; the main classifier is already AI-first."""
    return classify_governance_action(ga)
