"""listener_pools.py
Ogmios listener から呼ばれる Pool cert の DB 直書きハンドラ (Phase 3)。

対象イベント (Ogmios cert.type):
  - stakePoolRegistration  (新規登録 + 再登録による手数料/誓約変更)
  - stakePoolRetirement    (引退予告)

書き込み: pools テーブルの static 列のみ。
  - pool_id_bech32 / pool_id_hex / vrf_key_hash / reward_addr
  - pledge / margin / fixed_cost
  - meta_url / meta_hash
  - retiring_epoch / pool_status
  - last_event_slot

非対象 (Koios sync 担当):
  - 動的: active_stake / live_stake / live_pledge / live_delegators / live_saturation / sigma /
          block_count / block_history_5ep / apy_history_7ep
  - メタデータ: ticker / pool_name / description / homepage / pool_icon_url / pool_logo_url /
                extended_about / SNS handles
  - リレー疎通: relay_alive / relay_checked_at
  - エポック確定値: active_epoch_no / op_cert / op_cert_counter
  - リスト系: owners / relays (Koios の bech32 形式と Ogmios の hex 形式が異なるので
              整形コストを避けるため listener では触らない)
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

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
                last_event_slot
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?
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
                int(last_event_slot),
            ),
        )
        conn.commit()


def record_pool_registration(cert: dict, slot: int) -> bool:
    """stakePoolRegistration cert を pools に反映する。

    新規登録 / 再登録 (手数料・誓約・メタデータ変更) のどちらでもこの cert が来る。
    pool_id が同じならば ON DUPLICATE KEY UPDATE で既存行に上書き。
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
        last_event_slot=slot,
    )
    logger.info(
        "listener: pool 登録 pool=%s pledge=%s cost=%s margin=%.4f",
        pool_id, pledge, fixed_cost, margin if margin is not None else float("nan"),
    )
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
