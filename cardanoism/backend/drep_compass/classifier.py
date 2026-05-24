"""drep_compass.classifier
Governance Action の Cardanoism独自タグ分類 (ルールベース MVP)。

入力:
  governance_actions row (proposal_id, proposal_type, title, abstract,
  title_ja, abstract_ja, withdrawal_total_lovelace)

出力:
  list[ClassifiedTag] = [(tag, tag_type, confidence, rationale)]
  → gov_action_tags テーブルに INSERT

MVP はルールベースのみ。AI 分類器の stub も用意し、将来差し替え可能にする。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

from cardanoism.backend.drep_compass import config
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
    rationale: str  # どのキーワードが効いたかの説明
    source: str = "rule"  # "rule" | "ai" | "manual"


# ── キーワードルール ────────────────────────────────────────
# (パターン, 付与タグ群, rationale テンプレート) のタプル列。
# パターンは title + abstract (ja/en 両方) に対して大文字小文字無視で評価。
#
# 1 GA に複数タグが付くのは普通 (e.g., marketing + awareness + event)。
_KW_RULES: list[tuple[str, tuple[str, ...], str]] = [
    # ── category 系 ────────────────────────────────────────
    (r"\bmarketing\b|広告|プロモーション|プロモ", ("marketing", "awareness"),
        "title/abstract に marketing 関連語"),
    (r"\bPR\b|public[\s_-]?relations|広報", ("marketing", "awareness"),
        "PR / 広報 関連語"),
    (r"\bcampaign\b|キャンペーン", ("marketing", "awareness"),
        "campaign 関連語"),
    (r"\bawareness\b|認知|認識度|brand[\s_-]?awareness", ("marketing", "awareness"),
        "awareness 関連語"),
    (r"\bconference\b|\bsummit\b|\bmeetup\b|カンファレンス|サミット|ミートアップ",
        ("event", "marketing"),
        "conference / summit / meetup"),
    (r"\bevent\b|\bbooth\b|展示|出展|イベント", ("event", "community"),
        "event / booth"),
    (r"\bhackathon\b|ハッカソン", ("event", "education", "developer_experience"),
        "hackathon"),
    (r"\bwallet\b|ウォレット", ("wallet", "ecosystem"),
        "wallet 関連語"),
    (r"\bdefi\b|stable[\s_-]?coin|\bDEX\b|lending|liquidity",
        ("defi", "ecosystem"),
        "DeFi / DEX / stablecoin"),
    (r"\bdapp\b|application|アプリケーション", ("dapp", "ecosystem"),
        "dApp / application"),
    (r"\binfrastructure\b|node|\btooling\b|indexer|explorer|インフラ",
        ("infrastructure", "developer_experience"),
        "infrastructure / node / tooling"),
    (r"\bresearch\b|cryptography|formal\s+methods|formal\s+verification|学術|暗号研究",
        ("long_term_research", "core_development"),
        "research / cryptography / formal methods"),
    (r"\beducation\b|teaching|curriculum|教育|学習", ("education",),
        "education / teaching"),
    (r"\bcommunity\b|ambassador|コミュニティ", ("community",),
        "community / ambassador"),
    (r"\bplutus\b|aiken|marlowe|core\s+protocol|consensus|node\s+implementation",
        ("core_development", "developer_experience"),
        "Plutus / Aiken / consensus / node implementation"),
    (r"\bsecurity\b|audit|セキュリティ|監査",
        ("security_related",),
        "security / audit"),

    # ── quality 系 ─────────────────────────────────────────
    (r"\bKPI\b|key\s+performance\s+indicators?", ("kpi_defined",),
        "KPI 明示"),
    (r"\bmetrics?\b|measurable|定量的", ("kpi_defined",),
        "metrics / measurable"),
    (r"\bmilestone\b|マイルストーン", ("milestone_based",),
        "milestone 言及"),
    (r"open[\s_-]?source|github\.com|gitlab\.com|オープンソース",
        ("open_source",),
        "open source / GitHub / GitLab"),
    (r"\brecurring\b|annual|monthly|定期|年次|月次",
        ("recurring_budget",),
        "recurring / annual / monthly"),
    (r"operational\s+budget|maintenance|運営費|維持費",
        ("operational_budget", "recurring_budget"),
        "operational budget / maintenance"),

    # ── attribute 系 (主体 / 領域) ──────────────────────────
    (r"\bIntersect\b|IOG\b|input\s+output|cardano\s+foundation|emurgo",
        ("existing_entity",),
        "IO / Intersect / CF / Emurgo"),
    (r"\bRealFi\b|real[\s_-]?world\s+finance|enterprise\s+adoption|government",
        ("user_adoption",),
        "RealFi / enterprise adoption"),
]

# 既存タグ重複を避けるため、ルールが返したタグはすべて lower 化して扱う。


def _grep_keywords(haystack: str, rules: Iterable[tuple[str, tuple[str, ...], str]]
                   ) -> list[tuple[str, str]]:
    """haystack に対しルール群を適用し、ヒットしたタグと rationale を返す。

    1 つのルールが複数タグを生成する場合あり。同じタグが複数ルールから出るのは
    上位呼び出し側で重複除去する。
    """
    hits: list[tuple[str, str]] = []
    for pattern, tags, label in rules:
        try:
            if re.search(pattern, haystack, flags=re.IGNORECASE):
                for t in tags:
                    hits.append((t, label))
        except re.error as e:
            logger.warning("classifier: invalid regex %r: %s", pattern, e)
    return hits


def _classify_by_proposal_type(ptype: str) -> list[tuple[str, str]]:
    """proposal_type から自動的に付くタグ (spec 第 3 節)。"""
    p = (ptype or "").strip()
    if p == "TreasuryWithdrawals":
        return [("treasury", "proposal_type=TreasuryWithdrawals")]
    if p == "ParameterChange":
        return [
            ("protocol", "proposal_type=ParameterChange"),
            ("parameter_change", "proposal_type=ParameterChange"),
        ]
    if p == "HardForkInitiation":
        return [
            ("protocol", "proposal_type=HardForkInitiation"),
            ("hard_fork", "proposal_type=HardForkInitiation"),
        ]
    if p in ("NewConstitution", "ConstitutionUpdate"):
        return [
            ("governance", f"proposal_type={p}"),
            ("constitution", f"proposal_type={p}"),
        ]
    if p == "InfoAction":
        return [("governance", "proposal_type=InfoAction")]
    if p in ("NoConfidence", "NewCommittee", "UpdateCommittee"):
        return [("governance", f"proposal_type={p}")]
    return []


def _classify_by_amount(withdrawal_total_lovelace: int | None) -> list[tuple[str, str]]:
    """金額しきい値で large_budget / high_risk タグ。"""
    if not withdrawal_total_lovelace:
        return []
    out: list[tuple[str, str]] = []
    if withdrawal_total_lovelace >= config.HIGH_RISK_LOVELACE:
        ada = withdrawal_total_lovelace // 1_000_000
        out.append(("high_risk", f"withdrawal {ada:,} ADA ≥ HIGH_RISK_LOVELACE"))
        out.append(("large_budget", f"withdrawal {ada:,} ADA ≥ HIGH_RISK_LOVELACE"))
    elif withdrawal_total_lovelace >= config.LARGE_BUDGET_LOVELACE:
        ada = withdrawal_total_lovelace // 1_000_000
        out.append(("large_budget", f"withdrawal {ada:,} ADA ≥ LARGE_BUDGET_LOVELACE"))
    return out


def classify_governance_action(ga: dict[str, Any]) -> list[ClassifiedTag]:
    """1 GA の rule-based 分類結果を返す。

    Args:
      ga: governance_actions テーブルから取った dict (proposal_type, title,
          abstract, title_ja, abstract_ja, withdrawal_total_lovelace を含む)

    Returns:
      ClassifiedTag のリスト。同じタグの重複は除去 (最初の rationale を採用)。
    """
    if not ga:
        return []

    raw_hits: list[tuple[str, str]] = []

    # 1. proposal_type からの自動タグ
    raw_hits.extend(_classify_by_proposal_type(str(ga.get("proposal_type") or "")))

    # 2. キーワード分類 (title + abstract 両言語)
    haystack_parts = [
        str(ga.get("title") or ""),
        str(ga.get("abstract") or ""),
        str(ga.get("title_ja") or ""),
        str(ga.get("abstract_ja") or ""),
    ]
    haystack = " ".join(p for p in haystack_parts if p)
    if haystack:
        raw_hits.extend(_grep_keywords(haystack, _KW_RULES))

    # 3. 金額しきい値
    try:
        amt = int(ga.get("withdrawal_total_lovelace") or 0)
    except (TypeError, ValueError):
        amt = 0
    raw_hits.extend(_classify_by_amount(amt))

    # 4. 重複除去 (同じタグは最初の rationale を採用)
    seen: dict[str, str] = {}
    for tag, rationale in raw_hits:
        if not is_valid_tag(tag):
            logger.debug("classifier: skip unknown tag %r", tag)
            continue
        if tag not in seen:
            seen[tag] = rationale

    out: list[ClassifiedTag] = []
    for tag, rationale in seen.items():
        ttype = tag_type_of(tag)
        if ttype is None:
            continue
        out.append(ClassifiedTag(
            tag=tag,
            tag_type=ttype,
            confidence=1.0,  # rule-based は確信度 1.0
            rationale=rationale,
            source="rule",
        ))

    # 何も付かなかった場合のフォールバック
    if not out:
        out.append(ClassifiedTag(
            tag="other",
            tag_type="category",
            confidence=0.5,
            rationale="no rule matched",
            source="rule",
        ))

    return out


def classify_governance_action_ai_stub(ga: dict[str, Any]) -> list[ClassifiedTag]:
    """AI 分類器の stub。本実装は将来 ai_client 経由で OpenAI を呼ぶ予定。

    現状は何も返さない (ルールベースが主、AI は補助になる想定)。
    """
    logger.debug("classify_governance_action_ai_stub called for %s (no-op)",
                 ga.get("proposal_id"))
    return []
