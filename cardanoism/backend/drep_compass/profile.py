"""drep_compass.profile (v3: GA tag aggregation, no AI per DRep)

DRep の投票履歴 × GA per-axis タグを集計して 7 axis スコアを算出する。

v2 との違い:
- v2: AI が DRep の投票履歴を読んで 7 axis スコアを推論
- v3: AI は GA 1 件につき 1 度だけ axis_tags を抽出 (ga_ai_worker)。
      drep_compass はその tag を読んで投票を集計するだけ。AI 推論なし。

利点:
- 透明性: 各 axis スコアの根拠 (どの投票がどう寄与したか) が完全に追跡可能
- 一貫性: 60 票制限なし、3 evidence 制限なし、全投票を対象
- コスト: DRep 側の AI コール無し (compass_profile_all がほぼ無料)
- 再現性: 同じデータからは同じスコアが必ず出る

データソース:
  - proposal_votes (voter_role='DRep', voter_id=<drep_id>)
  - governance_ai_analysis.axis_tags_json (各 GA の AI 抽出タグ)

axis ごとの集計ロジック (詳細は compute_axis_scores 参照):
  - org      : big5 (IO/CF/Intersect/Emurgo/Midnight) への Yes/No と
               new_team/individual への Yes/No を反対方向に集計
  - treasury : large 支出への Yes (0=攻め) / No (1=守り)
  - priority : technical Yes (0) / adoption Yes (1)
  - protocol : hard_fork/param_change への Yes (0=革新) / No (1=安定)
  - marketing: marketing_purpose=yes への Yes (0) / No (1)
  - transparency: kpi_unclear への Yes (0=ゆるめ) / No (1=厳しめ)
  - risk     : risk_high への Yes (0=大胆) / No (1=慎重)

DB スキーマは v2 と同じ drep_profiles を使う (summary 列は v3 では NULL のまま)。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.drep_compass import config
from cardanoism.backend.drep_compass.taxonomy import AXES

logger = logging.getLogger(__name__)


# big5 = 既存大組織 (org axis の 0.0 側を支持する受益)
_BIG5_ORGS = frozenset({"IO", "CF", "Intersect", "Emurgo", "Midnight"})
# distributed = 分散派 (org axis の 1.0 側を支持する受益)
_DISTRIBUTED_ORGS = frozenset({"new_team", "individual"})


@dataclass
class AxisEvidenceItem:
    """1 axis に寄与した 1 投票の根拠。"""
    proposal_id: str
    vote: str          # Yes / No / Abstain
    direction: float   # この投票が axis スコアに寄与した値 (0.0 or 1.0)
    reason: str        # GA axis_tags の reasoning から


@dataclass
class DrepProfileResult:
    """1 DRep の集計結果 (DB INSERT 直前の形)。"""
    drep_id: str
    profile: dict[str, float]
    confidence: dict[str, float]
    evidence: dict[str, list[dict[str, Any]]]
    analyzed_vote_count: int
    reasoning_disclosure_rate: float


# ── DB から DRep の投票 + GA タグを取得 ──────────────────────


def _fetch_drep_votes_with_tags(drep_id: str) -> list[dict[str, Any]]:
    """DRep の全投票を、対応する GA の axis_tags / rationale と一緒に取得する。

    axis_tags_json が NULL の GA (ga_ai_worker 未処理) はタグ無しとして返す
    (axis 集計には寄与しないが analyzed_vote_count にはカウント)。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT pv.proposal_id,
                   pv.vote,
                   COALESCE(pv.rationale_ja, pv.rationale, '') AS rationale,
                   gaa.axis_tags_json
              FROM proposal_votes pv
              LEFT JOIN governance_ai_analysis gaa
                ON gaa.proposal_id = pv.proposal_id
             WHERE pv.voter_role = 'DRep'
               AND pv.voter_id   = ?
            """,
            (str(drep_id),),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    out: list[dict[str, Any]] = []
    for r in rows:
        tags: dict[str, Any] = {}
        if r.get("axis_tags_json"):
            try:
                tags = json.loads(r["axis_tags_json"]) or {}
            except (TypeError, ValueError, json.JSONDecodeError):
                tags = {}
        out.append({
            "proposal_id": str(r.get("proposal_id") or ""),
            "vote":        str(r.get("vote") or ""),
            "rationale":   str(r.get("rationale") or ""),
            "axis_tags":   tags,
        })
    return out


# ── 集計ロジック (各 axis ごと) ───────────────────────────────


def _axis_direction_for_vote(
    axis: str,
    vote: str,
    tags: dict[str, Any],
) -> float | None:
    """1 axis × 1 投票 → axis スコアへの寄与値 (0.0 / 1.0) または None。

    None の場合は「この投票はこの axis に寄与しない」(タグ無 or 不適合)。
    """
    if vote not in ("Yes", "No"):
        # Abstain は方向性 signal が弱いので除外 (analyzed_vote_count にはカウント)
        return None

    if axis == "treasury":
        # large 支出への Yes (攻め=0.0) / No (守り=1.0)
        if tags.get("treasury_size") == "large":
            return 0.0 if vote == "Yes" else 1.0
        return None

    if axis == "priority":
        # technical Yes → 0.0 / adoption Yes → 1.0 / No 投票は ambiguous で除外
        p = tags.get("priority")
        if vote == "Yes" and p == "technical":
            return 0.0
        if vote == "Yes" and p == "adoption":
            return 1.0
        return None

    if axis == "org":
        orgs = tags.get("org_recipient") or []
        if not isinstance(orgs, list):
            return None
        has_big5 = any(o in _BIG5_ORGS for o in orgs)
        has_dist = any(o in _DISTRIBUTED_ORGS for o in orgs)
        if has_big5 and not has_dist:
            return 0.0 if vote == "Yes" else 1.0  # Yes=既存組織支持, No=拒否
        if has_dist and not has_big5:
            return 1.0 if vote == "Yes" else 0.0  # Yes=分散支持, No=拒否
        # 両方混在 or どちらでも無い (other / 空) は寄与なし
        return None

    if axis == "protocol":
        # hard_fork / param_change への Yes (革新=0.0) / No (安定=1.0)
        if tags.get("protocol_change") in ("hard_fork", "param_change"):
            return 0.0 if vote == "Yes" else 1.0
        return None

    if axis == "marketing":
        # marketing_purpose=yes への Yes (推進=0.0) / No (抑制=1.0)
        if tags.get("marketing_purpose") == "yes":
            return 0.0 if vote == "Yes" else 1.0
        return None

    if axis == "transparency":
        # kpi_unclear への Yes (ゆるめ=0.0) / No (厳しめ=1.0)
        if tags.get("kpi_clarity") == "unclear":
            return 0.0 if vote == "Yes" else 1.0
        return None

    if axis == "risk":
        # risk_level=high への Yes (大胆=0.0) / No (慎重=1.0)
        if tags.get("risk_level") == "high":
            return 0.0 if vote == "Yes" else 1.0
        return None

    return None


def compute_axis_scores(
    votes_with_tags: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, float], dict[str, list[dict[str, Any]]]]:
    """投票 × GA タグから 7 axis のスコア + 信頼度 + 根拠を算出。

    - score      : 寄与投票の方向値 (0.0/1.0) の平均。寄与ゼロなら 0.5
    - confidence : 寄与投票数を最大 10 票で正規化 (10 票以上で 1.0)
    - evidence   : axis ごとの寄与投票リスト (全件、上限なし)
    """
    profile: dict[str, float] = {}
    confidence: dict[str, float] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}

    for axis in AXES:
        directions: list[float] = []
        ev_items: list[dict[str, Any]] = []
        for v in votes_with_tags:
            d = _axis_direction_for_vote(axis, v["vote"], v["axis_tags"])
            if d is None:
                continue
            directions.append(d)
            reasoning = v["axis_tags"].get("reasoning") or {}
            reason = ""
            if isinstance(reasoning, dict):
                reason = str(reasoning.get(_axis_to_tag_key(axis)) or "")[:200]
            ev_items.append({
                "proposal_id": v["proposal_id"],
                "vote":        v["vote"],
                "direction":   d,
                "reason":      reason,
            })

        if not directions:
            profile[axis] = 0.5
            confidence[axis] = 0.0
        else:
            profile[axis] = sum(directions) / len(directions)
            confidence[axis] = min(1.0, len(directions) / 10.0)
        evidence[axis] = ev_items

    return profile, confidence, evidence


def _axis_to_tag_key(axis: str) -> str:
    """drep_compass axis 名 → governance_ai_analysis.axis_tags の reasoning キー。"""
    return {
        "treasury":     "treasury_size",
        "priority":     "priority",
        "org":          "org_recipient",
        "protocol":     "protocol_change",
        "marketing":    "marketing_purpose",
        "transparency": "kpi_clarity",
        "risk":         "risk_level",
    }.get(axis, axis)


# ── 公開: 1 DRep のプロファイル計算 → DB 保存 ───────────────


def calculate_and_save(drep_id: str) -> DrepProfileResult:
    """1 DRep のプロファイルを集計して drep_profiles に UPSERT する。

    v3 では AI コール無し。GA の axis_tags を信頼して投票を集計するのみ。
    """
    votes = _fetch_drep_votes_with_tags(drep_id)
    if not votes:
        empty = DrepProfileResult(
            drep_id=drep_id,
            profile={a: 0.5 for a in AXES},
            confidence={a: 0.0 for a in AXES},
            evidence={},
            analyzed_vote_count=0,
            reasoning_disclosure_rate=0.0,
        )
        _upsert(empty)
        return empty

    profile, confidence, evidence = compute_axis_scores(votes)

    # 参加投票数と理由公開率 (quality filter 用、v2 と同じ計算)
    voted = 0
    with_rationale = 0
    for v in votes:
        if v["vote"] in ("Yes", "No", "Abstain"):
            voted += 1
            if v["rationale"].strip():
                with_rationale += 1
    disclosure = (with_rationale / voted) if voted > 0 else 0.0

    result = DrepProfileResult(
        drep_id=drep_id,
        profile=profile,
        confidence=confidence,
        evidence=evidence,
        analyzed_vote_count=voted,
        reasoning_disclosure_rate=disclosure,
    )
    _upsert(result)
    logger.info(
        "calculate_and_save (v3): %s analyzed (votes=%d, axes with signal=%d)",
        drep_id, voted, sum(1 for a in AXES if confidence[a] > 0.0),
    )
    return result


def _upsert(result: DrepProfileResult) -> None:
    """drep_profiles に集計結果を UPSERT する。

    v3 では summary / summary_en は生成しない (集計式のため AI コール無し)。
    既存 v2 の summary が残っている場合は上書きしない方針で NULL を渡さない
    → COALESCE で既存値を保持するのが理想だが、シンプルさのため NULL を入れる
    (将来 v3 用の rule-based サマリを書くまでの暫定)。
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
            ) VALUES (?, ?, ?, NULL, 1.0, ?, ?, ?, ?, ?, NULL, NULL, NOW())
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
              summary                   = NULL,
              summary_en                = NULL,
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
            ),
        )
        conn.commit()
