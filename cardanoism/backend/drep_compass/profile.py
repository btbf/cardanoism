"""drep_compass.profile
DRep の過去の投票履歴 × Cardanoism独自タグ から 11 axis 価値観プロファイルを生成。

入力:
  - proposal_votes (voter_role='DRep', voter_id=<drep_id>) の Yes/No/Abstain
  - gov_action_tags (各 GA のタグ群)

出力:
  - final_score: axis ごとに 0.0〜1.0 (中立 0.5)
  - confidence:  axis ごとに 0.0〜1.0
  - raw_score:   debug 用に -1.0〜+1.0 の生スコア
  - participation_rate, reasoning_disclosure_rate
  - evidence: 各 axis を上げ下げした投票の根拠リスト

DB に書き込むのは drep_compass.api.calculate_drep_profile()。本モジュールは
集計ロジックだけを持つ (テスト可能性のため)。

spec 第 4 節「DRepプロファイル生成」を厳守。
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.drep_compass import config
from cardanoism.backend.drep_compass.taxonomy import AXES, AXES_SET

logger = logging.getLogger(__name__)


# ── タグ → axis 寄与マッピング ─────────────────────────────
# (tag) -> { axis: (yes_step, no_step) }
# Yes 投票で yes_step が axis raw_score に加算、No 投票で no_step が加算。
# Abstain は 0 加算 (axis に影響しない、参加率には反映)。
#
# spec 第 4 節「タグ×投票で axis を更新」を厳守。
# 「重要補正」(marketing + kpi_unclear に No の場合) は post-pass で処理。
_TAG_AXIS_STEP: dict[str, dict[str, tuple[float, float]]] = {
    # large_budget
    "large_budget": {
        "growth_investment":   (+1.0, -1.0),
        "treasury_discipline": (-1.0, +1.0),
    },
    # recurring_budget / operational_budget
    "recurring_budget": {
        "institutional_continuity": (+1.0,  0.0),
        "treasury_discipline":      ( 0.0, +1.0),
    },
    "operational_budget": {
        "institutional_continuity": (+1.0,  0.0),
        "treasury_discipline":      ( 0.0, +1.0),
    },
    # core_development / infrastructure / developer_experience / long_term_research
    "core_development":       {"technical_foundation": (+1.0, -1.0)},
    "infrastructure":         {"technical_foundation": (+1.0, -1.0)},
    "developer_experience":   {"technical_foundation": (+1.0, -1.0)},
    "long_term_research":     {"technical_foundation": (+1.0, -1.0)},
    # ecosystem / dapp / wallet / defi / user_adoption
    "ecosystem": {
        "ecosystem_expansion": (+1.0, -1.0),
        "growth_investment":   (+1.0,  0.0),
    },
    "dapp": {
        "ecosystem_expansion": (+1.0, -1.0),
        "growth_investment":   (+1.0,  0.0),
    },
    "wallet": {
        "ecosystem_expansion": (+1.0, -1.0),
        "growth_investment":   (+1.0,  0.0),
    },
    "defi": {
        "ecosystem_expansion": (+1.0, -1.0),
        "growth_investment":   (+1.0,  0.0),
    },
    "user_adoption": {
        "ecosystem_expansion": (+1.0, -1.0),
        "growth_investment":   (+1.0,  0.0),
    },
    # marketing / event / awareness
    "marketing": {
        "marketing_support":   (+1.0, -1.0),
        "growth_investment":   (+1.0,  0.0),
        "treasury_discipline": ( 0.0, +1.0),
    },
    "event": {
        "marketing_support":   (+1.0, -1.0),
        "growth_investment":   (+1.0,  0.0),
        "treasury_discipline": ( 0.0, +1.0),
    },
    "awareness": {
        "marketing_support":   (+1.0, -1.0),
        "growth_investment":   (+1.0,  0.0),
        "treasury_discipline": ( 0.0, +1.0),
    },
    # existing_entity / new_team / individual_contributor / regional_focus
    "existing_entity": {
        "institutional_continuity": (+1.0, -1.0),
        "decentralized_allocation": ( 0.0, +1.0),
    },
    "new_team": {
        "decentralized_allocation": (+1.0, -1.0),
    },
    "individual_contributor": {
        "decentralized_allocation": (+1.0, -1.0),
    },
    "regional_focus": {
        "decentralized_allocation": (+1.0, -1.0),
    },
    # parameter_change / hard_fork
    "parameter_change": {
        "protocol_innovation":   (+1.0, -1.0),
        "protocol_conservatism": (-1.0, +1.0),
    },
    "hard_fork": {
        "protocol_innovation":   (+1.0, -1.0),
        "protocol_conservatism": (-1.0, +1.0),
    },
    # quality_unclear 系
    "kpi_unclear": {
        "treasury_discipline": (-1.0, +1.0),
        "transparency_focus":  (-1.0, +1.0),
    },
    "milestone_unclear": {
        "treasury_discipline": (-1.0, +1.0),
        "transparency_focus":  (-1.0, +1.0),
    },
    "budget_unclear": {
        "treasury_discipline": (-1.0, +1.0),
        "transparency_focus":  (-1.0, +1.0),
    },
    "accountability_unclear": {
        "treasury_discipline": (-1.0, +1.0),
        "transparency_focus":  (-1.0, +1.0),
    },
    "transparency_low": {
        "treasury_discipline": (-1.0, +1.0),
        "transparency_focus":  (-1.0, +1.0),
    },
    # quality_defined 系
    "kpi_defined":            {"transparency_focus": (+1.0, -1.0)},
    "milestone_based":        {"transparency_focus": (+1.0, -1.0)},
    "accountability_defined": {"transparency_focus": (+1.0, -1.0)},
    "transparency_high":      {"transparency_focus": (+1.0, -1.0)},
}


@dataclass
class _AxisAcc:
    """axis ごとの集計バケット。"""
    raw_score: float = 0.0
    related_vote_count: int = 0   # この axis に寄与した投票 (Yes/No) の数
    has_rationale: bool = False    # rationale 付き投票が 1 件でもあったか
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DrepProfileResult:
    """1 DRep のプロファイル計算結果 (DB INSERT 直前の形)。"""
    drep_id: str
    final_score: dict[str, float]
    raw_score: dict[str, float]
    confidence: dict[str, float]
    participation_rate: float
    reasoning_disclosure_rate: float
    analyzed_vote_count: int
    eligible_action_count: int
    evidence: dict[str, list[dict[str, Any]]]


def _is_quality_unclear(tags: set[str]) -> bool:
    return bool(tags & {
        "kpi_unclear", "milestone_unclear", "budget_unclear",
        "accountability_unclear", "transparency_low",
    })


def _is_marketing_like(tags: set[str]) -> bool:
    return bool(tags & {"marketing", "event", "awareness"})


def _apply_vote(
    acc: dict[str, _AxisAcc],
    tags: set[str],
    vote: str,
    has_rationale: bool,
    proposal_id: str,
):
    """1 投票がこの GA のタグ群経由で各 axis に寄与する分を加算する。

    重要補正:
      marketing + kpi_unclear に No の場合、marketing_support を下げすぎず
      treasury_discipline / transparency_focus を上げる。
      (spec 第 4 節「重要補正」)
    """
    if vote == "Abstain":
        # Abstain は axis スコアに影響させない (参加率には別途反映)
        return

    sign = 0
    if vote == "Yes":
        sign = +1
    elif vote == "No":
        sign = -1
    else:
        return  # 想定外 vote 値

    marketing_caution = (sign == -1
                         and _is_marketing_like(tags)
                         and _is_quality_unclear(tags))

    for tag in tags:
        steps = _TAG_AXIS_STEP.get(tag)
        if not steps:
            continue
        for axis, (yes_step, no_step) in steps.items():
            step = yes_step if sign > 0 else no_step
            if step == 0.0:
                continue

            # 重要補正: marketing 系タグかつ品質不明タグもある No 投票では
            # marketing_support / growth_investment への減少幅を半分にする
            # (反対は「カテゴリ反対」ではなく「品質への慎重」可能性を考慮)
            if marketing_caution and tag in {"marketing", "event", "awareness"} \
               and axis in {"marketing_support", "growth_investment"}:
                step = step * 0.5

            entry = acc.setdefault(axis, _AxisAcc())
            entry.raw_score += step
            entry.related_vote_count += 1
            if has_rationale:
                entry.has_rationale = True
            entry.evidence.append({
                "proposal_id": proposal_id,
                "tag": tag,
                "vote": vote,
                "step": round(step, 3),
            })


def compute_profile_from_rows(
    drep_id: str,
    vote_rows: list[dict[str, Any]],
    tag_rows: list[dict[str, Any]],
) -> DrepProfileResult:
    """テスト可能性のため、SQL を切り離した純粋ロジック。

    Args:
      vote_rows: [{proposal_id, vote, has_rationale}, ...]
                 vote: "Yes" / "No" / "Abstain" のいずれか
                 (シンプル化方針により、DRep が実際に投票した GA だけが対象)
      tag_rows:  [{proposal_id, tag}, ...] (gov_action_tags 全件)

    Returns:
      DrepProfileResult

    アルゴリズム:
      1. proposal_id → set(tag) のマップを構築
      2. 各 vote_row について タグ × vote を _apply_vote で加算
         (Yes / No 票だけが axis スコアに影響、Abstain は中立扱い)
      3. 各 axis について normalized = (raw + 1) / 2 にクランプ
         confidence = min(1.0, related_vote_count / 5) + rationale bonus
         final = 0.5 * (1 - confidence) + normalized * confidence
      4. reasoning_disclosure_rate = rationale 付き / 投票総数
      5. participation_rate / eligible_action_count は廃止 (シンプル化)
    """
    # tag マップ
    ga_tags: dict[str, set[str]] = defaultdict(set)
    for row in tag_rows:
        pid = row.get("proposal_id")
        tag = row.get("tag")
        if pid and tag:
            ga_tags[str(pid)].add(str(tag))

    # 投票集計 (vote_rows は既に DRep の実投票のみ)
    acc: dict[str, _AxisAcc] = {}
    total_actual_votes = 0
    rationale_count = 0

    for vrow in vote_rows:
        pid = str(vrow.get("proposal_id") or "")
        vote = str(vrow.get("vote") or "").strip()
        has_rationale = bool(vrow.get("has_rationale"))

        if vote in ("Yes", "No", "Abstain"):
            total_actual_votes += 1
            if has_rationale:
                rationale_count += 1

        if vote in ("Yes", "No"):
            tags = ga_tags.get(pid, set())
            if tags:
                _apply_vote(acc, tags, vote, has_rationale, pid)

    # axis ごとに final_score / confidence
    final_score: dict[str, float] = {}
    raw_score: dict[str, float] = {}
    confidence: dict[str, float] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}

    for axis in AXES:
        a = acc.get(axis)
        if a is None or a.related_vote_count <= 0:
            # データなし — 中立 0.5、confidence 0
            final_score[axis] = config.NEUTRAL_MIDPOINT
            raw_score[axis] = 0.0
            confidence[axis] = 0.0
            evidence[axis] = []
            continue

        # raw_score は集計したまま (-related_count 〜 +related_count) なので
        # 正規化のために件数で割って [-1, +1] に収める
        normalized_raw = a.raw_score / max(1, a.related_vote_count)
        # クランプ
        normalized_raw = max(-1.0, min(1.0, normalized_raw))

        # 0.0〜1.0 へ
        normalized = (normalized_raw + 1.0) / 2.0

        conf = min(1.0, a.related_vote_count / config.CONFIDENCE_VOTE_TARGET)
        if a.has_rationale:
            conf = min(1.0, conf + config.RATIONALE_CONFIDENCE_BONUS)

        # final_score = 中立に向けて confidence で引き戻す
        final = config.NEUTRAL_MIDPOINT * (1.0 - conf) + normalized * conf

        final_score[axis] = round(final, 4)
        raw_score[axis] = round(normalized_raw, 4)
        confidence[axis] = round(conf, 4)
        evidence[axis] = a.evidence[:20]  # 上限 20 件 (DB JSON 肥大化防止)

    # reasoning_disclosure axis は別途計算 (rationale 公開率そのもの)
    if total_actual_votes > 0:
        disclosure = rationale_count / total_actual_votes
    else:
        disclosure = 0.0
    final_score["reasoning_disclosure"] = round(disclosure, 4)
    raw_score["reasoning_disclosure"] = round(disclosure * 2.0 - 1.0, 4)
    # disclosure 自体が観測値なので confidence は投票総数で決める
    conf_dis = min(1.0, total_actual_votes / config.CONFIDENCE_VOTE_TARGET)
    confidence["reasoning_disclosure"] = round(conf_dis, 4)

    reasoning_disclosure_rate = disclosure  # 0.0〜1.0

    # participation_rate / eligible_action_count は廃止 (シンプル化方針)。
    # DB スキーマ互換性のため列は残置し、固定値を書き込む:
    #   participation_rate = 1.0 (vote_rows は実投票のみなので)
    #   eligible_action_count = 分析対象投票数と同じ
    return DrepProfileResult(
        drep_id=drep_id,
        final_score=final_score,
        raw_score=raw_score,
        confidence=confidence,
        participation_rate=1.0 if total_actual_votes > 0 else 0.0,
        reasoning_disclosure_rate=round(reasoning_disclosure_rate, 4),
        analyzed_vote_count=total_actual_votes,
        eligible_action_count=total_actual_votes,
        evidence=evidence,
    )


# ── DB I/O ─────────────────────────────────────────────────


def _fetch_vote_and_tag_rows(drep_id: str) -> tuple[list[dict], list[dict]]:
    """DB から 1 DRep の vote_rows と全 GA の tag_rows を取得する。

    シンプル化方針:
      - DRep が実際に投票した GA だけが分析対象 (Yes / No / Abstain いずれか)
      - GA のステータス (active / ratified / dropped / expired) は問わない
      - 未投票の GA はそもそも思想マッチの判断材料にならないため母数に入れない
      → SQL は proposal_votes だけを INNER で取得する
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT pv.proposal_id,
                   pv.vote,
                   CASE
                     WHEN (pv.rationale IS NOT NULL AND pv.rationale <> '')
                       OR (pv.meta_url IS NOT NULL AND pv.meta_url <> '')
                     THEN 1 ELSE 0
                   END AS has_rationale
              FROM proposal_votes pv
             WHERE pv.voter_role = 'DRep'
               AND pv.voter_id   = ?
            """,
            (str(drep_id),),
        )
        vote_rows = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT gov_action_id AS proposal_id, tag
              FROM gov_action_tags
            """
        )
        tag_rows = [dict(r) for r in cursor.fetchall()]
    return vote_rows, tag_rows


def upsert_drep_profile(result: DrepProfileResult) -> None:
    """計算結果を drep_profiles テーブルに UPSERT する。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO drep_profiles (
              drep_id, profile_json, confidence_json, raw_score_json,
              participation_rate, reasoning_disclosure_rate,
              analyzed_vote_count, eligible_action_count,
              analysis_version, evidence_json, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
            ON DUPLICATE KEY UPDATE
              profile_json              = VALUES(profile_json),
              confidence_json           = VALUES(confidence_json),
              raw_score_json            = VALUES(raw_score_json),
              participation_rate        = VALUES(participation_rate),
              reasoning_disclosure_rate = VALUES(reasoning_disclosure_rate),
              analyzed_vote_count       = VALUES(analyzed_vote_count),
              eligible_action_count     = VALUES(eligible_action_count),
              analysis_version          = VALUES(analysis_version),
              evidence_json             = VALUES(evidence_json),
              calculated_at             = NOW()
            """,
            (
                result.drep_id,
                json.dumps(result.final_score, ensure_ascii=False),
                json.dumps(result.confidence, ensure_ascii=False),
                json.dumps(result.raw_score, ensure_ascii=False),
                float(result.participation_rate),
                float(result.reasoning_disclosure_rate),
                int(result.analyzed_vote_count),
                int(result.eligible_action_count),
                config.ANALYSIS_VERSION,
                json.dumps(result.evidence, ensure_ascii=False),
            ),
        )
        conn.commit()


def calculate_and_save(drep_id: str) -> DrepProfileResult:
    """1 DRep のプロファイルを計算して DB UPSERT する高レベル関数。"""
    vote_rows, tag_rows = _fetch_vote_and_tag_rows(drep_id)
    result = compute_profile_from_rows(drep_id, vote_rows, tag_rows)
    upsert_drep_profile(result)
    return result
