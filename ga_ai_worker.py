"""
ga_ai_worker.py
GA AI 分析の常駐ワーカー。

- governance_ai_db.claim_next で pending / failed の行を atomic に取得
- ai_analyze_worker.analyze_claimed で実際の分析を実行
- 並列度は --concurrency (デフォルト 3)
- --poll-interval 秒ごとにキューを再走査
- 起動時 / 各サイクル前に reclaim_stale でクラッシュ復旧

systemd 等で常駐させる想定。SIGINT / SIGTERM で graceful shutdown。

使い方:
  python ga_ai_worker.py [--poll-interval 20] [--concurrency 3]

依存:
  ANTHROPIC_API_KEY ではなく GPT_API_KEY (or OPENAI_API_KEY) を使う。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cardanoism.backend import governance_ai_db
from cardanoism.backend.ai_analyze_worker import analyze_claimed

logger = logging.getLogger("ga_ai_worker")

_DEFAULT_POLL_INTERVAL_SEC = 20
_DEFAULT_CONCURRENCY = 3

_shutdown = False


def _setup_signals() -> None:
    def _handle(signum, frame):
        global _shutdown
        if not _shutdown:
            logger.info("シャットダウンシグナル受信: %s — drain 中のジョブを完了させて停止します", signum)
        _shutdown = True
    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)


def _make_drainer_worker_id(slot: int) -> str:
    """各 drainer スロット用に一意な worker_id を生成。"""
    return f"{socket.gethostname()}-{os.getpid()}-{int(time.time())}-{slot}"[:64]


async def _drain_one_slot(slot: int) -> int:
    """1 つの drainer スロットの処理ループ。
    pending が枯渇するまで連続で claim → analyze する。
    戻り値: 処理した件数。
    """
    loop = asyncio.get_running_loop()
    processed = 0
    while not _shutdown:
        worker_id = _make_drainer_worker_id(slot)
        pid = await loop.run_in_executor(None, governance_ai_db.claim_next, worker_id)
        if pid is None:
            break
        try:
            ok = await loop.run_in_executor(None, analyze_claimed, pid)
            if ok:
                processed += 1
        except Exception as e:
            logger.exception("slot=%d analyze_claimed unexpected error for %s: %s", slot, pid, e)
    return processed


async def _run_cycle(concurrency: int) -> int:
    """1 サイクル分: reclaim_stale → 並列 drainer × concurrency → 全完了待ち。
    戻り値: このサイクルで処理した合計件数。
    """
    loop = asyncio.get_running_loop()
    try:
        recovered = await loop.run_in_executor(None, governance_ai_db.reclaim_stale)
        if recovered > 0:
            logger.info("reclaim_stale: %d 件の stuck analyzing を pending に戻しました", recovered)
    except Exception as e:
        logger.warning("reclaim_stale 失敗 (継続): %s", e)

    drainers = [_drain_one_slot(slot) for slot in range(concurrency)]
    results = await asyncio.gather(*drainers, return_exceptions=True)
    total = 0
    for r in results:
        if isinstance(r, int):
            total += r
        elif isinstance(r, Exception):
            logger.warning("drainer エラー: %s", r)
    return total


async def main_async(poll_interval: int, concurrency: int) -> None:
    logger.info("ga_ai_worker 起動: poll_interval=%ds, concurrency=%d", poll_interval, concurrency)
    while not _shutdown:
        try:
            n = await _run_cycle(concurrency)
            if n > 0:
                logger.info("サイクル完了: %d 件処理", n)
        except Exception as e:
            logger.exception("サイクル中に予期しない例外: %s", e)

        if _shutdown:
            break
        # ポーリング待機（中断シグナルに反応するため細かく刻む）
        for _ in range(poll_interval):
            if _shutdown:
                break
            await asyncio.sleep(1)
    logger.info("ga_ai_worker 停止")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="GA AI 分析の常駐ワーカー")
    parser.add_argument("--poll-interval", type=int, default=_DEFAULT_POLL_INTERVAL_SEC,
                        help=f"キュー再走査の間隔（秒、デフォルト: {_DEFAULT_POLL_INTERVAL_SEC}）")
    parser.add_argument("--concurrency", type=int, default=_DEFAULT_CONCURRENCY,
                        help=f"並列度（デフォルト: {_DEFAULT_CONCURRENCY}）")
    args = parser.parse_args()

    _setup_signals()
    try:
        asyncio.run(main_async(args.poll_interval, args.concurrency))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
