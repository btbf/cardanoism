"""
ogmios_listener.py
Ogmios WebSocket チェーンシンク デーモン

cardano-node → Ogmios (ws://localhost:1337) → 本スクリプト

実装済みイベント（Ogmios は Conway era 完全対応）:
  - epoch_start                : slot からエポック変化を検知
  - pool_retire                : stakePoolRetirement cert
  - pool_fee_change            : stakePoolRegistration cert（再登録）
  - drep_new_governance_action : proposals
  - drep_vote                  : votes（DRep role のみ）

使い方:
  python ogmios_listener.py [--ogmios-url ws://localhost:1337]

依存パッケージ:
  pip install websockets>=12.0
"""
import asyncio
import hashlib
import json
import logging
import os
import sys
import argparse
from datetime import datetime, timezone

import websockets

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
from cardanoism.backend.koios import get_proposal_title, get_pool_name, get_pool_epoch_stats, get_pool_apy
from cardanoism.backend.recent_blocks_db import insert_block, trim_old_blocks, delete_blocks_after_slot
from cardanoism.backend.mempool_db import upsert_mempool_state

logger = logging.getLogger("ogmios_listener")

KOIOS_NETWORK = os.getenv("KOIOS_NETWORK", "mainnet").lower()

_EPOCH_LENGTHS = {
    "mainnet": 432_000,
    "preprod": 432_000,
    "preview": 86_400,
}

_GA_TYPE_MAP_JA = {
    "treasuryWithdrawals": "国庫引き出し",
    "parameterChange":     "プロトコル変更",
    "hardForkInitiation":  "ハードフォーク",
    "noConfidence":        "不信任",
    "updateCommittee":     "委員会変更",
    "newConstitution":     "新憲法",
    "information":         "情報提案",
}

_GA_TYPE_MAP_EN = {
    "treasuryWithdrawals": "Treasury Withdrawals",
    "parameterChange":     "Protocol Parameter Change",
    "hardForkInitiation":  "Hard Fork Initiation",
    "noConfidence":        "No Confidence",
    "updateCommittee":     "Update Committee",
    "newConstitution":     "New Constitution",
    "information":         "Information",
}


def _epoch_from_slot(slot: int) -> int:
    return slot // _EPOCH_LENGTHS.get(KOIOS_NETWORK, 432_000)


# ブロック記録の TRIM 頻度（毎ブロックではなくこの間隔で古い行を削除）
_BLOCK_TRIM_INTERVAL = 50
_block_count_since_trim = 0


def _pool_id_hex_from_issuer(block: dict) -> str | None:
    """Praos ブロックの issuer.verificationKey (cold key) から blake2b-224 で pool_id_hex を算出。"""
    issuer = block.get("issuer") or {}
    vkey_hex = issuer.get("verificationKey") if isinstance(issuer, dict) else None
    if not vkey_hex or not isinstance(vkey_hex, str):
        return None
    try:
        vkey_bytes = bytes.fromhex(vkey_hex.strip())
    except (ValueError, TypeError):
        return None
    if not vkey_bytes:
        return None
    return hashlib.blake2b(vkey_bytes, digest_size=28).hexdigest()


def _record_recent_block(block: dict, current_epoch: int) -> None:
    """recent_blocks テーブルに 1 ブロック書き込み + 周期的に古い行を TRIM。失敗は静かにログだけ。"""
    global _block_count_since_trim
    try:
        height = block.get("height")
        if height is None:
            return
        slot = block.get("slot", 0)
        block_hash = block.get("id", "")
        tx_count = len(block.get("transactions") or [])
        pool_id_hex = _pool_id_hex_from_issuer(block)
        # ブロックサイズ (bytes) — Ogmios v6 は block.size.bytes
        size_obj = block.get("size") or {}
        block_size = int(size_obj.get("bytes") or 0) if isinstance(size_obj, dict) else 0
        # block_time は現在時刻で代用（Ogmios 受信ラグは < 1秒で実用上問題ない）
        block_time = datetime.now(timezone.utc).replace(tzinfo=None)

        insert_block(
            block_height=int(height),
            block_hash=str(block_hash),
            slot_no=int(slot),
            epoch_no=int(current_epoch),
            block_time=block_time,
            pool_id_hex=pool_id_hex,
            tx_count=tx_count,
            block_size=block_size,
        )
        _block_count_since_trim += 1
        if _block_count_since_trim >= _BLOCK_TRIM_INTERVAL:
            try:
                deleted = trim_old_blocks(keep=100)
                if deleted:
                    logger.debug("recent_blocks TRIM: %d 件削除", deleted)
            finally:
                _block_count_since_trim = 0
    except Exception as e:
        logger.debug("recent_blocks 書き込み失敗: %s", e)


# ──────────────────────────────────────────────────────────────────────────────
# カーソル管理（再起動耐性）
# ──────────────────────────────────────────────────────────────────────────────

def _save_cursor(slot: int, block_id: str) -> None:
    set_state("global", None, "ogmios_last_slot", str(slot))
    set_state("global", None, "ogmios_last_id", block_id)


def _get_pool_fee_state(pool_id: str) -> str | None:
    return get_state("global", None, f"pool_fee:{pool_id}")


def _set_pool_fee_state(pool_id: str, value: str) -> None:
    set_state("global", None, f"pool_fee:{pool_id}", value)


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: pool_epoch_performance（エポック切り替わり時に前エポック実績を通知）
# ──────────────────────────────────────────────────────────────────────────────

def _notify_pool_epoch_performance(prev_epoch: int) -> None:
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("pool_epoch_performance"),
        get_stake_addrs_with_email_event("pool_epoch_performance"),
    )
    addrs = [a for a in addrs if a.get("delegated_pool_id")]
    if not addrs:
        return

    # プール単位で Koios を1回だけ叩く
    # APY は2エポック遅延のため prev_epoch-1 から取得
    apy_epoch = prev_epoch - 1
    unique_pools = {a["delegated_pool_id"] for a in addrs}
    stats_cache: dict[str, dict] = {}
    for pool_id in unique_pools:
        stats = get_pool_epoch_stats(pool_id, prev_epoch)
        if stats:
            stats["apy"] = get_pool_apy(pool_id, apy_epoch)
            stats_cache[pool_id] = stats

    for addr in addrs:
        pool_id = addr["delegated_pool_id"]
        stats = stats_cache.get(pool_id)
        if not stats:
            continue

        user_id = addr["user_id"]
        lang = addr.get("language", "ja")
        pool_name = addr.get("delegated_pool_name") or get_pool_name(pool_id) or pool_id[:12]
        nickname = addr["nickname"]
        dedup_key = f"pool_epoch_perf_{addr['stake_id']}_{prev_epoch}"

        if addr.get("line_notify_id") and not already_sent(user_id, "pool_epoch_performance", dedup_key):
            alt = (f"【Cardanoism】Epoch {prev_epoch} の{pool_name}実績が確定しました" if lang == "ja"
                   else f"[Cardanoism] Epoch {prev_epoch} performance for {pool_name}")
            flex_and_log(addr["line_notify_id"], user_id, "pool_epoch_performance", dedup_key, alt,
                         line_flex.pool_epoch_performance(
                             pool_name=pool_name, epoch_no=prev_epoch,
                             active_stake_ada=stats["active_stake_ada"],
                             saturation_pct=stats["saturation_pct"],
                             block_cnt=stats["block_cnt"],
                             apy=stats["apy"],
                             nickname=nickname, url=CARDANOISM_URL, lang=lang,
                             apy_epoch_no=apy_epoch if stats["apy"] is not None else None,
                         ))

        if addr.get("email_addr"):
            dk = dedup_key + "_email"
            if not already_sent(user_id, "pool_epoch_performance", dk):
                subj = (f"Epoch {prev_epoch} の{pool_name}実績が確定しました" if lang == "ja"
                        else f"Epoch {prev_epoch} performance for {pool_name}")
                if lang == "ja":
                    ls = [f"ウォレット: {nickname}", f"プール: {pool_name}", f"エポック: {prev_epoch}"]
                    if stats["active_stake_ada"] is not None:
                        ls.append(f"有効ステーク: {stats['active_stake_ada'] / 1_000_000:,.1f}M ADA")
                    if stats["saturation_pct"] is not None:
                        ls.append(f"飽和度: {stats['saturation_pct']:.1f}%")
                    if stats["block_cnt"] is not None:
                        ls.append(f"ブロック生成数: {stats['block_cnt']}")
                    if stats["apy"] is not None:
                        ls.append(f"APY（Ep.{apy_epoch} 実績）: {stats['apy']:.2f}%")
                else:
                    ls = [f"Wallet: {nickname}", f"Pool: {pool_name}", f"Epoch: {prev_epoch}"]
                    if stats["active_stake_ada"] is not None:
                        ls.append(f"Active Stake: {stats['active_stake_ada'] / 1_000_000:,.1f}M ADA")
                    if stats["saturation_pct"] is not None:
                        ls.append(f"Saturation: {stats['saturation_pct']:.1f}%")
                    if stats["block_cnt"] is not None:
                        ls.append(f"Blocks Minted: {stats['block_cnt']}")
                    if stats["apy"] is not None:
                        ls.append(f"APY (Ep.{apy_epoch}): {stats['apy']:.2f}%")
                email_and_log(addr["email_addr"], user_id, "pool_epoch_performance", dk, subj,
                              build_html(subj, ls, CARDANOISM_URL, "マイページを開く" if lang == "ja" else "Open MyPage", lang),
                              build_text(subj, ls, CARDANOISM_URL, lang))


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
        pool_name = addr.get("delegated_pool_name") or get_pool_name(pool_id) or pool_id[:12]
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
# 通知発火: pool_fee_change（margin / fixed_cost / pledge の変化を統合検知）
# state は pool 単位で管理（複数ユーザーが委任していても Cert 検知は1回）
# state フォーマット: "{margin}:{fixed_cost}:{pledge_lovelace}"
# ──────────────────────────────────────────────────────────────────────────────

def _notify_pool_fee_change(pool_id: str, margin: float, fixed_cost: int, pledge: int) -> None:
    current_val = f"{margin}:{fixed_cost}:{pledge}"
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

    # 旧フォーマット（pledge なし）に対する後方互換
    parts = stored.split(":")
    old_margin_pct = float(parts[0]) * 100
    old_fixed_ada = int(parts[1]) / 1_000_000 if len(parts) > 1 else 0.0
    old_pledge_ada = int(parts[2]) / 1_000_000 if len(parts) > 2 else None

    margin_pct = margin * 100
    fixed_ada = fixed_cost / 1_000_000
    pledge_ada = pledge / 1_000_000

    fee_changed = (old_margin_pct != margin_pct or old_fixed_ada != fixed_ada)
    # old_pledge_ada が None（旧フォーマット）の場合も pledge 変化として扱う
    pledge_changed = (old_pledge_ada != pledge_ada)

    for addr in addrs:
        user_id = addr["user_id"]
        lang = addr.get("language", "ja")
        pool_name = addr.get("delegated_pool_name") or get_pool_name(pool_id) or pool_id[:12]
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
                             old_pledge_ada=old_pledge_ada, new_pledge_ada=pledge_ada,
                         ))

        if addr.get("email_addr"):
            dk = dedup_key + "_email"
            if not already_sent(user_id, "pool_fee_change", dk):
                subj = (f"委任先プール「{pool_name}」の手数料が変更されました" if lang == "ja"
                        else f"Pool '{pool_name}' fee has changed")
                if lang == "ja":
                    ls = [f"ウォレット: {nickname}"]
                    if fee_changed:
                        ls += [f"変動手数料: {old_margin_pct:.2f}% → {margin_pct:.2f}%",
                               f"固定手数料: {old_fixed_ada:.0f} ADA → {fixed_ada:.0f} ADA"]
                    if pledge_changed:
                        if old_pledge_ada is not None:
                            ls.append(f"誓約: {old_pledge_ada:.0f} ADA → {pledge_ada:.0f} ADA")
                        else:
                            ls.append(f"誓約: {pledge_ada:.0f} ADA")
                else:
                    ls = [f"Wallet: {nickname}"]
                    if fee_changed:
                        ls += [f"Margin: {old_margin_pct:.2f}% → {margin_pct:.2f}%",
                               f"Fixed cost: {old_fixed_ada:.0f} ADA → {fixed_ada:.0f} ADA"]
                    if pledge_changed:
                        if old_pledge_ada is not None:
                            ls.append(f"Pledge: {old_pledge_ada:.0f} ADA → {pledge_ada:.0f} ADA")
                        else:
                            ls.append(f"Pledge: {pledge_ada:.0f} ADA")
                email_and_log(addr["email_addr"], user_id, "pool_fee_change", dk, subj,
                              build_html(subj, ls, CARDANOISM_URL, "マイページを開く" if lang == "ja" else "Open MyPage", lang),
                              build_text(subj, ls, CARDANOISM_URL, lang))


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: drep_new_governance_action
# ──────────────────────────────────────────────────────────────────────────────

def _notify_governance_action(tx_id: str, action_type_raw: str) -> None:
    gov_url = f"{CARDANOISM_URL}/governance"

    for addr in get_stake_addrs_with_event("drep_new_governance_action"):
        user_id = addr["user_id"]
        lang = addr.get("language", "ja")
        dedup_key = f"new_gov_{tx_id}_{addr['stake_id']}"
        if already_sent(user_id, "drep_new_governance_action", dedup_key):
            continue
        label = (_GA_TYPE_MAP_JA if lang == "ja" else _GA_TYPE_MAP_EN).get(action_type_raw, action_type_raw)
        alt = (f"【Cardanoism】新しいガバナンスアクションが提出されました: {label}" if lang == "ja"
               else f"[Cardanoism] New governance action submitted: {label}")
        flex_and_log(addr["line_notify_id"], user_id, "drep_new_governance_action", dedup_key, alt,
                     line_flex.drep_new_governance_action(label, gov_url, lang=lang))

    for addr in get_stake_addrs_with_email_event("drep_new_governance_action"):
        user_id = addr["user_id"]
        lang = addr.get("language", "ja")
        dk = f"new_gov_{tx_id}_{addr['stake_id']}_email"
        if already_sent(user_id, "drep_new_governance_action", dk):
            continue
        label = (_GA_TYPE_MAP_JA if lang == "ja" else _GA_TYPE_MAP_EN).get(action_type_raw, action_type_raw)
        subj = (f"新しいガバナンスアクションが提出されました: {label}" if lang == "ja"
                else f"New governance action submitted: {label}")
        ls = ([f"新しいガバナンスアクション（{label}）が提出されました。", "Cardanoism でアクションの詳細を確認できます。"] if lang == "ja"
              else [f"A new governance action ({label}) has been submitted.", "Check the details on Cardanoism."])
        email_and_log(addr["email_addr"], user_id, "drep_new_governance_action", dk, subj,
                      build_html(subj, ls, gov_url, "ガバナンスを確認" if lang == "ja" else "Check Governance", lang),
                      build_text(subj, ls, gov_url, lang))


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: drep_vote
# ──────────────────────────────────────────────────────────────────────────────

def _notify_drep_vote(drep_id: str, vote_str: str, gov_tx_hash: str, gov_index: int) -> None:
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_vote"),
        get_stake_addrs_with_email_event("drep_vote"),
    )
    addrs = [a for a in addrs if a.get("delegated_drep_id") == drep_id]
    if not addrs:
        return

    proposal_title = get_proposal_title(gov_tx_hash, gov_index) if gov_tx_hash else None
    gov_url = f"{CARDANOISM_URL}/governance"
    vote_lower = vote_str.lower()
    vote_label_ja = {"yes": "賛成", "no": "反対", "abstain": "棄権"}.get(vote_lower, vote_str)
    vote_label_en = {"yes": "Yes", "no": "No", "abstain": "Abstain"}.get(vote_lower, vote_str)

    for addr in addrs:
        user_id = addr["user_id"]
        lang = addr.get("language", "ja")
        drep_name = addr.get("delegated_drep_name") or drep_id[:12]
        nickname = addr["nickname"]
        dedup_key = f"drep_vote_{addr['stake_id']}_{gov_tx_hash}_{gov_index}"

        if addr.get("line_notify_id") and not already_sent(user_id, "drep_vote", dedup_key):
            vote_label = vote_label_ja if lang == "ja" else vote_label_en
            alt = (f"【Cardanoism】委任先DRep「{drep_name}」が投票しました（{vote_label}）" if lang == "ja"
                   else f"[Cardanoism] Delegated DRep '{drep_name}' voted ({vote_label})")
            flex_and_log(addr["line_notify_id"], user_id, "drep_vote", dedup_key, alt,
                         line_flex.drep_vote(drep_name, vote_str, proposal_title, nickname, gov_url, lang=lang))

        if addr.get("email_addr"):
            dk = dedup_key + "_email"
            if not already_sent(user_id, "drep_vote", dk):
                vote_label = vote_label_ja if lang == "ja" else vote_label_en
                subj = (f"委任先DRep「{drep_name}」が投票しました（{vote_label}）" if lang == "ja"
                        else f"Delegated DRep '{drep_name}' voted ({vote_label})")
                ls_ja = [f"ウォレット: {nickname}", f"DRep: {drep_name}", f"投票結果: {vote_label_ja}"]
                ls_en = [f"Wallet: {nickname}", f"DRep: {drep_name}", f"Vote: {vote_label_en}"]
                if proposal_title:
                    ls_ja.append(f"対象: {proposal_title}")
                    ls_en.append(f"Proposal: {proposal_title}")
                ls = ls_ja if lang == "ja" else ls_en
                email_and_log(addr["email_addr"], user_id, "drep_vote", dk, subj,
                              build_html(subj, ls, gov_url, "ガバナンスを確認" if lang == "ja" else "Check Governance", lang),
                              build_text(subj, ls, gov_url, lang))


# ──────────────────────────────────────────────────────────────────────────────
# ブロック処理
# ──────────────────────────────────────────────────────────────────────────────

def _process_cert(cert: dict) -> None:
    cert_type = cert.get("type")

    if cert_type == "stakePoolRetirement":
        pool = cert.get("stakePool", {})
        pool_id = pool.get("id", "")
        retiring_epoch = pool.get("retirementEpoch", 0)
        logger.info("pool_retire 検知: pool=%s epoch=%d", pool_id, retiring_epoch)
        _notify_pool_retire(pool_id, retiring_epoch)

    elif cert_type == "stakePoolRegistration":
        pool = cert.get("stakePool", {})
        pool_id = pool.get("id", "")
        cost_lovelace = pool.get("cost", {}).get("ada", {}).get("lovelace", 0)
        pledge_lovelace = pool.get("pledge", {}).get("ada", {}).get("lovelace", 0)
        margin_str = pool.get("margin", "0/1")
        try:
            num, den = margin_str.split("/")
            margin = int(num) / int(den)
        except (ValueError, ZeroDivisionError):
            logger.warning("margin パース失敗: pool=%s margin=%s", pool_id, margin_str)
            return
        logger.info("pool_registration 検知: pool=%s margin=%.4f cost=%d pledge=%d",
                    pool_id, margin, cost_lovelace, pledge_lovelace)
        _notify_pool_fee_change(pool_id, margin, cost_lovelace, pledge_lovelace)


def _process_tx(tx: dict) -> None:
    tx_id = tx.get("id", "")

    for cert in tx.get("certificates", []):
        try:
            _process_cert(cert)
        except Exception as e:
            logger.exception("cert 処理エラー tx=%s: %s", tx_id, e)

    for proposal in tx.get("proposals", []):
        try:
            action_type = proposal.get("action", {}).get("type", "")
            logger.info("governance_action 検知: tx=%s type=%s", tx_id, action_type)
            _notify_governance_action(tx_id, action_type)
        except Exception as e:
            logger.exception("proposal 処理エラー tx=%s: %s", tx_id, e)

    for vote in tx.get("votes", []):
        try:
            voter = vote.get("voter", {})
            if voter.get("role") != "delegateRepresentative":
                continue
            drep_id = voter.get("id", "")
            vote_str = vote.get("vote", "")
            action_id = vote.get("actionId", {})
            gov_tx_hash = action_id.get("transaction", {}).get("id", "")
            gov_index = action_id.get("index", 0)
            logger.info("drep_vote 検知: drep=%s vote=%s gov_tx=%s#%d", drep_id, vote_str, gov_tx_hash, gov_index)
            _notify_drep_vote(drep_id, vote_str, gov_tx_hash, gov_index)
        except Exception as e:
            logger.exception("vote 処理エラー tx=%s: %s", tx_id, e)


def _process_block(block: dict, prev_epoch: int) -> int:
    slot = block.get("slot", 0)
    block_id = block.get("id", "")
    current_epoch = _epoch_from_slot(slot)

    if prev_epoch >= 0 and current_epoch != prev_epoch:
        logger.info("epoch_start 検知: epoch=%d (slot=%d)", current_epoch, slot)
        last_notified = get_state("global", None, "current_epoch")
        if last_notified != str(current_epoch):
            set_state("global", None, "current_epoch", str(current_epoch))
            if last_notified is not None:
                _notify_epoch_start(current_epoch)
                try:
                    _notify_pool_epoch_performance(prev_epoch)
                except Exception as e:
                    logger.exception("pool_epoch_performance 通知エラー: %s", e)

    for tx in block.get("transactions", []):
        _process_tx(tx)

    # ライブブロック一覧用に記録（ダッシュボード /staking で表示）
    _record_recent_block(block, current_epoch)

    _save_cursor(slot, block_id)
    return current_epoch


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket セッション管理
# ──────────────────────────────────────────────────────────────────────────────

async def _find_intersection(ws, points: list) -> None:
    await ws.send(json.dumps({
        "jsonrpc": "2.0",
        "method": "findIntersection",
        "params": {"points": points},
    }))
    resp = json.loads(await ws.recv())
    if "error" in resp:
        logger.warning("findIntersection 失敗（カーソル不一致）: %s — origin から再開", resp.get("error"))
    else:
        tip = resp.get("result", {}).get("tip", {})
        intersection = resp.get("result", {}).get("intersection", {})
        logger.info("findIntersection 成功: intersection slot=%s, tip slot=%s",
                    intersection.get("slot", "?"), tip.get("slot", "?"))
        if isinstance(tip, dict) and isinstance(intersection, dict):
            tip_slot = tip.get("slot", 0)
            inter_slot = intersection.get("slot", 0)
            if tip_slot and inter_slot and tip_slot - inter_slot > 10000:
                logger.info("同期待ち: tip まで %d slot 残っています（しばらくログが続きます）", tip_slot - inter_slot)
            else:
                logger.info("tip 付近から開始: 新しいブロックを待機します（mainnet は約20秒ごと）")


def _fetch_tip(ogmios_url: str) -> tuple[int, str]:
    import urllib.request
    global KOIOS_NETWORK
    http_url = ogmios_url.replace("ws://", "http://").replace("wss://", "https://")
    logger.info("Ogmios /health 取得中: %s", http_url)
    with urllib.request.urlopen(f"{http_url}/health", timeout=10) as r:
        health = json.loads(r.read())
    # Ogmios v6.14+ は {"Health": {"status": {...}}} 形式
    status = health.get("Health", {}).get("status", health)
    # ネットワークを自動検出（環境変数未設定時のみ上書き）
    detected = status.get("network", "")
    if detected and os.getenv("KOIOS_NETWORK") is None:
        KOIOS_NETWORK = detected.lower()
        logger.info("ネットワーク自動検出: %s", KOIOS_NETWORK)
    sync = status.get("networkSynchronization", status.get("syncProgress", "?"))
    tip = status["lastKnownTip"]
    slot, block_id = tip["slot"], tip["id"]
    logger.info("networkSynchronization: %s, tip slot=%d network=%s", sync, slot, KOIOS_NETWORK)
    return slot, block_id


async def _run_mempool_poller(ogmios_url: str, interval: float = 1.0) -> None:
    """Ogmios の Mempool Monitoring プロトコルを 1 秒間隔で叩いて mempool_state を更新する。
    UI 側も 1 秒 polling なので、画面表示は実質リアルタイム（最大ラグ ~1秒）。
    Chain-Sync とは別 WebSocket 接続で並走させる。

    フロー: acquireMempool → sizeOfMempool → releaseMempool
    """
    while True:
        try:
            async with websockets.connect(ogmios_url, ping_interval=30) as ws:
                logger.info("mempool poller 起動 (interval=%.1fs)", interval)
                while True:
                    # 1) acquire（スナップショット取得）
                    await ws.send(json.dumps({"jsonrpc": "2.0", "method": "acquireMempool"}))
                    json.loads(await ws.recv())

                    # 2) sizeOfMempool（容量と件数を取得）
                    await ws.send(json.dumps({"jsonrpc": "2.0", "method": "sizeOfMempool"}))
                    resp = json.loads(await ws.recv())
                    result = resp.get("result", {}) if isinstance(resp, dict) else {}
                    tx_count = (result.get("transactions") or {}).get("count", 0)
                    cur_size = (result.get("currentSize") or {}).get("bytes", 0)
                    max_cap  = (result.get("maxCapacity") or {}).get("bytes")

                    try:
                        upsert_mempool_state(
                            tx_count=int(tx_count or 0),
                            byte_size=int(cur_size or 0),
                            capacity_bytes=int(max_cap) if max_cap is not None else None,
                        )
                    except Exception as e:
                        logger.warning("mempool_state 書き込み失敗: %s", e)

                    # 3) release（次回 acquire のために解放）
                    await ws.send(json.dumps({"jsonrpc": "2.0", "method": "releaseMempool"}))
                    json.loads(await ws.recv())

                    await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("mempool poller エラー、5秒後に再接続: %s", e)
            await asyncio.sleep(5)


async def _run(ogmios_url: str, from_tip: bool = False) -> None:
    if from_tip:
        slot, block_id = _fetch_tip(ogmios_url)
        _save_cursor(slot, block_id)
        logger.info("tip カーソルを設定: slot=%d", slot)
        points = [{"slot": slot, "id": block_id}, "origin"]
        prev_epoch = _epoch_from_slot(slot)
    else:
        _fetch_tip(ogmios_url)  # ネットワーク自動検出のみ（カーソルは上書きしない）
        slot_str = get_state("global", None, "ogmios_last_slot")
        block_id = get_state("global", None, "ogmios_last_id")
        if slot_str and block_id:
            logger.info("前回カーソルから再開: slot=%s", slot_str)
            points = [{"slot": int(slot_str), "id": block_id}, "origin"]
            prev_epoch = _epoch_from_slot(int(slot_str))
        else:
            logger.info("genesis から同期開始")
            points = ["origin"]
            prev_epoch = -1

    async with websockets.connect(ogmios_url, ping_interval=30) as ws:
        await _find_intersection(ws, points)

        while True:
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "nextBlock"}))
            data = json.loads(await ws.recv())
            result = data.get("result", {})
            direction = result.get("direction")
            if direction == "forward":
                block = result.get("block", {})
                logger.info("ブロック受信 slot=%s", block.get("slot", "?"))
                try:
                    prev_epoch = _process_block(block, prev_epoch)
                except Exception as e:
                    logger.exception("ブロック処理エラー (slot=%s): %s", block.get("slot", "?"), e)

            elif direction == "backward":
                point = result.get("point", {})
                if not isinstance(point, dict):
                    # "origin" 文字列の場合: カーソル + recent_blocks 全消し
                    logger.info("rollback: origin まで巻き戻し → recent_blocks 全削除")
                    try:
                        deleted = delete_blocks_after_slot(0)
                        if deleted:
                            logger.info("rollback: recent_blocks から %d 件削除", deleted)
                    except Exception as e:
                        logger.warning("rollback の recent_blocks 削除失敗: %s", e)
                    prev_epoch = -1
                    continue
                slot = point.get("slot", 0)
                bid = point.get("id", "")
                logger.info("rollback: slot=%s", slot)
                _save_cursor(slot, bid)
                # rollback point より後 (slot > rollback_slot) のブロックを recent_blocks から削除
                try:
                    deleted = delete_blocks_after_slot(int(slot))
                    if deleted:
                        logger.info("rollback: slot > %d のブロックを %d 件削除", slot, deleted)
                except Exception as e:
                    logger.warning("rollback の recent_blocks 削除失敗: %s", e)
                if slot:
                    prev_epoch = _epoch_from_slot(slot)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cardanoism Ogmios チェーンシンク リスナー")
    parser.add_argument(
        "--ogmios-url",
        default=os.getenv("OGMIOS_URL", "ws://localhost:1337"),
        help="Ogmios WebSocket URL",
    )
    parser.add_argument(
        "--from-tip",
        action="store_true",
        help="起動時に現在の tip からカーソルを設定してジェネシスからの再生をスキップする",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    async def _run_all() -> None:
        await asyncio.gather(
            _run(args.ogmios_url, from_tip=args.from_tip),
            _run_mempool_poller(args.ogmios_url),
        )

    asyncio.run(_run_all())


if __name__ == "__main__":
    main()
