"""drep_compass.match
ユーザー価値観ベクトルと DRep プロファイルの相性スコアを計算する。

spec 第 6 節「マッチング計算」を厳守。
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


@dataclass
class AxisDetail:
    axis: str
    user_value: float       # 0.0〜1.0
    drep_value: float       # 0.0〜1.0
    similarity: float       # 0.0〜1.0
    confidence: float       # 0.0〜1.0
    weight: float           # 1.0 or 1.5
    weighted_contribution: float  # similarity * weight * confidence
    excluded: bool = False  # confidence < LOW_CONFIDENCE_THRESHOLD で除外


@dataclass
class MatchResult:
    drep_id: str
    total_score: float                       # 0.0〜100.0
    axis_details: list[AxisDetail] = field(default_factory=list)
    matched_axes: list[str] = field(default_factory=list)
    mismatched_axes: list[str] = field(default_factory=list)
    low_confidence_axes: list[str] = field(default_factory=list)
    participation_rate: float = 0.0
    reasoning_disclosure_rate: float = 0.0
    analyzed_vote_count: int = 0
    evidence_summary: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def _axis_similarity(user_value: float, drep_value: float) -> float:
    """1 - abs(user - drep) を 0.0〜1.0 にクランプして返す。"""
    return max(0.0, min(1.0, 1.0 - abs(user_value - drep_value)))


def calculate_drep_match(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    drep_profile: dict[str, Any],
) -> MatchResult:
    """1 DRep に対する match を計算。

    Args:
      user_vector:   axis -> 0.0〜1.0 (questionnaire.build_user_vector の出力)
      axis_weights:  axis -> 1.0 or 1.5
      drep_profile:  drep_profiles row を dict 化したもの
                     (profile_json / confidence_json / participation_rate / ...)

    Returns:
      MatchResult (total_score は 0〜100)
    """
    drep_id = str(drep_profile.get("drep_id") or "")

    try:
        profile = json.loads(drep_profile.get("profile_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        profile = {}
    try:
        confidence = json.loads(drep_profile.get("confidence_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        confidence = {}
    try:
        evidence = json.loads(drep_profile.get("evidence_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        evidence = {}

    details: list[AxisDetail] = []
    sum_weighted_sim = 0.0
    sum_weight_conf = 0.0

    matched: list[str] = []
    mismatched: list[str] = []
    low_conf: list[str] = []

    for axis in AXES:
        if axis not in user_vector:
            # ユーザーが回答してない axis はスキップ
            continue
        uv = float(user_vector[axis])
        try:
            dv = float(profile.get(axis, config.NEUTRAL_MIDPOINT))
        except (TypeError, ValueError):
            dv = config.NEUTRAL_MIDPOINT
        try:
            conf = float(confidence.get(axis, 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        weight = float(axis_weights.get(axis, config.WEIGHT_NORMAL))

        sim = _axis_similarity(uv, dv)
        excluded = conf < config.LOW_CONFIDENCE_THRESHOLD
        contribution = sim * weight * conf if not excluded else 0.0
        denom = weight * conf if not excluded else 0.0

        if not excluded:
            sum_weighted_sim += contribution
            sum_weight_conf += denom

        details.append(AxisDetail(
            axis=axis,
            user_value=round(uv, 4),
            drep_value=round(dv, 4),
            similarity=round(sim, 4),
            confidence=round(conf, 4),
            weight=round(weight, 4),
            weighted_contribution=round(contribution, 4),
            excluded=excluded,
        ))

        if excluded:
            low_conf.append(axis)
        elif sim >= 0.75:
            matched.append(axis)
        elif sim <= 0.30:
            mismatched.append(axis)

    if sum_weight_conf > 0:
        total = (sum_weighted_sim / sum_weight_conf) * 100.0
    else:
        total = 0.0

    return MatchResult(
        drep_id=drep_id,
        total_score=round(total, 1),
        axis_details=details,
        matched_axes=matched,
        mismatched_axes=mismatched,
        low_confidence_axes=low_conf,
        participation_rate=float(drep_profile.get("participation_rate") or 0.0),
        reasoning_disclosure_rate=float(drep_profile.get("reasoning_disclosure_rate") or 0.0),
        analyzed_vote_count=int(drep_profile.get("analyzed_vote_count") or 0),
        evidence_summary=evidence,
    )


def list_matches(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    *,
    limit: int = config.DEFAULT_MATCH_LIMIT,
    only_registered: bool = True,
) -> list[MatchResult]:
    """全 DRep プロファイルを取得し、相性スコアを TOP N 返す。

    フィルタ: drep_profiles.analyzed_vote_count >= MIN_ANALYZED_VOTE_COUNT。
    only_registered=True なら dreps.registered=1 のみ。
    """
    sql = """
        SELECT dp.drep_id, dp.profile_json, dp.confidence_json,
               dp.evidence_json,
               dp.participation_rate, dp.reasoning_disclosure_rate,
               dp.analyzed_vote_count,
               d.given_name, d.image_url, d.drep_status, d.registered, d.amount
          FROM drep_profiles dp
          JOIN dreps d ON d.drep_id = dp.drep_id
         WHERE dp.analyzed_vote_count >= ?
    """
    params: list[Any] = [int(config.MIN_ANALYZED_VOTE_COUNT)]
    if only_registered:
        sql += " AND d.registered = 1"

    with get_db() as (cursor, _):
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]

    out: list[tuple[MatchResult, dict[str, Any]]] = []
    for row in rows:
        try:
            r = calculate_drep_match(user_vector, axis_weights, row)
        except Exception as e:  # noqa: BLE001
            logger.warning("calculate_drep_match failed for %s: %s",
                           row.get("drep_id"), e)
            continue
        out.append((r, row))

    # 総合スコア降順 → 委任量降順 で安定ソート
    out.sort(key=lambda t: (-t[0].total_score, -int(t[1].get("amount") or 0)))
    return [r for r, _ in out[:max(1, int(limit))]]
