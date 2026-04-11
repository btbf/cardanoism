"""
blockfrost.py
Blockfrost API を使ったオンチェーンデータ取得ユーティリティ
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

BLOCKFROST_PROJECT_ID = os.getenv("BLOCKFROST_PROJECT_ID", "")
BLOCKFROST_BASE_URL = "https://cardano-mainnet.blockfrost.io/api/v0"


def _headers() -> dict:
    return {"project_id": BLOCKFROST_PROJECT_ID}


def _fetch_drep_name(drep_id: str) -> str:
    """DRepのオフチェーンメタデータから名前を取得する。取得できない場合は空文字。"""
    try:
        resp = requests.get(
            f"{BLOCKFROST_BASE_URL}/governance/dreps/{drep_id}/metadata",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        # CIP-119: json_metadata.body.givenName
        body = (data.get("json_metadata") or {}).get("body") or {}
        name = body.get("givenName") or ""
        # {"@value": "..."} 形式の場合
        if isinstance(name, dict):
            name = name.get("@value") or ""
        return str(name).strip()
    except Exception as e:
        logger.debug("_fetch_drep_name error: %s", e)
    return ""


def detect_stake_role(stake_address: str) -> dict:
    """
    ステークアドレスのロールと委任先DRep情報を返す。

    戻り値: {
        "role": "drep" | "delegator" | "abstain",
        "drep_id": str | None,   # 委任先DRep ID（delegator のみ）
        "drep_name": str | None, # 委任先DRep 名（delegator のみ）
    }

    判定ロジック:
    1. /accounts/{stake_address} から drep_id を取得
    2. drep_id がなければ delegator
    3. drep_always_abstain → abstain
    4. /governance/dreps/{drep_id}/delegators に stake_address があれば drep
    5. なければ delegator（委任先DRep名を取得して返す）
    """
    result = {"role": "delegator", "drep_id": None, "drep_name": None}

    if not BLOCKFROST_PROJECT_ID:
        logger.warning("BLOCKFROST_PROJECT_ID が未設定のため role 判定をスキップ")
        return result

    try:
        # Step 1: アカウント情報取得
        resp = requests.get(
            f"{BLOCKFROST_BASE_URL}/accounts/{stake_address}",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("accounts API error %s for %s", resp.status_code, stake_address)
            return result

        drep_id = resp.json().get("drep_id")
        if not drep_id:
            return result

        # 棄権（always abstain）
        if drep_id == "drep_always_abstain":
            result["role"] = "abstain"
            return result

        # 不信任（always no confidence）は委任者扱い・DRep名なし
        if drep_id == "drep_always_no_confidence":
            return result

        # Step 2: そのDRepの委任者リストをページ巡回して確認
        page = 1
        while True:
            resp = requests.get(
                f"{BLOCKFROST_BASE_URL}/governance/dreps/{drep_id}/delegators",
                headers=_headers(),
                params={"count": 100, "page": page},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("dreps delegators API error %s", resp.status_code)
                break

            delegators = resp.json()
            if not delegators:
                break

            for d in delegators:
                if d.get("address") == stake_address:
                    result["role"] = "drep"
                    return result

            if len(delegators) < 100:
                break
            page += 1

        # delegator → 委任先DRep情報を保存
        result["drep_id"] = drep_id
        result["drep_name"] = _fetch_drep_name(drep_id)

    except Exception as e:
        logger.error("detect_stake_role error: %s", e)

    return result
