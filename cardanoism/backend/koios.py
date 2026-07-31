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
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except ImportError:  # urllib3 v2 互換
    from urllib3 import Retry  # type: ignore

logger = logging.getLogger(__name__)

KOIOS_BATCH_SIZE = 1000  # Koios POST エンドポイントの上限件数

# 接続再利用用の Session: 同一ホスト宛の TCP 接続を使い回し DNS 解決ストームを防ぐ。
# urllib3 のリトライで一過性の 5xx / 429 / 接続切断を自動再試行する。
_session = requests.Session()
_retry = Retry(
    total=4,
    backoff_factor=1.5,                          # 1.5 → 3 → 6 → 12 秒のバックオフ（429 復帰待ち）
    status_forcelist=(500, 502, 503, 504, 429),
    allowed_methods=("GET", "POST"),
    raise_on_status=False,
    respect_retry_after_header=True,             # サーバー指定の Retry-After を尊重
)
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=20, pool_maxsize=40)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def _chunks(lst: list, n: int):
    """リストを n 件ずつのチャンクに分割するジェネレータ。"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


class _RateLimiter:
    """スレッドセーフなスライディングウィンドウ方式レートリミッター。
    Koios の公式 burst limit は 100 req / 10s (= 10 req/s)。
    安全マージンを取って 90 / 10s = 9 req/s で運用する。
    1 プロセスあたりの burst 上限。複数プロセス並走時は別途プロセス間調整が必要。
    """
    def __init__(self, max_calls: int = 90, period: float = 10.0):
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


_NETWORK_URLS = {
    "mainnet": "https://api.koios.rest/api/v1",
    "preprod": "https://preprod.koios.rest/api/v1",
    "preview": "https://preview.koios.rest/api/v1",
}
_network = os.getenv("KOIOS_NETWORK", "mainnet").lower()
KOIOS_BASE_URL = _NETWORK_URLS.get(_network, _NETWORK_URLS["mainnet"])

# Koios API key (任意): 設定すると Authorization: Bearer ヘッダで認証されるためレート制限が緩和される
# https://api.koios.rest からプロジェクト登録で無料取得可能
KOIOS_API_KEY = os.getenv("KOIOS_API_KEY", "").strip()
if KOIOS_API_KEY:
    _session.headers.update({"Authorization": f"Bearer {KOIOS_API_KEY}"})
    logger.info("Koios ネットワーク: %s (%s) [API key 認証あり]", _network, KOIOS_BASE_URL)
else:
    logger.info("Koios ネットワーク: %s (%s) [anonymous]", _network, KOIOS_BASE_URL)
# Koios のティア (https://koios.rest/tiers.html):
#   Public (anonymous)    :  5,000 req/日 / burst 100 per 10s
#   Free   (API key)      : 50,000 req/日 / burst 100 per 10s
#   Pro                   : 500,000 req/日 / burst 250 per 10s
# burst は Public と Free で同じなのでレートリミッタは共通。API key の恩恵は
# **日次上限が 10 倍** になること (と利用量のダッシュボード可視化)。
_rate_limiter = _RateLimiter(max_calls=90, period=10.0)


def _retry_after_seconds(resp) -> float | None:
    """Retry-After ヘッダを秒に変換する。無い / 解釈不能なら None。"""
    val = resp.headers.get("Retry-After") if resp is not None else None
    if not val:
        return None
    try:
        return max(0.0, float(val))
    except (TypeError, ValueError):
        return None


def _request_with_retry(method: str, endpoint: str, *, params=None, json_body=None, timeout: float):
    """Session 経由 + アプリ層の追加リトライ。urllib3 のリトライで拾えない接続切断
    (RemoteDisconnected / NameResolutionError) もここで 3 回まで再試行する。
    POST でも params (?limit=N&offset=N 等) を許容する。

    429 は urllib3 側でも 4 回リトライ (1.5→3→6→12 秒) するが、それを使い切っても
    返ってくることがある (/proposal_voting_summary のような重いエンドポイントを
    並列で叩いたとき)。その場合はアプリ層でさらに長めに待って再試行する。
    ここで諦めて None を返すとデータが欠けたまま次の sync まで放置されるため。
    """
    last_err = None
    for attempt in range(3):
        _rate_limiter.acquire()
        try:
            if method == "GET":
                resp = _session.get(f"{KOIOS_BASE_URL}{endpoint}", params=params, timeout=timeout)
            else:
                resp = _session.post(
                    f"{KOIOS_BASE_URL}{endpoint}",
                    json=json_body, params=params, timeout=timeout,
                )
            if resp.status_code == 429:
                last_err = "429 Too Many Requests"
                if attempt == 2:
                    break
                sleep_for = _retry_after_seconds(resp) or (10.0 * (attempt + 1))
                logger.warning(
                    "Koios %s 429 (attempt %d/3, %.1fs 待機): %s",
                    method, attempt + 1, sleep_for, endpoint,
                )
                time.sleep(sleep_for)
                continue
            if resp.status_code != 200:
                logger.warning("Koios %s error %s: %s", method, resp.status_code, endpoint)
                return None
            return resp.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            sleep_for = 1.0 * (attempt + 1)
            logger.warning("Koios %s 接続エラー (attempt %d/3, retry in %.1fs): %s",
                           method, attempt + 1, sleep_for, e)
            time.sleep(sleep_for)
        except Exception as e:
            logger.error("Koios %s exception %s: %s", method, endpoint, e)
            return None
    logger.error("Koios %s 諦め (3回失敗) %s: %s", method, endpoint, last_err)
    return None


def _post(endpoint: str, payload: dict, timeout: float = 10.0, params: dict | None = None) -> list | dict | None:
    return _request_with_retry("POST", endpoint, json_body=payload, params=params, timeout=timeout)


def get_drep_delegators_total(drep_id: str, page_size: int = 1000, timeout: float = 15.0) -> int:
    """指定 DRep の現在の委任者 amount を全件合計して返す。
    /drep_delegators は POST + ?limit=&offset= のページネーション。
    Koios の上限 (1000 行/page) を超える委任者がいる DRep でも正確に合計できる。
    """
    total = 0
    offset = 0
    while True:
        data = _post(
            "/drep_delegators",
            {"_drep_id": drep_id},
            timeout=timeout,
            params={"limit": page_size, "offset": offset},
        )
        if not data or not isinstance(data, list):
            break
        for row in data:
            try:
                total += int(row.get("amount") or 0)
            except (TypeError, ValueError):
                continue
        if len(data) < page_size:
            break
        offset += page_size
    return total


def _get(endpoint: str, params: dict | None = None, timeout: float = 10.0) -> list | dict | None:
    return _request_with_retry("GET", endpoint, params=params, timeout=timeout)


# ─── /tip プロセス内キャッシュ ────────────────────────────────
# /tip は Reflex のページ遷移ごと + 各 worker からも頻繁に叩かれるため
# プロセス内で 30 秒キャッシュする。
# epoch_no はエポック中変わらず、epoch_slot / block_time は最大 30 秒のズレ。
# UI 表示なら全く問題なし。429 対策としてリクエスト数を 99%+ 削減する。
_TIP_CACHE: dict | None = None
_TIP_CACHE_AT: float = 0.0
_TIP_CACHE_TTL = 30.0
_TIP_CACHE_LOCK = threading.Lock()


def _get_tip_cached() -> dict | None:
    global _TIP_CACHE, _TIP_CACHE_AT
    now = time.monotonic()
    with _TIP_CACHE_LOCK:
        if _TIP_CACHE is not None and (now - _TIP_CACHE_AT) < _TIP_CACHE_TTL:
            return _TIP_CACHE
    data = _get("/tip")
    if not data or not isinstance(data, list) or not data[0]:
        return None
    with _TIP_CACHE_LOCK:
        _TIP_CACHE = data[0]
        _TIP_CACHE_AT = time.monotonic()
    return _TIP_CACHE


def get_current_epoch() -> int | None:
    """現在のエポック番号を返す (/tip を 30 秒キャッシュ)。"""
    tip = _get_tip_cached()
    return tip.get("epoch_no") if tip else None


def get_tip() -> dict | None:
    """Koios `/tip` の生レスポンス (epoch_no / epoch_slot / block_time 等) を返す。

    プロセス内で 30 秒キャッシュ。ダッシュボードでエポック残時間を計算するため使用。
    レスポンス例:
      { "epoch_no": 567, "epoch_slot": 12345, "block_no": ..., "block_time": 1716000000, ... }
    block_time は UNIX 秒 (UTC)。
    """
    return _get_tip_cached()


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
        # 自身が DRep のときは drep_id / drep_name も保持（未投票通知などで自分の voter_id 突合に使う）
        result["drep_id"] = drep_id
        result["drep_name"] = drep_name
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
    戻り値: {stake_address: lovelace合計} (type 区別せず合算)

    Type 別が必要なら batch_account_reward_history_by_type を使う。
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


def batch_account_reward_history_by_type(
    stake_addresses: list[str], epoch: int,
) -> dict[tuple[str, str], int]:
    """指定エポックの報酬を type 別に取得する。

    戻り値: {(stake_address, type): lovelace合計}
            type は member / leader / other に正規化済み。
    """
    if not stake_addresses:
        return {}
    out: dict[tuple[str, str], int] = {}
    for chunk in _chunks(stake_addresses, KOIOS_BATCH_SIZE):
        data = _post("/account_reward_history", {"_stake_addresses": chunk, "_epoch_no": epoch})
        if not data or not isinstance(data, list):
            continue
        for r in data:
            sa = r.get("stake_address")
            if not sa:
                continue
            t = r.get("type")
            t_norm = t if t in ("member", "leader") else "other"
            try:
                amt = int(r.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            key = (sa, t_norm)
            out[key] = out.get(key, 0) + amt
    return out


def fetch_reward_history_recent(
    stake_addresses: list[str], n_epochs: int = 30,
) -> list[dict]:
    """各 stake address の直近 N エポック分の raw 報酬履歴を取得する。

    Koios `/account_reward_history` は `_epoch_no` を省略すると全履歴を返す。
    PostgREST の `?order=earned_epoch.desc&limit=N` を併用して直近のみを抜き取る。

    レスポンスは 1 行 = (stake_address × earned_epoch × type)。
    type は member / leader / treasury / reserves / refund のいずれか。
    呼び出し側で stake × epoch 軸に集計する (aggregate_rewards_by_epoch)。
    """
    if not stake_addresses:
        return []
    out: list[dict] = []
    # 1 stake あたり最大 5 type/epoch のため安全マージンを取る
    for chunk in _chunks(stake_addresses, KOIOS_BATCH_SIZE):
        limit = max(1000, n_epochs * 5 * len(chunk))
        path = f"/account_reward_history?order=earned_epoch.desc&limit={int(limit)}"
        data = _post(path, {"_stake_addresses": chunk})
        if data and isinstance(data, list):
            out.extend(data)
    return out


def fetch_treasury_rewards_by_epoch(
    stake_addresses: list[str], epoch: int,
) -> list[dict]:
    """指定エポックの type=treasury 報酬行をそのまま返す（1,000件チャンク対応）。

    GA (TreasuryWithdrawals) の出金照合用。戻り値の各行は Koios の生レスポンス
    形式: {stake_address, earned_epoch, amount, type, spendable_epoch, ...}。
    type 別に正規化せず treasury 行だけを抜き出す。
    """
    if not stake_addresses:
        return []
    out: list[dict] = []
    for chunk in _chunks(stake_addresses, KOIOS_BATCH_SIZE):
        data = _post("/account_reward_history", {"_stake_addresses": chunk, "_epoch_no": epoch})
        if not data or not isinstance(data, list):
            continue
        for r in data:
            if r.get("type") == "treasury":
                out.append(r)
    return out


def aggregate_rewards_by_epoch(
    rows: list[dict],
) -> list[tuple[str, int, int, str | None, str]]:
    """fetch_reward_history_recent の戻り値を (stake, epoch, type) 軸に集計する。

    1 stake × 1 epoch でも type ごと (member / leader / other) に別行を返す。
    Koios は同一 (stake, epoch, type) で複数行になることはほぼないが、念のため合算。

    treasury / reserves / refund は "other" にまとめる (UI 表示優先度が低いため)。

    pool_id_bech32 は最初に見つかった非 None を採用 (member 行などに紐づくはず)。
    戻り値タプル: (stake_address, epoch, amount_lovelace, pool_id_or_None, reward_type)
    """
    agg: dict[tuple[str, int, str], dict] = {}
    for r in rows:
        sa = r.get("stake_address")
        epoch = r.get("earned_epoch")
        if not sa or epoch is None:
            continue
        try:
            epoch_int = int(epoch)
            amount = int(r.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        t = r.get("type")
        t_norm = t if t in ("member", "leader") else "other"
        key = (str(sa), epoch_int, t_norm)
        slot = agg.setdefault(key, {"amount": 0, "pool_id": None})
        slot["amount"] += amount
        if slot["pool_id"] is None and r.get("pool_id_bech32"):
            slot["pool_id"] = str(r.get("pool_id_bech32"))
    return [
        (sa, epoch, agg[(sa, epoch, t)]["amount"], agg[(sa, epoch, t)]["pool_id"], t)
        for sa, epoch, t in agg
    ]


def _fetch_drep_name(drep_id: str) -> str:
    """DRepの表示名を /drep_updates の最新エントリから取得する。"""
    updates = _post("/drep_updates", {"_drep_id": drep_id})
    if not updates or not isinstance(updates, list):
        return ""
    body = (updates[0].get("meta_json") or {}).get("body") or {}
    return _extract_str(body.get("givenName"))


# ============================================================
# トレジャリー関連
# ============================================================

# ─── /totals プロセス内キャッシュ ─────────────────────────────
# /totals はエポック単位の値 (epoch 中は不変) なので 5 分 TTL で十分。
# epoch_no 指定/未指定で別キーで保持する。
_TOTALS_CACHE: dict[str, tuple[float, dict]] = {}
_TOTALS_CACHE_TTL = 300.0  # 5 分
_TOTALS_CACHE_LOCK = threading.Lock()


def get_totals(epoch_no: int | None = None) -> dict | None:
    """
    指定エポック（未指定時は最新）の循環供給・トレジャリー・リワード・準備金を返す。
    レスポンスは最新順で返ってくる想定。
    戻り値: {epoch_no, circulation, treasury, reward, supply, reserves}（すべて Lovelace 文字列）

    プロセス内で 5 分キャッシュ。エポック単位で値が変わらないため十分。
    """
    key = "_latest" if epoch_no is None else str(int(epoch_no))
    now = time.monotonic()
    with _TOTALS_CACHE_LOCK:
        cached = _TOTALS_CACHE.get(key)
        if cached and (now - cached[0]) < _TOTALS_CACHE_TTL:
            return cached[1]
    params = {"_epoch_no": epoch_no} if epoch_no is not None else None
    data = _get("/totals", params)
    if not data or not isinstance(data, list) or not data[0]:
        return None
    # Koios は降順で返すため先頭が最新
    result = data[0]
    with _TOTALS_CACHE_LOCK:
        _TOTALS_CACHE[key] = (time.monotonic(), result)
    return result


def get_treasury_withdrawals(limit: int = 1000) -> list[dict]:
    """
    トレジャリー引き出し履歴を返す（降順）。
    戻り値: [{stake_address, amount, earned_epoch, spendable_epoch}, ...]
    """
    data = _get("/treasury_withdrawals", {"limit": limit, "order": "earned_epoch.desc"})
    if not data or not isinstance(data, list):
        return []
    return data


def get_treasury_proposals() -> list[dict]:
    """
    TreasuryWithdrawals タイプのガバナンスアクションを返す。
    ステータス判定（active/ratified/enacted/...）は上位で行う想定。
    """
    data = _get("/proposal_list")
    if not data or not isinstance(data, list):
        return []
    return [p for p in data if p.get("proposal_type") == "TreasuryWithdrawals"]


def _parse_ncl_from_body(body: dict) -> tuple[int | None, int | None, int | None]:
    """
    NCL提案の body から上限ADA・開始エポック・終了エポックを抽出する。
    戻り値: (limit_ada, start_epoch, end_epoch) - いずれも取れない場合は None。

    タイトル例:
      "Net Change Limit (Epoch 613 to Epoch 713)"
      "Net Change Limit of 300 Million ADA for Epochs 613–713"
    本文（abstract / rationale）例:
      "350,000,000,000,000 lovelace (350M ada)"
      "start of Epoch 613" ... "end of Epoch 713"
      "Epochs 563–635"
    """
    import re

    def _extract_str(val) -> str:
        if isinstance(val, dict):
            return str(val.get("@value") or "")
        return str(val or "")

    title = _extract_str(body.get("title"))
    abstract = _extract_str(body.get("abstract"))
    rationale = _extract_str(body.get("rationale"))
    text = "\n".join([title, abstract, rationale])

    # 上限 ADA 抽出
    limit_ada: int | None = None
    # 1) lovelace 数値（"350,000,000,000,000 lovelace"）
    m = re.search(r"([\d,]{10,})\s*lovelace", text, re.IGNORECASE)
    if m:
        try:
            limit_ada = int(m.group(1).replace(",", "")) // 1_000_000
        except ValueError:
            pass
    # 2) "350M ada" / "350 million ada"
    if limit_ada is None:
        m = re.search(r"(\d{1,4}(?:[.,]\d+)?)\s*(?:M|million)\s*ada", text, re.IGNORECASE)
        if m:
            try:
                limit_ada = int(float(m.group(1).replace(",", "")) * 1_000_000)
            except ValueError:
                pass
    # 3) "350,000,000 ada"
    if limit_ada is None:
        m = re.search(r"([\d,]{9,})\s*ada", text, re.IGNORECASE)
        if m:
            try:
                limit_ada = int(m.group(1).replace(",", ""))
            except ValueError:
                pass

    # エポック範囲抽出（"Epoch 613 to Epoch 713" / "Epochs 613–713" / "Epochs 613-713"）
    start_epoch: int | None = None
    end_epoch: int | None = None
    m = re.search(r"Epochs?\s+(\d{3,4})\s*(?:to|-|–|through|〜)\s*(?:Epoch\s+)?(\d{3,4})", text, re.IGNORECASE)
    if m:
        try:
            start_epoch = int(m.group(1))
            end_epoch = int(m.group(2))
        except ValueError:
            pass
    if start_epoch is None:
        m = re.search(r"start of\s+Epoch\s+(\d{3,4})", text, re.IGNORECASE)
        if m:
            start_epoch = int(m.group(1))
    if end_epoch is None:
        m = re.search(r"(?:end of|conclusion of|conclude[^.]*?|finishing at[^.]*?)\s+Epoch\s+(\d{3,4})", text, re.IGNORECASE)
        if m:
            end_epoch = int(m.group(1))

    return limit_ada, start_epoch, end_epoch


# NCL 取得キャッシュ（重い API 呼び出しを抑制）
_NCL_CACHE: dict | None = None
_NCL_CACHE_AT: float = 0.0
_NCL_CACHE_TTL = 30 * 60  # 30分


def fetch_active_ncl(use_cache: bool = True) -> dict | None:
    """
    直近のNCL提案のうち、DRep の賛成が過半数（>50%）に達しているものを1件返す。

    憲法規定: "approval of a Net Change Limit requires a threshold of greater than
    50% of the active voting DRep stake." ため、enacted_epoch が立たない
    InfoAction でも DRep 過半数賛成で有効。

    戻り値:
      {
        "limit_ada": int,
        "start_epoch": int,
        "end_epoch": int,
        "title": str,
        "proposal_tx_hash": str,
        "proposal_id": str,
        "drep_yes_pct": float,
      }
    または解析失敗時は None。
    """
    global _NCL_CACHE, _NCL_CACHE_AT
    if use_cache and _NCL_CACHE and (time.time() - _NCL_CACHE_AT) < _NCL_CACHE_TTL:
        return _NCL_CACHE

    proposals = _post("/proposal_list", {}) or _get("/proposal_list") or []
    if not isinstance(proposals, list):
        return None

    candidates: list[dict] = []
    for p in proposals:
        if p.get("proposal_type") != "InfoAction":
            continue
        meta_body = (p.get("meta_json") or {}).get("body") or {}
        title_raw = meta_body.get("title")
        title = title_raw.get("@value") if isinstance(title_raw, dict) else title_raw
        if not isinstance(title, str):
            continue
        tl = title.lower()
        if "net change limit" not in tl and "ncl" not in tl:
            continue
        candidates.append(p)

    candidates.sort(key=lambda p: (p.get("proposed_epoch") or 0), reverse=True)

    for p in candidates:
        pid = p.get("proposal_id")
        if not pid:
            continue
        summary = _get("/proposal_voting_summary", {"_proposal_id": pid}, timeout=30.0)
        if not summary or not isinstance(summary, list) or not summary[0]:
            continue
        drep_yes_pct = summary[0].get("drep_yes_pct")
        try:
            yes = float(drep_yes_pct) if drep_yes_pct is not None else 0.0
        except (TypeError, ValueError):
            yes = 0.0
        if yes <= 50.0:
            continue

        body = (p.get("meta_json") or {}).get("body") or {}
        limit_ada, start_epoch, end_epoch = _parse_ncl_from_body(body)
        if limit_ada is None or start_epoch is None or end_epoch is None:
            logger.warning("NCL提案 %s のパースに失敗: limit=%s start=%s end=%s",
                           pid, limit_ada, start_epoch, end_epoch)
            continue

        title_raw = body.get("title")
        title = title_raw.get("@value") if isinstance(title_raw, dict) else (title_raw or "")
        result = {
            "limit_ada": limit_ada,
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
            "title": str(title),
            "proposal_tx_hash": p.get("proposal_tx_hash") or "",
            "proposal_id": pid,
            "drep_yes_pct": yes,
        }
        _NCL_CACHE = result
        _NCL_CACHE_AT = time.time()
        return result
    return None


# ============================================================
# DRep 関連
# ============================================================

def get_drep_list() -> list[dict]:
    """全 DRep の最小情報（drep_id, hex, has_script, registered）を返す。
    Koios GET はデフォルト 1000 件上限なので offset で全件取得するまでループ。
    """
    all_out: list[dict] = []
    limit = 1000
    offset = 0
    while True:
        data = _get("/drep_list", {"limit": limit, "offset": offset})
        if not data or not isinstance(data, list):
            break
        all_out.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return all_out


# Koios /drep_info と /drep_metadata は他の POST より厳しいペイロード制限がある。
# 実測 (2026-07, mainnet): 75 件 = OK / 90 件 = 413 Payload Too Large。
#
# drep_sync は registered 全件 (実測 9,875 件) を毎回このサイズで刻んで叩くため、
# ここが Koios 日次上限に対する最大の消費源になる。15 分 cron での req/日:
#     25 件 → 395 req/回 = 37,920 req/日
#     50 件 → 198 req/回 = 19,008 req/日   ← 採用
#     75 件 → 132 req/回 = 12,672 req/日   (上限に近く 413 のリスク)
# 413 が返っても _post_split_on_413 が半分に割って再試行するのでデータは欠けないが、
# その分リクエストが増える (1 失敗 + 2 分割 = 3 req)。上限ギリギリは避けて 50 とする。
DREP_BATCH_SIZE = 50


def _post_split_on_413(endpoint: str, key: str, ids: list[str], timeout: float = 10.0) -> list[dict]:
    """POST して 413 などで None が返った場合、ペイロードを半分に分割して再帰リトライ。"""
    if not ids:
        return []
    data = _post(endpoint, {key: ids}, timeout=timeout)
    if isinstance(data, list):
        return data
    # 取得失敗（413 等）: 1 件まで縮めても失敗する場合は諦める
    if len(ids) <= 1:
        logger.warning("Koios %s: id=%s の取得を断念", endpoint, ids[0] if ids else "?")
        return []
    mid = len(ids) // 2
    return _post_split_on_413(endpoint, key, ids[:mid], timeout=timeout) + _post_split_on_413(endpoint, key, ids[mid:], timeout=timeout)


def get_drep_info_batch(drep_ids: list[str]) -> list[dict]:
    """複数 DRep の登録情報・委任量を一括取得（25 件チャンク + 413 自動分割）。"""
    if not drep_ids:
        return []
    out: list[dict] = []
    for chunk in _chunks(drep_ids, DREP_BATCH_SIZE):
        out.extend(_post_split_on_413("/drep_info", "_drep_ids", chunk))
    return out


def get_committee_info() -> dict | None:
    """現在の Constitutional Committee 情報（quorum と members）を返す。"""
    data = _get("/committee_info", timeout=15.0)
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data


def get_epoch_params(epoch_no: int | None = None) -> dict | None:
    """指定エポック（未指定なら最新）のプロトコルパラメータを返す。"""
    params = {"_epoch_no": epoch_no} if epoch_no is not None else None
    data = _get("/epoch_params", params, timeout=15.0)
    if not data or not isinstance(data, list) or not data[0]:
        return None
    return data[0]


# /proposal_voting_summary は Koios 側の計算コストが高く、並列で叩くと 429 を返す。
# グローバルなレートリミッタとは別に、このエンドポイントだけ同時実行数を絞る。
# ThreadPoolExecutor の worker 数を増やしても、ここが実質の上限になる。
_SUMMARY_SEMAPHORE = threading.BoundedSemaphore(2)


def get_proposal_voting_summary(proposal_id: str) -> dict | None:
    """指定 proposal の投票集計（Yes/No/Abstain の票数・パーセンテージ）を返す。
    Koios 側で計算コストが高く数十秒かかることがあるため、長めのタイムアウト + リトライ。
    同時実行は _SUMMARY_SEMAPHORE で 2 に制限する（429 対策）。
    """
    if not proposal_id:
        return None
    with _SUMMARY_SEMAPHORE:
        for attempt in range(3):
            data = _get(
                "/proposal_voting_summary",
                {"_proposal_id": proposal_id},
                timeout=60.0,
            )
            if data and isinstance(data, list) and data[0]:
                return data[0]
            if attempt < 2:
                time.sleep(5.0 * (attempt + 1))
    return None


def get_proposal_votes(proposal_id: str, limit: int = 1000) -> list[dict]:
    """指定された proposal_id への投票一覧を全件取得する（Koios ページネーション対応）。"""
    if not proposal_id:
        return []
    all_out: list[dict] = []
    offset = 0
    while True:
        data = _get(
            "/proposal_votes",
            {"_proposal_id": proposal_id, "limit": limit, "offset": offset},
            timeout=30.0,
        )
        if not data or not isinstance(data, list):
            break
        all_out.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return all_out


def get_drep_metadata_batch(drep_ids: list[str]) -> list[dict]:
    """複数 DRep の CIP-119 メタデータを一括取得（25 件チャンク + 413 自動分割）。"""
    if not drep_ids:
        return []
    out: list[dict] = []
    for chunk in _chunks(drep_ids, DREP_BATCH_SIZE):
        out.extend(_post_split_on_413("/drep_metadata", "_drep_ids", chunk))
    return out


# ============================================================
# プール（SPO）関連
# ============================================================

# /pool_info は Koios 側で live_stake / saturation / 累計ブロック等の集計が走るため重い。
# 25 件バッチでは 60 秒タイムアウトに収まらないケースが多発するため 10 件に絞る。
# 失敗時はさらに半分ずつ分割（_post_split_on_413）するので保険は効く。
POOL_BATCH_SIZE = 10


def get_pool_list() -> list[dict]:
    """全プールの最小情報（pool_id_bech32, pool_id_hex, ticker, pool_status, retiring_epoch 等）を返す。
    Koios GET はデフォルト 1000 件上限なので offset で全件取得するまでループ。
    """
    all_out: list[dict] = []
    limit = 1000
    offset = 0
    while True:
        data = _get("/pool_list", {"limit": limit, "offset": offset}, timeout=20.0)
        if not data or not isinstance(data, list):
            break
        all_out.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return all_out


# 現在エポックのブロック→プール→protocol version マップ（オンデマンドフェッチ用）
# Koios /blocks は重いので 5 分の in-memory キャッシュを噛ませる。
_EPOCH_PROTO_TTL = 300.0
_epoch_proto_cache: tuple[float, int, dict[str, dict]] | None = None
_epoch_proto_lock = threading.Lock()


def get_current_epoch_block_stats(current_epoch: int | None = None) -> dict:
    """現在エポックの全ブロックを Koios /blocks から集計して返す。

    戻り値:
      {
        "epoch":        int,                                 # 集計対象エポック
        "total_blocks": int,                                 # 取得ブロック総数
        "pool_latest":  {pool_id: {"major": int, "minor": int}},  # プールごとの最新ブロック
        "version_block_counts": [{"major": int, "minor": int, "count": int}],  # version 別ブロック数 (count desc)
      }
    """
    empty: dict = {"epoch": 0, "total_blocks": 0, "pool_latest": {}, "version_block_counts": []}
    if current_epoch is None:
        current_epoch = get_current_epoch()
        if current_epoch is None:
            logger.warning("block_stats: 現在エポックの取得に失敗しました")
            return empty

    global _epoch_proto_cache
    with _epoch_proto_lock:
        now = time.time()
        if _epoch_proto_cache:
            ts, ep, data = _epoch_proto_cache
            if ep == current_epoch and now - ts < _EPOCH_PROTO_TTL:
                return data

    pool_latest: dict[str, dict] = {}
    counts: dict[tuple[int, int], int] = {}
    total = 0
    offset = 0
    limit = 1000
    while True:
        params = {
            "epoch_no": f"eq.{int(current_epoch)}",
            "order":    "block_time.desc",
            "offset":   offset,
            "limit":    limit,
        }
        try:
            data = _get("/blocks", params, timeout=20.0)
        except Exception as e:  # noqa: BLE001
            logger.warning("block_stats fetch failed (offset=%d): %s", offset, e)
            break
        if not data or not isinstance(data, list):
            if offset == 0:
                logger.warning("block_stats: Koios /blocks epoch_no=%d が空レスポンス", current_epoch)
            break
        total += len(data)
        for b in data:
            mj = b.get("proto_major")
            mn = b.get("proto_minor")
            if mj is not None and mn is not None:
                k = (int(mj), int(mn))
                counts[k] = counts.get(k, 0) + 1
            pool = b.get("pool")
            if pool and pool not in pool_latest:
                pool_latest[pool] = {
                    "major": mj,
                    "minor": mn,
                    "abs_slot":    b.get("abs_slot"),
                    "block_height": b.get("block_height"),
                }
        if len(data) < limit:
            break
        offset += limit

    vbc = sorted(
        [{"major": k[0], "minor": k[1], "count": v} for k, v in counts.items()],
        key=lambda d: -d["count"],
    )
    stats = {
        "epoch":                int(current_epoch),
        "total_blocks":         total,
        "pool_latest":          pool_latest,
        "version_block_counts": vbc,
    }

    logger.info(
        "block_stats: epoch=%d total_blocks=%d pools=%d versions=%d",
        current_epoch, total, len(pool_latest), len(vbc),
    )

    with _epoch_proto_lock:
        _epoch_proto_cache = (time.time(), current_epoch, stats)
    return stats


def get_pool_history(pool_id_bech32: str, limit: int = 5, timeout: float = 10.0) -> list[dict]:
    """指定プールの履歴をエポック降順で取得（最新 limit 件）。
    各要素は epoch_no / block_cnt / active_stake / saturation_pct 等を含む。
    """
    if not pool_id_bech32:
        return []
    params = {
        "_pool_bech32": pool_id_bech32,
        "order": "epoch_no.desc",
        "limit": limit,
    }
    data = _get("/pool_history", params, timeout=timeout)
    if not data or not isinstance(data, list):
        return []
    return data


def get_pool_info_batch(pool_ids: list[str], timeout: float = 60.0) -> list[dict]:
    """複数プールの詳細情報を一括取得（10 件チャンク + 413 自動分割）。
    /pool_info は live_stake / saturation / 累計ブロック等を集計するため Koios 側で重い。
    """
    if not pool_ids:
        return []
    total_chunks = (len(pool_ids) + POOL_BATCH_SIZE - 1) // POOL_BATCH_SIZE
    logger.info("/pool_info フェッチ開始: %d 件 / %d チャンク (バッチ=%d, timeout=%.0fs)",
                len(pool_ids), total_chunks, POOL_BATCH_SIZE, timeout)
    out: list[dict] = []
    done_chunks = 0
    for chunk in _chunks(pool_ids, POOL_BATCH_SIZE):
        out.extend(_post_split_on_413("/pool_info", "_pool_bech32_ids", chunk, timeout=timeout))
        done_chunks += 1
        # 25 チャンクごと（= 250 件処理ごと）にログ
        if done_chunks % 25 == 0 or done_chunks == total_chunks:
            logger.info("/pool_info 進捗: %d / %d チャンク完了 (%d 件取得済み)",
                        done_chunks, total_chunks, len(out))
    return out


def get_recent_pool_updates(min_active_epoch: int, timeout: float = 30.0) -> dict[str, list[dict]]:
    """active_epoch_no >= min_active_epoch の cert 更新を全プール分一括取得する。

    Koios `/pool_updates` は GET エンドポイントで `_pool_bech32` (単数) しか
    受け付けないため、3000+ プールを 1 件ずつ叩くのは現実的でない。代わりに
    PostgREST フィルタ (`active_epoch_no=gte.N`) で「直近のみ」を全プール横断
    1 リクエストで取得し、pagination で全件回収する。

    `min_active_epoch = current_epoch - 1` 程度を渡せば:
      - active 候補 (active_epoch_no = current_epoch or current_epoch - 1)
      - pending 候補 (active_epoch_no > current_epoch)
    の両方をカバーできる。それより古い更新しか無いプールは「ここ最近変化無し」
    として扱い、active 値は呼び出し側で /pool_info の値を使えばよい。

    Returns: {pool_id_bech32: [update_dict, ...]} (active_epoch_no DESC)
    """
    out: dict[str, list[dict]] = {}
    limit = 1000
    offset = 0
    while True:
        data = _get(
            "/pool_updates",
            {
                "active_epoch_no": f"gte.{int(min_active_epoch)}",
                "order": "active_epoch_no.desc",
                "offset": offset,
                "limit": limit,
            },
            timeout=timeout,
        )
        if not data or not isinstance(data, list):
            break
        for r in data:
            pid = r.get("pool_id_bech32")
            if pid:
                out.setdefault(pid, []).append(r)
        logger.info(
            "/pool_updates 取得: offset=%d 件=%d 累計プール=%d",
            offset, len(data), len(out),
        )
        if len(data) < limit:
            break
        offset += limit
    return out


def get_proposal_title(proposal_tx_hash: str, proposal_index: int = 0) -> str | None:
    """
    ガバナンスアクションのタイトルを取得する。
    /proposal_list (GET) で全件取得し、proposal_tx_hash と index で照合して
    meta_json.body.title を返す。取得できない場合は proposal_type を返す。
    """
    info = get_proposal_info(proposal_tx_hash, proposal_index)
    if not info:
        return None
    return info.get("title") or info.get("proposal_type") or None


def get_proposal_info(proposal_tx_hash: str, proposal_index: int = 0) -> dict | None:
    """ガバナンスアクションの基本情報を返す。

    戻り値: {"title": str, "proposal_id": str, "proposal_type": str} or None
    """
    data = _get("/proposal_list")
    if not data or not isinstance(data, list):
        return None
    target_id = f"{proposal_tx_hash}#{proposal_index}"
    for item in data:
        item_id = f"{item.get('proposal_tx_hash') or ''}#{item.get('proposal_index') or 0}"
        if item_id == target_id:
            body = (item.get("meta_json") or {}).get("body") or {}
            return {
                "title":         _extract_str(body.get("title")),
                "proposal_id":   _extract_str(item.get("proposal_id")),
                "proposal_type": _extract_str(item.get("proposal_type")),
            }
    return None
