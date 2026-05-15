"""listener_dreps.py
Ogmios listener から呼ばれる DRep cert の DB 直書きハンドラ (Phase 2)。

対象イベント (Ogmios cert.type):
  - delegateRepresentativeRegistration  (RegDRepCert)
  - delegateRepresentativeRetirement    (UnRegDRepCert)
  - delegateRepresentativeUpdate        (UpdateDRepCert)

書き込み: dreps テーブルの static 列のみ。
  - drep_id / hex / has_script / registered / deposit / meta_url / meta_hash
  - last_event_slot

非対象 (Koios sync 担当):
  - amount (総委任量)
  - drep_status / active / expires_epoch_no
  - CIP-119 メタデータ (given_name / image_url / motivations / objectives / qualifications / references_json)
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.listener_governance import encode_voter_id

logger = logging.getLogger(__name__)


def _parse_drep_credential(cert: dict) -> tuple[str | None, bool]:
    """Ogmios の DRep cert から (drep_id_bech32, has_script) を返す。

    Ogmios v6 の delegateRepresentative は credential 情報を持つ:
      {"id": "<28 byte hex>", "type": "verificationKey" | "script"}
    あるいは {"id": "<hex>", "kind": "verificationKey" | "scriptHash"}
    """
    drep = cert.get("delegateRepresentative") or cert.get("dRep") or {}
    if not isinstance(drep, dict):
        return None, False
    voter_hex = drep.get("id") or ""
    type_str = (drep.get("type") or drep.get("kind") or "").lower()
    has_script = "script" in type_str
    drep_id = encode_voter_id("DRep", voter_hex, has_script=has_script)
    return drep_id, has_script


def _upsert_drep_static(
    drep_id: str,
    voter_hex: str,
    has_script: bool,
    registered: int,
    deposit: int | None,
    meta_url: str | None,
    meta_hash: str | None,
    drep_status: str | None,
    last_event_slot: int,
) -> None:
    """listener 専用の dreps 部分 UPSERT。

    Koios sync が管理する動的列 (amount / active / expires_epoch_no / CIP-119 metadata) は
    一切触らない。INSERT 時のみ NULL/0 でデフォルト埋め。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO dreps (
                drep_id, hex, has_script, registered, drep_status,
                deposit, meta_url, meta_hash,
                amount, last_event_slot
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                0, ?
            )
            ON DUPLICATE KEY UPDATE
                hex             = COALESCE(VALUES(hex), hex),
                has_script      = VALUES(has_script),
                registered      = VALUES(registered),
                drep_status     = COALESCE(VALUES(drep_status), drep_status),
                deposit         = COALESCE(VALUES(deposit), deposit),
                meta_url        = VALUES(meta_url),
                meta_hash       = VALUES(meta_hash),
                last_event_slot = COALESCE(VALUES(last_event_slot), last_event_slot)
            """,
            (
                drep_id,
                voter_hex,
                int(bool(has_script)),
                int(registered),
                drep_status,
                int(deposit) if deposit is not None else None,
                meta_url,
                meta_hash,
                int(last_event_slot),
            ),
        )
        conn.commit()


def _extract_anchor(cert: dict) -> tuple[str | None, str | None]:
    # Ogmios v6.10+ は "metadata"、旧は "anchor"
    anchor = cert.get("metadata") or cert.get("anchor") or {}
    if not isinstance(anchor, dict):
        return None, None
    return anchor.get("url"), anchor.get("hash")


def _extract_deposit(cert: dict) -> int | None:
    dep = cert.get("deposit") or {}
    if not isinstance(dep, dict):
        return None
    ada = dep.get("ada") or {}
    if not isinstance(ada, dict):
        return None
    lov = ada.get("lovelace")
    try:
        return int(lov) if lov is not None else None
    except (TypeError, ValueError):
        return None


def record_drep_registration(cert: dict, slot: int) -> bool:
    """RegDRepCert (delegateRepresentativeRegistration) を反映する。"""
    drep_id, has_script = _parse_drep_credential(cert)
    if not drep_id:
        logger.warning("listener: DRep registration の id 解決失敗 cert=%s", cert)
        return False

    drep = cert.get("delegateRepresentative") or cert.get("dRep") or {}
    voter_hex = drep.get("id") or ""

    deposit = _extract_deposit(cert)
    meta_url, meta_hash = _extract_anchor(cert)

    _upsert_drep_static(
        drep_id=drep_id,
        voter_hex=voter_hex,
        has_script=has_script,
        registered=1,
        deposit=deposit,
        meta_url=meta_url,
        meta_hash=meta_hash,
        drep_status="active",
        last_event_slot=slot,
    )
    logger.info("listener: DRep 登録 drep_id=%s deposit=%s", drep_id[:24], deposit)
    return True


def record_drep_retirement(cert: dict, slot: int) -> bool:
    """UnRegDRepCert (delegateRepresentativeRetirement) を反映する。

    deposit refund の額は cert に載っているが本筋ではないので無視。
    """
    drep_id, has_script = _parse_drep_credential(cert)
    if not drep_id:
        logger.warning("listener: DRep retirement の id 解決失敗 cert=%s", cert)
        return False

    drep = cert.get("delegateRepresentative") or cert.get("dRep") or {}
    voter_hex = drep.get("id") or ""

    _upsert_drep_static(
        drep_id=drep_id,
        voter_hex=voter_hex,
        has_script=has_script,
        registered=0,
        deposit=None,           # COALESCE で既存値を保持
        meta_url=None,
        meta_hash=None,
        drep_status="deregistered",
        last_event_slot=slot,
    )
    logger.info("listener: DRep 退任 drep_id=%s", drep_id[:24])
    return True


def record_drep_update(cert: dict, slot: int) -> bool:
    """UpdateDRepCert (delegateRepresentativeUpdate) を反映する。

    ほぼ anchor の更新のみ。CIP-119 本文 (given_name 等) は Koios sync で取得する。
    """
    drep_id, has_script = _parse_drep_credential(cert)
    if not drep_id:
        logger.warning("listener: DRep update の id 解決失敗 cert=%s", cert)
        return False

    drep = cert.get("delegateRepresentative") or cert.get("dRep") or {}
    voter_hex = drep.get("id") or ""

    meta_url, meta_hash = _extract_anchor(cert)

    _upsert_drep_static(
        drep_id=drep_id,
        voter_hex=voter_hex,
        has_script=has_script,
        registered=1,           # update なので登録状態を維持
        deposit=None,
        meta_url=meta_url,
        meta_hash=meta_hash,
        drep_status=None,       # 既存値を保持
        last_event_slot=slot,
    )
    logger.info("listener: DRep 更新 drep_id=%s anchor=%s", drep_id[:24], meta_url)
    return True
