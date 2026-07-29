"""listener_governance.py
Ogmios listener から呼ばれる Governance Action / 投票の DB 直書きハンドラ。

Phase 1 で実装した即時反映ロジック:
- ProposalProcedure 検出 → governance_actions に新規行 INSERT (anchor URL 等の最小限)
- VotingProcedure 検出   → proposal_votes に新規行 UPSERT
- title / abstract / motivation / rationale 等のメタデータは Koios sync が後追いで埋める
  (anchor IPFS の非同期 fetch は Phase 1.1 で追加検討)

データソースは Ogmios から流れてくる block.transactions の中の proposals[] / votes[]。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pycardano.crypto.bech32 import bech32_encode, convertbits, Encoding  # type: ignore

from cardanoism.backend.governance import upsert_proposal as governance_upsert
from cardanoism.backend.vote_db import upsert_vote as vote_upsert
from cardanoism.backend.spo_targets import compute_spo_target

logger = logging.getLogger(__name__)


# Ogmios action.type (camelCase) → Koios/DB 表記 (PascalCase / 一部別名)
_ACTION_TYPE_MAP = {
    "treasuryWithdrawals": "TreasuryWithdrawals",
    "parameterChange":     "ParameterChange",
    "hardForkInitiation":  "HardForkInitiation",
    "noConfidence":        "NoConfidence",
    "updateCommittee":     "UpdateCommittee",
    "newConstitution":     "NewConstitution",
    "information":         "InfoAction",
}

# Ogmios voter.role → DB voter_role
_VOTER_ROLE_MAP = {
    "delegateRepresentative":  "DRep",
    "stakePoolOperator":       "SPO",
    "constitutionalCommittee": "ConstitutionalCommittee",
}


def _encode_bech32(hrp: str, data_bytes: bytes) -> str | None:
    """8-bit bytes を bech32 文字列にエンコードする。Cardano の HRP は全て BECH32 (BECH32M 不使用)。"""
    try:
        bits5 = convertbits(list(data_bytes), 8, 5, True)
        if bits5 is None:
            return None
        return bech32_encode(hrp, bits5, Encoding.BECH32)
    except Exception as e:  # noqa: BLE001
        logger.warning("bech32_encode failed (hrp=%s): %s", hrp, e)
        return None


def encode_proposal_id(tx_hash_hex: str, index: int) -> str | None:
    """CIP-129 gov_action ID を bech32 で構築する。

    HRP="gov_action", data = tx_hash (32 byte) + index (1 byte)
    """
    try:
        tx_bytes = bytes.fromhex(tx_hash_hex)
    except ValueError:
        return None
    if len(tx_bytes) != 32 or not (0 <= index <= 255):
        return None
    return _encode_bech32("gov_action", tx_bytes + bytes([index]))


# CIP-129 の header byte = (key type << 4) | credential type
#   key type  : CC Hot = 0b0000 / CC Cold = 0b0001 / DRep = 0b0010
#   cred type : KeyHash = 0b0010 / ScriptHash = 0b0011
# → DRep   key=0x22 script=0x23
#   CC Hot key=0x02 script=0x03
# pool id だけは CIP-129 ではなく生の 28byte ハッシュ (hrp="pool")。
_CIP129_HEADERS = {
    # role: (key hash header, script hash header)
    "DRep":                    (0x22, 0x23),
    "ConstitutionalCommittee": (0x02, 0x03),
}


def encode_voter_id(role: str, voter_hex: str, has_script: bool = False) -> str | None:
    """Ogmios voter id (hex) → Koios と同じ bech32 形式に変換する。

    DRep    : CIP-129 形式 (header byte + 28 byte hash) → drep1...
    CC      : CIP-129 形式 (header byte + 28 byte hash) → cc_hot1...
    SPO     : pool1... (CIP-129 ではなく生の 28 byte hash)

    CC に header byte を付け忘れると Koios の voter_id と一致せず、
    cc_members と突き合わない別人の投票として二重登録されるので注意。
    """
    try:
        raw = bytes.fromhex(voter_hex)
    except ValueError:
        return None
    if len(raw) != 28:
        return None

    if role == "SPO":
        return _encode_bech32("pool", raw)
    headers = _CIP129_HEADERS.get(role)
    if headers is None:
        return None
    header = headers[1] if has_script else headers[0]
    hrp = "drep" if role == "DRep" else "cc_hot"
    return _encode_bech32(hrp, bytes([header]) + raw)


def _now_dt() -> datetime:
    """Ogmios 受信時刻を block_time として使う (秒オーダー誤差 OK)。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _extract_withdrawals(action: dict) -> tuple[int | None, str | None]:
    """TreasuryWithdrawals action の withdrawal 配列を集計。

    Ogmios v6 形式:
      action.withdrawals = [{value: {ada: {lovelace: N}}, address: "stake1..."}, ...]
    """
    wlist = action.get("withdrawals") or []
    if not isinstance(wlist, list) or not wlist:
        return None, None
    total = 0
    normalized = []
    for w in wlist:
        if not isinstance(w, dict):
            continue
        val = w.get("value") or {}
        ada = val.get("ada") if isinstance(val, dict) else None
        amt = (ada.get("lovelace") if isinstance(ada, dict) else None) or w.get("amount") or 0
        stake = w.get("address") or w.get("stake_address") or w.get("rewardAccount")
        try:
            amt_int = int(amt)
        except (TypeError, ValueError):
            continue
        total += amt_int
        if stake:
            normalized.append({"stake_address": str(stake), "amount": amt_int})
    if total == 0 and not normalized:
        return None, None
    return total, json.dumps(normalized, ensure_ascii=False) if normalized else None


def record_proposal_from_event(
    tx_hash: str,
    proposal_index: int,
    proposal_obj: dict,
    slot: int,
    epoch_no: int,
) -> tuple[bool, str | None]:
    """Ogmios の proposal を governance_actions に upsert する。

    戻り値: (新規 INSERT なら True, proposal_id)
    """
    proposal_id = encode_proposal_id(tx_hash, proposal_index)
    if not proposal_id:
        logger.warning("listener: proposal_id 計算失敗 tx=%s idx=%d", tx_hash, proposal_index)
        return False, None

    action = proposal_obj.get("action") or {}
    action_type_raw = action.get("type") or ""
    proposal_type = _ACTION_TYPE_MAP.get(action_type_raw, action_type_raw)

    deposit_obj = (proposal_obj.get("deposit") or {}).get("ada") or {}
    deposit = deposit_obj.get("lovelace") if isinstance(deposit_obj, dict) else None
    return_address = proposal_obj.get("returnAccount")

    # Ogmios v6.10+ は "metadata"、旧は "anchor"
    anchor = proposal_obj.get("metadata") or proposal_obj.get("anchor") or {}
    meta_url = anchor.get("url") if isinstance(anchor, dict) else None
    meta_hash = anchor.get("hash") if isinstance(anchor, dict) else None

    withdrawal_total, withdrawal_json = (None, None)
    if proposal_type == "TreasuryWithdrawals":
        withdrawal_total, withdrawal_json = _extract_withdrawals(action)

    # SPO 投票対象判定 (security group の ParameterChange 等)
    spo_target = compute_spo_target(proposal_type, action)

    fields = {
        "proposal_id":      proposal_id,
        "proposal_tx_hash": tx_hash,
        "proposal_index":   int(proposal_index),
        "proposal_type":    proposal_type,
        "deposit":          int(deposit) if deposit is not None else None,
        "withdrawal_total_lovelace": withdrawal_total,
        "withdrawal_json":  withdrawal_json,
        "return_address":   return_address,
        "proposed_epoch":   int(epoch_no) if epoch_no is not None else None,
        "ratified_epoch":   None,
        "enacted_epoch":    None,
        "dropped_epoch":    None,
        "expired_epoch":    None,
        "expiration":       None,
        "block_time":       _now_dt(),
        "meta_url":         meta_url,
        "meta_hash":        meta_hash,
        "meta_is_valid":    None,
        "title":            None,
        "abstract":         None,
        "motivation":       None,
        "rationale":        None,
        "references_json":  None,
        "action_anchor_url":  None,
        "action_anchor_hash": None,
        "last_event_slot":  int(slot),
        "spo_target":       spo_target,
    }

    try:
        is_new = governance_upsert(fields)
    except Exception as e:  # noqa: BLE001
        logger.exception("listener: governance_actions upsert 失敗 proposal_id=%s: %s", proposal_id, e)
        return False, proposal_id

    if is_new:
        logger.info("listener: 新 GA INSERT proposal_id=%s type=%s", proposal_id, proposal_type)
    else:
        logger.debug("listener: 既存 GA UPDATE proposal_id=%s", proposal_id)
    return is_new, proposal_id


def record_vote_from_event(vote_obj: dict, slot: int) -> bool:
    """Ogmios の vote を proposal_votes に upsert する。

    Ogmios v6.10 以降は vote の構造が変わっており、以下の対応で両対応する:
      - voter   → issuer
      - actionId → proposal
      - anchor   → metadata
    """
    voter = vote_obj.get("issuer") or vote_obj.get("voter") or {}
    role_raw = voter.get("role") or ""
    role = _VOTER_ROLE_MAP.get(role_raw)
    if not role:
        logger.debug("listener: 未対応 voter role: %s", role_raw)
        return False

    voter_hex = voter.get("id") or ""
    # Ogmios は credential が鍵ベースか script ベースかを "from" フィールドで示す
    # (CredentialOrigin enum = "verificationKey" / "script")。これを取りこぼすと
    # script DRep を鍵ヘッダ 0x22 で誤エンコードし voter_id が変わってしまう。
    has_script = voter.get("from") == "script"
    voter_id = encode_voter_id(role, voter_hex, has_script)
    if not voter_id:
        logger.warning("listener: voter_id 計算失敗 role=%s id=%s", role, voter_hex)
        return False

    # v6.10+ は "proposal"、旧は "actionId"
    action_id = vote_obj.get("proposal") or vote_obj.get("actionId") or {}
    gov_tx = (action_id.get("transaction") or {}).get("id") or ""
    gov_idx = int(action_id.get("index") or 0)
    proposal_id = encode_proposal_id(gov_tx, gov_idx)
    if not proposal_id:
        logger.warning("listener: vote の proposal_id 計算失敗 tx=%s idx=%d", gov_tx, gov_idx)
        return False

    # Ogmios は "yes" / "no" / "abstain" (lowercase) で来るが、UI の _vote_badge は
    # Koios sync 由来の "Yes" / "No" / "Abstain" (capitalized) でマッチングするため統一。
    _VOTE_NORMALIZE = {"yes": "Yes", "no": "No", "abstain": "Abstain"}
    raw_vote = (vote_obj.get("vote") or "").lower()
    vote_str = _VOTE_NORMALIZE.get(raw_vote, raw_vote)

    # v6.10+ は "metadata"、旧は "anchor"
    anchor = vote_obj.get("metadata") or vote_obj.get("anchor") or {}
    meta_url = anchor.get("url") if isinstance(anchor, dict) else None
    meta_hash = anchor.get("hash") if isinstance(anchor, dict) else None

    data = {
        "proposal_id": proposal_id,
        "voter_role":  role,
        "voter_id":    voter_id,
        "voter_hex":   voter_hex,
        "voter_has_script": has_script,
        "vote":        vote_str,
        "block_time":  int(datetime.now(timezone.utc).timestamp()),
        "meta_url":    meta_url,
        "meta_hash":   meta_hash,
        "last_event_slot": int(slot),
    }

    try:
        vote_upsert(data)
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "listener: vote upsert 失敗 proposal_id=%s voter=%s: %s",
            proposal_id, voter_id, e,
        )
        return False

    logger.info(
        "listener: vote UPSERT proposal=%s… voter=%s… vote=%s",
        proposal_id[:24], voter_id[:24], vote_str,
    )
    return True
