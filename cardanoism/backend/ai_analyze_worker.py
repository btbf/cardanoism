"""
ai_analyze_worker.py
1 つの GA を分析するエントリポイント。

- Phase 3 の Ogmios リスナーから呼ばれる: enqueue 後にバックグラウンドで実行
- Phase 3.5 のバッチからも呼ばれる: 初回同期で対象 GA をループ実行
- 単体実行も可能（CLI スクリプトとして使う場合の例は ai_analyze_main を参照）

責務:
1. governance_ai_db.claim_next で 1 件取得（atomic claim）
2. governance_actions から本体取得
3. 憲法本文取得（in-process キャッシュで複数件分析時の重複フェッチ回避）
4. ai_client.analyze_proposal を呼ぶ
5. governance_ai_db.save_result / save_failure に書き戻す
"""
from __future__ import annotations

import logging
import os
import socket
import time

from cardanoism.backend import ai_client, governance_ai_db
from cardanoism.backend.constitution_fetcher import (
    fetch_constitution_text, get_latest_constitution_meta_url,
)
from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


# プロセス内キャッシュ: 憲法本文の取得は数秒かかるため、複数 GA をまとめて
# 処理する場合に毎回フェッチしないよう同一プロセス内で再利用する。
# キーは meta_url。新しい NewConstitution が enacted されると DB から
# 取れる meta_url が変わるので、自動的にキャッシュ無効化される。
_constitution_cache: dict[str, str] = {}  # {meta_url: text}


def _get_constitution_cached() -> tuple[str | None, str | None]:
    """憲法本文を取得（プロセス内キャッシュ）。
    DB から最新の meta_url を毎回引き、キャッシュキーと比較する。
    Returns: (text, meta_url) または (None, None)。
    """
    latest_url = get_latest_constitution_meta_url()
    if not latest_url:
        return None, None

    cached_text = _constitution_cache.get(latest_url)
    if cached_text:
        return cached_text, latest_url

    text, used_url = fetch_constitution_text(latest_url)
    if text and used_url:
        # 新規 enacted で url が変わった場合、古いエントリを掃除
        _constitution_cache.clear()
        _constitution_cache[used_url] = text
        return text, used_url
    return None, latest_url


def invalidate_constitution_cache() -> None:
    """強制再 fetch したいときに呼ぶ（通常は url 変更で自動無効化される）。"""
    _constitution_cache.clear()


def _make_worker_id() -> str:
    """ホスト名 + PID + epoch を結合した worker_id を生成（衝突回避）。"""
    return f"{socket.gethostname()}-{os.getpid()}-{int(time.time())}"[:64]


def _load_proposal(proposal_id: str) -> dict | None:
    """governance_actions から AI 分析に必要なフィールドを取得する。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, proposal_type,
                   title, title_ja,
                   `abstract`, abstract_ja,
                   motivation, motivation_ja,
                   rationale, rationale_ja,
                   withdrawal_total_lovelace
            FROM governance_actions
            WHERE proposal_id = ?
            LIMIT 1
            """,
            (str(proposal_id),),
        )
        row = cursor.fetchone()
    return dict(row) if row else None


def analyze_claimed(proposal_id: str) -> bool:
    """既に analyzing 状態でクレーム済みの proposal_id を実際に分析する。

    内部で claim はしない。常駐ワーカー (ga_ai_worker.py) が
    governance_ai_db.claim_next で取得した行をこの関数に渡す。

    Returns: 成功時 True / 何かしらの理由で失敗（save_failure 済み）なら False。
    """
    proposal = _load_proposal(proposal_id)
    if proposal is None:
        msg = f"governance_actions に proposal_id={proposal_id} が見つかりません"
        logger.warning(msg)
        governance_ai_db.save_failure(proposal_id, msg)
        return False

    text, meta_url = _get_constitution_cached()
    if not text:
        msg = "憲法本文の取得に失敗しました（IPFS gateway 全滅 or 未 enacted）"
        logger.warning(msg)
        governance_ai_db.save_failure(proposal_id, msg)
        return False

    try:
        result = ai_client.analyze_proposal(proposal, text)
    except Exception as e:
        logger.exception("analyze_proposal failed for %s: %s", proposal_id, e)
        governance_ai_db.save_failure(proposal_id, f"{type(e).__name__}: {e}")
        return False

    try:
        governance_ai_db.save_result(
            proposal_id,
            result.payload,
            constitution_meta_url=meta_url,
            model_id=result.model_id,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            cost_usd=result.cost_usd,
        )
    except Exception as e:
        logger.exception("save_result failed for %s: %s", proposal_id, e)
        governance_ai_db.save_failure(proposal_id, f"save_result: {e}")
        return False

    logger.info(
        "analyze_claimed done: %s (tokens in=%d/cached=%d out=%d cost=$%.4f)",
        proposal_id,
        result.tokens_input,
        result.tokens_cached_input,
        result.tokens_output,
        result.cost_usd,
    )
    return True


def analyze_one(proposal_id: str, *, worker_id: str | None = None) -> bool:
    """指定された proposal_id を単体で分析する（手動実行 / リカバリ用）。

    内部で claim を試みるため、他ワーカーが先取済み or 既に analyzed の場合は
    False を返して何もしない。常駐ワーカーは claim_next + analyze_claimed を直接
    呼ぶこと。
    """
    wid = worker_id or _make_worker_id()

    if not _claim_specific(proposal_id, wid):
        logger.info("analyze_one: %s already claimed by another worker, skip", proposal_id)
        return False
    return analyze_claimed(proposal_id)


def _claim_specific(proposal_id: str, worker_id: str) -> bool:
    """指定 proposal_id を pending/failed → analyzing に状態遷移させる。
    既に他ワーカーが取っている / analyzed なら False。
    """
    with get_db() as (cursor, conn):
        # 行が無ければ enqueue してから claim する（手動実行用フォールバック）
        cursor.execute(
            "INSERT IGNORE INTO governance_ai_analysis (proposal_id, status) VALUES (?, 'pending')",
            (str(proposal_id),),
        )
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
            (str(worker_id)[:64], str(proposal_id)),
        )
        ok = (cursor.rowcount or 0) > 0
        conn.commit()
    return ok
