"""
vote_meta_fetch.py
投票メタデータ（CIP-100 / CIP-136）を meta_url から取得し、rationale / comment を抽出する。

meta_url は ipfs://... または https?://... 形式。ipfs:// の場合は複数の gateway でフォールバック取得する。
"""
from __future__ import annotations

import logging
import re
import requests

logger = logging.getLogger(__name__)


# 複数ゲートウェイを順に試す。最初に成功したものを使う。
IPFS_GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://dweb.link/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
]


def _extract_str(value) -> str:
    """CIP-100 系の {"@value": "..."} / 文字列の両対応。"""
    if isinstance(value, dict):
        return str(value.get("@value") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_url_candidates(meta_url: str) -> list[str]:
    """ipfs://CID や https?://... を取得候補 URL のリストに変換する。"""
    if not meta_url:
        return []
    meta_url = meta_url.strip()
    if meta_url.startswith("ipfs://"):
        cid_path = meta_url[len("ipfs://"):]
        return [gw + cid_path for gw in IPFS_GATEWAYS]
    if meta_url.startswith(("http://", "https://")):
        return [meta_url]
    return []


def fetch_vote_metadata_json(meta_url: str, timeout: float = 15.0) -> dict | None:
    """meta_url から JSON を取得して dict を返す。失敗時 None。"""
    for url in _normalize_url_candidates(meta_url):
        try:
            resp = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                logger.debug("meta_url %s: status=%s", url, resp.status_code)
                continue
            try:
                return resp.json()
            except ValueError:
                # JSON パース失敗 → 次のゲートウェイへ
                logger.debug("meta_url %s: invalid JSON", url)
                continue
        except Exception as e:
            logger.debug("meta_url %s: %s", url, e)
            continue
    return None


def extract_rationale(meta_json: dict | None) -> str:
    """
    CIP-100 投票メタデータから投票理由テキストを抽出する。
    CIP-100 では body.comment が正式な投票理由フィールド。
    CC / SPO が使う CIP-136 (Vote Rationale) は rationaleStatement / summary なので
    それも拾う。拾わないと CC・SPO の投票理由が常に空になる。
    """
    if not isinstance(meta_json, dict):
        return ""
    body = meta_json.get("body") or {}
    if not isinstance(body, dict):
        return ""
    for key in ("comment", "rationale", "reasoning", "rationaleStatement", "summary"):
        val = _extract_str(body.get(key))
        if val:
            return val
    return ""


def extract_author_name(meta_json: dict | None) -> str:
    """CIP-100 投票メタデータの authors[0].name を返す。

    CC メンバー / SPO は Koios に名前を持つエンドポイントが無く、投票メタデータの
    authors が唯一の実データ源。例: {"name": "Cardano Japan Council", "witness": {...}}
    """
    if not isinstance(meta_json, dict):
        return ""
    authors = meta_json.get("authors")
    if not isinstance(authors, list):
        return ""
    for a in authors:
        if isinstance(a, dict):
            name = _extract_str(a.get("name"))
        else:
            name = _extract_str(a)
        if name:
            return name[:255]
    return ""


# ============================================================
# 言語判定
# ============================================================

_JA_RE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")


def is_japanese(text: str, threshold: float = 0.1) -> bool:
    """text 中の日本語文字割合が threshold 以上なら True。"""
    if not text:
        return False
    ja = len(_JA_RE.findall(text))
    if ja == 0:
        return False
    return (ja / max(len(text), 1)) >= threshold
