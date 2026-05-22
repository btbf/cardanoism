"""fix_drep_vote_ids.py
一度きりのデータ修正スクリプト。

ogmios_listener の script credential 判定バグ（Ogmios の "from" フィールド未対応）に
より、script ベース DRep の投票が CIP-129 の鍵ヘッダ 0x22 で誤エンコードされ、
proposal_votes に間違った voter_id で記録されていた。

判定は dreps テーブルの hex（生 28byte ハッシュ）と has_script を真実とする。
bech32 の形式に依存しないので確実:
  - proposal_votes の DRep 行の voter_hex が dreps の「script ベース DRep の hex」
    集合に含まれ、かつ
  - その行の voter_id が voter_hex の鍵ヘッダ (0x22) エンコードと一致する
ものを「誤 id 行」と判定して削除する。

正規の鍵ベース DRep は hex が script 集合に入らないため、絶対に誤検出しない。

デフォルトは dry-run（削除せず一覧表示のみ）。実削除は --apply。

実行（必ず -m で。スクリプト直接実行はモジュール名衝突で失敗する:
cardanoism/backend/ が sys.path 先頭に入り blockfrost.py が本物の
blockfrost パッケージを隠してしまうため）:
  infisical run --env=mainnet -- python -m cardanoism.backend.fix_drep_vote_ids
  infisical run --env=mainnet -- python -m cardanoism.backend.fix_drep_vote_ids --apply
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

    # script ベース DRep の生ハッシュ集合（dreps.has_script=1）
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT hex FROM dreps WHERE has_script = 1 AND hex IS NOT NULL AND hex <> ''"
        )
        script_hexes = {
            str(r["hex"]).lower().strip()
            for r in cursor.fetchall() if r.get("hex")
        }
    logger.info("script ベース DRep: %d 件", len(script_hexes))

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
        hex_norm = str(r["voter_hex"]).lower().strip()
        if hex_norm not in script_hexes:
            continue  # script ベース DRep ではない → 対象外
        key_id = encode_voter_id("DRep", r["voter_hex"], has_script=False)    # 0x22
        if not key_id:
            continue
        # script DRep なのに鍵ヘッダ (0x22) で記録されている → 誤 id
        if r["voter_id"] == key_id:
            script_id = encode_voter_id("DRep", r["voter_hex"], has_script=True)
            wrong_ids.append(r["id"])
            logger.info(
                "誤 id 行: id=%d proposal=%s… 誤(鍵)=%s… 正(script)=%s…",
                r["id"], str(r["proposal_id"])[:20], key_id[:24],
                (script_id or "?")[:24],
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
