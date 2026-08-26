"""listener_epoch_sync.py
Ogmios listener が epoch_start を検知したタイミングで、
エポック境界に依存する各種 *_sync を発火させる (Phase 5)。

エポック境界 (5 日に 1 回) でのみ意味がある同期処理:
  - governance.py     : GA ステータス列 (ratified/enacted/dropped/expired) の更新
  - params_sync       : プロトコルパラメータ + CC メンバー
  - treasury_sync     : treasury_snapshot / treasury_history / NCL
  - drep_sync         : amount / drep_status / active / expires_epoch_no の集計値
  - pool_sync         : live_stake / saturation / sigma 等の集計値
  - pool_block_history_sync : 直近 5 epoch のブロック生成数 + APY
  - summary_sync      : proposal_voting_summary
  - constitution_sync : 憲法本文 (NewConstitution enacted 直後のみ意味あり)

設計方針:
  - listener メインループ (ChainSync) をブロックしないよう subprocess + Thread で fire-and-forget
  - 各 sync は逐次実行 (Koios レート制限を避けるため並列化しない)
  - 失敗してもメインループに波及しない
  - listener が停止していた間のスキップは cron フォールバックで自動カバー (Phase 6 設計)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from cardanoism.backend.sync_lock import SyncLockError, sync_job_lock

logger = logging.getLogger(__name__)


# 1 sync の最大実行時間 (timeout)。pool_sync は重いので長めに。
_SYNC_TIMEOUT_SECONDS = {
    "governance":              1800,   # 30 min (フェッチ + ステータス更新)
    "params_sync":             300,
    "treasury_sync":           600,
    "drep_sync":               1800,
    "pool_sync":               2400,   # 40 min: 全プール + extended fetch
    "pool_block_history_sync": 1800,
    "summary_sync":            1800,   # 重い: 1 GA あたり数十秒
    "constitution_sync":       600,
}


# 実行順序 (依存関係を考慮した逐次実行):
#   ① governance: 新 GA / status を最新化
#   ② params_sync: NCL / treasury 計算の前提
#   ③ treasury_sync: NCL は params 後
#   ④ drep_sync: 委任量集計
#   ⑤ pool_sync: 委任量集計
#   ⑥ pool_block_history_sync: pool_sync 後 (active なプールのみ /pool_history を叩く)
#   ⑦ summary_sync: 投票集計 (重い)
#   ⑧ constitution_sync: NewConstitution enacted 後の最新 GA を見て決まる
_EPOCH_SYNC_SEQUENCE = [
    "governance",
    "params_sync",
    "treasury_sync",
    "drep_sync",
    "pool_sync",
    "pool_block_history_sync",
    "summary_sync",
    "constitution_sync",
]


def _project_root() -> Path:
    """notify_worker.py / governance.py が置かれているプロジェクトルートを返す。"""
    return Path(__file__).resolve().parents[2]


def _run_one_sync(event: str) -> int:
    """1 件の sync を subprocess で実行し、終了コードを返す。

    listener と同じ Python インタプリタ (sys.executable) を使う。
    Infisical secrets は os.environ 経由で自動継承される。
    """
    root = _project_root()
    timeout = _SYNC_TIMEOUT_SECONDS.get(event, 1800)

    if event == "governance":
        # governance.py は notify_worker.py 経由ではなく直接スクリプト実行
        cmd = [sys.executable, "cardanoism/backend/governance.py", "--no-translate"]
    else:
        cmd = [sys.executable, "notify_worker.py", "--event", event]

    logger.info("epoch_start sync: %s 起動 (cwd=%s)", event, root)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(root),
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
        if result.returncode == 0:
            logger.info("epoch_start sync: %s 完了 (rc=0)", event)
        else:
            logger.warning("epoch_start sync: %s 異常終了 (rc=%d)", event, result.returncode)
        return result.returncode
    except subprocess.TimeoutExpired:
        logger.warning("epoch_start sync: %s タイムアウト (%ds)", event, timeout)
        return -1
    except Exception as e:  # noqa: BLE001
        logger.exception("epoch_start sync: %s 起動失敗: %s", event, e)
        return -1


def _run_epoch_sync_chain(epoch_no: int) -> None:
    """エポック境界の sync 群を逐次実行する (別スレッドから呼ばれる)。"""
    try:
        with sync_job_lock("epoch_sync_chain", timeout=0) as acquired:
            if not acquired:
                logger.info(
                    "epoch_start sync chain skipped: another process is running "
                    "(epoch=%d)",
                    epoch_no,
                )
                return

            logger.info("=== epoch_start sync チェーン開始 (epoch=%d) ===", epoch_no)
            for event in _EPOCH_SYNC_SEQUENCE:
                try:
                    _run_one_sync(event)
                except Exception as e:  # noqa: BLE001
                    logger.exception("epoch_start sync chain: %s で例外 (継続): %s", event, e)
            logger.info("=== epoch_start sync チェーン完了 (epoch=%d) ===", epoch_no)
    except SyncLockError as exc:
        logger.exception(
            "epoch_start sync chain aborted because its lock is unavailable "
            "(epoch=%d): %s",
            epoch_no,
            exc,
        )


def trigger_epoch_syncs(epoch_no: int) -> None:
    """listener から呼び出すエントリポイント。

    別スレッドで sync チェーンを開始 (listener メインループはブロックしない)。
    daemon=True なので listener 終了時に未完了タスクは強制終了される。
    """
    threading.Thread(
        target=_run_epoch_sync_chain,
        args=(epoch_no,),
        name=f"epoch_sync_{epoch_no}",
        daemon=True,
    ).start()
    logger.info("epoch_start sync チェーンを別スレッドで起動 (epoch=%d)", epoch_no)
