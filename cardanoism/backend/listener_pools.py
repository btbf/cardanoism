"""listener_pools.py
Ogmios listener から呼ばれる Pool cert の DB 直書きハンドラ (Phase 3)。

対象イベント (Ogmios cert.type):
  - stakePoolRegistration  (新規登録 + 再登録による手数料/誓約変更)
  - stakePoolRetirement    (引退予告)

書き込み: pools テーブルの static 列。
  - pool_id_bech32 / pool_id_hex / vrf_key_hash / reward_addr
  - pledge / margin / fixed_cost
  - meta_url / meta_hash
  - retiring_epoch / pool_status
  - owners (hex → stake1 bech32 に変換して JSON 配列で書込み)
  - last_event_slot

非対象 (Koios sync 担当):
  - 動的: active_stake / live_stake / live_pledge / live_delegators / live_saturation / sigma /
          block_count / block_history_5ep / apy_history_7ep
  - メタデータ: ticker / pool_name / description / homepage / pool_icon_url / pool_logo_url /
                extended_about / SNS handles
  - リレー疎通: relay_alive / relay_checked_at
  - エポック確定値: active_epoch_no / op_cert / op_cert_counter
  - リスト系: relays (Ogmios と Koios で構造が異なるので listener では触らない)

副作用 (Step 1: SPO 判定):
  - PoolRegistration cert を反映後、pool の reward_addr / owners が登録済み
    stake_addresses に該当する場合は spo_pool_id を更新する。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.listener_stake import _credential_to_stake_address

logger = logging.getLogger(__name__)


def _parse_margin(margin_str: str | None) -> float | None:
    """Ogmios の margin "num/den" → 小数。失敗時は None。"""
    if not margin_str or not isinstance(margin_str, str):
        return None
    try:
        num, den = margin_str.split("/")
        d = int(den)
        if d == 0:
            return None
        return int(num) / d
    except (ValueError, ZeroDivisionError):
        return None


def _ada_lovelace(obj: Any) -> int | None:
    """{"ada": {"lovelace": N}} 形式から N を取り出す。"""
    if not isinstance(obj, dict):
        return None
    ada = obj.get("ada") or {}
    if not isinstance(ada, dict):
        return None
    lov = ada.get("lovelace")
    try:
        return int(lov) if lov is not None else None
    except (TypeError, ValueError):
        return None


def _upsert_pool_static(
    pool_id_bech32: str,
    *,
    vrf_key_hash: str | None = None,
    reward_addr: str | None = None,
    pledge: int | None = None,
    margin: float | None = None,
    fixed_cost: int | None = None,
    meta_url: str | None = None,
    meta_hash: str | None = None,
    retiring_epoch: int | None = None,
    pool_status: str | None = None,
    owners_json: str | None = None,
    last_event_slot: int = 0,
) -> None:
    """listener 専用の pools 部分 UPSERT。

    Koios sync が管理する動的列・メタデータ列は一切触らない。
    指定されなかった引数は None で渡され、ON DUPLICATE KEY UPDATE 側で COALESCE により
    既存値が保持される。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO pools (
                pool_id_bech32, vrf_key_hash, reward_addr,
                pledge, margin, fixed_cost,
                meta_url, meta_hash,
                retiring_epoch, pool_status,
                owners, last_event_slot
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?
            )
            ON DUPLICATE KEY UPDATE
                vrf_key_hash    = COALESCE(VALUES(vrf_key_hash),  vrf_key_hash),
                reward_addr     = COALESCE(VALUES(reward_addr),   reward_addr),
                pledge          = COALESCE(VALUES(pledge),        pledge),
                margin          = COALESCE(VALUES(margin),        margin),
                fixed_cost      = COALESCE(VALUES(fixed_cost),    fixed_cost),
                meta_url        = COALESCE(VALUES(meta_url),      meta_url),
                meta_hash       = COALESCE(VALUES(meta_hash),     meta_hash),
                retiring_epoch  = COALESCE(VALUES(retiring_epoch), retiring_epoch),
                pool_status     = COALESCE(VALUES(pool_status),   pool_status),
                owners          = COALESCE(VALUES(owners),        owners),
                last_event_slot = COALESCE(VALUES(last_event_slot), last_event_slot)
            """,
            (
                pool_id_bech32,
                vrf_key_hash,
                reward_addr,
                int(pledge) if pledge is not None else None,
                float(margin) if margin is not None else None,
                int(fixed_cost) if fixed_cost is not None else None,
                meta_url,
                meta_hash,
                int(retiring_epoch) if retiring_epoch is not None else None,
                pool_status,
                owners_json,
                int(last_event_slot),
            ),
        )
        conn.commit()


def _convert_owners_to_stake_addresses(owners_hex: list) -> list[str]:
    """Ogmios の owners (28 byte hex の配列) を stake1... bech32 配列に変換する。

    変換失敗した hex は無視 (スキップ)。
    """
    out: list[str] = []
    if not isinstance(owners_hex, list):
        return out
    for cred_hex in owners_hex:
        if not isinstance(cred_hex, str):
            continue
        # owners は key-based (script は基本ない仕様) として扱う
        addr = _credential_to_stake_address(cred_hex, has_script=False)
        if addr:
            out.append(addr)
    return out


def _detect_user_spo_addresses(reward_addr: str | None, owners: list[str]) -> list[tuple[int, str]]:
    """Pool cert に含まれる reward_addr / owners が登録済み stake_addresses に該当するか調べる。

    戻り値: [(stake_address_id, matched_address), ...]
    """
    candidates = [a for a in ([reward_addr] + (owners or [])) if a]
    if not candidates:
        return []
    placeholders = ",".join(["?"] * len(candidates))
    with get_db() as (cursor, _):
        cursor.execute(
            f"SELECT id, address FROM stake_addresses WHERE address IN ({placeholders})",
            tuple(candidates),
        )
        return [(int(r["id"]), str(r["address"])) for r in cursor.fetchall()]


def _mark_user_addresses_as_spo(stake_address_ids: list[int], pool_id: str) -> None:
    """登録済み stake_addresses 行を SPO としてマークする。"""
    if not stake_address_ids:
        return
    with get_db() as (cursor, conn):
        for sid in stake_address_ids:
            cursor.execute(
                "UPDATE stake_addresses SET spo_pool_id = ? WHERE id = ?",
                (pool_id, int(sid)),
            )
        conn.commit()


def record_pool_registration(cert: dict, slot: int) -> bool:
    """stakePoolRegistration cert を pools に反映する。

    新規登録 / 再登録 (手数料・誓約・メタデータ変更) のどちらでもこの cert が来る。
    pool_id が同じならば ON DUPLICATE KEY UPDATE で既存行に上書き。

    副作用: cert に含まれる reward_addr / owners が登録済み stake_addresses に
    該当する場合、spo_pool_id をマークする。
    """
    pool = cert.get("stakePool") or {}
    pool_id = pool.get("id")
    if not pool_id:
        logger.warning("listener: pool_registration の id 解決失敗 cert=%s", cert)
        return False

    pledge = _ada_lovelace(pool.get("pledge"))
    fixed_cost = _ada_lovelace(pool.get("cost"))
    margin = _parse_margin(pool.get("margin"))
    vrf = pool.get("vrf") or pool.get("vrfVerificationKeyHash")
    reward_addr = pool.get("rewardAccount") or pool.get("rewardAddress")
    metadata = pool.get("metadata") or {}
    meta_url = metadata.get("url") if isinstance(metadata, dict) else None
    meta_hash = metadata.get("hash") if isinstance(metadata, dict) else None

    # owners (28 byte hex の配列) を stake1... bech32 に変換
    owners_hex = pool.get("owners") or []
    owners_bech = _convert_owners_to_stake_addresses(owners_hex)
    owners_json = json.dumps(owners_bech, ensure_ascii=False) if owners_bech else None

    _upsert_pool_static(
        pool_id_bech32=pool_id,
        vrf_key_hash=vrf,
        reward_addr=reward_addr,
        pledge=pledge,
        margin=margin,
        fixed_cost=fixed_cost,
        meta_url=meta_url,
        meta_hash=meta_hash,
        pool_status="registered",
        owners_json=owners_json,
        last_event_slot=slot,
    )
    logger.info(
        "listener: pool 登録 pool=%s pledge=%s cost=%s margin=%.4f owners=%d",
        pool_id, pledge, fixed_cost,
        margin if margin is not None else float("nan"),
        len(owners_bech),
    )

    # 登録済みユーザーの stake_addresses に該当があれば SPO としてマーク
    try:
        matched = _detect_user_spo_addresses(reward_addr, owners_bech)
        if matched:
            _mark_user_addresses_as_spo([sid for sid, _ in matched], pool_id)
            logger.info(
                "listener: SPO マーク pool=%s 該当ユーザーアドレス=%d",
                pool_id, len(matched),
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("listener: SPO マーク失敗 pool=%s: %s", pool_id, e)

    return True


def record_pool_retirement(cert: dict, slot: int) -> bool:
    """stakePoolRetirement cert を pools に反映する。"""
    pool = cert.get("stakePool") or {}
    pool_id = pool.get("id")
    if not pool_id:
        logger.warning("listener: pool_retirement の id 解決失敗 cert=%s", cert)
        return False

    retiring_epoch = pool.get("retirementEpoch")
    try:
        retiring_epoch_int = int(retiring_epoch) if retiring_epoch is not None else None
    except (TypeError, ValueError):
        retiring_epoch_int = None

    _upsert_pool_static(
        pool_id_bech32=pool_id,
        retiring_epoch=retiring_epoch_int,
        pool_status="retiring",
        last_event_slot=slot,
    )
    logger.info(
        "listener: pool 引退予告 pool=%s retiring_epoch=%s",
        pool_id, retiring_epoch_int,
    )
    return True
