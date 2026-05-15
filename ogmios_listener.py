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
    get_users_with_event, get_users_with_email_event, get_users_with_telegram_event,
    get_stake_addrs_with_event, get_stake_addrs_with_email_event,
    get_stake_addrs_with_telegram_event,
    _merge_stake_channels,
    CARDANOISM_URL,
)
from cardanoism.backend import line_flex
from cardanoism.backend.mail_notify import build_html, build_text
from cardanoism.backend.koios import get_proposal_title, get_proposal_info, get_pool_name, get_pool_epoch_stats, get_pool_apy
from cardanoism.backend.recent_blocks_db import insert_block, trim_old_blocks, delete_blocks_after_slot
from cardanoism.backend.mempool_db import upsert_mempool_state
from cardanoism.backend.listener_db import rollback_listener_state
from cardanoism.backend.listener_governance import (
    record_proposal_from_event,
    record_vote_from_event,
    encode_voter_id,
)
from cardanoism.backend.listener_dreps import (
    record_drep_registration,
    record_drep_retirement,
    record_drep_update,
)
from cardanoism.backend.listener_pools import (
    record_pool_registration,
    record_pool_retirement,
)
from cardanoism.backend.listener_stake import (
    record_stake_delegation,
    record_vote_delegation,
    record_stake_and_vote_delegation,
    record_combined_registration_and_delegation,
)
from cardanoism.backend.listener_epoch_sync import trigger_epoch_syncs

logger = logging.getLogger("ogmios_listener")

KOIOS_NETWORK = os.getenv("KOIOS_NETWORK", "mainnet").lower()

# 診断用: LISTENER_DEBUG_TX_DUMP=1 のとき、tx のキー一覧と votes/proposals の生 JSON を WARNING ログに出す。
# 未設定なら無効。本番では env を立てないこと。
_DBG_TX_DUMP = os.getenv("LISTENER_DEBUG_TX_DUMP", "").strip().lower() in ("1", "true", "yes")
_dbg_tx_keys_logged = 0

# 診断用: LISTENER_DEBUG_CERT_DUMP=1 のとき、各 cert の type と生 JSON を WARNING ログに出す。
# Ogmios v6 の cert (delegation / DRep registration 等) の構造確認用。
_DBG_CERT_DUMP = os.getenv("LISTENER_DEBUG_CERT_DUMP", "").strip().lower() in ("1", "true", "yes")

# DRep 投票 → rationale 取得 + 翻訳 を直列化するロック。
# 並列バースト (OpenAI レート制限ヒット) を避けるため、bg タスクは順次実行する。
_rationale_lock: asyncio.Lock | None = None


def _get_rationale_lock() -> asyncio.Lock:
    """asyncio.Lock を遅延初期化 (実行中の event loop に紐付ける)。"""
    global _rationale_lock
    if _rationale_lock is None:
        _rationale_lock = asyncio.Lock()
    return _rationale_lock

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
    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.pool_epoch_performance import (
        context as build_ctx, EVENT_TYPE,
    )
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("pool_epoch_performance"),
        get_stake_addrs_with_email_event("pool_epoch_performance"),
        get_stake_addrs_with_telegram_event("pool_epoch_performance"),
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
        pool_name = addr.get("delegated_pool_name") or get_pool_name(pool_id) or pool_id[:12]
        ctx = build_ctx(
            pool_name=pool_name, prev_epoch=prev_epoch,
            active_stake_ada=stats["active_stake_ada"],
            saturation_pct=stats["saturation_pct"],
            block_cnt=stats["block_cnt"],
            apy=stats["apy"], apy_epoch=apy_epoch if stats["apy"] is not None else None,
            nickname=addr["nickname"], base_url=CARDANOISM_URL,
        )
        deliver(addr, EVENT_TYPE, ctx,
                dedup_base=f"pool_epoch_perf_{addr['stake_id']}_{prev_epoch}")


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: epoch_start
# ──────────────────────────────────────────────────────────────────────────────

def _notify_epoch_start(epoch: int) -> None:
    """新エポック開始通知。3 チャンネル統合送信を notify_templates 経由で行う。"""
    from cardanoism.backend.notify_templates import (
        deliver, merge_user_channels,
    )
    from cardanoism.backend.notify_templates.epoch_start import (
        context as build_ctx, EVENT_TYPE,
    )

    line_users = get_users_with_event("epoch_start")
    email_users = get_users_with_email_event("epoch_start")
    tg_users = get_users_with_telegram_event("epoch_start")

    addrs = merge_user_channels(line_users, email_users, tg_users)
    if not addrs:
        return

    ctx = build_ctx(epoch, CARDANOISM_URL)
    for addr in addrs:
        deliver(addr, EVENT_TYPE, ctx, dedup_base=f"epoch_{epoch}")


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: pool_retire
# ──────────────────────────────────────────────────────────────────────────────

def _notify_pool_retire(pool_id: str, retiring_epoch: int) -> None:
    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.pool_retire import context as build_ctx, EVENT_TYPE
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("pool_retire"),
        get_stake_addrs_with_email_event("pool_retire"),
        get_stake_addrs_with_telegram_event("pool_retire"),
    )
    for addr in addrs:
        if addr.get("delegated_pool_id") != pool_id:
            continue
        pool_name = addr.get("delegated_pool_name") or get_pool_name(pool_id) or pool_id[:12]
        ctx = build_ctx(
            pool_name=pool_name, retiring_epoch=retiring_epoch,
            nickname=addr["nickname"], base_url=CARDANOISM_URL,
        )
        deliver(addr, EVENT_TYPE, ctx,
                dedup_base=f"pool_retire_{addr['stake_id']}_{retiring_epoch}")


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
        get_stake_addrs_with_telegram_event("pool_fee_change"),
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

    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.pool_fee_change import context as build_ctx, EVENT_TYPE

    for addr in addrs:
        pool_name = addr.get("delegated_pool_name") or get_pool_name(pool_id) or pool_id[:12]
        ctx = build_ctx(
            pool_name=pool_name,
            old_margin_pct=old_margin_pct, new_margin_pct=margin_pct,
            old_fixed_ada=old_fixed_ada,   new_fixed_ada=fixed_ada,
            old_pledge_ada=old_pledge_ada, new_pledge_ada=pledge_ada,
            apy=None,
            nickname=addr["nickname"], base_url=CARDANOISM_URL,
        )
        deliver(addr, EVENT_TYPE, ctx,
                dedup_base=f"pool_fee_change_{addr['stake_id']}_{current_val}")


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: drep_new_governance_action
# ──────────────────────────────────────────────────────────────────────────────

def _notify_governance_action(tx_id: str, proposal_idx: int, action_type_raw: str) -> None:
    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.drep_new_governance_action import (
        context as build_ctx, EVENT_TYPE,
    )
    from cardanoism.backend.listener_governance import encode_proposal_id

    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_new_governance_action"),
        get_stake_addrs_with_email_event("drep_new_governance_action"),
        get_stake_addrs_with_telegram_event("drep_new_governance_action"),
    )
    if not addrs:
        return

    proposal_id = encode_proposal_id(tx_id, proposal_idx) or ""

    for addr in addrs:
        lang = addr.get("language", "ja")
        label = (_GA_TYPE_MAP_JA if lang == "ja" else _GA_TYPE_MAP_EN).get(action_type_raw, action_type_raw)
        ctx = build_ctx(action_label=label, base_url=CARDANOISM_URL, proposal_id=proposal_id)
        deliver(addr, EVENT_TYPE, ctx, dedup_base=f"new_gov_{tx_id}_{proposal_idx}_{addr['stake_id']}")


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: spo_pending_vote (SPO 対象 GA が新規提出された)
# ──────────────────────────────────────────────────────────────────────────────

def _notify_spo_pending_vote(tx_id: str, proposal_idx: int, action_type_raw: str) -> None:
    """SPO 対象の新規 GA が提出されたとき、SPO 設定があるユーザーへ催促通知。

    対象判定は spo_pool_id が NULL でない stake_address のみ。通知設定 spo_pending_vote
    が ON のチャンネルに送信。
    """
    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.spo_pending_vote import (
        context as build_ctx, EVENT_TYPE,
    )
    from cardanoism.backend.listener_governance import encode_proposal_id

    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("spo_pending_vote"),
        get_stake_addrs_with_email_event("spo_pending_vote"),
        get_stake_addrs_with_telegram_event("spo_pending_vote"),
    )
    addrs = [a for a in addrs if a.get("spo_pool_id")]
    if not addrs:
        return

    proposal_id = encode_proposal_id(tx_id, proposal_idx) or ""

    for addr in addrs:
        lang = addr.get("language", "ja")
        label = (_GA_TYPE_MAP_JA if lang == "ja" else _GA_TYPE_MAP_EN).get(action_type_raw, action_type_raw)
        ctx = build_ctx(action_label=label, base_url=CARDANOISM_URL, proposal_id=proposal_id)
        deliver(addr, EVENT_TYPE, ctx,
                dedup_base=f"spo_pending_{tx_id}_{proposal_idx}_{addr['stake_id']}")


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: drep_vote
# ──────────────────────────────────────────────────────────────────────────────

def _notify_drep_vote(drep_id: str, votes_list: list[dict], tx_id: str) -> None:
    """DRep 投票を Tx 単位で集約して通知する。

    votes_list: [{"vote": "Yes", "gov_tx_hash": "...", "gov_index": 0}, ...]
      - 1 件のみ: 投票タイトル + 投票内容 + GA リンク (個別通知)
      - 2 件以上: N 件投票 + DRep 個人ページリンク (集約通知)
    """
    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.drep_vote import (
        context as build_ctx, EVENT_TYPE,
    )
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_vote"),
        get_stake_addrs_with_email_event("drep_vote"),
        get_stake_addrs_with_telegram_event("drep_vote"),
    )
    addrs = [a for a in addrs if a.get("delegated_drep_id") == drep_id]
    if not addrs or not votes_list:
        return

    vote_count = len(votes_list)
    if vote_count == 1:
        v = votes_list[0]
        gov_tx_hash = v["gov_tx_hash"]
        gov_index = v["gov_index"]
        info = get_proposal_info(gov_tx_hash, gov_index) if gov_tx_hash else None
        proposal_title = (info or {}).get("title") or None
        action_type    = (info or {}).get("proposal_type") or None
        proposal_id    = (info or {}).get("proposal_id") or None
        for addr in addrs:
            drep_name = addr.get("delegated_drep_name") or drep_id[:12]
            ctx = build_ctx(
                drep_name=drep_name, vote=v["vote"], proposal_title=proposal_title,
                nickname=addr["nickname"], base_url=CARDANOISM_URL,
                action_type=action_type, proposal_id=proposal_id,
                vote_count=1, drep_id=drep_id,
            )
            deliver(addr, EVENT_TYPE, ctx,
                    dedup_base=f"drep_vote_{addr['stake_id']}_{gov_tx_hash}_{gov_index}")
    else:
        # 集約: 1 Tx 内に複数の vote (= 同じ DRep が複数 GA に投票)
        for addr in addrs:
            drep_name = addr.get("delegated_drep_name") or drep_id[:12]
            ctx = build_ctx(
                drep_name=drep_name, vote="", proposal_title=None,
                nickname=addr["nickname"], base_url=CARDANOISM_URL,
                action_type=None, proposal_id=None,
                vote_count=vote_count, drep_id=drep_id,
            )
            deliver(addr, EVENT_TYPE, ctx,
                    dedup_base=f"drep_vote_batch_{addr['stake_id']}_{tx_id}")


async def _process_drep_vote_post(drep_id: str, votes_list: list[dict], tx_id: str) -> None:
    """DRep 投票検知後のバックグラウンド処理。

    1. IPFS から meta_url を辿って投票理由本文を取得
    2. 英語なら OpenAI で日本語訳して proposal_votes.rationale / rationale_ja を埋める
    3. 上記が失敗しても必ず _notify_drep_vote は呼ぶ (rationale 抜きでも通知は飛ばす)

    listener のメインループはこのタスクを待たない (asyncio.create_task で発火)。
    並列バースト (OpenAI レート制限) を避けるため _rationale_lock で順次実行する。
    """
    loop = asyncio.get_event_loop()
    try:
        async with _get_rationale_lock():
            # 既存の sync 処理を別スレッドで呼ぶ。fetch_limit を絞って 1 ループあたり軽量に。
            # 今 listener が書いた vote も block_time DESC で対象に含まれる。
            from notify_worker import check_vote_rationale_sync
            await loop.run_in_executor(
                None,
                check_vote_rationale_sync,
                20,   # fetch_limit
                10,   # translate_limit
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("rationale 取得失敗 (続行): drep=%s tx=%s: %s", drep_id, tx_id, e)
    # rationale 取得の成否に関わらず通知発火 (UX 優先)
    try:
        _notify_drep_vote(drep_id, votes_list, tx_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("drep_vote 通知失敗: drep=%s tx=%s: %s", drep_id, tx_id, e)


# ──────────────────────────────────────────────────────────────────────────────
# ブロック処理
# ──────────────────────────────────────────────────────────────────────────────

def _process_cert(cert: dict, slot: int) -> None:
    cert_type = cert.get("type")

    # ── 診断 (LISTENER_DEBUG_CERT_DUMP=1 のときのみ) ──
    # cert の生 JSON を出して Ogmios v6 の実構造を確認する。
    if _DBG_CERT_DUMP:
        logger.warning(
            "DEBUG_CERT type=%s slot=%d raw=%s",
            cert_type, slot,
            json.dumps(cert, ensure_ascii=False)[:800],
        )

    if cert_type == "stakePoolRetirement":
        pool = cert.get("stakePool", {})
        pool_id = pool.get("id", "")
        retiring_epoch = pool.get("retirementEpoch", 0)
        logger.info("pool_retire 検知: pool=%s epoch=%d", pool_id, retiring_epoch)
        # Phase 3: pools テーブルに反映
        try:
            record_pool_retirement(cert, slot)
        except Exception as e:
            logger.exception("listener: pool 引退 DB 書込み失敗: %s", e)
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
        # Phase 3: pools テーブルに反映
        try:
            record_pool_registration(cert, slot)
        except Exception as e:
            logger.exception("listener: pool 登録 DB 書込み失敗: %s", e)
        _notify_pool_fee_change(pool_id, margin, cost_lovelace, pledge_lovelace)

    # ── Phase 2: DRep cert ─────────────────────────────────────────────────
    elif cert_type == "delegateRepresentativeRegistration":
        try:
            record_drep_registration(cert, slot)
        except Exception as e:
            logger.exception("listener: DRep 登録 DB 書込み失敗: %s", e)

    elif cert_type == "delegateRepresentativeRetirement":
        try:
            record_drep_retirement(cert, slot)
        except Exception as e:
            logger.exception("listener: DRep 退任 DB 書込み失敗: %s", e)

    elif cert_type == "delegateRepresentativeUpdate":
        try:
            record_drep_update(cert, slot)
        except Exception as e:
            logger.exception("listener: DRep 更新 DB 書込み失敗: %s", e)

    # ── Phase 4: 委任 cert ─────────────────────────────────────────────────
    elif cert_type == "stakeDelegation":
        try:
            record_stake_delegation(cert, slot)
        except Exception as e:
            logger.exception("listener: stake 委任 DB 書込み失敗: %s", e)

    elif cert_type == "voteDelegation":
        try:
            record_vote_delegation(cert, slot)
        except Exception as e:
            logger.exception("listener: vote 委任 DB 書込み失敗: %s", e)

    elif cert_type == "stakeAndVoteDelegation":
        try:
            record_stake_and_vote_delegation(cert, slot)
        except Exception as e:
            logger.exception("listener: stake+vote 委任 DB 書込み失敗: %s", e)

    elif cert_type in (
        "stakeRegistrationAndDelegation",
        "stakeRegistrationAndVoteDelegation",
        "stakeRegistrationAndStakeAndVoteDelegation",
    ):
        try:
            record_combined_registration_and_delegation(cert, slot)
        except Exception as e:
            logger.exception("listener: stake 登録 + 委任合体 cert DB 書込み失敗: %s", e)


def _process_tx(tx: dict, slot: int, current_epoch: int) -> None:
    tx_id = tx.get("id", "")

    # ── 診断 (LISTENER_DEBUG_TX_DUMP=1 のときのみ) ──
    # listener が受け取った tx オブジェクトの構造を確認するためのログ。
    # (1) 最初の 5 件: tx のトップレベルキー一覧
    # (2) votes / proposals を持つ tx: 生 JSON (Conway era で実際に渡される内容を確認)
    if _DBG_TX_DUMP:
        global _dbg_tx_keys_logged
        if _dbg_tx_keys_logged < 5:
            logger.warning(
                "DEBUG_TX_KEYS tx=%s slot=%d keys=%s",
                tx_id[:16], slot, list(tx.keys()),
            )
            _dbg_tx_keys_logged += 1
        if tx.get("votes") or tx.get("proposals"):
            logger.warning(
                "DEBUG_TX_GOV tx=%s slot=%d votes=%d proposals=%d raw_votes=%s raw_proposals=%s",
                tx_id, slot,
                len(tx.get("votes") or []),
                len(tx.get("proposals") or []),
                json.dumps(tx.get("votes") or [], ensure_ascii=False)[:600],
                json.dumps(tx.get("proposals") or [], ensure_ascii=False)[:1200],
            )

    for cert in tx.get("certificates", []):
        try:
            _process_cert(cert, slot)
        except Exception as e:
            logger.exception("cert 処理エラー tx=%s: %s", tx_id, e)

    for proposal_idx, proposal in enumerate(tx.get("proposals", []) or []):
        try:
            action_type = proposal.get("action", {}).get("type", "")
            logger.info("governance_action 検知: tx=%s idx=%d type=%s", tx_id, proposal_idx, action_type)
            # Phase 1: governance_actions に直接 INSERT
            try:
                record_proposal_from_event(tx_id, proposal_idx, proposal, slot, current_epoch)
            except Exception as e:
                logger.exception("listener: GA DB 書込み失敗 tx=%s idx=%d: %s", tx_id, proposal_idx, e)
            # 通知発火: 全員向け (drep_new_governance_action)
            _notify_governance_action(tx_id, proposal_idx, action_type)
            # SPO 対象の場合は SPO 専用通知も発火
            try:
                from cardanoism.backend.spo_targets import compute_spo_target
                from cardanoism.backend.listener_governance import _ACTION_TYPE_MAP
                proposal_type_pascal = _ACTION_TYPE_MAP.get(action_type, action_type)
                if compute_spo_target(proposal_type_pascal, proposal.get("action")):
                    _notify_spo_pending_vote(tx_id, proposal_idx, action_type)
            except Exception as e:
                logger.exception("listener: spo_pending_vote 通知失敗: %s", e)
        except Exception as e:
            logger.exception("proposal 処理エラー tx=%s: %s", tx_id, e)

    # DRep 投票を drep_id 単位に集約して、Tx 終わりに 1 回だけ通知発火する。
    # (1 Tx で複数 GA に投票するケースを集約通知に切り替えるため)
    drep_votes_by_id: dict[str, list[dict]] = {}
    _VOTE_NORMALIZE = {"yes": "Yes", "no": "No", "abstain": "Abstain"}
    for vote in tx.get("votes", []):
        try:
            # Ogmios v6.10+ は "issuer" / "proposal"、旧は "voter" / "actionId"。両対応。
            voter = vote.get("issuer") or vote.get("voter") or {}
            voter_role = voter.get("role")
            # Phase 1: 全 voter role を proposal_votes に書く (DRep / SPO / CC)
            try:
                record_vote_from_event(vote, slot)
            except Exception as e:
                logger.exception("listener: vote DB 書込み失敗 tx=%s: %s", tx_id, e)
            # 通知発火は従来どおり DRep のみ
            if voter_role != "delegateRepresentative":
                continue
            # DRep id は Ogmios だと hex で来るが、stake_addresses.delegated_drep_id は
            # bech32 (drep1...) で記録される。フィルタを通すため bech32 に揃える。
            drep_hex = voter.get("id", "")
            has_script = bool(
                voter.get("isScript")
                or voter.get("kind") == "scriptHash"
                or voter.get("type") == "script"
                or voter.get("from") == "scriptHash"
            )
            drep_id = encode_voter_id("DRep", drep_hex, has_script=has_script) or drep_hex
            raw_vote = (vote.get("vote") or "").lower()
            vote_str = _VOTE_NORMALIZE.get(raw_vote, raw_vote)
            action_id = vote.get("proposal") or vote.get("actionId") or {}
            gov_tx_hash = action_id.get("transaction", {}).get("id", "")
            gov_index = action_id.get("index", 0)
            logger.info("drep_vote 検知: drep=%s vote=%s gov_tx=%s#%d", drep_id, vote_str, gov_tx_hash, gov_index)
            drep_votes_by_id.setdefault(drep_id, []).append({
                "vote": vote_str,
                "gov_tx_hash": gov_tx_hash,
                "gov_index": gov_index,
            })
        except Exception as e:
            logger.exception("vote 処理エラー tx=%s: %s", tx_id, e)

    # 集約通知発火（drep_id ごとに 1 回。vote_count で個別/集約を出し分ける）
    # rationale 取得 (IPFS + OpenAI) と通知発火はバックグラウンドタスクに切り出して
    # listener のメインループを止めない。IPFS / OpenAI が失敗しても _process_drep_vote_post
    # 内で通知は必ず飛ぶ仕様。
    if drep_votes_by_id:
        loop = asyncio.get_event_loop()
        for drep_id, votes_list in drep_votes_by_id.items():
            loop.create_task(_process_drep_vote_post(drep_id, votes_list, tx_id))


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
                # Phase 5: エポック境界に依存する各種 *_sync を非同期で発火
                try:
                    trigger_epoch_syncs(current_epoch)
                except Exception as e:
                    logger.exception("epoch_start sync 起動エラー: %s", e)

    for tx in block.get("transactions", []):
        _process_tx(tx, slot, current_epoch)

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
        # intersection / tip は "origin" 文字列の場合があるので dict 限定で slot を取り出す
        inter_disp = intersection.get("slot", "?") if isinstance(intersection, dict) else str(intersection)
        tip_disp = tip.get("slot", "?") if isinstance(tip, dict) else str(tip)
        logger.info("findIntersection 成功: intersection=%s, tip slot=%s", inter_disp, tip_disp)
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
                logger.info(
                    "ブロック受信 height=%s slot=%s",
                    block.get("height", "?"), block.get("slot", "?"),
                )
                try:
                    prev_epoch = _process_block(block, prev_epoch)
                except Exception as e:
                    logger.exception(
                        "ブロック処理エラー (height=%s slot=%s): %s",
                        block.get("height", "?"), block.get("slot", "?"), e,
                    )

            elif direction == "backward":
                point = result.get("point", {})
                if not isinstance(point, dict):
                    # "origin" 文字列の場合: カーソル + 全 listener-managed テーブル全消し
                    logger.info("rollback: origin まで巻き戻し")
                    try:
                        deleted = delete_blocks_after_slot(0)
                        if deleted:
                            logger.info("rollback: recent_blocks から %d 件削除", deleted)
                    except Exception as e:
                        logger.warning("rollback の recent_blocks 削除失敗: %s", e)
                    rollback_listener_state(0)
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
                # listener-managed テーブルも巻き戻す (Phase 1〜4 で対象が増える)
                rollback_listener_state(int(slot))
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
