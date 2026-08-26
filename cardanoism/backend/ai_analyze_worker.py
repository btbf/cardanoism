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
    fetch_constitution_text, get_latest_constitution_anchor,
)
from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


# プロセス内キャッシュ: 憲法本文の取得は数秒かかるため、複数 GA をまとめて
# 処理する場合に毎回フェッチしないよう同一プロセス内で再利用する。
# キーは meta_url。新しい NewConstitution が enacted されると DB から
# 取れる meta_url が変わるので、自動的にキャッシュ無効化される。
_constitution_cache: dict[str, tuple[str, str]] = {}  # {meta_url: (text_en, text_ja)}


def _get_constitution_cached() -> tuple[str | None, str | None, str | None]:
    """憲法本文を取得（プロセス内キャッシュ）。
    優先順位:
      1. constitution_cache テーブル (notify_worker --event constitution_sync 済み)
         → 原文 + 日本語訳の両方が取れる
      2. governance_actions の最新 enacted NewConstitution から IPFS フェッチ
         → 原文のみ、日本語訳は空文字
    Returns: (text_en, text_ja, source_url) または (None, None, None)。
    """
    # まず constitution_cache テーブルを見る（翻訳済みなら一発）
    try:
        from cardanoism.backend.constitution_db import get_constitution
        row = get_constitution()
        if row and row.get("original_text"):
            url = str(row.get("source_url") or "") or "constitution_cache"
            text_en = str(row.get("original_text") or "")
            text_ja = str(row.get("translated_text") or "")
            cached = _constitution_cache.get(url)
            if cached and cached == (text_en, text_ja):
                return text_en, text_ja, url
            _constitution_cache.clear()
            _constitution_cache[url] = (text_en, text_ja)
            return text_en, text_ja, url
    except Exception as e:
        logger.warning("constitution_cache 参照失敗 (continue with IPFS): %s", e)

    # フォールバック: IPFS 直フェッチ（日本語訳は無し）
    latest_url, latest_hash = get_latest_constitution_anchor()
    if not latest_url:
        return None, None, None
    cached = _constitution_cache.get(latest_url)
    if cached:
        return cached[0], cached[1], latest_url
    text, used_url = fetch_constitution_text(latest_url, expected_hash=latest_hash)
    if text and used_url:
        _constitution_cache.clear()
        _constitution_cache[used_url] = (text, "")
        return text, "", used_url
    return None, None, latest_url


def invalidate_constitution_cache() -> None:
    """強制再 fetch したいときに呼ぶ（通常は url 変更で自動無効化される）。"""
    _constitution_cache.clear()


def _make_worker_id() -> str:
    """ホスト名 + PID + epoch を結合した worker_id を生成（衝突回避）。"""
    return f"{socket.gethostname()}-{os.getpid()}-{int(time.time())}"[:64]


def _load_proposal(proposal_id: str) -> dict | None:
    """governance_actions から AI 分析 + ルールチェックに必要なフィールドを取得する。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, proposal_type,
                   title, title_ja,
                   `abstract`, abstract_ja,
                   motivation, motivation_ja,
                   rationale, rationale_ja,
                   references_json,
                   deposit, proposed_epoch,
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

    # 現状の AI 分析（A 方針: ファクト整理ツール）は憲法本文を参照しない。
    # 提案本文だけから summary + facts を抽出するので Constitution fetch はスキップ。
    meta_url: str | None = None

    try:
        result = ai_client.analyze_proposal(proposal, "")
    except Exception as e:
        logger.exception("analyze_proposal failed for %s: %s", proposal_id, e)
        governance_ai_db.save_failure(proposal_id, f"{type(e).__name__}: {e}")
        return False

    # 補足ファクト（NCL 上限内チェック等。AI ではなく機械計算で確実に出せる数値情報）
    try:
        supplemental = governance_ai_db.compute_supplemental_facts(proposal)
    except Exception as e:
        logger.warning("compute_supplemental_facts failed for %s: %s", proposal_id, e)
        supplemental = []

    # AI が抽出した facts に補足ファクトを末尾に追加する
    if supplemental:
        ai_facts = result.payload.get("proposal_facts") or []
        if not isinstance(ai_facts, list):
            ai_facts = []
        result.payload["proposal_facts"] = ai_facts + supplemental

    try:
        governance_ai_db.save_result(
            proposal_id,
            result.payload,
            None,  # rule_checks は撤去（補足ファクトに統合済み）
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
