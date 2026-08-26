"""
vote_meta_fetch.py
投票メタデータ（CIP-100 / CIP-136）を meta_url から取得し、rationale / comment を抽出する。

meta_url は ipfs://... または https?://... 形式。ipfs:// の場合は複数の gateway でフォールバック取得する。
"""
from __future__ import annotations

import logging
import re

from cardanoism.backend.safe_remote_fetch import (
    IPFS_GATEWAYS as _SAFE_IPFS_GATEWAYS,
    RemoteFetchError,
    fetch_remote_json,
    remote_url_candidates,
)

logger = logging.getLogger(__name__)

# 既存 import との互換用。実際の候補生成は safe_remote_fetch に集約する。
IPFS_GATEWAYS = list(_SAFE_IPFS_GATEWAYS)


def _extract_str(value) -> str:
    """CIP-100 系の {"@value": "..."} / 文字列の両対応。"""
    if isinstance(value, dict):
        return str(value.get("@value") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_url_candidates(meta_url: str) -> list[str]:
    """ipfs://CID や https?://... を取得候補 URL のリストに変換する。"""
    return remote_url_candidates(meta_url)


def fetch_vote_metadata_json(
    meta_url: str,
    timeout: float = 15.0,
    *,
    expected_hash: str | bytes | None = None,
) -> dict | None:
    """meta_url から JSON を取得して dict を返す。失敗時 None。"""
    try:
        parsed, _ = fetch_remote_json(
            meta_url,
            expected_hash=expected_hash,
            timeout=timeout,
        )
    except RemoteFetchError as exc:
        logger.warning("metadata fetch rejected/failed: %s", exc)
        return None
    if not isinstance(parsed, dict):
        logger.warning("metadata fetch returned non-object JSON")
        return None
    return parsed


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
