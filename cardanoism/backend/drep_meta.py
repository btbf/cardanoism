"""drep_meta.py
CIP-119 DRep メタデータ表示用ヘルパー。

旧 drep_match.py に同居していた表示ロジックを切り出して、
DRep 詳細ページ / DRep 委任コンパスの両方から再利用できるようにする。
"""
from __future__ import annotations

import json

# bio として表示する最大文字数
_BIO_MAX_CHARS = 160

# CIP-119 references_json から表示する外部リンク最大件数
_LINKS_MAX = 6


def classify_url(url: str) -> str:
    """URL から表示用アイコン名 (lucide tag) を返す。"""
    u = url.lower()
    if "twitter.com" in u or "://x.com" in u or "/x.com" in u or u.startswith("x.com"):
        return "twitter"
    if "github.com" in u:
        return "github"
    if "t.me/" in u or "telegram.me" in u:
        return "send"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "discord.gg" in u or "discord.com" in u:
        return "message-circle"
    if "linkedin.com" in u:
        return "linkedin"
    return "globe"


def format_links(refs_json: str | None) -> list[tuple[str, str]]:
    """CIP-119 references_json から [(icon, url), ...] を抽出（重複除去、http(s) のみ）。

    CSV エンコード安全性: '|' や ',' を含む URL は除外する。
    """
    if not refs_json:
        return []
    try:
        refs = json.loads(refs_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(refs, list):
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r in refs:
        if not isinstance(r, dict):
            continue
        url = (r.get("uri") or r.get("url") or "")
        url = str(url).strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        if "|" in url or "," in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((classify_url(url), url))
        if len(out) >= _LINKS_MAX:
            break
    return out


def format_bio(objectives: str | None, motivations: str | None) -> str:
    """objectives → motivations の順で fallback し、改行を畳んで N 文字以内に切り詰める。"""
    raw = (objectives or motivations or "").strip()
    if not raw:
        return ""
    flat = " ".join(raw.split())
    if len(flat) <= _BIO_MAX_CHARS:
        return flat
    return flat[:_BIO_MAX_CHARS].rstrip() + "…"
