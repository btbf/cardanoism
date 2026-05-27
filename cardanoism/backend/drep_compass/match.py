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

# confidence がこれ未満の axis は「一致 / 相違」表示から除外して
# 「判断材料が少ない項目」として表示する。
# v3 では confidence = min(1.0, 寄与投票数 / 10) なので 0.3 = 3 票分。
_LOW_CONFIDENCE = 0.3


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
    summary: str = ""                        # AI 生成サマリ (JA)
    summary_en: str = ""                     # AI 生成サマリ (EN)
    axis_details: list[AxisDetail] = field(default_factory=list)
    matched_axes: list[str] = field(default_factory=list)      # similarity >= 0.75
    mismatched_axes: list[str] = field(default_factory=list)   # similarity <= 0.30
    low_confidence_axes: list[str] = field(default_factory=list)
    reasoning_disclosure_rate: float = 0.0
    analyzed_vote_count: int = 0
    # v3 透明性: 各 axis に寄与した投票 (drep_profiles.evidence_json の生)
    # {axis: [{proposal_id, vote, direction, reason}, ...]}
    evidence_per_axis: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


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
    summary_en = str(drep_row.get("summary_en") or "")
    try:
        profile = json.loads(drep_row.get("profile_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        profile = {}
    try:
        confidence = json.loads(drep_row.get("confidence_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        confidence = {}
    try:
        evidence = json.loads(drep_row.get("evidence_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        evidence = {}

    details: list[AxisDetail] = []
    sum_weighted_effective = 0.0   # Σ (effective_sim × weight)
    sum_weight = 0.0               # Σ weight (低信頼 axis も母数に含める)
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

        # effective_sim: 信頼度に応じて raw sim と中立 (0.5) を線形補間。
        # conf=1.0 → sim そのまま、conf=0.0 → 0.5 (中立)。
        # 低信頼の axis は「分からない = 中立」扱いで必ず母数に含める。
        # これで「1 axis だけ評価可能で sim=1.0 → 全体 100%」のバグを防ぐ。
        effective_sim = conf * sim + (1.0 - conf) * 0.5
        sum_weighted_effective += effective_sim * weight
        sum_weight += weight

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

    total = (sum_weighted_effective / sum_weight * 100.0) if sum_weight > 0 else 0.0

    return MatchResult(
        drep_id=drep_id,
        total_score=round(total, 1),
        summary=summary,
        summary_en=summary_en,
        axis_details=details,
        matched_axes=matched,
        mismatched_axes=mismatched,
        low_confidence_axes=low_conf,
        reasoning_disclosure_rate=float(drep_row.get("reasoning_disclosure_rate") or 0.0),
        analyzed_vote_count=int(drep_row.get("analyzed_vote_count") or 0),
        evidence_per_axis=evidence if isinstance(evidence, dict) else {},
    )


def _fetch_and_score(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    *,
    only_active: bool = True,
) -> list[tuple[MatchResult, dict[str, Any]]]:
    """全 DRep プロファイルを取得して match score を計算する内部ヘルパー。

    quality filter:
      - dp.analyzed_vote_count >= MIN_ANALYZED_VOTE_COUNT
      - dp.reasoning_disclosure_rate >= MIN_REASONING_DISCLOSURE_RATE
      - REQUIRE_GIVEN_NAME=True なら d.given_name IS NOT NULL AND <> ''
    amount (委任量) はソート / フィルタには使わない。
    結果: [(MatchResult, drep_row dict), ...] (未ソート)
    """
    sql = """
        SELECT dp.drep_id, dp.profile_json, dp.confidence_json,
               dp.evidence_json, dp.summary, dp.summary_en,
               dp.reasoning_disclosure_rate, dp.analyzed_vote_count,
               d.given_name, d.image_url, d.drep_status, d.registered, d.amount
          FROM drep_profiles dp
          JOIN dreps d ON d.drep_id = dp.drep_id
         WHERE dp.analyzed_vote_count >= ?
           AND dp.reasoning_disclosure_rate >= ?
           AND d.registered = 1
    """
    params: list[Any] = [
        int(config.MIN_ANALYZED_VOTE_COUNT),
        float(config.MIN_REASONING_DISCLOSURE_RATE),
    ]
    if only_active:
        sql += " AND d.drep_status = 'active'"
    if config.REQUIRE_GIVEN_NAME:
        sql += " AND d.given_name IS NOT NULL AND d.given_name <> ''"

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
    """quality filter を通った DRep プロファイルから match 上位 N 件を返す。

    委任量 (amount) はソートに使わず、マッチ度のみで並べる。
    influence power に依存しない liquid democracy 的な並べ方。
    """
    scored = _fetch_and_score(user_vector, axis_weights, only_active=only_active)
    # 総合スコア降順 → 投票実績多い順 (タイブレーク)
    scored.sort(key=lambda t: (-t[0].total_score, -int(t[0].analyzed_vote_count or 0)))
    return [r for r, _ in scored[:max(1, int(limit))]]
