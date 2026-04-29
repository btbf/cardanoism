"""
constitution_fetcher.py
最新 enacted NewConstitution の **本文ドキュメント** を取得する。

Cardano の NewConstitution 提案では:
- governance_actions.meta_url   = 提案メタデータ JSON (CIP-108、提案の説明文)
- governance_actions.action_anchor_url = 実際の憲法本文ドキュメント (PDF/Markdown 等)

action_anchor_url の方が正解なので、まずそちらを試す。
未取得の場合のフォールバックとして:
  (1) meta_url JSON の body.references[] から "Constitution" 系のラベルを探す
  (2) meta_url JSON の本文フィールド (title/abstract/motivation/rationale) を結合

PDF 検出時は pypdf でテキスト抽出する（pypdf 未インストールなら諦める）。

公開関数:
    get_latest_constitution_meta_url() -> str | None
        最新の enacted NewConstitution の "anchor URL"（無ければ meta_url）を返す。
    fetch_constitution_text(meta_url=None) -> tuple[str | None, str | None]
        本文テキストと使用 URL のタプル。
"""
from __future__ import annotations

import io
import json
import logging
from typing import Any

import requests

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.vote_meta_fetch import _normalize_url_candidates

logger = logging.getLogger(__name__)


def get_latest_constitution_meta_url() -> str | None:
    """最新 enacted NewConstitution の本文 URL を返す。

    優先順:
      1. action_anchor_url（実際の憲法本文ドキュメント）
      2. meta_url（提案メタデータ JSON、フォールバック）
    どちらもなければ None。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT action_anchor_url, meta_url
            FROM governance_actions
            WHERE proposal_type = 'NewConstitution'
              AND enacted_epoch IS NOT NULL
            ORDER BY enacted_epoch DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    if not row:
        return None
    url = (row.get("action_anchor_url") or row.get("meta_url") or "").strip()
    return url or None


# ─── Content-Type / フォーマット検出 ─────────────────────────────────────────

def _looks_like_pdf(content: bytes, content_type: str) -> bool:
    if "pdf" in (content_type or "").lower():
        return True
    return content[:5] == b"%PDF-"


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """pypdf で PDF からテキスト抽出。失敗時は空文字。"""
    try:
        import pypdf  # type: ignore
    except ImportError:
        logger.warning("pypdf が未インストールのため PDF 本文を抽出できません。"
                       "`pip install pypdf` を実行してください。")
        return ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        chunks: list[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception as e:
                logger.debug("pypdf page.extract_text 失敗: %s", e)
                t = ""
            if t.strip():
                chunks.append(t)
        return "\n\n".join(chunks).strip()
    except Exception as e:
        logger.warning("pypdf による PDF 解析失敗: %s", e)
        return ""


# ─── JSON 内本文抽出（フォールバック用） ──────────────────────────────────────

def _walk_for_text(node: Any, depth: int = 0) -> list[str]:
    """JSON ツリーを再帰的に走査して長文ブロックを集める。"""
    if depth > 6:
        return []
    out: list[str] = []
    if isinstance(node, str):
        s = node.strip()
        if len(s) >= 200:
            out.append(s)
        return out
    if isinstance(node, dict):
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


def _val(node) -> str:
    if isinstance(node, dict) and "@value" in node:
        v = node.get("@value")
        return str(v).strip() if v is not None else ""
    if isinstance(node, str):
        return node.strip()
    return ""


def _extract_constitution_text_from_json(meta_json: dict | None) -> str:
    """JSON metadata の本文フィールドを連結する（最終フォールバック）。"""
    if not isinstance(meta_json, dict):
        return ""
    body = meta_json.get("body") or {}
    if not isinstance(body, dict):
        body = {}

    parts: list[str] = []
    for key in ("title", "abstract", "motivation", "rationale"):
        v = _val(body.get(key))
        if v:
            parts.append(f"# {key.title()}\n{v}")
    for key in ("constitution", "text", "content"):
        v = _val(body.get(key))
        if v:
            parts.append(v)

    text = "\n\n".join(parts).strip()
    if len(text) < 1000:
        long_blocks = _walk_for_text(meta_json)
        if long_blocks:
            text = (text + "\n\n" + "\n\n".join(long_blocks)).strip()
    return text


def _find_constitution_url_in_meta(meta_json: dict | None) -> str | None:
    """meta_json の body.references[] から憲法らしき URL を探す。"""
    if not isinstance(meta_json, dict):
        return None
    body = meta_json.get("body") or {}
    refs = body.get("references") or []
    if not isinstance(refs, list):
        return None
    for r in refs:
        if not isinstance(r, dict):
            continue
        label = str(r.get("label") or r.get("@type") or "").lower()
        uri = r.get("uri") or r.get("url")
        if uri and ("constitution" in label or "憲法" in label):
            return str(uri)
    return None


# ─── ダウンロード本体 ────────────────────────────────────────────────────────

def _download(url: str, timeout: float) -> tuple[bytes | None, str]:
    """IPFS gateway フォールバック付きダウンロード。
    Returns: (bytes, content_type) または (None, "")。
    """
    candidates = _normalize_url_candidates(url) or [url]
    for u in candidates:
        try:
            resp = requests.get(u, timeout=timeout)
            if resp.status_code != 200:
                logger.debug("constitution download %s: status=%s", u, resp.status_code)
                continue
            return resp.content, (resp.headers.get("Content-Type") or "")
        except Exception as e:
            logger.debug("constitution download %s: %s", u, e)
            continue
    return None, ""


def _extract_text(content: bytes, content_type: str) -> str:
    """ダウンロードした bytes からテキストを抽出。
    PDF / JSON / Markdown / プレーンテキスト に対応。
    """
    if _looks_like_pdf(content, content_type):
        return _extract_pdf_text(content)

    # JSON の場合
    if "json" in (content_type or "").lower() or content[:1] == b"{":
        try:
            obj = json.loads(content.decode("utf-8", errors="ignore"))
            text = _extract_constitution_text_from_json(obj)
            if text:
                return text
        except Exception:
            pass

    # Markdown / プレーンテキストとして decode
    try:
        return content.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


# ─── 公開関数 ────────────────────────────────────────────────────────────────

def fetch_constitution_text(
    meta_url: str | None = None,
    *,
    timeout: float = 30.0,
) -> tuple[str | None, str | None]:
    """憲法本文を取得する。

    meta_url が None の場合は DB から最新 enacted NewConstitution の URL を引いてくる
    （action_anchor_url を優先、無ければ meta_url）。

    URL の中身が PDF / JSON / Markdown / テキストでも適切にテキスト抽出する。
    JSON で本文が見つからない場合は body.references[] から憲法 URL を 1 段辿る。

    Returns:
        (本文テキスト, 採用した URL) のタプル。失敗時 (None, None)。
    """
    if not meta_url:
        meta_url = get_latest_constitution_meta_url()
    if not meta_url:
        logger.warning("No enacted NewConstitution found in governance_actions")
        return None, None

    content, content_type = _download(meta_url, timeout)
    if content is None:
        logger.warning("constitution: 全 gateway で取得失敗 url=%s", meta_url)
        return None, meta_url

    text = _extract_text(content, content_type)

    # JSON で本文が空 or 短すぎ → references[] から憲法 URL を辿る
    if (len(text) < 1000) and ("json" in (content_type or "").lower() or content[:1] == b"{"):
        try:
            obj = json.loads(content.decode("utf-8", errors="ignore"))
        except Exception:
            obj = None
        nested_url = _find_constitution_url_in_meta(obj)
        if nested_url:
            logger.info("constitution: JSON 内 references から本文 URL を発見: %s", nested_url)
            content2, ct2 = _download(nested_url, timeout)
            if content2 is not None:
                text2 = _extract_text(content2, ct2)
                if len(text2) > len(text):
                    return text2, nested_url

    if text and len(text) >= 100:
        logger.info("constitution fetched: %d chars from %s", len(text), meta_url)
        return text, meta_url

    logger.warning("constitution: 本文抽出に失敗 (extracted_chars=%d) url=%s",
                   len(text), meta_url)
    return None, meta_url
