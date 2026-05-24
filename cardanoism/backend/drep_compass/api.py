"""drep_compass.api
DRep委任コンパス MVP の公開関数集約モジュール。

UI / cron / CLI からはこのモジュール経由で呼ぶ。
内部実装 (classifier / profile / match / questionnaire) は直接呼ばないこと。

spec 第 7 節「API / Backend functions」を厳守。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.drep_compass import config
from cardanoism.backend.drep_compass.classifier import (
    classify_governance_action as _classify_ga,
    classify_governance_action_ai_stub as _classify_ga_ai,
)
from cardanoism.backend.drep_compass.match import (
    calculate_drep_match as _calc_match,
    list_matches as _list_matches,
)
from cardanoism.backend.drep_compass.profile import (
    calculate_and_save as _profile_calc_and_save,
    compute_profile_from_rows as _profile_compute,
)
from cardanoism.backend.drep_compass.questionnaire import (
    QUESTIONS, QUESTION_TOTAL, build_user_vector,
)
from cardanoism.backend.drep_compass.taxonomy import (
    is_valid_tag,
    tag_type_of,
)

logger = logging.getLogger(__name__)


# ═══ Governance Action 分類 ═══════════════════════════════════════════════


def _fetch_ga(gov_action_id: str) -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, proposal_type, title, abstract,
                   title_ja, abstract_ja, withdrawal_total_lovelace
              FROM governance_actions
             WHERE proposal_id = ?
            """,
            (str(gov_action_id),),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def _insert_tags(gov_action_id: str, tags: list[Any]) -> int:
    """gov_action_tags に INSERT IGNORE (重複は UNIQUE で弾く)。

    Returns: 新規挿入された件数。
    """
    inserted = 0
    with get_db() as (cursor, conn):
        for t in tags:
            cursor.execute(
                """
                INSERT IGNORE INTO gov_action_tags
                  (gov_action_id, tag, tag_type, confidence, source, rationale)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(gov_action_id),
                    str(t.tag),
                    str(t.tag_type),
                    float(t.confidence),
                    str(t.source),
                    str(t.rationale)[:1000],
                ),
            )
            if cursor.rowcount:
                inserted += 1
        conn.commit()
    return inserted


def _delete_tags_by_source(gov_action_id: str, source: str) -> int:
    """指定 source のタグだけ削除 (rule / ai / manual を選択的に再分類)。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            "DELETE FROM gov_action_tags WHERE gov_action_id = ? AND source = ?",
            (str(gov_action_id), str(source)),
        )
        affected = cursor.rowcount or 0
        conn.commit()
    return affected


def classify_governance_action(gov_action_id: str) -> int:
    """1 GA をルールベースで分類し gov_action_tags へ INSERT IGNORE する。

    既存のルールタグが残っている場合はスキップ (重複は UNIQUE で弾く)。
    完全に再生成したい場合は reclassify_governance_action() を使うこと。

    Returns:
      新規 INSERT された tag 件数。
    """
    ga = _fetch_ga(gov_action_id)
    if not ga:
        logger.warning("classify_governance_action: GA not found: %s", gov_action_id)
        return 0
    tags = _classify_ga(ga)
    inserted = _insert_tags(gov_action_id, tags)
    logger.info(
        "classify_governance_action: %s → %d 件 INSERT (total candidates=%d)",
        gov_action_id, inserted, len(tags),
    )
    return inserted


def reclassify_governance_action(gov_action_id: str, *, ai: bool = False) -> int:
    """1 GA のルールタグを全削除してから再分類する。

    Args:
      ai: True にすると AI 分類器の stub も呼ぶ (現状 no-op)。

    Returns:
      新規 INSERT された tag 件数。
    """
    ga = _fetch_ga(gov_action_id)
    if not ga:
        logger.warning("reclassify_governance_action: GA not found: %s", gov_action_id)
        return 0
    _delete_tags_by_source(gov_action_id, "rule")
    if ai:
        _delete_tags_by_source(gov_action_id, "ai")
    rule_tags = _classify_ga(ga)
    ai_tags = _classify_ga_ai(ga) if ai else []
    inserted = _insert_tags(gov_action_id, list(rule_tags) + list(ai_tags))
    logger.info(
        "reclassify_governance_action: %s → %d 件 INSERT (rule=%d, ai=%d)",
        gov_action_id, inserted, len(rule_tags), len(ai_tags),
    )
    return inserted


def list_gov_action_tags(gov_action_id: str) -> list[dict]:
    """指定 GA に付いた gov_action_tags 全件を返す (UI / debug 用)。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT id, tag, tag_type, confidence, source, rationale,
                   reviewed_by, reviewed_at, created_at, updated_at
              FROM gov_action_tags
             WHERE gov_action_id = ?
             ORDER BY tag_type, tag
            """,
            (str(gov_action_id),),
        )
        return [dict(r) for r in cursor.fetchall()]


def update_gov_action_tags(
    gov_action_id: str,
    tags: list[dict[str, Any]],
    *,
    reviewed_by: str | None = None,
) -> int:
    """manual 更新 API。受け取った tags リストで gov_action_tags の manual 行を
    置き換える (rule / ai 行は触らない)。

    Args:
      tags: [{tag, confidence, rationale}] の list。tag は taxonomy 検証する。

    Returns:
      新規 INSERT された件数。
    """
    # 既存 manual 削除
    _delete_tags_by_source(gov_action_id, "manual")

    inserted = 0
    with get_db() as (cursor, conn):
        for t in tags:
            tag = str(t.get("tag") or "").strip()
            if not is_valid_tag(tag):
                logger.warning("update_gov_action_tags: invalid tag %r", tag)
                continue
            ttype = tag_type_of(tag)
            if ttype is None:
                continue
            cursor.execute(
                """
                INSERT IGNORE INTO gov_action_tags
                  (gov_action_id, tag, tag_type, confidence, source, rationale,
                   reviewed_by, reviewed_at)
                VALUES (?, ?, ?, ?, 'manual', ?, ?, NOW())
                """,
                (
                    str(gov_action_id),
                    tag,
                    ttype,
                    float(t.get("confidence") or 1.0),
                    str(t.get("rationale") or "")[:1000],
                    str(reviewed_by) if reviewed_by else None,
                ),
            )
            if cursor.rowcount:
                inserted += 1
        conn.commit()
    return inserted


# ═══ DRep プロファイル ════════════════════════════════════════════════════


def calculate_drep_profile(drep_id: str) -> dict[str, Any]:
    """1 DRep のプロファイルを計算し DB 保存。dict 形で結果を返す。"""
    result = _profile_calc_and_save(drep_id)
    return {
        "drep_id": result.drep_id,
        "final_score": result.final_score,
        "confidence": result.confidence,
        "raw_score": result.raw_score,
        "participation_rate": result.participation_rate,
        "reasoning_disclosure_rate": result.reasoning_disclosure_rate,
        "analyzed_vote_count": result.analyzed_vote_count,
        "eligible_action_count": result.eligible_action_count,
        "evidence": result.evidence,
    }


def recalculate_all_drep_profiles() -> int:
    """全 registered DRep について計算を再走らせる。

    Returns: 処理した DRep 件数。
    """
    with get_db() as (cursor, _):
        cursor.execute("SELECT drep_id FROM dreps WHERE registered = 1")
        ids = [r["drep_id"] for r in cursor.fetchall()]
    logger.info("recalculate_all_drep_profiles: target %d DReps", len(ids))
    n = 0
    for drep_id in ids:
        try:
            calculate_drep_profile(drep_id)
            n += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("calculate_drep_profile failed for %s: %s", drep_id, e)
    logger.info("recalculate_all_drep_profiles: done %d/%d", n, len(ids))
    return n


def get_drep_profile(drep_id: str) -> dict | None:
    """drep_profiles の 1 行を返す (UI 用)。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT drep_id, profile_json, confidence_json, raw_score_json,
                   participation_rate, reasoning_disclosure_rate,
                   analyzed_vote_count, eligible_action_count,
                   analysis_version, evidence_json, calculated_at, updated_at
              FROM drep_profiles
             WHERE drep_id = ?
            """,
            (str(drep_id),),
        )
        row = cursor.fetchone()
    if not row:
        return None
    row = dict(row)
    # JSON フィールドはパース済みで返す (UI が直接参照しやすいよう)
    for jk in ("profile_json", "confidence_json", "raw_score_json", "evidence_json"):
        try:
            row[jk] = json.loads(row.get(jk) or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            row[jk] = {}
    return row


# ═══ ユーザーアンケート ════════════════════════════════════════════════════


def save_drep_compass_answers(
    *,
    user_id: int | None,
    session_id: str | None,
    answers: dict[str, int],
    importance: list[str] | None = None,
) -> int:
    """アンケート回答を user_drep_compass_answers に保存。

    user_id / session_id のいずれかは必須。両方 None なら 0 を返して何もしない。

    Returns:
      新規 INSERT 行 ID (失敗時 0)。
    """
    if user_id is None and not session_id:
        logger.warning("save_drep_compass_answers: user_id / session_id がどちらも未指定")
        return 0
    importance = (importance or [])[:config.MAX_IMPORTANT_AXES]
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO user_drep_compass_answers
              (user_id, session_id, answer_json, importance_json,
               questionnaire_version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(user_id) if user_id is not None else None,
                str(session_id) if session_id else None,
                json.dumps(answers, ensure_ascii=False),
                json.dumps(importance, ensure_ascii=False),
                config.QUESTIONNAIRE_VERSION,
            ),
        )
        new_id = int(cursor.lastrowid or 0)
        conn.commit()
    return new_id


def get_drep_compass_answers(
    *,
    user_id: int | None,
    session_id: str | None,
) -> dict | None:
    """最新の回答を 1 件返す (user_id 優先、無ければ session_id)。"""
    with get_db() as (cursor, _):
        if user_id is not None:
            cursor.execute(
                """
                SELECT id, user_id, session_id, answer_json, importance_json,
                       questionnaire_version, created_at
                  FROM user_drep_compass_answers
                 WHERE user_id = ?
                 ORDER BY id DESC
                 LIMIT 1
                """,
                (int(user_id),),
            )
        elif session_id:
            cursor.execute(
                """
                SELECT id, user_id, session_id, answer_json, importance_json,
                       questionnaire_version, created_at
                  FROM user_drep_compass_answers
                 WHERE session_id = ?
                 ORDER BY id DESC
                 LIMIT 1
                """,
                (str(session_id),),
            )
        else:
            return None
        row = cursor.fetchone()
    if not row:
        return None
    row = dict(row)
    try:
        row["answers"] = json.loads(row.get("answer_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        row["answers"] = {}
    try:
        row["importance"] = json.loads(row.get("importance_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        row["importance"] = []
    return row


# ═══ マッチング ════════════════════════════════════════════════════════════


def calculate_drep_match(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    drep_id: str,
) -> dict | None:
    """1 DRep に対するマッチを計算 (dict で返す)。"""
    profile = get_drep_profile(drep_id)
    if not profile:
        return None
    # match.calculate_drep_match は profile_json / confidence_json を str 期待
    # するため再 JSON 化 (parsed の場合は dump し直す)
    row_for_match = {
        **profile,
        "profile_json":   json.dumps(profile.get("profile_json") or {},
                                     ensure_ascii=False),
        "confidence_json": json.dumps(profile.get("confidence_json") or {},
                                      ensure_ascii=False),
        "evidence_json":  json.dumps(profile.get("evidence_json") or {},
                                     ensure_ascii=False),
    }
    result = _calc_match(user_vector, axis_weights, row_for_match)
    return {
        "drep_id":                   result.drep_id,
        "total_score":               result.total_score,
        "matched_axes":              result.matched_axes,
        "mismatched_axes":           result.mismatched_axes,
        "low_confidence_axes":       result.low_confidence_axes,
        "participation_rate":        result.participation_rate,
        "reasoning_disclosure_rate": result.reasoning_disclosure_rate,
        "analyzed_vote_count":       result.analyzed_vote_count,
        "axis_details": [
            {
                "axis":         d.axis,
                "user_value":   d.user_value,
                "drep_value":   d.drep_value,
                "similarity":   d.similarity,
                "confidence":   d.confidence,
                "weight":       d.weight,
                "excluded":     d.excluded,
            }
            for d in result.axis_details
        ],
        "evidence_summary": result.evidence_summary,
    }


def list_drep_matches_for_vector(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    *,
    limit: int = config.DEFAULT_MATCH_LIMIT,
) -> list[dict]:
    """user_vector / weights を直接受け取り TOP N マッチを返す。

    UI から submit 時にメモリ内で計算する用 (DB 保存と独立)。
    """
    results = _list_matches(user_vector, axis_weights, limit=limit)
    return [
        {
            "drep_id":                   r.drep_id,
            "total_score":               r.total_score,
            "matched_axes":              r.matched_axes,
            "mismatched_axes":           r.mismatched_axes,
            "low_confidence_axes":       r.low_confidence_axes,
            "participation_rate":        r.participation_rate,
            "reasoning_disclosure_rate": r.reasoning_disclosure_rate,
            "analyzed_vote_count":       r.analyzed_vote_count,
        }
        for r in results
    ]


def list_drep_matches(
    *,
    user_id: int | None,
    session_id: str | None,
    limit: int = config.DEFAULT_MATCH_LIMIT,
) -> list[dict]:
    """保存済みの回答から TOP N マッチを返す。"""
    saved = get_drep_compass_answers(user_id=user_id, session_id=session_id)
    if not saved:
        return []
    user_vector, weights = build_user_vector(
        saved.get("answers") or {},
        saved.get("importance") or [],
    )
    results = _list_matches(user_vector, weights, limit=limit)
    return [
        {
            "drep_id":                   r.drep_id,
            "total_score":               r.total_score,
            "matched_axes":              r.matched_axes,
            "mismatched_axes":           r.mismatched_axes,
            "low_confidence_axes":       r.low_confidence_axes,
            "participation_rate":        r.participation_rate,
            "reasoning_disclosure_rate": r.reasoning_disclosure_rate,
            "analyzed_vote_count":       r.analyzed_vote_count,
        }
        for r in results
    ]


def explain_drep_match(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    drep_id: str,
) -> dict | None:
    """根拠付き match 結果を返す (DRep 詳細ページ用)。

    calculate_drep_match に加えて evidence_summary を整形して返す。
    """
    base = calculate_drep_match(user_vector, axis_weights, drep_id)
    if not base:
        return None
    # axis ごとの evidence を user の関心軸順に絞り込み
    ev = base.get("evidence_summary") or {}
    by_axis: dict[str, list[dict[str, Any]]] = {}
    for axis_detail in base.get("axis_details", []):
        axis = axis_detail["axis"]
        items = ev.get(axis) or []
        by_axis[axis] = items[:10]
    base["evidence_by_axis"] = by_axis
    return base


# ═══ 公開: 質問定義 (UI 描画用) ════════════════════════════════════════════


def get_questionnaire() -> dict:
    """UI が質問を描画するための定義を返す。i18n_key を AuthState.t で引いて表示。"""
    return {
        "version": config.QUESTIONNAIRE_VERSION,
        "max_important": config.MAX_IMPORTANT_AXES,
        "questions": [
            {"q_id": q.q_id, "i18n_key": q.i18n_key, "axes": list(q.axes)}
            for q in QUESTIONS
        ],
        "total": QUESTION_TOTAL,
    }
