"""
constitution_fetcher.py
最新 enacted NewConstitution GA の meta_url から憲法本文を取得する。

vote_meta_fetch.py の IPFS gateway フォールバック処理を再利用し、
ipfs:// 形式と https?:// 形式の両方に対応する。

公開関数:
    get_latest_constitution_meta_url() -> str | None
    fetch_constitution_text(meta_url=None) -> tuple[str | None, str | None]
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.vote_meta_fetch import _normalize_url_candidates
import requests

logger = logging.getLogger(__name__)


def get_latest_constitution_meta_url() -> str | None:
    """governance_actions から最新 enacted NewConstitution の meta_url を取得。
    enacted_epoch が最新のものを採用する。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT meta_url
            FROM governance_actions
            WHERE proposal_type = 'NewConstitution'
              AND enacted_epoch IS NOT NULL
              AND meta_url IS NOT NULL AND meta_url <> ''
            ORDER BY enacted_epoch DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    if not row:
        return None
    return str(row.get("meta_url") or "")


def _walk_for_text(node: Any, depth: int = 0) -> list[str]:
    """JSON ツリーを再帰的に走査して、まとまった本文として有用な文字列を集める。
    短い ID やラベル文字列を除外しつつ、長文（≥200 chars）を中心に拾う。
    """
    if depth > 6:
        return []
    out: list[str] = []
    if isinstance(node, str):
        s = node.strip()
        if len(s) >= 200:
            out.append(s)
        return out
    if isinstance(node, dict):
        # CIP-100 系の {"@value": "..."} を優先
        if "@value" in node and isinstance(node["@value"], str):
            v = node["@value"].strip()
            if len(v) >= 100:
                out.append(v)
        for v in node.values():
            out.extend(_walk_for_text(v, depth + 1))
        return out
    if isinstance(node, list):
        for item in node:
            out.extend(_walk_for_text(item, depth + 1))
        return out
    return out


def _extract_constitution_text(meta_json: dict | None) -> str:
    """憲法 JSON metadata から本文テキストを抽出する。
    まず CIP-108 の標準フィールド (body.title / abstract / motivation / rationale) を
    優先的に拾い、それでも短ければ JSON 全体から長い文字列ブロックを集める。
    """
    if not isinstance(meta_json, dict):
        return ""
    body = meta_json.get("body") or {}
    if not isinstance(body, dict):
        body = {}

    parts: list[str] = []

    def _val(node) -> str:
        if isinstance(node, dict) and "@value" in node:
            v = node.get("@value")
            return str(v).strip() if v is not None else ""
        if isinstance(node, str):
            return node.strip()
        return ""

    for key in ("title", "abstract", "motivation", "rationale"):
        v = _val(body.get(key))
        if v:
            parts.append(f"# {key.title()}\n{v}")

    # CIP-108 で本文が constitution / text フィールドに入るケース
    for key in ("constitution", "text", "content"):
        v = _val(body.get(key))
        if v:
            parts.append(v)

    text = "\n\n".join(parts).strip()

    # 標準フィールドだけでは短い場合（典型: 全体が summary しか持たない）、
    # JSON 全体から長文ブロックを集めて補完する
    if len(text) < 1000:
        long_blocks = _walk_for_text(meta_json)
        if long_blocks:
            text = (text + "\n\n" + "\n\n".join(long_blocks)).strip()

    return text


def fetch_constitution_text(
    meta_url: str | None = None,
    *,
    timeout: float = 20.0,
) -> tuple[str | None, str | None]:
    """憲法本文を取得する。

    meta_url が None の場合は DB から最新 enacted NewConstitution を引いてくる。
    IPFS 複数 gateway フォールバック対応。

    Returns:
        (本文テキスト, 採用した meta_url) のタプル。失敗時 (None, None)。
    """
    if not meta_url:
        meta_url = get_latest_constitution_meta_url()
    if not meta_url:
        logger.warning("No enacted NewConstitution found in governance_actions")
        return None, None

    candidates = _normalize_url_candidates(meta_url)
    if not candidates:
        logger.warning("Cannot normalize constitution meta_url: %s", meta_url)
        return None, meta_url

    for url in candidates:
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.debug("constitution meta %s: status=%s", url, resp.status_code)
                continue
            try:
                meta_json = resp.json()
            except ValueError:
                logger.debug("constitution meta %s: invalid JSON", url)
                continue
            text = _extract_constitution_text(meta_json)
            if text and len(text) >= 100:
                logger.info("constitution fetched: %d chars from %s", len(text), url)
                return text, meta_url
            logger.debug("constitution meta %s: extracted text too short (%d chars)",
                         url, len(text))
        except Exception as e:
            logger.debug("constitution meta %s: %s", url, e)
            continue

    logger.warning("Failed to fetch constitution from all gateways: %s", meta_url)
    return None, meta_url
