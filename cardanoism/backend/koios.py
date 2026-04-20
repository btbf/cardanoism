"""
koios.py
Koios API を使ったオンチェーンデータ取得ユーティリティ

環境変数 KOIOS_NETWORK で切り替え:
  mainnet (デフォルト): https://api.koios.rest/api/v1
  preprod            : https://preprod.koios.rest/api/v1
"""
import os
import time
import threading
import logging
import requests

logger = logging.getLogger(__name__)

KOIOS_BATCH_SIZE = 1000  # Koios POST エンドポイントの上限件数


def _chunks(lst: list, n: int):
    """リストを n 件ずつのチャンクに分割するジェネレータ。"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


class _RateLimiter:
    """スレッドセーフなスライディングウィンドウ方式レートリミッター。
    Koios burst limit: 100 req / 10s。安全マージンとして 80/10s に設定。
    """
    def __init__(self, max_calls: int = 80, period: float = 10.0):
        self._lock = threading.Lock()
        self._timestamps: list[float] = []
        self._max = max_calls
        self._period = period

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            # ウィンドウ外のタイムスタンプを除去
            self._timestamps = [t for t in self._timestamps if now - t < self._period]
            if len(self._timestamps) >= self._max:
                # ウィンドウの先頭が抜けるまで待機
                sleep_for = self._period - (now - self._timestamps[0])
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if now - t < self._period]
            self._timestamps.append(time.monotonic())


_rate_limiter = _RateLimiter()


_NETWORK_URLS = {
    "mainnet": "https://api.koios.rest/api/v1",
    "preprod": "https://preprod.koios.rest/api/v1",
    "preview": "https://preview.koios.rest/api/v1",
}
_network = os.getenv("KOIOS_NETWORK", "mainnet").lower()
KOIOS_BASE_URL = _NETWORK_URLS.get(_network, _NETWORK_URLS["mainnet"])
logger.info("Koios ネットワーク: %s (%s)", _network, KOIOS_BASE_URL)


def _post(endpoint: str, payload: dict) -> list | dict | None:
    _rate_limiter.acquire()
    try:
        resp = requests.post(
            f"{KOIOS_BASE_URL}{endpoint}",
            json=payload,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Koios API error %s: %s", resp.status_code, endpoint)
            return None
        return resp.json()
    except Exception as e:
        logger.error("Koios API exception %s: %s", endpoint, e)
        return None


def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    _rate_limiter.acquire()
    try:
        resp = requests.get(
            f"{KOIOS_BASE_URL}{endpoint}",
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Koios GET error %s: %s", resp.status_code, endpoint)
            return None
        return resp.json()
    except Exception as e:
        logger.error("Koios GET exception %s: %s", endpoint, e)
        return None


def get_current_epoch() -> int | None:
    """現在のエポック番号を返す。"""
    data = _get("/tip")
    if not data or not isinstance(data, list) or not data[0]:
        return None
    return data[0].get("epoch_no")


def get_stake_address_from_addr(addr: str) -> str | None:
    """
    受信アドレス（addr1...）からステークアドレスを取得する。
    エンタープライズアドレス（ステークキーなし）は None を返す。
    """
    data = _post("/address_info", {"_addresses": [addr]})
    if not data or not isinstance(data, list) or not data[0]:
        return None
    return data[0].get("stake_address") or None


def _extract_str(value) -> str:
    """{"@value": "..."} 形式と文字列の両方に対応して文字列を返す。"""
    if isinstance(value, dict):
        return str(value.get("@value") or "").strip()
    return str(value or "").strip()


def get_pool_name(pool_id: str) -> str:
    """プールIDからプール名（ticker → name → meta_url フェッチの順）を取得する。"""
    data = _post("/pool_info", {"_pool_bech32_ids": [pool_id]})
    if not data or not isinstance(data, list) or not data[0]:
        return ""
    info = data[0]
    meta = info.get("meta_json") or {}
    name = _extract_str(meta.get("ticker") or meta.get("name"))
    if name:
        return name
    # meta_json に名前がない場合は meta_url から直接取得
    meta_url = _extract_str(info.get("meta_url"))
    if meta_url:
        try:
            resp = requests.get(meta_url, timeout=5)
            resp.raise_for_status()
            remote = resp.json()
            name = _extract_str(remote.get("ticker") or remote.get("name"))
            if name:
                return name
        except Exception as e:
            logger.debug("meta_url 取得失敗 pool=%s url=%s: %s", pool_id, meta_url, e)
    return ""


def batch_account_info(stake_addresses: list[str]) -> dict[str, dict]:
    """複数ステークアドレスのアカウント情報を一括取得（1,000件チャンク対応）。
    戻り値: {stake_address: account_info_dict}
    """
    if not stake_addresses:
        return {}
    result: dict[str, dict] = {}
    for chunk in _chunks(stake_addresses, KOIOS_BATCH_SIZE):
        data = _post("/account_info", {"_stake_addresses": chunk})
        if data and isinstance(data, list):
            for item in data:
                if item.get("stake_address"):
                    result[item["stake_address"]] = item
    return result


def detect_stake_role(stake_address: str) -> dict:
    """
    ステークアドレスのロールと委任先DRep・プール情報を返す。

    戻り値: {
        "role": "drep" | "delegator" | "abstain",
        "drep_id": str | None,
        "drep_name": str | None,
        "pool_id": str | None,
        "pool_name": str | None,
    }

    判定ロジック:
    1. /account_info で delegated_drep (drep_id) を取得
    2. drep_always_abstain → abstain
    3. /drep_updates から action=registered の meta_json.body.paymentAddress を取得
    4. その payment_address から /address_info でステークアドレスを取得
    5. 元のステークアドレスと一致 → drep、不一致 → delegator
    6. 委任者の場合、最新 update の givenName をDRep名として保存
    """
    result = {"role": "delegator", "drep_id": None, "drep_name": None, "pool_id": None, "pool_name": None}

    # Step 1: アカウント情報からDRep委任先・プール委任先を取得
    data = _post("/account_info", {"_stake_addresses": [stake_address]})
    if not data or not isinstance(data, list) or not data[0]:
        return result

    account = data[0]

    # プール委任先を取得
    pool_id = account.get("delegated_pool") or None
    if pool_id:
        result["pool_id"] = pool_id
        result["pool_name"] = get_pool_name(pool_id)

    drep_id = account.get("delegated_drep")
    if not drep_id:
        return result

    if drep_id == "drep_always_abstain":
        result["role"] = "abstain"
        return result

    if drep_id == "drep_always_no_confidence":
        return result

    # Step 2: /drep_updates を取得（block_time降順）
    updates = _post("/drep_updates", {"_drep_id": drep_id})
    if not updates or not isinstance(updates, list):
        result["drep_id"] = drep_id
        return result

    # 最新エントリからDRep名を取得
    latest_body = (updates[0].get("meta_json") or {}).get("body") or {}
    drep_name = _extract_str(latest_body.get("givenName"))

    # registered アクションから paymentAddress を取得
    payment_address = None
    for update in updates:
        if update.get("action") == "registered":
            body = (update.get("meta_json") or {}).get("body") or {}
            payment_address = _extract_str(body.get("paymentAddress"))
            break

    if not payment_address:
        result["drep_id"] = drep_id
        result["drep_name"] = drep_name
        return result

    # Step 3: paymentAddress のステークアドレスと照合
    drep_stake = get_stake_address_from_addr(payment_address)
    if drep_stake and drep_stake == stake_address:
        result["role"] = "drep"
        return result

    # 委任者
    result["drep_id"] = drep_id
    result["drep_name"] = drep_name
    return result


def _get_latest_delegation_date(stake_address: str, action_type: str):
    """
    /account_updates から指定 action_type の最新エントリの block_time を返す。
    レスポンスはフラットな配列。
    """
    from datetime import datetime, timezone
    data = _post("/account_updates", {"_stake_addresses": [stake_address]})
    if not data or not isinstance(data, list):
        return None
    entries = [u for u in data if u.get("action_type") == action_type]
    if not entries:
        return None
    latest = max(entries, key=lambda u: u.get("block_time", 0))
    block_time = latest.get("block_time")
    if not block_time:
        return None
    return datetime.fromtimestamp(block_time, tz=timezone.utc)


def get_pool_epoch_stats(pool_id: str, epoch_no: int) -> dict | None:
    """指定エポックのプール実績を返す。
    戻り値: {active_stake_ada, saturation_pct, block_cnt, apy} or None
    """
    data = _get("/pool_history", {"_pool_bech32": pool_id, "_epoch_no": epoch_no})
    if not data or not isinstance(data, list) or not data[0]:
        return None
    row = data[0]
    active_stake = row.get("active_stake")
    saturation = row.get("saturation_pct")
    block_cnt = row.get("block_cnt")
    ros = row.get("epoch_ros")
    return {
        "active_stake_ada": int(active_stake) / 1_000_000 if active_stake is not None else None,
        "saturation_pct": float(saturation) if saturation is not None else None,
        "block_cnt": int(block_cnt) if block_cnt is not None else None,
        "apy": float(ros) if ros is not None else None,
    }


def get_pool_apy(pool_id: str, epoch: int | None = None) -> float | None:
    """
    プールの APY（年率換算ROA）を返す。
    /pool_history の epoch_ros フィールドを使用（すでにパーセント表記）。
    epoch 未指定の場合は現在エポック-1（直前の完了エポック）を使用。
    """
    if not pool_id:
        return None
    if epoch is None:
        current = get_current_epoch()
        if current is None:
            return None
        epoch = current - 2
    data = _get("/pool_history", {"_pool_bech32": pool_id, "_epoch_no": epoch})
    if not data or not isinstance(data, list):
        return None
    ros = data[0].get("epoch_ros")
    if ros is None:
        return None
    return float(ros)


def get_pool_delegation_date(stake_address: str, pool_id: str = ""):
    """プールへの最新委任日時を返す（UTCのdatetime）。"""
    return _get_latest_delegation_date(stake_address, "delegation_pool")


def get_drep_delegation_date(stake_address: str, drep_id: str = ""):
    """DRepへの最新委任日時を返す（UTCのdatetime）。"""
    return _get_latest_delegation_date(stake_address, "delegation_drep")


def batch_account_update_history(stake_addresses: list[str]) -> dict[str, list]:
    """複数ステークアドレスのアカウント更新履歴を一括取得（1,000件チャンク対応）。
    戻り値: {stake_address: [update_entry, ...]}
    """
    if not stake_addresses:
        return {}
    result: dict[str, list] = {}
    for chunk in _chunks(stake_addresses, KOIOS_BATCH_SIZE):
        data = _post("/account_update_history", {"_stake_addresses": chunk})
        if data and isinstance(data, list):
            for item in data:
                sa = item.get("stake_address")
                if sa:
                    result.setdefault(sa, []).append(item)
    return result


def batch_account_reward_history(stake_addresses: list[str], epoch: int) -> dict[str, int]:
    """複数アドレスの指定エポック報酬合計を一括取得（1,000件チャンク対応）。
    戻り値: {stake_address: lovelace合計}
    """
    if not stake_addresses:
        return {}
    reward_map: dict[str, int] = {}
    for chunk in _chunks(stake_addresses, KOIOS_BATCH_SIZE):
        data = _post("/account_reward_history", {"_stake_addresses": chunk, "_epoch_no": epoch})
        if data and isinstance(data, list):
            for r in data:
                sa = r.get("stake_address")
                if sa:
                    reward_map[sa] = reward_map.get(sa, 0) + int(r.get("amount", 0))
    return reward_map


def _fetch_drep_name(drep_id: str) -> str:
    """DRepの表示名を /drep_updates の最新エントリから取得する。"""
    updates = _post("/drep_updates", {"_drep_id": drep_id})
    if not updates or not isinstance(updates, list):
        return ""
    body = (updates[0].get("meta_json") or {}).get("body") or {}
    return _extract_str(body.get("givenName"))


def get_proposal_title(proposal_tx_hash: str, proposal_index: int = 0) -> str | None:
    """
    ガバナンスアクションのタイトルを取得する。
    /proposal_list (GET) で全件取得し、proposal_tx_hash と index で照合して
    meta_json.body.title を返す。取得できない場合は proposal_type を返す。
    """
    data = _get("/proposal_list")
    if not data or not isinstance(data, list):
        return None
    target_id = f"{proposal_tx_hash}#{proposal_index}"
    for item in data:
        item_id = f"{item.get('proposal_tx_hash') or ''}#{item.get('proposal_index') or 0}"
        if item_id == target_id:
            body = (item.get("meta_json") or {}).get("body") or {}
            title = _extract_str(body.get("title"))
            if title:
                return title
            return _extract_str(item.get("proposal_type")) or None
    return None
