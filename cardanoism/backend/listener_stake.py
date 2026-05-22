"""listener_stake.py
Ogmios listener から呼ばれる委任 cert の DB 直書きハンドラ (Phase 4)。

対象イベント (Ogmios cert.type):
  - stakeDelegation                          (旧 StakeDelegCert: → SPO)
  - voteDelegation                           (CIP-1694 VoteDelegCert: → DRep)
  - stakeAndVoteDelegation                   (合体 cert: SPO + DRep)
  - stakeRegistrationAndDelegation           (stake 登録 + SPO 委任の合体)
  - stakeRegistrationAndVoteDelegation       (stake 登録 + DRep 委任の合体)
  - stakeRegistrationAndStakeAndVoteDelegation (3つの合体)

書き込み: stake_addresses テーブルの該当ユーザー行のみ (address カラム一致時)。
listener は無関係チェーンの委任を DB に流し込まない (= ユーザー所有データに限定)。

delegated_pool_name / delegated_drep_name は cert に含まれないが、ユーザー登録
アドレスが委任したときだけ Koios で名前を即解決して埋める (ダッシュボードに
旧名が残らないようにするため)。名前解決は affected 行があったときのみ実行する
ので、無関係チェーンの委任で Koios を叩くことはない。

非対象 (Koios sync 担当):
  - role / role_checked_at の正確な確定 (DRep / abstain / delegator) は detect_stake_role が後追い
"""
from __future__ import annotations

import logging
import os
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.listener_governance import _encode_bech32, encode_voter_id

logger = logging.getLogger(__name__)


# update 対象を「明示的に NULL にしたい」と「触らない」を区別するためのセンチネル
class _NoChange:
    pass


_NO_CHANGE: Any = _NoChange()


def _credential_to_stake_address(cred_hex: str, has_script: bool) -> str | None:
    """stake credential 28 byte hex → stake1... / stake_test1... bech32。

    header byte:
      0xE0 + network_id (key-based)   : 0xE1 mainnet / 0xE0 testnet
      0xF0 + network_id (script-based): 0xF1 mainnet / 0xF0 testnet
    """
    try:
        raw = bytes.fromhex(cred_hex)
    except ValueError:
        return None
    if len(raw) != 28:
        return None
    network = (os.getenv("KOIOS_NETWORK") or "mainnet").lower()
    is_mainnet = network == "mainnet"
    network_bit = 1 if is_mainnet else 0
    header = (0xF0 if has_script else 0xE0) | network_bit
    hrp = "stake" if is_mainnet else "stake_test"
    return _encode_bech32(hrp, bytes([header]) + raw)


def _resolve_stake_addr_from_cert(cert: dict) -> tuple[str | None, str | None]:
    """cert の credential から (stake_address_bech32, voter_hex) を返す。"""
    cred = cert.get("credential") or cert.get("delegator") or {}
    if not isinstance(cred, dict):
        return None, None
    cred_hex = cred.get("id") or ""
    # Ogmios の CredentialOrigin enum は "verificationKey" / "script"。
    has_script = cred.get("from") == "script"
    stake_addr = _credential_to_stake_address(cred_hex, has_script)
    return stake_addr, cred_hex


def _resolve_drep_target(drep_obj: Any) -> str | _NoChange | None:
    """vote delegation の DRep フィールドを bech32 drep_id か None (特殊値) に解決する。

    戻り値:
      - str       : 通常の DRep への委任 (bech32 形式 drep1...)
      - None      : Always Abstain / Always No Confidence (DB は NULL に)
      - _NoChange : 解決失敗 (= 触らない)
    """
    if not isinstance(drep_obj, dict):
        return _NO_CHANGE
    type_str = (drep_obj.get("type") or drep_obj.get("kind") or "").lower()
    if "abstain" in type_str:
        return None
    if "noconfidence" in type_str or "no_confidence" in type_str:
        return None
    drep_hex = drep_obj.get("id") or ""
    # 鍵/script の判別は type ではなく Ogmios の "from" フィールド
    # (CredentialOrigin enum = "verificationKey" / "script")。
    has_script = drep_obj.get("from") == "script"
    drep_id = encode_voter_id("DRep", drep_hex, has_script=has_script)
    if not drep_id:
        return _NO_CHANGE
    return drep_id


def _resolve_pool_name(pool_id: str) -> str:
    """pool_id (bech32) からプール名を Koios で解決。失敗時は空文字。"""
    try:
        from cardanoism.backend.koios import get_pool_name
        return get_pool_name(pool_id) or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("listener: pool 名解決失敗 %s: %s", pool_id, e)
        return ""


def _resolve_drep_name(drep_id: str) -> str:
    """drep_id (bech32) から DRep 名を Koios で解決。失敗時は空文字。"""
    try:
        from cardanoism.backend.koios import _fetch_drep_name
        return _fetch_drep_name(drep_id) or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("listener: drep 名解決失敗 %s: %s", drep_id, e)
        return ""


def _update_stake_delegation(
    stake_addr: str,
    *,
    pool_id: Any = _NO_CHANGE,
    drep_id: Any = _NO_CHANGE,
    slot: int,
) -> bool:
    """stake_addresses 行を UPDATE。listener は address 一致行のみ触る。

    pool_id / drep_id のうち _NO_CHANGE は触らない。
    None を渡すと NULL に設定される (Always Abstain 等の特殊値)。

    影響行があった (= ユーザー登録済みアドレス) 場合は、続けて
    delegated_pool_name / delegated_drep_name も Koios で解決して更新する。

    戻り値: 影響行数 > 0 なら True。
    """
    sets = ["last_event_slot = ?", "role_checked_at = NOW()"]
    params: list = [int(slot)]
    if pool_id is not _NO_CHANGE:
        sets.append("delegated_pool_id = ?")
        params.append(pool_id)
    if drep_id is not _NO_CHANGE:
        sets.append("delegated_drep_id = ?")
        params.append(drep_id)
    params.append(stake_addr)

    with get_db() as (cursor, conn):
        cursor.execute(
            f"UPDATE stake_addresses SET {', '.join(sets)} WHERE address = ?",
            params,
        )
        affected = cursor.rowcount or 0
        conn.commit()

    if affected <= 0:
        return False

    # ユーザー登録アドレスだったので名前も即時解決して更新する。
    # (cert に名前は含まれないため Koios で引く。委任イベントは稀なのでコスト許容)
    name_sets: list[str] = []
    name_params: list = []
    if pool_id is not _NO_CHANGE and pool_id:
        name_sets.append("delegated_pool_name = ?")
        name_params.append(_resolve_pool_name(pool_id) or None)
    if drep_id is not _NO_CHANGE:
        name_sets.append("delegated_drep_name = ?")
        # drep_id が None (Always Abstain 等) なら名前も NULL
        name_params.append(_resolve_drep_name(drep_id) or None if drep_id else None)
    if name_sets:
        name_params.append(stake_addr)
        try:
            with get_db() as (cursor, conn):
                cursor.execute(
                    f"UPDATE stake_addresses SET {', '.join(name_sets)} WHERE address = ?",
                    name_params,
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("listener: 委任先名の更新失敗 stake=%s: %s", stake_addr[:30], e)

    return True


# ─── Cert ハンドラ ─────────────────────────────────────────


def record_stake_delegation(cert: dict, slot: int) -> bool:
    """stakeDelegation: 委任先 SPO (pool) を更新。"""
    stake_addr, _ = _resolve_stake_addr_from_cert(cert)
    if not stake_addr:
        return False
    # Ogmios v6.10+ は "stakePool" (dict)、旧は "pool" (string or dict)
    pool_obj = cert.get("stakePool") or cert.get("pool")
    if isinstance(pool_obj, dict):
        pool_id = pool_obj.get("id")
    else:
        pool_id = pool_obj
    if not pool_id:
        return False
    updated = _update_stake_delegation(stake_addr, pool_id=pool_id, slot=slot)
    if updated:
        logger.info("listener: 委任先 SPO 更新 stake=%s pool=%s", stake_addr[:30], pool_id[:20])
    return updated


def record_vote_delegation(cert: dict, slot: int) -> bool:
    """voteDelegation: 委任先 DRep を更新。"""
    stake_addr, _ = _resolve_stake_addr_from_cert(cert)
    if not stake_addr:
        return False
    drep_obj = cert.get("delegateRepresentative") or cert.get("dRep") or {}
    drep_id = _resolve_drep_target(drep_obj)
    if drep_id is _NO_CHANGE:
        return False
    updated = _update_stake_delegation(stake_addr, drep_id=drep_id, slot=slot)
    if updated:
        logger.info(
            "listener: 委任先 DRep 更新 stake=%s drep=%s",
            stake_addr[:30], drep_id[:20] if drep_id else "(special)",
        )
    return updated


def record_stake_and_vote_delegation(cert: dict, slot: int) -> bool:
    """stakeAndVoteDelegation: SPO + DRep の合体 cert。"""
    stake_addr, _ = _resolve_stake_addr_from_cert(cert)
    if not stake_addr:
        return False
    # Ogmios v6.10+ は "stakePool" (dict)、旧は "pool" (string or dict)
    pool_obj = cert.get("stakePool") or cert.get("pool")
    if isinstance(pool_obj, dict):
        pool_id = pool_obj.get("id")
    else:
        pool_id = pool_obj
    drep_obj = cert.get("delegateRepresentative") or cert.get("dRep") or {}
    drep_id = _resolve_drep_target(drep_obj)

    kwargs: dict[str, Any] = {"slot": slot}
    if pool_id:
        kwargs["pool_id"] = pool_id
    if drep_id is not _NO_CHANGE:
        kwargs["drep_id"] = drep_id
    if "pool_id" not in kwargs and "drep_id" not in kwargs:
        return False

    updated = _update_stake_delegation(stake_addr, **kwargs)
    if updated:
        logger.info(
            "listener: 委任先 (SPO+DRep) 更新 stake=%s pool=%s drep=%s",
            stake_addr[:30],
            (pool_id or "-")[:20],
            (drep_id[:20] if isinstance(drep_id, str) else "(special/none)"),
        )
    return updated


def record_combined_registration_and_delegation(cert: dict, slot: int) -> bool:
    """stakeRegistrationAndDelegation 系の合体 cert を扱う。

    Conway era で stake registration と SPO/DRep 委任を 1 cert にまとめる形式。
    実体は cert の中に pool / dRep / credential が同居しているので
    record_stake_and_vote_delegation と同じ抽出ロジックでよい。
    """
    return record_stake_and_vote_delegation(cert, slot)
