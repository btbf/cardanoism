"""drep_compass.match
ユーザー価値観ベクトルと DRep プロファイルの相性スコアを計算する。

新設計: 7 軸ベース、シンプルな重み付き平均。
  similarity[axis] = 1 - |user[axis] - drep[axis]|
  total = Σ(similarity × weight × confidence) / Σ(weight × confidence)
  confidence < LOW_CONFIDENCE_THRESHOLD の axis は除外。
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

# confidence がこれ未満の axis はマッチ計算から除外
_LOW_CONFIDENCE = 0.2


@dataclass
class AxisDetail:
    axis: str
    user_value: float
    drep_value: float
    similarity: float
    confidence: float
    weight: float
    excluded: bool = False


@dataclass
class MatchResult:
    drep_id: str
    total_score: float                       # 0〜100
    summary: str = ""                        # AI 生成サマリ
    axis_details: list[AxisDetail] = field(default_factory=list)
    matched_axes: list[str] = field(default_factory=list)      # similarity >= 0.75
    mismatched_axes: list[str] = field(default_factory=list)   # similarity <= 0.30
    low_confidence_axes: list[str] = field(default_factory=list)
    reasoning_disclosure_rate: float = 0.0
    analyzed_vote_count: int = 0


def _axis_similarity(uv: float, dv: float) -> float:
    return max(0.0, min(1.0, 1.0 - abs(uv - dv)))


def calculate_drep_match(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    drep_row: dict[str, Any],
) -> MatchResult:
    """1 DRep に対するマッチを計算する。

    drep_row: drep_profiles の 1 行 dict (profile_json / confidence_json / ...)
    """
    drep_id = str(drep_row.get("drep_id") or "")
    summary = str(drep_row.get("summary") or "")
    try:
        profile = json.loads(drep_row.get("profile_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        profile = {}
    try:
        confidence = json.loads(drep_row.get("confidence_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        confidence = {}

    details: list[AxisDetail] = []
    sum_weighted_sim = 0.0
    sum_weight_conf = 0.0
    matched: list[str] = []
    mismatched: list[str] = []
    low_conf: list[str] = []

    for axis in AXES:
        if axis not in user_vector:
            continue
        uv = float(user_vector[axis])
        try:
            dv = float(profile.get(axis, 0.5))
        except (TypeError, ValueError):
            dv = 0.5
        try:
            conf = float(confidence.get(axis, 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        weight = float(axis_weights.get(axis, config.WEIGHT_NORMAL))

        sim = _axis_similarity(uv, dv)
        excluded = conf < _LOW_CONFIDENCE
        if not excluded:
            sum_weighted_sim += sim * weight * conf
            sum_weight_conf += weight * conf

        details.append(AxisDetail(
            axis=axis,
            user_value=round(uv, 4),
            drep_value=round(dv, 4),
            similarity=round(sim, 4),
            confidence=round(conf, 4),
            weight=round(weight, 4),
            excluded=excluded,
        ))

        if excluded:
            low_conf.append(axis)
        elif sim >= 0.75:
            matched.append(axis)
        elif sim <= 0.30:
            mismatched.append(axis)

    total = (sum_weighted_sim / sum_weight_conf * 100.0) if sum_weight_conf > 0 else 0.0

    return MatchResult(
        drep_id=drep_id,
        total_score=round(total, 1),
        summary=summary,
        axis_details=details,
        matched_axes=matched,
        mismatched_axes=mismatched,
        low_confidence_axes=low_conf,
        reasoning_disclosure_rate=float(drep_row.get("reasoning_disclosure_rate") or 0.0),
        analyzed_vote_count=int(drep_row.get("analyzed_vote_count") or 0),
    )


def _fetch_and_score(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    *,
    only_active: bool = True,
) -> list[tuple[MatchResult, dict[str, Any]]]:
    """全 DRep プロファイルを取得して match score を計算する内部ヘルパー。
    結果: [(MatchResult, drep_row dict), ...] (未ソート)
    """
    sql = """
        SELECT dp.drep_id, dp.profile_json, dp.confidence_json,
               dp.evidence_json, dp.summary,
               dp.reasoning_disclosure_rate, dp.analyzed_vote_count,
               d.given_name, d.image_url, d.drep_status, d.registered, d.amount
          FROM drep_profiles dp
          JOIN dreps d ON d.drep_id = dp.drep_id
         WHERE dp.analyzed_vote_count >= ?
           AND d.registered = 1
    """
    params: list[Any] = [int(config.MIN_ANALYZED_VOTE_COUNT)]
    if only_active:
        sql += " AND d.drep_status = 'active'"

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
    return out


def list_matches(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    *,
    limit: int = config.DEFAULT_MATCH_LIMIT,
    only_active: bool = True,
) -> list[MatchResult]:
    """全 DRep プロファイルを取得し、相性スコアを TOP N 返す (単一リスト)。

    only_active=True なら drep_status='active' のみ。
    """
    scored = _fetch_and_score(user_vector, axis_weights, only_active=only_active)
    # 総合スコア降順 → 委任量降順
    scored.sort(key=lambda t: (-t[0].total_score, -int(t[1].get("amount") or 0)))
    return [r for r, _ in scored[:max(1, int(limit))]]


def list_matches_split(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    *,
    top_amount_pool: int = 20,
    per_group: int = 5,
    only_active: bool = True,
) -> dict[str, list[MatchResult]]:
    """マッチ結果を 2 グループに分けて返す。

    - "top_amount":  委任量上位 top_amount_pool 名の中で、マッチ度上位 per_group 名
    - "discovery":   それ以外の DRep の中で、マッチ度上位 per_group 名

    用途: 「大手 DRep からのおすすめ」と「それ以外の遺珠発見」の 2 セクション表示。
    """
    scored = _fetch_and_score(user_vector, axis_weights, only_active=only_active)

    # 委任量降順にソートして TOP pool / その他 に二分
    by_amount = sorted(scored, key=lambda t: -int(t[1].get("amount") or 0))
    top_pool = by_amount[:max(1, int(top_amount_pool))]
    other_pool = by_amount[max(1, int(top_amount_pool)):]

    # 各グループ内で match score 降順 → 委任量降順
    def _pick(pool: list[tuple[MatchResult, dict[str, Any]]]) -> list[MatchResult]:
        sorted_pool = sorted(
            pool,
            key=lambda t: (-t[0].total_score, -int(t[1].get("amount") or 0)),
        )
        return [r for r, _ in sorted_pool[:max(1, int(per_group))]]

    return {
        "top_amount": _pick(top_pool),
        "discovery":  _pick(other_pool),
    }
