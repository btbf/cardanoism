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

# 新規 GA → IPFS メタ取得 + 翻訳 を直列化するロック。
_governance_lock: asyncio.Lock | None = None


def _get_rationale_lock() -> asyncio.Lock:
    """asyncio.Lock を遅延初期化 (実行中の event loop に紐付ける)。"""
    global _rationale_lock
    if _rationale_lock is None:
        _rationale_lock = asyncio.Lock()
    return _rationale_lock


def _get_governance_lock() -> asyncio.Lock:
    """asyncio.Lock を遅延初期化 (実行中の event loop に紐付ける)。"""
    global _governance_lock
    if _governance_lock is None:
        _governance_lock = asyncio.Lock()
    return _governance_lock

# Shelley+ era の epoch 長 (slot/epoch)。Byron-Shelley 遷移後はこの値で固定。
_SHELLEY_EPOCH_LENGTHS = {
    "mainnet": 432_000,
    "preprod": 432_000,
    "preview": 86_400,
}

# Byron-Shelley 遷移点 (Shelley が始まる絶対 slot と epoch 番号)。
# Byron era は 1 epoch = 21_600 slot 固定。
# preview は genesis から Shelley なので遷移点なし (slot 0 / epoch 0)。
_SHELLEY_TRANSITION = {
    "mainnet": (4_492_800, 208),   # epoch 0〜207 が Byron
    "preprod": (   86_400,   4),   # epoch 0〜3   が Byron
    "preview": (        0,   0),   # 純粋 Shelley
}
_BYRON_EPOCH_LENGTH = 21_600

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
    """絶対 slot から epoch 番号を導出する。

    mainnet / preprod は Byron-Shelley 遷移を考慮する。preview は純粋 Shelley。
    Shelley era の epoch 長はネットワークごとに違う (mainnet/preprod=432_000、
    preview=86_400)。
    """
    network = KOIOS_NETWORK if KOIOS_NETWORK in _SHELLEY_TRANSITION else "mainnet"
    transition_slot, transition_epoch = _SHELLEY_TRANSITION[network]
    shelley_len = _SHELLEY_EPOCH_LENGTHS[network]
    if slot < transition_slot:
        return slot // _BYRON_EPOCH_LENGTH
    return transition_epoch + (slot - transition_slot) // shelley_len


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
#
# 比較ベースラインは pools テーブル (Koios sync が常時更新する live 値) を使う。
# 再配信時の二重通知防止は notification_log.dedup_key 側で担保する。
# ──────────────────────────────────────────────────────────────────────────────

def _read_pool_pending_epoch(pool_id: str) -> int | None:
    """pools.pending_effective_epoch を返す (cert 反映予定エポック)。"""
    try:
        from cardanoism.backend.db_connect import get_db
        with get_db() as (cursor, _):
            cursor.execute(
                "SELECT pending_effective_epoch FROM pools "
                "WHERE pool_id_bech32 = ? LIMIT 1",
                (pool_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            v = row["pending_effective_epoch"]
            return int(v) if v is not None else None
    except Exception as e:  # noqa: BLE001
        logger.warning("listener: pending_effective_epoch 読み出し失敗 pool=%s: %s", pool_id, e)
        return None


def _read_pool_prev_fees(pool_id: str) -> tuple[float | None, int | None, int | None]:
    """pools テーブルの現在値 (margin, fixed_cost, pledge) を返す。
    cert 上書き前に呼ぶ前提。行が無い場合は (None, None, None)。
    """
    try:
        from cardanoism.backend.db_connect import get_db
        with get_db() as (cursor, _):
            cursor.execute(
                "SELECT margin, fixed_cost, pledge FROM pools "
                "WHERE pool_id_bech32 = ? LIMIT 1",
                (pool_id,),
            )
            row = cursor.fetchone()
            if not row:
                return (None, None, None)
            m = row["margin"]
            fc = row["fixed_cost"]
            pl = row["pledge"]
            return (
                float(m) if m is not None else None,
                int(fc) if fc is not None else None,
                int(pl) if pl is not None else None,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("listener: pools 旧値読み出し失敗 pool=%s: %s", pool_id, e)
        return (None, None, None)


def _notify_pool_fee_change(
    pool_id: str, margin: float, fixed_cost: int, pledge: int,
    prev: tuple[float | None, int | None, int | None] | None = None,
) -> None:
    """pools テーブル (Koios sync が常時更新) の前回値を比較ベースラインに通知判定する。

    prev が None または三項全 NULL の場合は比較ベースライン無しとみなして黙って終了
    する (新規プール / Koios sync 未到達)。
    """
    if prev is None:
        return
    old_margin, old_fixed, old_pledge = prev
    if old_margin is None and old_fixed is None and old_pledge is None:
        return

    # 変更判定: margin は float なので tolerance 比較、その他は整数比較
    margin_changed = old_margin is None or abs(float(old_margin) - float(margin)) > 1e-9
    fixed_changed = old_fixed is None or int(old_fixed) != int(fixed_cost)
    pledge_changed = old_pledge is None or int(old_pledge) != int(pledge)
    if not (margin_changed or fixed_changed or pledge_changed):
        return

    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("pool_fee_change"),
        get_stake_addrs_with_email_event("pool_fee_change"),
        get_stake_addrs_with_telegram_event("pool_fee_change"),
    )
    addrs = [a for a in addrs if a.get("delegated_pool_id") == pool_id]
    if not addrs:
        return

    old_margin_pct = (float(old_margin) * 100) if old_margin is not None else 0.0
    old_fixed_ada = (int(old_fixed) / 1_000_000) if old_fixed is not None else 0.0
    old_pledge_ada = (int(old_pledge) / 1_000_000) if old_pledge is not None else None

    margin_pct = margin * 100
    fixed_ada = fixed_cost / 1_000_000
    pledge_ada = pledge / 1_000_000

    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.pool_fee_change import context as build_ctx, EVENT_TYPE

    # 反映予定エポック (= cert 検知時点の次エポック)。pools.pending_effective_epoch と
    # 同じ値が入っていることを期待する。
    effective_epoch = _read_pool_pending_epoch(pool_id)

    for addr in addrs:
        pool_name = addr.get("delegated_pool_name") or get_pool_name(pool_id) or pool_id[:12]
        ctx = build_ctx(
            pool_name=pool_name,
            old_margin_pct=old_margin_pct, new_margin_pct=margin_pct,
            old_fixed_ada=old_fixed_ada,   new_fixed_ada=fixed_ada,
            old_pledge_ada=old_pledge_ada, new_pledge_ada=pledge_ada,
            apy=None,
            nickname=addr["nickname"], base_url=CARDANOISM_URL,
            effective_epoch=effective_epoch,
        )
        # dedup_key は cert の (margin, fixed_cost, pledge) で構成。同一 cert が
        # 再配信されても二重通知しない。
        dedup_val = f"{margin}:{fixed_cost}:{pledge}"
        deliver(addr, EVENT_TYPE, ctx,
                dedup_base=f"pool_fee_change_{addr['stake_id']}_{dedup_val}")


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: drep_new_governance_action (Tx 単位で集約)
#   proposals: [{"proposal_id": str, "proposal_index": int, "action_type": str,
#                "proposal_title": str | None, "is_spo": bool}, ...]
#   - 1 件のみ : 個別通知 (タイトル + action_type + GA リンク)
#   - 2 件以上 : 集約通知 (N 件の新 GA + governance ページリンク)
# ──────────────────────────────────────────────────────────────────────────────

def _notify_governance_action(tx_id: str, proposals: list[dict]) -> None:
    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.drep_new_governance_action import (
        context as build_ctx, EVENT_TYPE,
    )
    if not proposals:
        return
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("drep_new_governance_action"),
        get_stake_addrs_with_email_event("drep_new_governance_action"),
        get_stake_addrs_with_telegram_event("drep_new_governance_action"),
    )
    if not addrs:
        return

    # 新 GA 通知の内容はユーザーの委任先に依存しない (新 GA 自体の告知) ため、
    # 複数アドレスを登録していても 1 ユーザー 1 通知にする (epoch_start と同じ方針)。
    # 通知チャンネルは user 単位なので、user_id ごとに最初の 1 件だけ残せばよい。
    by_user: dict = {}
    for a in addrs:
        by_user.setdefault(a["user_id"], a)
    addrs = list(by_user.values())

    count = len(proposals)
    if count == 1:
        p = proposals[0]
        action_type_raw = p["action_type"]
        for addr in addrs:
            lang = addr.get("language", "ja")
            label = (_GA_TYPE_MAP_JA if lang == "ja" else _GA_TYPE_MAP_EN).get(action_type_raw, action_type_raw)
            ctx = build_ctx(
                action_label=label, base_url=CARDANOISM_URL,
                proposal_id=p["proposal_id"],
                proposal_title=p.get("proposal_title") or None,
                proposal_count=1,
            )
            deliver(addr, EVENT_TYPE, ctx,
                    dedup_base=f"new_gov_{tx_id}_{p['proposal_index']}_{addr['user_id']}")
    else:
        # 集約: 1 Tx に複数 GA
        for addr in addrs:
            ctx = build_ctx(
                action_label="", base_url=CARDANOISM_URL,
                proposal_id=None, proposal_title=None,
                proposal_count=count,
            )
            deliver(addr, EVENT_TYPE, ctx,
                    dedup_base=f"new_gov_batch_{tx_id}_{addr['user_id']}")


# ──────────────────────────────────────────────────────────────────────────────
# 通知発火: spo_pending_vote (SPO 対象 GA が新規提出された、Tx 単位で集約)
# ──────────────────────────────────────────────────────────────────────────────

def _notify_spo_pending_vote(tx_id: str, proposals: list[dict]) -> None:
    """SPO 対象の新規 GA が提出されたとき、SPO 設定があるユーザーへ催促通知。

    対象判定は spo_pool_id が NULL でない stake_address のみ。通知設定 spo_pending_vote
    が ON のチャンネルに送信。proposals は SPO 対象に絞り込み済み。
    """
    from cardanoism.backend.notify_templates import deliver
    from cardanoism.backend.notify_templates.spo_pending_vote import (
        context as build_ctx, EVENT_TYPE,
    )
    if not proposals:
        return
    addrs = _merge_stake_channels(
        get_stake_addrs_with_event("spo_pending_vote"),
        get_stake_addrs_with_email_event("spo_pending_vote"),
        get_stake_addrs_with_telegram_event("spo_pending_vote"),
    )
    addrs = [a for a in addrs if a.get("spo_pool_id")]
    if not addrs:
        return

    count = len(proposals)
    if count == 1:
        p = proposals[0]
        action_type_raw = p["action_type"]
        for addr in addrs:
            lang = addr.get("language", "ja")
            label = (_GA_TYPE_MAP_JA if lang == "ja" else _GA_TYPE_MAP_EN).get(action_type_raw, action_type_raw)
            ctx = build_ctx(
                action_label=label, base_url=CARDANOISM_URL,
                proposal_id=p["proposal_id"],
                proposal_title=p.get("proposal_title") or None,
                proposal_count=1,
            )
            deliver(addr, EVENT_TYPE, ctx,
                    dedup_base=f"spo_pending_{tx_id}_{p['proposal_index']}_{addr['stake_id']}")
    else:
        for addr in addrs:
            ctx = build_ctx(
                action_label="", base_url=CARDANOISM_URL,
                proposal_id=None, proposal_title=None,
                proposal_count=count,
            )
            deliver(addr, EVENT_TYPE, ctx,
                    dedup_base=f"spo_pending_batch_{tx_id}_{addr['stake_id']}")


# ──────────────────────────────────────────────────────────────────────────────
# 新規 GA 提案検知後のバックグラウンドタスク (IPFS フェッチ + 翻訳 + 通知)
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_and_save_proposal_meta(proposal_id: str, meta_url: str | None) -> dict | None:
    """IPFS / HTTPS から CIP-100/108 body を取得して governance_actions を UPDATE する。
    取得後の行 (翻訳ターゲット形式) を返す。失敗時は None。
    """
    from cardanoism.backend.db_connect import get_db
    from cardanoism.backend.vote_meta_fetch import fetch_vote_metadata_json, _extract_str

    title = abstract = motivation = rationale = None
    authors_json = None
    if meta_url:
        try:
            meta = fetch_vote_metadata_json(meta_url)
            if isinstance(meta, dict):
                body = meta.get("body") or {}
                if isinstance(body, dict):
                    title = _extract_str(body.get("title")) or None
                    abstract = _extract_str(body.get("abstract")) or None
                    motivation = _extract_str(body.get("motivation")) or None
                    rationale = _extract_str(body.get("rationale")) or None
                authors = meta.get("authors")
                if isinstance(authors, list):
                    names = [
                        str(a.get("name")).strip()
                        for a in authors
                        if isinstance(a, dict) and a.get("name")
                    ]
                    if names:
                        authors_json = json.dumps(names, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("listener: IPFS メタ取得失敗 proposal_id=%s url=%s: %s",
                           proposal_id, meta_url, e)

    with get_db() as (cursor, conn):
        # 取得できたフィールドだけ COALESCE で上書き (既存値を消さない)
        cursor.execute(
            """
            UPDATE governance_actions
               SET title       = COALESCE(?, title),
                   `abstract`  = COALESCE(?, `abstract`),
                   motivation  = COALESCE(?, motivation),
                   rationale   = COALESCE(?, rationale),
                   authors_json= COALESCE(?, authors_json),
                   updated_at  = NOW()
             WHERE proposal_id = ?
            """,
            (title, abstract, motivation, rationale, authors_json, proposal_id),
        )
        conn.commit()
        cursor.execute(
            "SELECT id, proposal_tx_hash, title, `abstract`, motivation, rationale, "
            "title_ja, abstract_ja, motivation_ja, rationale_ja "
            "FROM governance_actions WHERE proposal_id = ? LIMIT 1",
            (proposal_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


async def _process_proposal_post(tx_id: str, proposals: list[dict]) -> None:
    """新規 GA 提案検知後の bg タスク。

    proposals: [{"proposal_id": str, "proposal_index": int, "action_type": str,
                 "meta_url": str | None, "is_spo": bool}, ...]

    1. 各 proposal について IPFS から CIP-100/108 body を取得して DB を埋める
    2. OpenAI で title/abstract/motivation/rationale を翻訳して *_ja に保存
    3. AI 分析キューに enqueue (ga_ai_worker が後で拾う)
    4. 翻訳完了後、Tx 単位で集約 / 個別通知を発火
       - 1 件 : 個別通知 (タイトル + action_type + GA リンク)
       - 2 件以上 : 集約通知 (N 件の新 GA + governance ページリンク)

    listener のメインループはこのタスクを待たない (asyncio.create_task で発火)。
    並列バースト (OpenAI レート制限) を避けるため _governance_lock で順次実行する。
    """
    if not proposals:
        return
    loop = asyncio.get_event_loop()

    async with _get_governance_lock():
        translator = None
        try:
            from cardanoism.backend.governance import build_translator
            translator = await loop.run_in_executor(None, build_translator)
        except Exception as e:  # noqa: BLE001
            logger.exception("listener: translator 初期化失敗 (翻訳スキップ): %s", e)

        from cardanoism.backend.governance import _translate_one, save_translation
        for p in proposals:
            pid = p["proposal_id"]
            meta_url = p.get("meta_url")
            try:
                row = await loop.run_in_executor(
                    None, _fetch_and_save_proposal_meta, pid, meta_url,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("listener: proposal メタ取得失敗 proposal_id=%s: %s", pid, e)
                row = None

            chosen_title: str | None = None
            if row:
                if translator and row.get("title"):
                    try:
                        updates = await loop.run_in_executor(
                            None, _translate_one, translator, row, False,
                        )
                        if updates:
                            await loop.run_in_executor(
                                None, save_translation, row["id"], updates,
                            )
                            row.update(updates)
                    except Exception as e:  # noqa: BLE001
                        logger.exception("listener: 翻訳失敗 proposal_id=%s: %s", pid, e)
                chosen_title = row.get("title_ja") or row.get("title")
            p["proposal_title"] = chosen_title

    # AI 分析キューに enqueue (ga_ai_worker が後で拾う)。listener bg は AI を回さない。
    try:
        from cardanoism.backend.governance_ai_db import bulk_enqueue
        ids = [p["proposal_id"] for p in proposals if p.get("proposal_id")]
        if ids:
            await loop.run_in_executor(None, bulk_enqueue, ids)
    except Exception as e:  # noqa: BLE001
        logger.warning("listener: AI enqueue 失敗 (継続): %s", e)

    # 通知発火: 全員向け
    try:
        _notify_governance_action(tx_id, proposals)
    except Exception as e:  # noqa: BLE001
        logger.exception("listener: drep_new_governance_action 通知失敗 tx=%s: %s", tx_id, e)

    spo_proposals = [p for p in proposals if p.get("is_spo")]
    if spo_proposals:
        try:
            _notify_spo_pending_vote(tx_id, spo_proposals)
        except Exception as e:  # noqa: BLE001
            logger.exception("listener: spo_pending_vote 通知失敗 tx=%s: %s", tx_id, e)


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
        # cert で上書きする前に pools の旧値を読み出して通知判定に渡す
        prev_fees = _read_pool_prev_fees(pool_id)
        # Phase 3: pools テーブルに反映 (現エポックは pending_effective_epoch 計算に使う)
        try:
            record_pool_registration(cert, slot, current_epoch=_epoch_from_slot(slot))
        except Exception as e:
            logger.exception("listener: pool 登録 DB 書込み失敗: %s", e)
        _notify_pool_fee_change(
            pool_id, margin, cost_lovelace, pledge_lovelace, prev=prev_fees,
        )

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

    # 新規 GA 提案を Tx 単位に集約し、Tx 終わりにバックグラウンドタスクへ流す。
    # bg 内で IPFS フェッチ + 翻訳 → 通知の順に処理する (タイトル抜きで先行通知しない)。
    tx_proposals: list[dict] = []
    for proposal_idx, proposal in enumerate(tx.get("proposals", []) or []):
        try:
            action_type = proposal.get("action", {}).get("type", "")
            logger.info("governance_action 検知: tx=%s idx=%d type=%s", tx_id, proposal_idx, action_type)
            # Phase 1: governance_actions に直接 INSERT (タイトル等は bg で後埋め)
            proposal_id = None
            try:
                _is_new, proposal_id = record_proposal_from_event(
                    tx_id, proposal_idx, proposal, slot, current_epoch,
                )
            except Exception as e:
                logger.exception("listener: GA DB 書込み失敗 tx=%s idx=%d: %s", tx_id, proposal_idx, e)
            if not proposal_id:
                continue
            # SPO 対象判定 (security group の ParameterChange 等)
            is_spo = False
            try:
                from cardanoism.backend.spo_targets import compute_spo_target
                from cardanoism.backend.listener_governance import _ACTION_TYPE_MAP
                proposal_type_pascal = _ACTION_TYPE_MAP.get(action_type, action_type)
                is_spo = bool(compute_spo_target(proposal_type_pascal, proposal.get("action")))
            except Exception as e:
                logger.exception("listener: spo 判定失敗 tx=%s idx=%d: %s", tx_id, proposal_idx, e)
            # IPFS メタ URL (Ogmios v6.10+ は "metadata"、旧は "anchor")
            anchor = proposal.get("metadata") or proposal.get("anchor") or {}
            meta_url = anchor.get("url") if isinstance(anchor, dict) else None
            tx_proposals.append({
                "proposal_id":    proposal_id,
                "proposal_index": proposal_idx,
                "action_type":    action_type,
                "meta_url":       meta_url,
                "is_spo":         is_spo,
            })
        except Exception as e:
            logger.exception("proposal 処理エラー tx=%s: %s", tx_id, e)

    if tx_proposals:
        loop = asyncio.get_event_loop()
        loop.create_task(_process_proposal_post(tx_id, tx_proposals))

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
            # Ogmios の CredentialOrigin enum は "verificationKey" / "script"。
            has_script = voter.get("from") == "script"
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
            # epoch_start 通知は listener 初回起動時の境界 (last_notified is None) でも
            # 必ず送る。dedup_base=f"epoch_{epoch}" で重複送信は防がれるため、
            # catch-up replay で複数回呼ばれても二重送信にはならない。
            _notify_epoch_start(current_epoch)
            # pool_epoch_performance / *_sync は初回起動時はスキップ。
            # (前エポックのデータが揃っていない / 起動直後に重い sync を走らせない)
            if last_notified is not None:
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

async def _find_intersection(ws, points: list) -> str:
    """findIntersection を投げて intersection 種別を返す。

    戻り値:
      "matched"          : 要求した非 origin の point に intersection 成立
      "origin_fallback"  : 要求は非 origin だったが Ogmios が origin に落とした
                           (= 保存カーソルが Ogmios の chain で見つからない)
      "origin_only"      : 元から origin だけ要求していて origin で成立 (新規同期)
      "error"            : JSON-RPC error
    """
    await ws.send(json.dumps({
        "jsonrpc": "2.0",
        "method": "findIntersection",
        "params": {"points": points},
    }))
    resp = json.loads(await ws.recv())
    if "error" in resp:
        logger.warning("findIntersection 失敗: %s", resp.get("error"))
        return "error"

    tip = resp.get("result", {}).get("tip", {})
    intersection = resp.get("result", {}).get("intersection", {})
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

    # 要求 points に非 origin が含まれていたかを判定
    requested_non_origin = any(p != "origin" for p in points)
    intersected_at_origin = (
        intersection == "origin"
        or (isinstance(intersection, dict) and intersection.get("slot", 0) == 0)
    )
    if requested_non_origin and intersected_at_origin:
        return "origin_fallback"
    return "matched" if requested_non_origin else "origin_only"


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
    """chainsync ループ本体。

    WebSocket 切断 (keepalive ping timeout / Ogmios 側エラー等) で例外が出たら
    5 秒待って再接続する。--from-tip 指定は初回起動時のみ有効で、再接続時は
    常に保存カーソルから再開する。
    """
    first_iter_from_tip = from_tip
    while True:
        try:
            await _run_session(ogmios_url, from_tip=first_iter_from_tip)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("chainsync 切断/エラー、5秒後に再接続: %s", e)
        first_iter_from_tip = False
        await asyncio.sleep(5)


async def _run_session(ogmios_url: str, from_tip: bool = False) -> None:
    """1 回ぶんの chainsync セッション。例外は呼び出し元 (_run) が拾って再接続。"""
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
        result = await _find_intersection(ws, points)
        # 保存カーソルが Ogmios の chain に見つからない (= ネットワーク切替や
        # Ogmios DB 再構築) と Ogmios は points 列の次候補 "origin" で intersection
        # を成立させてしまい、その後の nextBlock がジェネシスから流れ始める。
        # 想定外の全期間再生を避けるため、tip にジャンプして再 intersect する。
        if result == "origin_fallback":
            logger.warning(
                "保存カーソル (slot=%s) が Ogmios の chain に見つかりません — "
                "ジェネシス再生を回避するため tip にジャンプします",
                str(points[0].get("slot")) if isinstance(points[0], dict) else "?",
            )
            tip_slot, tip_id = _fetch_tip(ogmios_url)
            _save_cursor(tip_slot, tip_id)
            points = [{"slot": tip_slot, "id": tip_id}, "origin"]
            prev_epoch = _epoch_from_slot(tip_slot)
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
