"""drep_compass.api
DRepマッチング診断 (新設計) の公開関数集約モジュール。

公開関数:
  - calculate_drep_profile(drep_id)           : 1 DRep を AI 分析 + DB 保存
  - recalculate_all_drep_profiles()           : 全 active DRep を再分析
  - get_drep_profile(drep_id)                 : DB から取得 (parsed)
  - save_drep_match_answers(...)              : ユーザー回答を best-effort 保存
  - get_drep_match_answers(...)               : 保存済み回答を取得
  - list_drep_matches_for_vector(...)         : メモリ計算で TOP N 取得
  - get_questionnaire()                       : 設問定義を返す (UI 用)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.drep_compass import config
from cardanoism.backend.drep_compass.match import (
    calculate_drep_match as _calc_match,
    list_matches as _list_matches,
)
from cardanoism.backend.drep_compass.profile import (
    calculate_and_save as _profile_calc_and_save,
)
from cardanoism.backend.drep_compass.questionnaire import (
    QUESTIONS, QUESTION_TOTAL, build_user_vector,
)

logger = logging.getLogger(__name__)


# ═══ DRep プロファイル ════════════════════════════════════════════════════


def calculate_drep_profile(drep_id: str) -> dict[str, Any]:
    """1 DRep のプロファイルを集計して drep_profiles に保存し、結果を dict で返す。

    v3: axis スコアは GA per-axis タグ (governance_ai_analysis.axis_tags_json)
    の集計で決定論的に算出。最後に集計結果から AI が 1 文サマリを生成する。
    """
    result = _profile_calc_and_save(drep_id)
    return {
        "drep_id":                   result.drep_id,
        "profile":                   result.profile,
        "confidence":                result.confidence,
        "summary":                   result.summary_ja,
        "summary_en":                result.summary_en,
        "evidence":                  result.evidence,
        "analyzed_vote_count":       result.analyzed_vote_count,
        "reasoning_disclosure_rate": result.reasoning_disclosure_rate,
    }


def recalculate_all_drep_profiles(*, only_active: bool = True) -> int:
    """全 (active) DRep を再集計する。v3 では AI 不要なので高速 + ほぼ無料。"""
    sql = "SELECT drep_id FROM dreps WHERE registered = 1"
    if only_active:
        sql += " AND drep_status = 'active'"
    with get_db() as (cursor, _):
        cursor.execute(sql)
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
    """drep_profiles の 1 行を取得 (JSON はパース済み)。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT drep_id, profile_json, confidence_json, evidence_json,
                   summary, reasoning_disclosure_rate, analyzed_vote_count,
                   analysis_version, calculated_at, updated_at
              FROM drep_profiles
             WHERE drep_id = ?
            """,
            (str(drep_id),),
        )
        row = cursor.fetchone()
    if not row:
        return None
    row = dict(row)
    for jk in ("profile_json", "confidence_json", "evidence_json"):
        try:
            row[jk] = json.loads(row.get(jk) or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            row[jk] = {}
    return row


# ═══ ユーザーアンケート ════════════════════════════════════════════════════


def save_drep_match_answers(
    *,
    user_id: int | None,
    session_id: str | None,
    answers: dict[str, int],
    importance: list[str] | None = None,
) -> int:
    """ユーザーアンケート回答を best-effort で保存。"""
    if user_id is None and not session_id:
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


def get_drep_match_answers(
    *,
    user_id: int | None,
    session_id: str | None,
) -> dict | None:
    """最新の回答を 1 件返す。"""
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


def _serialize_match(r) -> dict:
    return {
        "drep_id":                   r.drep_id,
        "total_score":               r.total_score,
        "summary":                   r.summary,
        "summary_en":                r.summary_en,
        "matched_axes":              r.matched_axes,
        "mismatched_axes":           r.mismatched_axes,
        "low_confidence_axes":       r.low_confidence_axes,
        "reasoning_disclosure_rate": r.reasoning_disclosure_rate,
        "analyzed_vote_count":       r.analyzed_vote_count,
        "axis_details": [
            {
                "axis":       d.axis,
                "user_value": d.user_value,
                "drep_value": d.drep_value,
                "similarity": d.similarity,
                "confidence": d.confidence,
                "weight":     d.weight,
                "excluded":   d.excluded,
            }
            for d in r.axis_details
        ],
    }


def list_drep_matches_for_vector(
    user_vector: dict[str, float],
    axis_weights: dict[str, float],
    *,
    limit: int = config.DEFAULT_MATCH_LIMIT,
) -> list[dict]:
    """user_vector / weights を直接受け取り quality filter を通った TOP N マッチを返す。

    quality filter (config.py):
      - analyzed_vote_count >= MIN_ANALYZED_VOTE_COUNT (default 5)
      - reasoning_disclosure_rate >= MIN_REASONING_DISCLOSURE_RATE (default 0.30)
      - REQUIRE_GIVEN_NAME=True なら CIP-119 自己紹介必須
    委任量 (amount) はソート / フィルタには使わない。
    """
    results = _list_matches(user_vector, axis_weights, limit=limit, only_active=True)
    return [_serialize_match(r) for r in results]


def list_drep_matches(
    *,
    user_id: int | None,
    session_id: str | None,
    limit: int = config.DEFAULT_MATCH_LIMIT,
) -> list[dict]:
    """保存済みの回答から TOP N マッチを返す。"""
    saved = get_drep_match_answers(user_id=user_id, session_id=session_id)
    if not saved:
        return []
    user_vector, weights = build_user_vector(
        saved.get("answers") or {},
        saved.get("importance") or [],
    )
    return list_drep_matches_for_vector(user_vector, weights, limit=limit)


# ═══ 設問定義 (UI 用) ═════════════════════════════════════════════════════


def get_questionnaire() -> dict:
    """UI が設問を描画するための定義を返す。"""
    return {
        "version": config.QUESTIONNAIRE_VERSION,
        "max_important": config.MAX_IMPORTANT_AXES,
        "questions": [
            {
                "q_id":          q.q_id,
                "i18n_key":      q.i18n_key,
                "left_i18n_key": q.left_i18n_key,
                "right_i18n_key": q.right_i18n_key,
                "context_i18n_key": q.context_i18n_key,
                "axes":          list(q.axes),
            }
            for q in QUESTIONS
        ],
        "total": QUESTION_TOTAL,
    }
