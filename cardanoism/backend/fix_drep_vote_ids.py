"""fix_drep_vote_ids.py
一度きりのデータ修正スクリプト。

ogmios_listener の script credential 判定バグ（Ogmios の "from" フィールド未対応）に
より、script ベース DRep の投票が CIP-129 の鍵ヘッダ 0x22 で誤エンコードされ、
proposal_votes に間違った voter_id で記録されていた。

方式:
  1. dreps テーブルから has_script=1 の DRep の hex（生 28byte ハッシュ）を取得
  2. 各 hex について、バグで付与されたはずの鍵ヘッダ (0x22) id を逆算
  3. proposal_votes の DRep 行で voter_id がその誤 id 集合に含まれる行を削除

正規の鍵ベース DRep は別ハッシュなので、誤 id 集合に一致せず誤検出しない。

モード:
  （引数なし）       : dry-run。削除対象を一覧表示するだけ
  --apply           : 実際に削除する
  --inspect <id>    : 指定 DRep id をデコードし、dreps / proposal_votes の
                      実状態を表示する診断モード（削除はしない）

実行（必ず -m で。スクリプト直接実行はモジュール名衝突で失敗する:
cardanoism/backend/ が sys.path 先頭に入り blockfrost.py が本物の
blockfrost パッケージを隠してしまうため）:
  infisical run --env=mainnet -- python -m cardanoism.backend.fix_drep_vote_ids
  infisical run --env=mainnet -- python -m cardanoism.backend.fix_drep_vote_ids --apply
  infisical run --env=mainnet -- python -m cardanoism.backend.fix_drep_vote_ids --inspect drep1y...
"""
from __future__ import annotations

import argparse
import logging

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.listener_governance import encode_voter_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _decode_drep_id(drep_id: str) -> tuple[int, str] | None:
    """CIP-129 drep id を (header_byte, hash_hex) に分解。失敗時 None。"""
    try:
        from pycardano.crypto.bech32 import bech32_decode, convertbits  # type: ignore
        decoded = bech32_decode(drep_id)
        if not decoded or len(decoded) < 2 or decoded[1] is None:
            return None
        raw = convertbits(decoded[1], 5, 8, False)
        if not raw or len(raw) != 29:
            return None
        return raw[0], bytes(raw[1:]).hex()
    except Exception as e:  # noqa: BLE001
        logger.warning("decode 失敗 %s: %s", drep_id, e)
        return None


def _inspect(drep_id: str) -> None:
    """指定 DRep id について dreps / proposal_votes の実状態を表示する。"""
    dec = _decode_drep_id(drep_id)
    if not dec:
        logger.info("入力 id をデコードできませんでした: %s", drep_id)
        return
    header, hash_hex = dec
    logger.info(
        "入力 id: %s", drep_id,
    )
    logger.info(
        "  header=0x%02x (%s) / hash=%s",
        header, "script(0x23)" if header == 0x23 else "key(0x22)" if header == 0x22 else "?",
        hash_hex,
    )

    # dreps をハッシュ (hex) で照合（bech32 形式に依存しない）
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT drep_id, hex, has_script, drep_status, registered "
            "FROM dreps WHERE hex = ?",
            (hash_hex,),
        )
        drows = [dict(r) for r in cursor.fetchall()]
    logger.info("dreps で hex 一致する行: %d 件", len(drows))
    for d in drows:
        logger.info(
            "  drep_id=%s has_script=%s status=%s registered=%s",
            d["drep_id"], d["has_script"], d.get("drep_status"), d.get("registered"),
        )

    # 鍵ヘッダ / script ヘッダ両形式の id で proposal_votes を照合
    for label, has_script in (("鍵 0x22", False), ("script 0x23", True)):
        vid = encode_voter_id("DRep", hash_hex, has_script=has_script)
        with get_db() as (cursor, _):
            cursor.execute(
                "SELECT id, proposal_id, voter_hex, last_event_slot "
                "FROM proposal_votes WHERE voter_role = 'DRep' AND voter_id = ?",
                (vid,),
            )
            prows = [dict(r) for r in cursor.fetchall()]
        logger.info("proposal_votes voter_id=%s [%s]: %d 件", vid, label, len(prows))
        for p in prows:
            logger.info(
                "  id=%d proposal=%s voter_hex=%s last_event_slot=%s",
                p["id"], str(p["proposal_id"])[:24],
                p.get("voter_hex"), p.get("last_event_slot"),
            )


def _run_cleanup(apply: bool) -> None:
    # 1) script ベース DRep を dreps から取得
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT drep_id, hex FROM dreps "
            "WHERE has_script = 1 AND hex IS NOT NULL AND hex <> ''"
        )
        script_dreps = [dict(r) for r in cursor.fetchall()]
    logger.info("script ベース DRep: %d 件", len(script_dreps))

    # 2) 各 script DRep について、バグで付与されたはずの鍵ヘッダ (0x22) id を逆算
    wrong_to_correct: dict[str, str] = {}
    for d in script_dreps:
        hex_v = str(d["hex"]).strip()
        key_id = encode_voter_id("DRep", hex_v, has_script=False)
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

    if not apply:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="script DRep 投票の誤 voter_id 行を削除")
    parser.add_argument(
        "--apply", action="store_true",
        help="実際に削除する（未指定なら dry-run で一覧表示のみ）",
    )
    parser.add_argument(
        "--inspect", metavar="DREP_ID",
        help="指定 DRep id の dreps / proposal_votes 実状態を表示する診断モード",
    )
    args = parser.parse_args()

    if args.inspect:
        _inspect(args.inspect)
        return
    _run_cleanup(apply=args.apply)


if __name__ == "__main__":
    main()
