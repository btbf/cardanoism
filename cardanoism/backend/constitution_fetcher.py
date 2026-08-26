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

import base64
import io
import json
import logging
import os
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.safe_remote_fetch import (
    RemoteFetchError,
    fetch_remote_document,
)

logger = logging.getLogger(__name__)


# Vision OCR のモデル / プロンプト
_VISION_MODEL = "gpt-5.4-mini"
_VISION_PROMPT = (
    "You are a precise document transcription tool. Convert this page image of "
    "the Cardano Constitution (or related governance document) into clean Markdown.\n\n"
    "Rules:\n"
    "- Preserve heading hierarchy: ## for top-level (e.g., 'Preamble', 'Article I'), "
    "### for sub-sections, #### for further levels.\n"
    "- Preserve bold (**text**) and italic (*text*) styling visible in the document.\n"
    "- Preserve numbered lists (1. 2. 3.) and bullet lists (- item).\n"
    "- Preserve paragraph breaks.\n"
    "- Skip page numbers, running headers, and footers.\n"
    "- Skip footnote markers; if footnotes contain meaningful text, place them at "
    "the end of the page output as a Markdown footnote section.\n"
    "- Preserve the original language verbatim. Do NOT translate.\n"
    "- Do NOT add any explanation or commentary.\n"
    "- Output ONLY the Markdown content. If the page is blank or only contains a "
    "page number, output an empty string.\n"
)


def get_latest_constitution_anchor() -> tuple[str | None, str | bytes | None]:
    """最新 enacted NewConstitution の文書 URL と対応する on-chain hash を返す。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT action_anchor_url, action_anchor_hash, meta_url, meta_hash
            FROM governance_actions
            WHERE proposal_type = 'NewConstitution'
              AND enacted_epoch IS NOT NULL
            ORDER BY enacted_epoch DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    if not row:
        return None, None
    action_url = str(row.get("action_anchor_url") or "").strip()
    if action_url:
        return action_url, row.get("action_anchor_hash")
    meta_url = str(row.get("meta_url") or "").strip()
    if meta_url:
        return meta_url, row.get("meta_hash")
    return None, None


def get_latest_constitution_meta_url() -> str | None:
    """最新 enacted NewConstitution の本文 URL を返す。

    優先順:
      1. action_anchor_url（実際の憲法本文ドキュメント）
      2. meta_url（提案メタデータ JSON、フォールバック）
    どちらもなければ None。
    """
    url, _ = get_latest_constitution_anchor()
    return url


# ─── Content-Type / フォーマット検出 ─────────────────────────────────────────

def _looks_like_pdf(content: bytes, content_type: str) -> bool:
    if "pdf" in (content_type or "").lower():
        return True
    return content[:5] == b"%PDF-"


def _extract_pdf_text_via_pymupdf(pdf_bytes: bytes) -> str:
    """PyMuPDF でプレーンテキスト抽出（Vision 失敗時のフォールバック）。"""
    try:
        import pymupdf  # type: ignore
    except ImportError:
        logger.warning("pymupdf が未インストール。`pip install pymupdf` を実行してください。")
        return ""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        chunks = [page.get_text() for page in doc]
        return "\n\n".join(c for c in chunks if c.strip()).strip()
    except Exception as e:
        logger.warning("pymupdf プレーンテキスト抽出失敗: %s", e)
        return ""


def _extract_pdf_text_via_vision(pdf_bytes: bytes, *, dpi_scale: float = 2.0) -> str:
    """OpenAI Vision (gpt-5.4-mini) で PDF を Markdown 化する。
    PyMuPDF で各ページを PNG にレンダリング → Vision に送って Markdown を返してもらう。
    1 ページずつ独立に処理し、全ページの結果を改行 2 つで結合。
    pymupdf 未インストール / API キー未設定時は空文字を返す（caller がフォールバック）。
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:
        logger.warning("pymupdf 未インストールのため Vision OCR をスキップ")
        return ""

    api_key = os.getenv("GPT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("GPT_API_KEY 未設定のため Vision OCR をスキップ")
        return ""

    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        logger.warning("openai SDK 未インストール")
        return ""

    client = OpenAI(api_key=api_key)

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.warning("pymupdf で PDF を開けませんでした: %s", e)
        return ""

    total = len(doc)
    logger.info("Vision OCR 開始: %d ページ", total)
    out_parts: list[str] = []
    mat = pymupdf.Matrix(dpi_scale, dpi_scale)

    for page_num in range(total):
        try:
            page = doc[page_num]
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            b64 = base64.standard_b64encode(img_bytes).decode("ascii")
            response = client.chat.completions.create(
                model=_VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }],
                max_completion_tokens=4096,
            )
            page_md = (response.choices[0].message.content or "").strip()
            if page_md:
                out_parts.append(page_md)
            logger.info("  Vision OCR: page %d/%d done (%d chars)",
                        page_num + 1, total, len(page_md))
        except Exception as e:
            logger.warning("  Vision OCR page %d/%d failed: %s", page_num + 1, total, e)
            continue

    result = "\n\n".join(out_parts).strip()
    logger.info("Vision OCR 完了: total %d chars", len(result))
    return result


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

def _download(
    url: str,
    timeout: float,
    expected_hash: str | bytes | None = None,
) -> tuple[bytes | None, str]:
    """IPFS gateway フォールバック付きダウンロード。
    Returns: (bytes, content_type) または (None, "")。
    """
    try:
        document = fetch_remote_document(
            url,
            expected_hash=expected_hash,
            timeout=timeout,
            max_bytes=20 * 1024 * 1024,
        )
    except RemoteFetchError as exc:
        logger.warning("constitution download rejected/failed: %s", exc)
        return None, ""
    return document.content, document.content_type


def _extract_text(content: bytes, content_type: str) -> str:
    """ダウンロードした bytes からテキストを抽出。
    PDF / JSON / Markdown / プレーンテキスト に対応。
    PDF は OpenAI Vision で Markdown 化（見出し・太字を保持）。失敗時は
    pymupdf プレーンテキストにフォールバック。
    """
    if _looks_like_pdf(content, content_type):
        text = _extract_pdf_text_via_vision(content)
        if text:
            return text
        logger.info("Vision OCR が空。pymupdf プレーンテキストにフォールバック")
        return _extract_pdf_text_via_pymupdf(content)

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
    expected_hash: str | bytes | None = None,
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
        meta_url, expected_hash = get_latest_constitution_anchor()
    if not meta_url:
        logger.warning("No enacted NewConstitution found in governance_actions")
        return None, None

    content, content_type = _download(meta_url, timeout, expected_hash)
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
