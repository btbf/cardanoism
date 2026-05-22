"""fix_drep_vote_ids.py
一度きりのデータ修正スクリプト。

ogmios_listener の script credential 判定バグ（Ogmios の "from" フィールド未対応）に
より、script ベース DRep の投票が CIP-129 の鍵ヘッダ 0x22 で誤エンコードされ、
proposal_votes に間違った voter_id で記録されていた。

このスクリプトは proposal_votes の DRep 行のうち、
  - voter_id がその voter_hex の鍵ヘッダ (0x22) エンコードと一致し、かつ
  - 同じ voter_hex の script ヘッダ (0x23) エンコードが dreps テーブルに実在する
    （= 本来は script ベース DRep）
ものだけを「誤 id 行」と判定して削除する。

正規の鍵ベース DRep は script 版 id が実在しないため、絶対に誤検出しない。

デフォルトは dry-run（削除せず一覧表示のみ）。実削除は --apply。

実行:
  infisical run --env=mainnet -- python cardanoism/backend/fix_drep_vote_ids.py
  infisical run --env=mainnet -- python cardanoism/backend/fix_drep_vote_ids.py --apply
"""
from __future__ import annotations

import argparse
import logging

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.listener_governance import encode_voter_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="script DRep 投票の誤 voter_id 行を削除")
    parser.add_argument(
        "--apply", action="store_true",
        help="実際に削除する（未指定なら dry-run で一覧表示のみ）",
    )
    args = parser.parse_args()

    # 実在する DRep id の集合（Koios drep_sync が埋める dreps テーブル）
    with get_db() as (cursor, _):
        cursor.execute("SELECT drep_id FROM dreps WHERE drep_id IS NOT NULL")
        real_drep_ids = {r["drep_id"] for r in cursor.fetchall()}
    logger.info("dreps テーブルの実在 DRep id: %d 件", len(real_drep_ids))

    # proposal_votes の DRep 行（voter_hex があるもの = listener 由来）
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT id, proposal_id, voter_id, voter_hex "
            "FROM proposal_votes "
            "WHERE voter_role = 'DRep' AND voter_hex IS NOT NULL AND voter_hex <> ''"
        )
        rows = [dict(r) for r in cursor.fetchall()]
    logger.info("検査対象の DRep 投票行: %d 件", len(rows))

    wrong_ids: list[int] = []
    for r in rows:
        voter_hex = r["voter_hex"]
        key_id = encode_voter_id("DRep", voter_hex, has_script=False)    # 0x22
        script_id = encode_voter_id("DRep", voter_hex, has_script=True)  # 0x23
        if not key_id or not script_id:
            continue
        # 鍵ヘッダで記録されているが、本来は script DRep（script id が dreps に実在）
        if r["voter_id"] == key_id and script_id in real_drep_ids:
            wrong_ids.append(r["id"])
            logger.info(
                "誤 id 行: id=%d proposal=%s… 誤(鍵)=%s… 正(script)=%s…",
                r["id"], str(r["proposal_id"])[:20], key_id[:24], script_id[:24],
            )

    logger.info("誤 id 行: %d 件", len(wrong_ids))
    if not wrong_ids:
        logger.info("削除対象なし。終了。")
        return

    if not args.apply:
        logger.info("dry-run。実削除するには --apply を付けて再実行してください。")
        return

    with get_db() as (cursor, conn):
        placeholders = ",".join(["?"] * len(wrong_ids))
        cursor.execute(
            f"DELETE FROM proposal_votes WHERE id IN ({placeholders})",
            wrong_ids,
        )
        deleted = cursor.rowcount or 0
        conn.commit()
    logger.info("削除完了: %d 件", deleted)


if __name__ == "__main__":
    main()
