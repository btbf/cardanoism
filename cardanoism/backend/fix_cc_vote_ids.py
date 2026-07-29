"""fix_cc_vote_ids.py
一度きりのデータ修正スクリプト。

ogmios_listener の CIP-129 ヘッダ欠落バグにより、憲法委員会 (CC) の投票が
`cc_hot1...`(生 28byte ハッシュ) で proposal_votes に記録されていた。
Koios `/proposal_votes` は CIP-129 形式 (header byte + 28byte = 29byte) を返すため、
同じメンバーの同じ投票が **別 voter_id の 2 行** として登録され、さらに
cc_members (cc_hot_id は CIP-129 形式) と突き合わないため
GA 詳細の「投票集計」で現任メンバーが常に「未投票」と表示されていた。

listener 側の修正は listener_governance.encode_voter_id (_CIP129_HEADERS)。
本スクリプトは既に書かれてしまった行を後始末する。

方式:
  1. proposal_votes の CC 行を全件デコードし、29byte (正) と 28byte (誤) に分ける
  2. 誤行のハッシュから正しい CIP-129 id を再構成する
     - key / script の判別は cc_members.cc_hot_hex → cc_hot_has_script を参照
     - cc_members に無いハッシュは判別できないので touch しない (要 params_sync)
  3. 同じ (proposal_id, 正 id) の行が既にある → 誤行を DELETE (重複解消)
     無い                                    → 誤行の voter_id を正 id に UPDATE

モード:
  （引数なし） : dry-run。対象を一覧表示するだけ
  --apply     : 実際に DELETE / UPDATE する

実行 (必ず -m で。スクリプト直接実行は cardanoism/backend/ が sys.path 先頭に
入り blockfrost.py が本物の blockfrost パッケージを隠すため失敗する):
  infisical run --env=mainnet -- python -m cardanoism.backend.fix_cc_vote_ids
  infisical run --env=mainnet -- python -m cardanoism.backend.fix_cc_vote_ids --apply
"""
from __future__ import annotations

import argparse
import logging

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.listener_governance import encode_voter_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _decode(voter_id: str) -> tuple[int | None, str] | None:
    """cc_hot bech32 を (header_byte|None, hash_hex) に分解する。

    29byte なら (header, hash) / 28byte なら (None, hash) = ヘッダ欠落のバグ行。
    """
    try:
        from pycardano.crypto.bech32 import bech32_decode, convertbits  # type: ignore
        decoded = bech32_decode(voter_id)
        if not decoded or len(decoded) < 2 or decoded[1] is None:
            return None
        raw = convertbits(decoded[1], 5, 8, False)
    except Exception as e:  # noqa: BLE001
        logger.warning("decode 失敗 %s: %s", voter_id, e)
        return None
    if not raw:
        return None
    b = bytes(raw)
    if len(b) == 29:
        return b[0], b[1:].hex()
    if len(b) == 28:
        return None, b.hex()
    return None


def _hot_script_map() -> dict[str, bool]:
    """cc_hot_hex → cc_hot_has_script のマップ。"""
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT cc_hot_hex, cc_hot_has_script FROM cc_members "
            "WHERE cc_hot_hex IS NOT NULL AND cc_hot_hex <> ''"
        )
        return {
            str(r["cc_hot_hex"]).lower(): bool(r["cc_hot_has_script"])
            for r in cursor.fetchall()
        }


def _run(apply: bool) -> None:
    hot_map = _hot_script_map()
    logger.info("cc_members の hot key: %d 件", len(hot_map))

    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT id, proposal_id, voter_id, vote, last_event_slot "
            "FROM proposal_votes WHERE voter_role = 'ConstitutionalCommittee'"
        )
        rows = [dict(r) for r in cursor.fetchall()]
    logger.info("CC 投票: %d 件", len(rows))

    # (proposal_id, 正 voter_id) → 既存行 の索引
    correct_index: set[tuple[str, str]] = set()
    broken: list[dict] = []
    for r in rows:
        dec = _decode(str(r["voter_id"]))
        if dec is None:
            logger.warning("デコード不可 id=%s voter_id=%s", r["id"], r["voter_id"])
            continue
        header, hash_hex = dec
        if header is not None:
            correct_index.add((str(r["proposal_id"]), str(r["voter_id"])))
        else:
            r["hash_hex"] = hash_hex
            broken.append(r)

    logger.info("正 (CIP-129 29byte): %d 件 / 誤 (28byte): %d 件",
                len(rows) - len(broken), len(broken))
    if not broken:
        logger.info("対象なし。終了。")
        return

    to_delete: list[int] = []
    to_update: list[tuple[str, int]] = []
    unknown = 0
    for r in broken:
        has_script = hot_map.get(r["hash_hex"])
        if has_script is None:
            unknown += 1
            logger.warning(
                "cc_members に無いハッシュのため判別不可 (skip): id=%s hash=%s",
                r["id"], r["hash_hex"],
            )
            continue
        correct = encode_voter_id("ConstitutionalCommittee", r["hash_hex"], has_script=has_script)
        if not correct:
            unknown += 1
            continue
        key = (str(r["proposal_id"]), correct)
        if key in correct_index:
            to_delete.append(int(r["id"]))
            logger.info("重複 → DELETE id=%s proposal=%s… %s… (正行あり)",
                        r["id"], str(r["proposal_id"])[:20], str(r["voter_id"])[:24])
        else:
            to_update.append((correct, int(r["id"])))
            correct_index.add(key)
            logger.info("誤 id → UPDATE id=%s proposal=%s… %s… → %s…",
                        r["id"], str(r["proposal_id"])[:20],
                        str(r["voter_id"])[:24], correct[:24])

    logger.info("DELETE 対象: %d 件 / UPDATE 対象: %d 件 / 判別不可: %d 件",
                len(to_delete), len(to_update), unknown)
    if unknown:
        logger.info("判別不可が残る場合は先に params_sync で cc_members を更新すること。")
    if not apply:
        logger.info("dry-run。実行するには --apply を付けて再実行してください。")
        return

    with get_db() as (cursor, conn):
        if to_delete:
            ph = ",".join(["?"] * len(to_delete))
            cursor.execute(f"DELETE FROM proposal_votes WHERE id IN ({ph})", to_delete)
            logger.info("削除: %d 件", cursor.rowcount or 0)
        for correct, vid in to_update:
            cursor.execute(
                "UPDATE proposal_votes SET voter_id = ? WHERE id = ?", (correct, vid),
            )
        conn.commit()
    logger.info("更新: %d 件 / 完了", len(to_update))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CIP-129 ヘッダ欠落で記録された CC 投票の voter_id を修正する",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="実際に DELETE / UPDATE する（未指定なら dry-run で一覧表示のみ）",
    )
    args = parser.parse_args()
    _run(apply=args.apply)


if __name__ == "__main__":
    main()
