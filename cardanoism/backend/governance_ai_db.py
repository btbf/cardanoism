"""
governance_ai_db.py
governance_ai_analysis テーブルの読み書き。

呼び出し元:
- ogmios_listener.py:        GA 提出検知時に enqueue
- ジョブワーカー (Phase 3):    claim → save_result / save_failure
- notify_worker.py (Phase 3.5): 初回バッチで対象 GA を bulk_enqueue
- GovernanceState (Phase 3):   詳細ページ表示時に get_analysis
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


# 同時実行されたジョブが死んだ場合に再回収するためのタイムアウト
_STALE_ANALYZING_AFTER = timedelta(minutes=10)


# ─── 1. enqueue ────────────────────────────────────────────────────────────────

def enqueue(proposal_id: str) -> bool:
    """proposal_id を pending 状態で投入。既存行があれば何もしない。
    Returns: 新規挿入したら True、既存行があったら False。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT IGNORE INTO governance_ai_analysis (proposal_id, status)
            VALUES (?, 'pending')
            """,
            (str(proposal_id),),
        )
        affected = cursor.rowcount or 0
        conn.commit()
    return affected > 0


def bulk_enqueue(proposal_ids: list[str]) -> int:
    """複数 proposal_id を一括 enqueue。返り値は新規挿入された件数。"""
    if not proposal_ids:
        return 0
    rows = [(str(pid),) for pid in proposal_ids]
    with get_db() as (cursor, conn):
        cursor.executemany(
            """
            INSERT IGNORE INTO governance_ai_analysis (proposal_id, status)
            VALUES (?, 'pending')
            """,
            rows,
        )
        inserted = cursor.rowcount or 0
        conn.commit()
    return int(inserted)


# ─── 2. claim (atomic) ─────────────────────────────────────────────────────────

def claim_next(worker_id: str) -> str | None:
    """次の処理対象を排他取得する。
    pending または failed の中から 1 件選び、analyzing 状態に遷移させて proposal_id を返す。
    競合時は他ワーカーが取った扱いで None。
    """
    with get_db() as (cursor, conn):
        # 候補を 1 件 SELECT FOR UPDATE
        cursor.execute(
            """
            SELECT proposal_id FROM governance_ai_analysis
            WHERE status IN ('pending', 'failed')
            ORDER BY enqueued_at ASC
            LIMIT 1
            FOR UPDATE
            """
        )
        row = cursor.fetchone()
        if not row:
            conn.commit()
            return None

        pid = row["proposal_id"]
        cursor.execute(
            """
            UPDATE governance_ai_analysis
            SET status = 'analyzing',
                worker_id = ?,
                started_at = NOW(),
                attempts = attempts + 1,
                last_error = NULL
            WHERE proposal_id = ? AND status IN ('pending', 'failed')
            """,
            (str(worker_id)[:64], pid),
        )
        if cursor.rowcount == 0:
            conn.commit()
            return None
        conn.commit()
    return str(pid)


def reclaim_stale(now: datetime | None = None) -> int:
    """analyzing のままタイムアウトした行を pending に戻す。返り値は復元件数。
    ジョブワーカー再起動 / クラッシュからの復旧用。
    """
    cutoff = (now or datetime.now(timezone.utc)) - _STALE_ANALYZING_AFTER
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            UPDATE governance_ai_analysis
            SET status = 'pending', worker_id = NULL, started_at = NULL
            WHERE status = 'analyzing' AND started_at < ?
            """,
            (cutoff,),
        )
        affected = cursor.rowcount or 0
        conn.commit()
    return int(affected)


# ─── 3. save result / failure ──────────────────────────────────────────────────

def save_result(
    proposal_id: str,
    payload: dict[str, Any],
    *,
    constitution_meta_url: str | None,
    model_id: str,
    tokens_input: int,
    tokens_output: int,
    cost_usd: float,
) -> None:
    """analyze_proposal 成功時の結果を analyzed として書き込む。"""
    constitution = payload.get("constitution", {}) or {}
    pillars = payload.get("pillars", []) or []
    related = payload.get("related_kpis", []) or []
    articles = constitution.get("articles", []) or []
    concerns_ja = constitution.get("concerns_ja", []) or []
    concerns_en = constitution.get("concerns_en", []) or []

    score_raw = constitution.get("score")
    try:
        score = max(0, min(100, int(score_raw))) if score_raw is not None else None
    except (TypeError, ValueError):
        score = None

    with get_db() as (cursor, conn):
        cursor.execute(
            """
            UPDATE governance_ai_analysis
            SET status = 'analyzed',
                completed_at = NOW(),
                last_error = NULL,
                constitution_score      = ?,
                constitution_verdict_ja = ?,
                constitution_verdict_en = ?,
                constitution_summary_ja = ?,
                constitution_summary_en = ?,
                articles_json    = ?,
                concerns_ja_json = ?,
                concerns_en_json = ?,
                pillars_json     = ?,
                related_kpis_json = ?,
                model_id              = ?,
                constitution_meta_url = ?,
                tokens_input  = ?,
                tokens_output = ?,
                cost_usd      = ?
            WHERE proposal_id = ?
            """,
            (
                score,
                (constitution.get("verdict_ja") or "")[:64],
                (constitution.get("verdict_en") or "")[:64],
                constitution.get("summary_ja") or "",
                constitution.get("summary_en") or "",
                json.dumps(articles, ensure_ascii=False),
                json.dumps(concerns_ja, ensure_ascii=False),
                json.dumps(concerns_en, ensure_ascii=False),
                json.dumps(pillars, ensure_ascii=False),
                json.dumps(related, ensure_ascii=False),
                str(model_id)[:64],
                constitution_meta_url,
                int(tokens_input),
                int(tokens_output),
                float(cost_usd),
                str(proposal_id),
            ),
        )
        conn.commit()


def save_failure(proposal_id: str, error_message: str) -> None:
    """analyze 失敗時に failed 状態として記録する。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            UPDATE governance_ai_analysis
            SET status = 'failed',
                completed_at = NOW(),
                last_error = ?
            WHERE proposal_id = ?
            """,
            (str(error_message)[:65535], str(proposal_id)),
        )
        conn.commit()


# ─── 4. read ───────────────────────────────────────────────────────────────────

def get_analysis(proposal_id: str) -> dict[str, Any] | None:
    """1 件の分析結果を取得（GA 詳細ページが呼ぶ）。
    json カラムはパース済みで返す。行が無ければ None。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT * FROM governance_ai_analysis WHERE proposal_id = ?",
            (str(proposal_id),),
        )
        row = cursor.fetchone()
    if not row:
        return None

    result = dict(row)
    for key in ("articles_json", "concerns_ja_json", "concerns_en_json",
                "pillars_json", "related_kpis_json"):
        raw = result.get(key)
        if raw:
            try:
                result[key] = json.loads(raw)
            except (TypeError, ValueError):
                result[key] = []
        else:
            result[key] = []
    return result


def requeue(proposal_id: str) -> bool:
    """1 件の analysis を pending に戻して再分析対象にする（status 不問）。
    行が存在しなければ INSERT IGNORE で新規作成する。
    Returns: 行を pending に戻した（or 新規作成した）なら True。
    """
    with get_db() as (cursor, conn):
        # 行が無ければ作る
        cursor.execute(
            "INSERT IGNORE INTO governance_ai_analysis (proposal_id, status) VALUES (?, 'pending')",
            (str(proposal_id),),
        )
        inserted = cursor.rowcount or 0
        # 既存行を pending に戻す（INSERT IGNORE が効かなかった場合）
        cursor.execute(
            """
            UPDATE governance_ai_analysis
            SET status = 'pending',
                worker_id = NULL,
                started_at = NULL,
                completed_at = NULL,
                last_error = NULL
            WHERE proposal_id = ?
            """,
            (str(proposal_id),),
        )
        updated = cursor.rowcount or 0
        conn.commit()
    return (inserted > 0) or (updated > 0)


def requeue_all(*, only_analyzed: bool = True, active_only: bool = True) -> int:
    """analyzed 行を pending に戻す（status 不問なら only_analyzed=False）。

    active_only=True (デフォルト) の場合、governance_actions と JOIN し、
    Active な提案 (ratified/enacted/dropped/expired すべて NULL) だけに絞る。
    既に決着済みの古い GA を再分析するのは無駄なので、通常はこの動作を使う。

    分析中（analyzing）の行は active_only=False でも触らない（only_analyzed=False
    と組み合わせた場合のみ全 status を初期化）。

    Returns: 影響を受けた件数。
    """
    status_clause = "aia.status = 'analyzed'" if only_analyzed else "1=1"
    active_clause = (
        "ga.ratified_epoch IS NULL "
        "AND ga.enacted_epoch IS NULL "
        "AND ga.dropped_epoch IS NULL "
        "AND ga.expired_epoch IS NULL"
        if active_only else "1=1"
    )
    sql = f"""
        UPDATE governance_ai_analysis aia
        JOIN governance_actions ga ON ga.proposal_id = aia.proposal_id
        SET aia.status = 'pending',
            aia.worker_id = NULL,
            aia.started_at = NULL,
            aia.completed_at = NULL,
            aia.last_error = NULL
        WHERE {status_clause}
          AND ({active_clause})
    """
    with get_db() as (cursor, conn):
        cursor.execute(sql)
        affected = cursor.rowcount or 0
        conn.commit()
    return int(affected)


def list_pending_count() -> int:
    """現在 pending / analyzing 状態にある分析件数（UI のキュー表示用）。"""
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT COUNT(*) AS c FROM governance_ai_analysis WHERE status IN ('pending', 'analyzing')"
        )
        row = cursor.fetchone()
    return int(row["c"]) if row else 0
