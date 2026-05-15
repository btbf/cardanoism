"""
vote_rationale_worker.py
proposal_votes.rationale が空の行を見つけて IPFS fetch + OpenAI 翻訳で埋める常駐ワーカー。

ogmios_listener が新規投票を即時 DB 書き込みする（meta_url のみ、rationale は空）と、
このワーカーが短間隔ポーリングで rationale 本文を取りに行く責務分離。listener は
チェーン検知に専念し、重い I/O（IPFS / OpenAI）はこのワーカーに切り出す設計。

CLI:
  python vote_rationale_worker.py
  python vote_rationale_worker.py --poll-interval 10 --fetch-limit 20 --translate-limit 10

systemd 想定: deploy/README.md / docs/realtime-notification-backend.md を参照。
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from notify_worker import check_vote_rationale_sync

logger = logging.getLogger("vote_rationale_worker")


def main():
    parser = argparse.ArgumentParser(description="Vote rationale 取得・翻訳ワーカー（常駐）")
    parser.add_argument("--poll-interval", type=int, default=10,
                        help="ポーリング間隔（秒、デフォルト 10）")
    parser.add_argument("--fetch-limit", type=int, default=20,
                        help="1 ループあたりのメタデータ取得上限（デフォルト 20）")
    parser.add_argument("--translate-limit", type=int, default=10,
                        help="1 ループあたりの OpenAI 翻訳上限（デフォルト 10）")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info(
        "vote_rationale_worker 起動 (interval=%ds, fetch_limit=%d, translate_limit=%d)",
        args.poll_interval, args.fetch_limit, args.translate_limit,
    )

    while True:
        try:
            check_vote_rationale_sync(
                fetch_limit=args.fetch_limit,
                translate_limit=args.translate_limit,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("vote_rationale 処理失敗: %s", e)
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
