"""fix_drep_vote_ids.py
一度きりのデータ修正スクリプト。

ogmios_listener の script credential 判定バグ（Ogmios の "from" フィールド未対応）に
より、script ベース DRep の投票が CIP-129 の鍵ヘッダ 0x22 で誤エンコードされ、
proposal_votes に間違った voter_id で記録されていた。

方式:
  1. dreps テーブルから has_script=1 の DRep の hex（生 28byte ハッシュ）を取得
  2. 各 hex について、バグで付与されたはずの鍵ヘッダ (0x22) id を逆算
  3. proposal_votes の DRep 行で voter_id がその誤 id 集合に含まれる行を削除

proposal_votes.voter_hex には依存しない（誤行が voter_hex を持たない場合も拾える）。
正規の鍵ベース DRep は別ハッシュなので、誤 id 集合に一致せず誤検出しない。

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

    # 1) script ベース DRep を dreps から取得
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT drep_id, hex FROM dreps "
            "WHERE has_script = 1 AND hex IS NOT NULL AND hex <> ''"
        )
        script_dreps = [dict(r) for r in cursor.fetchall()]
    logger.info("script ベース DRep: %d 件", len(script_dreps))

    # 2) 各 script DRep について、バグで付与されたはずの鍵ヘッダ (0x22) id を逆算。
    #    wrong_id -> 正しい script id (dreps.drep_id) のマップ。
    wrong_to_correct: dict[str, str] = {}
    for d in script_dreps:
        hex_v = str(d["hex"]).strip()
        key_id = encode_voter_id("DRep", hex_v, has_script=False)  # 0x22
        if key_id:
            wrong_to_correct[key_id] = str(d["drep_id"])
    logger.info("逆算した誤 id（鍵ヘッダ）候補: %d 件", len(wrong_to_correct))
    if not wrong_to_correct:
        logger.info("対象なし。終了。")
        return

    # 3) proposal_votes の DRep 行で voter_id が誤 id 集合に含まれるものを抽出
    placeholders = ",".join(["?"] * len(wrong_to_correct))
    with get_db() as (cursor, _):
        cursor.execute(
            f"SELECT id, proposal_id, voter_id FROM proposal_votes "
            f"WHERE voter_role = 'DRep' AND voter_id IN ({placeholders})",
            list(wrong_to_correct.keys()),
        )
        wrong_rows = [dict(r) for r in cursor.fetchall()]

    for r in wrong_rows:
        logger.info(
            "誤 id 行: id=%d proposal=%s… 誤(鍵)=%s… 正(script)=%s…",
            r["id"], str(r["proposal_id"])[:20], str(r["voter_id"])[:24],
            wrong_to_correct.get(r["voter_id"], "?")[:24],
        )

    logger.info("誤 id 行: %d 件", len(wrong_rows))
    if not wrong_rows:
        logger.info("削除対象なし。終了。")
        return

    if not args.apply:
        logger.info("dry-run。実削除するには --apply を付けて再実行してください。")
        return

    wrong_ids = [r["id"] for r in wrong_rows]
    with get_db() as (cursor, conn):
        ph = ",".join(["?"] * len(wrong_ids))
        cursor.execute(
            f"DELETE FROM proposal_votes WHERE id IN ({ph})",
            wrong_ids,
        )
        deleted = cursor.rowcount or 0
        conn.commit()
    logger.info("削除完了: %d 件", deleted)


if __name__ == "__main__":
    main()
