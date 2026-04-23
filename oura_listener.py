"""
oura_listener.py
Dolos + UTxORPC ブロックストリームデーモン

常駐プロセスとして実行し、新しいブロックを監視して
cert を検知したら通知を発火する。

現在実装済み（utxorpc_spec 0.5.1 対応範囲）:
  - epoch_start    : slot からエポック変化を検知
  - pool_retire    : PoolRetirementCert
  - pool_fee_change: PoolRegistrationCert（再登録）

未実装（Conway era / utxorpc_spec 未収録）:
  - drep_new_governance_action : ProposalProcedure
  - drep_vote                  : VotingProcedure

使い方:
  python oura_listener.py [--dolos-url http://localhost:50051]

依存パッケージ:
  pip install utxorpc bech32
"""
import asyncio
import os
import sys
import logging
import argparse

from utxorpc.cardano import CardanoSyncClient, CardanoPoint
from utxorpc.generics.clients.sync_client import FollowTipResponseAction
import bech32 as bech32lib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notify_worker import (
    get_state, set_state,
    already_sent,
    flex_and_log, email_and_log,
    get_users_with_event, get_users_with_email_event,
    get_stake_addrs_with_event, get_stake_addrs_with_email_event,
    _merge_stake_channels,
    CARDANOISM_URL,
)
from cardanoism.backend import line_flex
from cardanoism.backend.mail_notify import build_html, build_text

logger = logging.getLogger("oura_listener")

KOIOS_NETWORK = os.getenv("KOIOS_NETWORK", "mainnet").lower()

_EPOCH_LENGTHS = {
    "mainnet": 432_000,
    "preprod": 432_000,
    "preview": 86_400,
}


def _epoch_from_slot(slot: int) -> int:
    return slot // _EPOCH_LENGTHS.get(KOIOS_NETWORK, 432_000)


def _keyhash_to_pool_id(raw_bytes: bytes) -> str:
    data = bech32lib.convertbits(raw_bytes, 8, 5)
    return bech32lib.encode("pool", data)


# ──────────────────────────────────────────────────────────────────────────────
# カーソル管理（再起動耐性）
# scope_type='global', scope_id=NULL で key_name に識別子を付与して保存
# ──────────────────────────────────────────────────────────────────────────────

def _load_cursor() -> list[CardanoPoint]:
    slot_str = get_state("global", None, "oura_last_slot")
    hash_str = get_state("global", None, "oura_last_hash")
    if slot_str and hash_str:
        return [CardanoPoint(slot=int(slot_str), hash=hash_str)]
    return []


def _save_cursor(slot: int, block_hash: bytes) -> None:
    set_state("global", None, "oura_last_slot", str(slot))
    set_state("global", None, "oura_last_hash", block_hash.hex())


# pool_fee の state は key_name に pool_id を埋め込んで global スコープで管理
# （notification_check_state.scope_type ENUM に 'pool' がないため）
def _get_pool_fee_state(pool_id: str) -> str | None:
    return get_state("global", None, f"pool_fee:{pool_id}")


def _set_pool_fee_state(pool_id: str, value: str) -> None:
    set_state("global", None, f"pool_fee:{pool_id}", value)


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: epoch_start
# ──────────────────────────────────────────────────────────────────────────────

def _notify_epoch_start(epoch: int) -> None:
    for user in get_users_with_event("epoch_start"):
        dedup_key = f"epoch_{epoch}"
        if already_sent(user["id"], "epoch_start", dedup_key):
            continue
        lang = user.get("language", "ja")
        alt = (f"【Cardanoism】新しいエポック（Epoch {epoch}）が始まりました" if lang == "ja"
               else f"[Cardanoism] New epoch started (Epoch {epoch})")
        flex_and_log(user["line_notify_id"], user["id"], "epoch_start", dedup_key, alt,
                     line_flex.epoch_start(epoch, CARDANOISM_URL, lang=lang))

    for user in get_users_with_email_event("epoch_start"):
        dedup_key = f"epoch_{epoch}_email"
        if already_sent(user["id"], "epoch_start", dedup_key):
            continue
        lang = user.get("language", "ja")
        subj = (f"新しいエポック（Epoch {epoch}）が始まりました" if lang == "ja"
                else f"New epoch started (Epoch {epoch})")
        ls = ([f"Epoch {epoch} が始まりました。", "Cardanoism でガバナンス情報や委任状況をご確認ください。"] if lang == "ja"
              else [f"Epoch {epoch} has started.", "Check governance info and delegation status on Cardanoism."])
        email_and_log(user["email_addr"], user["id"], "epoch_start", dedup_key, subj,
                      build_html(subj, ls, CARDANOISM_URL, "Cardanoismを開く" if lang == "ja" else "Open Cardanoism", lang),
                      build_text(subj, ls, CARDANOISM_URL, lang))


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: pool_retire
# ──────────────────────────────────────────────────────────────────────────────

def _notify_pool_retire(pool_id: str, retiring_epoch: int) -> None:
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("pool_retire"),
        get_stake_addrs_with_email_event("pool_retire"),
    )
    for addr in addrs:
        if addr.get("delegated_pool_id") != pool_id:
            continue
        user_id = addr["user_id"]
        lang = addr.get("language", "ja")
        pool_name = addr.get("delegated_pool_name") or pool_id[:12]
        nickname = addr["nickname"]
        dedup_key = f"pool_retire_{addr['stake_id']}_{retiring_epoch}"

        if addr.get("line_notify_id") and not already_sent(user_id, "pool_retire", dedup_key):
            alt = (f"【Cardanoism】委任先プール「{pool_name}」が Epoch {retiring_epoch} にリタイアします" if lang == "ja"
                   else f"[Cardanoism] Pool '{pool_name}' will retire at Epoch {retiring_epoch}")
            flex_and_log(addr["line_notify_id"], user_id, "pool_retire", dedup_key, alt,
                         line_flex.pool_retire(pool_name, retiring_epoch, nickname, CARDANOISM_URL, lang=lang))

        if addr.get("email_addr"):
            dk = dedup_key + "_email"
            if not already_sent(user_id, "pool_retire", dk):
                subj = (f"委任先プール「{pool_name}」が Epoch {retiring_epoch} にリタイアします" if lang == "ja"
                        else f"Pool '{pool_name}' will retire at Epoch {retiring_epoch}")
                ls = ([f"ウォレット: {nickname}", f"プール「{pool_name}」は Epoch {retiring_epoch} にリタイアする予定です。", "委任先の変更をご検討ください。"] if lang == "ja"
                      else [f"Wallet: {nickname}", f"Pool '{pool_name}' is scheduled to retire at Epoch {retiring_epoch}.", "Please consider changing your delegation."])
                email_and_log(addr["email_addr"], user_id, "pool_retire", dk, subj,
                              build_html(subj, ls, CARDANOISM_URL, "マイページを開く" if lang == "ja" else "Open MyPage", lang),
                              build_text(subj, ls, CARDANOISM_URL, lang))


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: pool_fee_change
# state は pool 単位で管理（複数ユーザーが委任していても Cert 検知は1回）
# ──────────────────────────────────────────────────────────────────────────────

def _notify_pool_fee_change(pool_id: str, margin: float, fixed_cost: int) -> None:
    current_val = f"{margin}:{fixed_cost}"
    stored = _get_pool_fee_state(pool_id)
    if stored is None:
        _set_pool_fee_state(pool_id, current_val)
        return
    if stored == current_val:
        return
    _set_pool_fee_state(pool_id, current_val)

    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("pool_fee_change"),
        get_stake_addrs_with_email_event("pool_fee_change"),
    )
    addrs = [a for a in addrs if a.get("delegated_pool_id") == pool_id]
    if not addrs:
        return

    old_margin_str, old_fixed_str = stored.split(":", 1)
    margin_pct = margin * 100
    old_margin_pct = float(old_margin_str) * 100 if old_margin_str else 0.0
    fixed_ada = fixed_cost / 1_000_000
    old_fixed_ada = int(old_fixed_str) / 1_000_000 if old_fixed_str else 0.0

    for addr in addrs:
        user_id = addr["user_id"]
        lang = addr.get("language", "ja")
        pool_name = addr.get("delegated_pool_name") or pool_id[:12]
        nickname = addr["nickname"]
        dedup_key = f"pool_fee_change_{addr['stake_id']}_{current_val}"

        if addr.get("line_notify_id") and not already_sent(user_id, "pool_fee_change", dedup_key):
            alt = (f"【Cardanoism】委任先プール「{pool_name}」の手数料が変更されました" if lang == "ja"
                   else f"[Cardanoism] Pool '{pool_name}' fee has changed")
            flex_and_log(addr["line_notify_id"], user_id, "pool_fee_change", dedup_key, alt,
                         line_flex.pool_fee_change(
                             pool_name=pool_name, old_margin_pct=old_margin_pct, new_margin_pct=margin_pct,
                             old_fixed_ada=old_fixed_ada, new_fixed_ada=fixed_ada, apy=None,
                             nickname=nickname, url=CARDANOISM_URL, lang=lang,
                         ))

        if addr.get("email_addr"):
            dk = dedup_key + "_email"
            if not already_sent(user_id, "pool_fee_change", dk):
                subj = (f"委任先プール「{pool_name}」の手数料が変更されました" if lang == "ja"
                        else f"Pool '{pool_name}' fee has changed")
                ls = ([f"ウォレット: {nickname}", f"変動手数料: {old_margin_pct:.2f}% → {margin_pct:.2f}%",
                       f"固定手数料: {old_fixed_ada:.0f} ADA → {fixed_ada:.0f} ADA"] if lang == "ja"
                      else [f"Wallet: {nickname}", f"Margin: {old_margin_pct:.2f}% → {margin_pct:.2f}%",
                            f"Fixed cost: {old_fixed_ada:.0f} ADA → {fixed_ada:.0f} ADA"])
                email_and_log(addr["email_addr"], user_id, "pool_fee_change", dk, subj,
                              build_html(subj, ls, CARDANOISM_URL, "マイページを開く" if lang == "ja" else "Open MyPage", lang),
                              build_text(subj, ls, CARDANOISM_URL, lang))


# ──────────────────────────────────────────────────────────────────────────────
# ブロック処理
# ──────────────────────────────────────────────────────────────────────────────

def _process_certificate(cert) -> None:
    which = cert.WhichOneof("certificate")

    if which == "pool_retirement":
        r = cert.pool_retirement
        try:
            pool_id = _keyhash_to_pool_id(bytes(r.pool_keyhash))
        except Exception as e:
            logger.warning("pool_retirement: keyhash変換失敗: %s", e)
            return
        logger.info("pool_retire 検知: pool=%s epoch=%d", pool_id, r.epoch)
        _notify_pool_retire(pool_id, r.epoch)

    elif which == "pool_registration":
        reg = cert.pool_registration
        try:
            pool_id = _keyhash_to_pool_id(bytes(reg.operator))
        except Exception as e:
            logger.warning("pool_registration: keyhash変換失敗: %s", e)
            return
        denom = reg.margin.denominator or 1
        margin = reg.margin.numerator / denom
        logger.info("pool_registration 検知: pool=%s margin=%.4f cost=%d", pool_id, margin, reg.cost)
        _notify_pool_fee_change(pool_id, margin, reg.cost)


def _process_block(block, prev_epoch: int) -> int:
    slot = block.header.slot
    block_hash = bytes(block.header.hash)
    current_epoch = _epoch_from_slot(slot)

    if prev_epoch >= 0 and current_epoch != prev_epoch:
        logger.info("epoch_start 検知: epoch=%d (slot=%d)", current_epoch, slot)
        last_notified = get_state("global", None, "current_epoch")
        if last_notified != str(current_epoch):
            set_state("global", None, "current_epoch", str(current_epoch))
            if last_notified is not None:
                _notify_epoch_start(current_epoch)

    for tx in block.body.tx:
        for cert in tx.certificates:
            try:
                _process_certificate(cert)
            except Exception as e:
                logger.exception("証明書処理エラー: %s", e)

    _save_cursor(slot, block_hash)
    return current_epoch


# ──────────────────────────────────────────────────────────────────────────────
# メインループ
# ──────────────────────────────────────────────────────────────────────────────

async def _run(dolos_url: str) -> None:
    secure = not dolos_url.startswith("http://")
    client = CardanoSyncClient(uri=dolos_url, secure=secure)

    intersect = _load_cursor()
    if intersect:
        logger.info("前回カーソルから再開: slot=%d", intersect[0].slot)
    else:
        logger.info("genesis から同期開始")

    prev_epoch = -1
    last_slot = get_state("global", None, "oura_last_slot")
    if last_slot:
        prev_epoch = _epoch_from_slot(int(last_slot))

    async with client.async_connect() as c:
        async for resp in c.async_follow_tip(intersect=intersect):
            if resp.action == FollowTipResponseAction.apply:
                try:
                    prev_epoch = _process_block(resp.block, prev_epoch)
                except Exception as e:
                    slot = getattr(resp.block.header, "slot", "?") if resp.block else "?"
                    logger.exception("ブロック処理エラー (slot=%s): %s", slot, e)

            elif resp.action == FollowTipResponseAction.undo:
                slot = getattr(resp.block.header, "slot", "?") if resp.block else "?"
                logger.info("rollback (undo) slot=%s: 通知スキップ", slot)

            elif resp.action == FollowTipResponseAction.reset:
                pt_slot = resp.point.slot if resp.point else "?"
                logger.info("reset 受信: slot=%s", pt_slot)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cardanoism Dolosブロックストリームリスナー")
    parser.add_argument(
        "--dolos-url",
        default=os.getenv("DOLOS_URL", "http://localhost:50051"),
        help="Dolos gRPC エンドポイント URL",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(_run(args.dolos_url))


if __name__ == "__main__":
    main()
