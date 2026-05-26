"""drep_compass.profile
DRep の投票履歴 + rationale を AI に投げて 7 axis プロファイルを生成する。

新設計: タグ集計の数式は廃止。AI (gpt-5.4-mini) が直接 rationale を読んで
7 axis スコアと 1 行サマリ文を返す。gov_action_tags / classifier は不要。

データソース:
  - proposal_votes (voter_role='DRep', voter_id=<drep_id>): Yes / No / Abstain
    + rationale 文
  - governance_actions: title / abstract (AI が文脈把握用)

出力:
  - drep_profiles に
    - profile_json     (7 axis スコア)
    - confidence_json  (7 axis 信頼度)
    - evidence_json    (AI 出力の axis ごと根拠)
    - summary          (AI 生成の 1 行サマリ、日本語)
    - reasoning_disclosure_rate (rationale 公開率)
    - analyzed_vote_count       (Yes/No/Abstain 投票数)
    - analysis_version          (config.ANALYSIS_VERSION)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from cardanoism.backend.ai_client import (
    analyze_drep_compass_profile as _ai_analyze,
)
from cardanoism.backend.db_connect import get_db
from cardanoism.backend.drep_compass import config
from cardanoism.backend.drep_compass.taxonomy import AXES

logger = logging.getLogger(__name__)


@dataclass
class DrepProfileResult:
    """1 DRep の AI 分析結果 (DB INSERT 直前の形)。"""
    drep_id: str
    profile: dict[str, float]     # 7 axis 0.0〜1.0
    confidence: dict[str, float]  # 7 axis 0.0〜1.0
    summary: str                  # 1 行サマリ (AI 生成、日本語)
    summary_en: str               # 1 行サマリ (AI 生成、英語)
    evidence: dict[str, list[dict[str, Any]]]
    analyzed_vote_count: int
    reasoning_disclosure_rate: float


# ── DB から DRep の投票履歴 + rationale + GA メタを取得 ─────


def _fetch_drep_votes(drep_id: str) -> list[dict[str, Any]]:
    """1 DRep の全投票を、GA メタと結合して取得する。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT pv.proposal_id,
                   pv.vote,
                   COALESCE(pv.rationale_ja, pv.rationale, '') AS rationale,
                   COALESCE(ga.title_ja, ga.title, '')         AS title,
                   COALESCE(ga.abstract_ja, ga.abstract, '')   AS abstract,
                   ga.proposal_type
              FROM proposal_votes pv
              LEFT JOIN governance_actions ga
                ON ga.proposal_id = pv.proposal_id
             WHERE pv.voter_role = 'DRep'
               AND pv.voter_id   = ?
             ORDER BY pv.block_time DESC
            """,
            (str(drep_id),),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    return rows


# ── AI 入力ペイロード組み立て ────────────────────────────────


# AI に渡す投票履歴の最大件数 (token 削減のため新しい順に N 件まで)
_MAX_VOTE_COUNT = 60


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _build_ai_payload(drep_id: str, votes: list[dict[str, Any]]) -> dict[str, Any]:
    """AI に渡す JSON ペイロード。"""
    items: list[dict[str, Any]] = []
    for v in votes[:_MAX_VOTE_COUNT]:
        rationale = _truncate(str(v.get("rationale") or ""), 800)
        abstract = _truncate(str(v.get("abstract") or ""), 500)
        title = _truncate(str(v.get("title") or ""), 200)
        items.append({
            "proposal_id":   str(v.get("proposal_id") or ""),
            "proposal_type": str(v.get("proposal_type") or ""),
            "title":         title,
            "abstract":      abstract,
            "vote":          str(v.get("vote") or ""),
            "rationale":     rationale,
        })
    return {
        "drep_id": str(drep_id),
        "votes":   items,
    }


# ── 公開: 1 DRep の AI 分析 → DB 保存 ────────────────────────


def calculate_and_save(drep_id: str) -> DrepProfileResult:
    """1 DRep のプロファイルを AI で生成して DB UPSERT する。"""
    votes = _fetch_drep_votes(drep_id)
    if not votes:
        # 投票履歴ゼロの DRep は AI 分析せず、空プロファイルで上書き
        empty = DrepProfileResult(
            drep_id=drep_id,
            profile={a: 0.5 for a in AXES},
            confidence={a: 0.0 for a in AXES},
            summary="",
            summary_en="",
            evidence={},
            analyzed_vote_count=0,
            reasoning_disclosure_rate=0.0,
        )
        _upsert(empty)
        return empty

    payload = _build_ai_payload(drep_id, votes)
    try:
        ai_result = _ai_analyze(payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("calculate_and_save: AI failed for %s: %s", drep_id, e)
        raise

    logger.info(
        "calculate_and_save: %s analyzed (votes=%d tokens in=%d out=%d cost=$%.4f)",
        drep_id, len(votes),
        ai_result.tokens_input, ai_result.tokens_output, ai_result.cost_usd,
    )

    # 7 axis のみ抽出 (AI が余計な axis を返しても無視)
    profile = {a: ai_result.profile.get(a, 0.5) for a in AXES}
    confidence = {a: ai_result.confidence.get(a, 0.0) for a in AXES}
    evidence = {a: ai_result.evidence.get(a, []) for a in AXES}

    # 参加投票数と理由公開率
    voted = 0
    with_rationale = 0
    for v in votes:
        vote = str(v.get("vote") or "")
        if vote in ("Yes", "No", "Abstain"):
            voted += 1
            if str(v.get("rationale") or "").strip():
                with_rationale += 1
    disclosure = (with_rationale / voted) if voted > 0 else 0.0

    result = DrepProfileResult(
        drep_id=drep_id,
        profile=profile,
        confidence=confidence,
        summary=ai_result.summary,
        summary_en=ai_result.summary_en,
        evidence=evidence,
        analyzed_vote_count=voted,
        reasoning_disclosure_rate=disclosure,
    )
    _upsert(result)
    return result


def _upsert(result: DrepProfileResult) -> None:
    """drep_profiles に AI 結果を UPSERT する。

    summary    列は migration 022 で追加 (日本語)。
    summary_en 列は migration 024 で追加 (英語)。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO drep_profiles (
              drep_id, profile_json, confidence_json, raw_score_json,
              participation_rate, reasoning_disclosure_rate,
              analyzed_vote_count, eligible_action_count,
              analysis_version, evidence_json, summary, summary_en,
              calculated_at
            ) VALUES (?, ?, ?, NULL, 1.0, ?, ?, ?, ?, ?, ?, ?, NOW())
            ON DUPLICATE KEY UPDATE
              profile_json              = VALUES(profile_json),
              confidence_json           = VALUES(confidence_json),
              raw_score_json            = NULL,
              participation_rate        = 1.0,
              reasoning_disclosure_rate = VALUES(reasoning_disclosure_rate),
              analyzed_vote_count       = VALUES(analyzed_vote_count),
              eligible_action_count     = VALUES(eligible_action_count),
              analysis_version          = VALUES(analysis_version),
              evidence_json             = VALUES(evidence_json),
              summary                   = VALUES(summary),
              summary_en                = VALUES(summary_en),
              calculated_at             = NOW()
            """,
            (
                result.drep_id,
                json.dumps(result.profile, ensure_ascii=False),
                json.dumps(result.confidence, ensure_ascii=False),
                float(result.reasoning_disclosure_rate),
                int(result.analyzed_vote_count),
                int(result.analyzed_vote_count),
                config.ANALYSIS_VERSION,
                json.dumps(result.evidence, ensure_ascii=False),
                result.summary,
                result.summary_en,
            ),
        )
        conn.commit()
