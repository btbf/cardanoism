"""tx_routes.py
ブラウザのフロントエンドが叩くトランザクション構築 API。

設計:
  - フロント (CIP-30 wallet) が UTXOs / addresses を JSON で POST
  - サーバ (pycardano) が unsigned tx を構築して CBOR hex を返す
  - フロントは受け取った CBOR を wallet.signTx + submitTx する

エンドポイント (Reflex の /api/* と衝突しないよう /wallet/tx/* を使用):
  POST /wallet/tx/pool_delegation
    body: {
      stake_address: hex   (CIP-30 wallet.getRewardAddresses()[0]),
      pool_id:       str   (bech32 "pool1..."),
      change_address: hex  (CIP-30 wallet.getChangeAddress()),
      utxos:         list[hex]  (CIP-30 wallet.getUtxos()),
    }
    res: { tx_cbor: str } / { error: str, detail?: str }

  POST /wallet/tx/drep_delegation
    body: {
      stake_address: hex,
      drep_id:       str   (bech32 "drep1..." | "always_abstain" | "always_no_confidence"),
      change_address: hex,
      utxos:         list[hex],
    }
    res: { tx_cbor: str } / { error: str, detail?: str }
"""
from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from cardanoism.backend.tx_builder import (
    build_drep_delegation_tx,
    build_pool_delegation_tx,
    combine_and_submit,
)

logger = logging.getLogger(__name__)


def _bad_request(message: str, detail: str = "") -> JSONResponse:
    payload: dict = {"error": message}
    if detail:
        payload["detail"] = detail
    return JSONResponse(payload, status_code=400)


def _server_error(message: str, detail: str = "") -> JSONResponse:
    payload: dict = {"error": message}
    if detail:
        payload["detail"] = detail
    return JSONResponse(payload, status_code=500)


async def _parse_json(request: Request) -> dict | None:
    try:
        data = await request.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _validate_common(data: dict) -> tuple[str, str, list[str]] | JSONResponse:
    """共通の必須フィールド検証。OK なら (stake_addr, change_addr, utxos)、NG なら 400。"""
    stake_addr = str(data.get("stake_address", "") or "").strip()
    change_addr = str(data.get("change_address", "") or "").strip()
    utxos_raw = data.get("utxos") or []

    if not stake_addr:
        return _bad_request("stake_address is required")
    if not change_addr:
        return _bad_request("change_address is required")
    if not isinstance(utxos_raw, list) or not utxos_raw:
        return _bad_request("utxos (non-empty list) is required")

    utxos = [str(x) for x in utxos_raw if x]
    if not utxos:
        return _bad_request("utxos is empty after normalization")

    return stake_addr, change_addr, utxos


async def pool_delegation(request: Request):
    data = await _parse_json(request)
    if data is None:
        return _bad_request("invalid JSON body")

    common = _validate_common(data)
    if isinstance(common, JSONResponse):
        return common
    stake_addr, change_addr, utxos = common

    pool_id = str(data.get("pool_id", "") or "").strip()
    if not pool_id or not pool_id.startswith("pool"):
        return _bad_request("pool_id must be bech32 'pool1...'")

    try:
        tx_cbor = build_pool_delegation_tx(
            stake_addr_cbor=stake_addr,
            pool_id_bech32=pool_id,
            change_addr_cbor=change_addr,
            utxos_cbor=utxos,
        )
        logger.info(
            "Built pool_delegation tx (cbor len=%d): pool=%s stake=%s utxos=%d",
            len(tx_cbor), pool_id, stake_addr[:20], len(utxos),
        )
        logger.debug("tx_cbor: %s", tx_cbor)
    except ValueError as e:
        return _bad_request("invalid input", str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("pool_delegation tx build failed")
        return _server_error("tx build failed", str(e))

    return JSONResponse({"tx_cbor": tx_cbor})


async def drep_delegation(request: Request):
    data = await _parse_json(request)
    if data is None:
        return _bad_request("invalid JSON body")

    common = _validate_common(data)
    if isinstance(common, JSONResponse):
        return common
    stake_addr, change_addr, utxos = common

    drep_id = str(data.get("drep_id", "") or "").strip()
    if not drep_id:
        return _bad_request("drep_id is required")

    try:
        tx_cbor = build_drep_delegation_tx(
            stake_addr_cbor=stake_addr,
            drep_id=drep_id,
            change_addr_cbor=change_addr,
            utxos_cbor=utxos,
        )
    except ValueError as e:
        return _bad_request("invalid input", str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("drep_delegation tx build failed")
        return _server_error("tx build failed", str(e))

    return JSONResponse({"tx_cbor": tx_cbor})


async def submit_tx(request: Request):
    """unsigned tx と CIP-30 wallet.signTx が返した witness set を結合して送信する。

    CIP-30 wallet.signTx は witness set だけを返すため、サーバ側で
    元の unsigned tx と結合してから Ogmios に submit する。
    一部の wallet (Eternl) は submitTx で 'unknown error' しか返さないので、
    サーバ submit で実際の rejection reason を取得する目的も兼ねる。
    """
    data = await _parse_json(request)
    if data is None:
        return _bad_request("invalid JSON body")
    unsigned_tx = str(data.get("unsigned_tx_cbor", "") or "").strip()
    witness_set = str(data.get("witness_set_cbor", "") or "").strip()
    if not unsigned_tx:
        return _bad_request("unsigned_tx_cbor is required")
    if not witness_set:
        return _bad_request("witness_set_cbor is required")

    try:
        tx_hash = combine_and_submit(unsigned_tx, witness_set)
    except Exception as e:  # noqa: BLE001
        logger.exception("submit_tx failed")
        return _server_error("submit failed", f"{type(e).__name__}: {e}")
    return JSONResponse({"tx_hash": tx_hash})


def get_routes() -> list[Route]:
    """Starlette の Route 配列を返す。cardanoism.py の api_transformer で組み込む。

    NOTE: パスは Reflex の /api/* (state 管理 WS 等) と衝突しないよう
    /wallet/tx/* にしている。
    """
    return [
        Route("/wallet/tx/pool_delegation", pool_delegation, methods=["POST"]),
        Route("/wallet/tx/drep_delegation", drep_delegation, methods=["POST"]),
        Route("/wallet/tx/submit", submit_tx, methods=["POST"]),
    ]
