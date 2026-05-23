"""drep_match.py
DRep マッチング診断 (/governance/drep の「マッチング診断」タブ) のバックエンド。

dreps.topic_profile_json (notify_worker --event drep_topic_profile_sync が
書き込む) と user の回答ベクトルから類似度を計算し TOP N の DRep を返す。

類似度: dimension ごとの絶対値差分の平均を 1 から引いた値（0〜1）。
        skip された dim (user 中立 / DRep データ無し) は計算対象から除外。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)

# notify_worker._DREP_TOPIC_KEYS と同期させる。"other" はマッチング対象外。
TOPIC_KEYS: tuple[str, ...] = (
    "core_dev", "research", "education", "community",
    "defi", "enterprise", "product", "governance",
)

# データ十分性のしきい値: Yes+No 票がこれ未満の DRep はマッチング対象外
MIN_VOTE_COUNT = 5

# bio として表示する最大文字数
_BIO_MAX_CHARS = 160

# CIP-119 references_json から表示する外部リンク最大件数
_LINKS_MAX = 6


def _classify_url(url: str) -> str:
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


def _format_links(refs_json: str | None) -> list[tuple[str, str]]:
    """CIP-119 references_json から [(icon, url), ...] を抽出（重複除去、http(s) のみ）。"""
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
        # 後段で "icon|url" の CSV エンコードを行うため、'|' や ',' を含む URL は除外
        if "|" in url or "," in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((_classify_url(url), url))
        if len(out) >= _LINKS_MAX:
            break
    return out


def _format_bio(objectives: str | None, motivations: str | None) -> str:
    """objectives → motivations の順で fallback し、改行を畳んで N 文字以内に切り詰める。"""
    raw = (objectives or motivations or "").strip()
    if not raw:
        return ""
    flat = " ".join(raw.split())
    if len(flat) <= _BIO_MAX_CHARS:
        return flat
    return flat[:_BIO_MAX_CHARS].rstrip() + "…"


def compute_match(
    user_vector: dict[str, float | None],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """user_vector に基づいて TOP N の DRep を返す。

    user_vector:
      {topic: 1.0 (積極的) | 0.0 (慎重) | None (中立 = 計算対象外)}

    戻り値（各 entry）:
      {
        drep_id, given_name, image_url, drep_status, registered, amount,
        similarity_pct: float (0〜100),
        match_dims: int,           # 比較に使った dimension 数
        top_yes_topics: [str],     # 0.7 以上の topic key (Yes 傾向)
        top_no_topics:  [str],     # 0.3 以下の topic key (No 傾向)
        topic_vote_count: int,     # この DRep の Yes+No 投票総数
      }
    """
    eval_dims = [t for t in TOPIC_KEYS if user_vector.get(t) is not None]
    if not eval_dims:
        return []

    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT drep_id, given_name, image_url, drep_status, registered,
                   amount, topic_profile_json, topic_vote_count,
                   objectives, motivations, references_json
              FROM dreps
             WHERE registered = 1
               AND topic_vote_count >= ?
               AND topic_profile_json IS NOT NULL
               AND topic_profile_json <> ''
            """,
            (int(MIN_VOTE_COUNT),),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    logger.info("compute_match: 候補 DRep %d 件 (eval_dims=%d)", len(rows), len(eval_dims))

    scored: list[dict[str, Any]] = []
    for r in rows:
        try:
            profile = json.loads(r.get("topic_profile_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(profile, dict):
            continue

        diffs: list[float] = []
        for t in eval_dims:
            if t not in profile:
                continue
            try:
                drep_v = float(profile[t])
            except (TypeError, ValueError):
                continue
            user_v = float(user_vector[t])
            diffs.append(abs(user_v - drep_v))

        if not diffs:
            continue

        mean_diff = sum(diffs) / len(diffs)
        similarity = 1.0 - mean_diff

        top_yes = sorted(
            [t for t in TOPIC_KEYS
             if t in profile and isinstance(profile[t], (int, float))
             and float(profile[t]) >= 0.7],
            key=lambda t: -float(profile[t]),
        )[:3]
        top_no = sorted(
            [t for t in TOPIC_KEYS
             if t in profile and isinstance(profile[t], (int, float))
             and float(profile[t]) <= 0.3],
            key=lambda t: float(profile[t]),
        )[:3]

        scored.append({
            "drep_id":          r["drep_id"],
            "given_name":       r.get("given_name") or "",
            "image_url":        r.get("image_url") or "",
            "drep_status":      r.get("drep_status") or "",
            "registered":       int(r.get("registered") or 0),
            "amount":           int(r.get("amount") or 0),
            "similarity_pct":   round(similarity * 100.0, 1),
            "match_dims":       len(diffs),
            "top_yes_topics":   top_yes,
            "top_no_topics":    top_no,
            "topic_vote_count": int(r.get("topic_vote_count") or 0),
            "bio":              _format_bio(r.get("objectives"), r.get("motivations")),
            "links":            _format_links(r.get("references_json")),
        })

    # 類似度降順 → 比較 dim 多 → 委任量降順 で安定ソート
    scored.sort(key=lambda d: (-d["similarity_pct"], -d["match_dims"], -d["amount"]))
    return scored[:max(1, int(limit))]
