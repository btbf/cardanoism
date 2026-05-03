"""tx_builder.py
サーバサイドで Cardano トランザクションを構築・送信するヘルパー (Phase 3)。

設計方針:
  - サーバ (Python) で unsigned tx を CBOR hex で構築
  - クライアント (ブラウザ) は CIP-30 の signTx + submitTx だけ実行
  - これにより MeshSDK / Lucid 等のフロントエンド側 WASM/Vite 問題を完全に回避

Chain context:
  - Ogmios v6 (109.123.231.103:1337, mainnet) を使用
  - 環境変数 OGMIOS_URL / OGMIOS_HOST / OGMIOS_PORT で上書き可能
  - 必要なら BlockFrost / Koios チェーンコンテキストにも切替可能

提供する API:
  - build_pool_delegation_tx() : ステークプール委任 cert を含む tx
  - build_drep_delegation_tx() : DRep 委任 cert (CIP-1694) を含む tx

入力 (CIP-30 から取得した値):
  - utxos_cbor:       wallet.getUtxos() の戻り値 (list[str], CBOR hex)
  - change_addr_cbor: wallet.getChangeAddress() の戻り値 (str, CBOR hex)
  - stake_addr_cbor:  wallet.getRewardAddresses()[0] (str, CBOR hex)

出力:
  - unsigned tx の CBOR hex (str)。フロントは api.signTx(hex, true) → submitTx
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from pycardano import (
    Address,
    DRep,
    DRepKind,
    Network,
    StakeCredential,
    StakeDelegation,
    StakeRegistrationAndDelegation,
    StakeRegistrationAndVoteDelegation,
    Transaction,
    TransactionBuilder,
    TransactionInput,
    TransactionOutput,
    UTxO,
    Value,
    VoteDelegation,
)
from pycardano.backend.ogmios_v6 import OgmiosV6ChainContext
from pycardano.cbor import cbor2
from pycardano.hash import PoolKeyHash, ScriptHash, VerificationKeyHash
from pycardano.transaction import TransactionBody
from pycardano.witness import TransactionWitnessSet

logger = logging.getLogger(__name__)


# ── Chain context (singleton) ──────────────────────────────

_chain_context: Optional[OgmiosV6ChainContext] = None


def _get_network() -> Network:
    n = (os.environ.get("KOIOS_NETWORK") or "mainnet").lower()
    return Network.TESTNET if n in ("preprod", "preview", "testnet") else Network.MAINNET


def get_chain_context() -> OgmiosV6ChainContext:
    """Ogmios chain context を返す (singleton)。"""
    global _chain_context
    if _chain_context is not None:
        return _chain_context

    host = os.environ.get("OGMIOS_HOST", "109.123.231.103")
    port = int(os.environ.get("OGMIOS_PORT", "1337"))
    secure = os.environ.get("OGMIOS_SECURE", "0") == "1"
    network = _get_network()

    logger.info(
        "Initializing Ogmios chain context: host=%s port=%d network=%s",
        host, port, network.name,
    )
    _chain_context = OgmiosV6ChainContext(
        host=host,
        port=port,
        secure=secure,
        network=network,
    )
    return _chain_context


# ── Helpers ────────────────────────────────────────────────

def _bytes_from_hex(hex_str: str) -> bytes:
    s = (hex_str or "").strip()
    if s.startswith("0x") or s.startswith("0X"):
        s = s[2:]
    return bytes.fromhex(s)


def _utxos_from_cbor_list(utxos_cbor: list[str]) -> list[UTxO]:
    """CIP-30 wallet.getUtxos() の戻り値 (CBOR hex の配列) を pycardano UTxO に変換。"""
    out: list[UTxO] = []
    for hex_str in utxos_cbor or []:
        try:
            raw = _bytes_from_hex(hex_str)
            decoded = cbor2.loads(raw)
            # CIP-30 の UTxO は [TransactionInput, TransactionOutput] の配列
            if not (isinstance(decoded, list) and len(decoded) == 2):
                logger.warning("Unexpected UTxO CBOR shape: %r", type(decoded))
                continue
            tx_input = TransactionInput.from_primitive(decoded[0])
            tx_output = TransactionOutput.from_primitive(decoded[1])
            out.append(UTxO(input=tx_input, output=tx_output))
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to decode UTxO %s: %s", hex_str[:20], e)
            continue
    return out


def _address_from_cbor(addr_cbor: str) -> Address:
    """CIP-30 wallet.getChangeAddress() / getRewardAddresses() の hex → Address。"""
    raw = _bytes_from_hex(addr_cbor)
    return Address.from_primitive(raw)


def _stake_credential_from_addr(stake_addr: Address) -> StakeCredential:
    """reward (stake) address から StakeCredential を抽出。"""
    if stake_addr.staking_part is None:
        raise ValueError("Address does not have a staking part")
    return StakeCredential(stake_addr.staking_part)


def _is_stake_registered(stake_addr: Address) -> bool:
    """Ogmios の rewardAccountSummaries で stake credential が登録済みか直接確認する。

    Why: Koios の `account_info.status` は tip キャッチアップ前にズレることがあり、
    StakeDelegation / StakeRegistrationAndDelegation の分岐を誤らせて
    Ogmios error 3146 (UnknownCredential / KeyAlreadyRegistered) を引き起こしていた。
    Ogmios は submit 先と同じ ledger 状態を見ているので、ここを情報源にすれば
    判定と submit の整合性が確実に取れる。
    """
    if stake_addr.staking_part is None:
        raise ValueError("Address does not have a staking part")

    cred_hex = stake_addr.staking_part.payload.hex()
    if isinstance(stake_addr.staking_part, ScriptHash):
        keys: Optional[list[str]] = None
        scripts: Optional[list[str]] = [cred_hex]
    else:
        keys = [cred_hex]
        scripts = None

    try:
        ctx = get_chain_context()
        summaries = ctx.query_account_reward_summaries(scripts=scripts, keys=keys)
    except Exception as e:  # noqa: BLE001
        logger.warning("[tx_builder] Ogmios reward summaries query failed: %s", e)
        return False

    is_reg = bool(summaries)
    logger.warning(
        "[tx_builder] Ogmios stake check: stake=%s registered=%s summaries=%d",
        stake_addr.encode(), is_reg, len(summaries),
    )
    return is_reg


# ── DRep helpers ──────────────────────────────────────────

def _bech32_to_bytes(bech: str) -> tuple[str, bytes]:
    """bech32 文字列を (hrp, raw bytes) に変換する。"""
    from pycardano.crypto.bech32 import bech32_decode, convertbits  # type: ignore
    hrp, data, _spec = bech32_decode(bech)
    if hrp is None or data is None:
        raise ValueError(f"Invalid bech32 string: {bech}")
    decoded = convertbits(data, 5, 8, False)
    if decoded is None:
        raise ValueError(f"Failed to convert bech32 data: {bech}")
    return hrp, bytes(decoded)


def _drep_from_id(drep_id: str) -> DRep:
    """drep1... bech32 もしくは "always_abstain" / "always_no_confidence" を DRep に変換。"""
    s = (drep_id or "").strip().lower()
    if s in ("always_abstain", "abstain"):
        return DRep(DRepKind.ALWAYS_ABSTAIN)
    if s in ("always_no_confidence", "no_confidence"):
        return DRep(DRepKind.ALWAYS_NO_CONFIDENCE)

    hrp, key_bytes = _bech32_to_bytes(s)
    if hrp == "drep":
        return DRep(DRepKind.VERIFICATION_KEY_HASH, VerificationKeyHash(key_bytes))
    if hrp == "drep_script":
        return DRep(DRepKind.SCRIPT_HASH, ScriptHash(key_bytes))
    raise ValueError(f"Unknown DRep hrp: {hrp}")


# ── Pool delegation ───────────────────────────────────────

def build_pool_delegation_tx(
    stake_addr_cbor: str,
    pool_id_bech32: str,
    change_addr_cbor: str,
    utxos_cbor: list[str],
) -> str:
    """ステークプール委任 cert を含む unsigned tx を構築し、CBOR hex を返す。"""
    if not pool_id_bech32 or not pool_id_bech32.startswith("pool"):
        raise ValueError(f"Invalid pool id: {pool_id_bech32}")

    ctx = get_chain_context()
    builder = TransactionBuilder(ctx)

    # Add wallet UTxOs as inputs (TransactionBuilder will pick what it needs)
    utxos = _utxos_from_cbor_list(utxos_cbor)
    if not utxos:
        raise ValueError("No UTxOs provided. Cannot build transaction.")
    for u in utxos:
        builder.add_input(u)

    # Stake credential from reward address
    stake_addr = _address_from_cbor(stake_addr_cbor)
    stake_cred = _stake_credential_from_addr(stake_addr)

    # Pool key hash (bech32 → 28 bytes)
    hrp, key_bytes = _bech32_to_bytes(pool_id_bech32)
    if hrp != "pool":
        raise ValueError(f"Pool id does not have 'pool' hrp: {hrp}")
    pool_keyhash = PoolKeyHash(key_bytes)

    if _is_stake_registered(stake_addr):
        cert = StakeDelegation(stake_cred, pool_keyhash)
    else:
        deposit = int(ctx.protocol_param.key_deposit or 2_000_000)
        cert = StakeRegistrationAndDelegation(stake_cred, pool_keyhash, deposit)
    builder.certificates = [cert]

    # Build the body, balance with change to wallet's change address
    change_addr = _address_from_cbor(change_addr_cbor)
    body: TransactionBody = builder.build(change_address=change_addr)

    # Empty witness set (wallet will add witnesses on signing)
    witness_set = TransactionWitnessSet()

    tx = Transaction(body, witness_set)
    return tx.to_cbor_hex()


# ── DRep delegation ───────────────────────────────────────

def combine_and_submit(unsigned_tx_cbor: str, witness_set_cbor: str) -> str:
    """unsigned tx と CIP-30 signTx が返した witness set を結合して送信する。

    CIP-30 仕様:
      signTx(tx, partialSign): Promise<cbor<TransactionWitnessSet>>
        → witness set のみを返す (full tx ではない)

    Returns:
        tx_hash の hex (str)
    """
    if not unsigned_tx_cbor or not unsigned_tx_cbor.strip():
        raise ValueError("unsigned_tx_cbor is empty")
    if not witness_set_cbor or not witness_set_cbor.strip():
        raise ValueError("witness_set_cbor is empty")

    raw_tx = _bytes_from_hex(unsigned_tx_cbor)
    raw_ws = _bytes_from_hex(witness_set_cbor)

    unsigned_tx = Transaction.from_cbor(raw_tx)
    new_ws = TransactionWitnessSet.from_cbor(raw_ws)

    signed_tx = Transaction(
        transaction_body=unsigned_tx.transaction_body,
        transaction_witness_set=new_ws,
        valid=unsigned_tx.valid,
        auxiliary_data=unsigned_tx.auxiliary_data,
    )

    ctx = get_chain_context()
    # 失敗時は詳細メッセージ付き例外を投げる
    ctx.submit_tx(signed_tx)

    # pycardano 0.19+ の TransactionBody.hash() は bytes を直接返す
    return signed_tx.transaction_body.hash().hex()


def build_drep_delegation_tx(
    stake_addr_cbor: str,
    drep_id: str,
    change_addr_cbor: str,
    utxos_cbor: list[str],
) -> str:
    """DRep 委任 cert (CIP-1694) を含む unsigned tx を構築し、CBOR hex を返す。

    drep_id は以下のいずれか:
      - drep1...           : bech32 形式 (verification key hash)
      - drep_script1...    : bech32 形式 (script hash)
      - "always_abstain"   : 常に棄権
      - "always_no_confidence" : 常に否決
    """
    ctx = get_chain_context()
    builder = TransactionBuilder(ctx)

    utxos = _utxos_from_cbor_list(utxos_cbor)
    if not utxos:
        raise ValueError("No UTxOs provided. Cannot build transaction.")
    for u in utxos:
        builder.add_input(u)

    stake_addr = _address_from_cbor(stake_addr_cbor)
    stake_cred = _stake_credential_from_addr(stake_addr)
    drep = _drep_from_id(drep_id)

    if _is_stake_registered(stake_addr):
        cert = VoteDelegation(stake_cred, drep)
    else:
        deposit = int(ctx.protocol_param.key_deposit or 2_000_000)
        cert = StakeRegistrationAndVoteDelegation(stake_cred, drep, deposit)
    builder.certificates = [cert]

    change_addr = _address_from_cbor(change_addr_cbor)
    body: TransactionBody = builder.build(change_address=change_addr)
    witness_set = TransactionWitnessSet()
    tx = Transaction(body, witness_set)
    return tx.to_cbor_hex()
