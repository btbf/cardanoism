"""
price.py
ADA の法定通貨レート取得と、サイト全体で共有するフォーマット関数。

APIコールは同期バッチ（notify_worker.py --event fiat_sync）でのみ使う。
ページ側はフォーマット関数（format_jpy_short / format_usd_short）のみを使う。
"""
from __future__ import annotations

import logging
import requests

logger = logging.getLogger(__name__)


COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"


def fetch_ada_rates() -> dict | None:
    """
    CoinGecko から ADA の JPY/USD レートを取得する。
    戻り値: {"ada_jpy": float, "ada_usd": float} または失敗時 None
    """
    try:
        resp = requests.get(
            COINGECKO_URL,
            params={"ids": "cardano", "vs_currencies": "jpy,usd"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("CoinGecko error %s: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json() or {}
        ada = data.get("cardano") or {}
        jpy = ada.get("jpy")
        usd = ada.get("usd")
        if jpy is None or usd is None:
            logger.warning("CoinGecko レスポンスが不完全: %s", data)
            return None
        return {"ada_jpy": float(jpy), "ada_usd": float(usd)}
    except Exception as e:
        logger.error("CoinGecko 取得失敗: %s", e)
        return None


# ============================================================
# フォーマット関数（UI 共通）
# ============================================================

def format_jpy_short(amount: float | int | None) -> str:
    """
    JPY を「万/億/兆」単位で読みやすく整形する。
    例:
      1,234 → ¥1,234
      12,345 → ¥1.2万
      123,456,789 → ¥1.2億
      1,234,567,890,123 → ¥1.2兆
    """
    if amount is None:
        return "-"
    try:
        v = float(amount)
    except (TypeError, ValueError):
        return "-"
    av = abs(v)
    if av >= 1e12:
        return f"¥{v / 1e12:,.2f}兆"
    if av >= 1e8:
        return f"¥{v / 1e8:,.2f}億"
    if av >= 1e4:
        return f"¥{v / 1e4:,.1f}万"
    return f"¥{v:,.0f}"


def format_usd_short(amount: float | int | None) -> str:
    """
    USD を K/M/B/T 単位で読みやすく整形する。
    例:
      1,234 → $1.2K
      1,234,567 → $1.23M
      1,234,567,890 → $1.23B
    """
    if amount is None:
        return "-"
    try:
        v = float(amount)
    except (TypeError, ValueError):
        return "-"
    av = abs(v)
    if av >= 1e12:
        return f"${v / 1e12:,.2f}T"
    if av >= 1e9:
        return f"${v / 1e9:,.2f}B"
    if av >= 1e6:
        return f"${v / 1e6:,.2f}M"
    if av >= 1e3:
        return f"${v / 1e3:,.1f}K"
    return f"${v:,.2f}"


def format_ada(lovelace: int | None, integer: bool = False) -> str:
    """
    ADA 金額を省略せず整形する。
      integer=True : 小数点以下は切り捨て（例: 1,617,354,048）
      integer=False: 整数なら整数、小数ありなら最大6桁（末尾ゼロ除去）
    """
    if lovelace is None:
        return "-"
    try:
        ada = int(lovelace) / 1_000_000
    except (TypeError, ValueError):
        return "-"
    if integer or ada == int(ada):
        return f"{int(ada):,}"
    s = f"{ada:,.6f}".rstrip("0").rstrip(".")
    return s


def fiat_display_from_ada(ada_amount: float, ada_jpy: float, ada_usd: float, language: str) -> str:
    """
    ADA 金額とレートから、言語に応じた法定通貨表示文字列を返す。
      language="ja" → JPY（万/億/兆）
      その他       → USD（K/M/B）
    """
    try:
        ada_v = float(ada_amount)
    except (TypeError, ValueError):
        return ""
    if language == "ja":
        return format_jpy_short(ada_v * ada_jpy) if ada_jpy else ""
    return format_usd_short(ada_v * ada_usd) if ada_usd else ""
