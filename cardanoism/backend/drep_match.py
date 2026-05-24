"""drep_match.py
DRep マッチング診断 (/governance/drep の「マッチング診断」タブ) のバックエンド。

5 軸派閥モデル:
  A. axis_treasury  : "discipline" (+) ⟷ "investment" (-)
  B. axis_protocol  : "conservative" (+) ⟷ "progressive" (-)
  C. axis_org       : "centralized" (+) ⟷ "decentralized" (-)
  D. axis_ecosystem : "technical" (+) ⟷ "expansion" (-)
  E. axis_marketing : "promotion" (+) ⟷ "restraint" (-)

dreps.axis_profile_json (notify_worker --event drep_axis_profile_sync が
書き込む) と user の軸スコアベクトル (-1.0 〜 +1.0) から類似度を計算し
TOP N の DRep を返す。

類似度: axis ごとの絶対値差分 |user - drep| を 0〜2 から 0〜1 に正規化した
        平均を 1 から引いた値 (0〜1)。skip された軸 (user None / DRep データ無し)
        は計算対象から除外。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)

# notify_worker._DREP_AXIS_DIRECTIONS と同期させる。
# (positive_faction, negative_faction) — +1.0 / -1.0 方向に対応。
AXIS_DIRECTIONS: dict[str, tuple[str, str]] = {
    "axis_treasury":  ("discipline", "investment"),
    "axis_protocol":  ("conservative", "progressive"),
    "axis_org":       ("centralized", "decentralized"),
    "axis_ecosystem": ("technical", "expansion"),
    "axis_marketing": ("promotion", "restraint"),
}
AXIS_KEYS: tuple[str, ...] = tuple(AXIS_DIRECTIONS.keys())

# データ十分性のしきい値: 軸タグ付き GA への Yes+No 票がこれ未満の DRep は
# マッチング対象外
MIN_VOTE_COUNT = 5

# bio として表示する最大文字数
_BIO_MAX_CHARS = 160

# CIP-119 references_json から表示する外部リンク最大件数
_LINKS_MAX = 6

# 派閥スコア絶対値がこれ以上のとき、結果カードに派閥バッジを出す
_FACTION_DISPLAY_THRESHOLD = 0.3


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


def _faction_label_for(axis_key: str, score: float) -> tuple[str, str]:
    """軸スコアから (派閥ラベルキー, 強度カテゴリ "strong"/"mid") を返す。

    返すラベルキーは i18n の `drep_match_faction_<axis>_<pos|neg>` 形式。
    呼び出し側で AuthState.t[key] と組み合わせて表示する。
    """
    pos, neg = AXIS_DIRECTIONS[axis_key]
    direction = "pos" if score >= 0 else "neg"
    label_key = f"drep_match_faction_{axis_key}_{direction}"
    strength = "strong" if abs(score) >= 0.6 else "mid"
    return label_key, strength


def compute_match(
    user_vector: dict[str, float | None],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """user_vector に基づいて TOP N の DRep を返す。

    user_vector:
      {axis_key: score in [-1.0, +1.0] | None (未回答 / 中立 → 計算対象外)}
      例: {"axis_treasury": 0.5, "axis_org": -1.0, "axis_marketing": None}

    戻り値（各 entry）:
      {
        drep_id, given_name, image_url, drep_status, registered, amount,
        similarity_pct: float (0〜100),
        match_dims: int,                    # 比較に使った軸数
        faction_chips: list[(label_key, score_str, strength)],
                                            # 結果カードに出す派閥バッジ
        axis_vote_count: int,               # DRep の axis 関連 Yes+No 投票数
        bio, links,
      }
    """
    eval_axes = [a for a in AXIS_KEYS if user_vector.get(a) is not None]
    if not eval_axes:
        return []

    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT drep_id, given_name, image_url, drep_status, registered,
                   amount, axis_profile_json, axis_vote_count,
                   objectives, motivations, references_json
              FROM dreps
             WHERE registered = 1
               AND axis_vote_count >= ?
               AND axis_profile_json IS NOT NULL
               AND axis_profile_json <> ''
            """,
            (int(MIN_VOTE_COUNT),),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    logger.info("compute_match: 候補 DRep %d 件 (eval_axes=%d)", len(rows), len(eval_axes))

    scored: list[dict[str, Any]] = []
    for r in rows:
        try:
            profile = json.loads(r.get("axis_profile_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(profile, dict):
            continue

        # 軸ごとに |user - drep| を 0〜2 から 0〜1 に正規化
        diffs: list[float] = []
        for axis in eval_axes:
            if axis not in profile:
                continue
            try:
                drep_v = float(profile[axis])
            except (TypeError, ValueError):
                continue
            user_v = float(user_vector[axis])
            diff = abs(user_v - drep_v) / 2.0  # 範囲 [-1,+1] の差は最大 2 → /2 で正規化
            diffs.append(min(1.0, diff))

        if not diffs:
            continue

        mean_diff = sum(diffs) / len(diffs)
        similarity = 1.0 - mean_diff

        # 派閥バッジ: |score| >= threshold の軸を強度降順で最大 5 件
        faction_chips: list[tuple[str, str, str]] = []
        for axis_key, score_v in profile.items():
            try:
                s = float(score_v)
            except (TypeError, ValueError):
                continue
            if abs(s) < _FACTION_DISPLAY_THRESHOLD:
                continue
            if axis_key not in AXIS_DIRECTIONS:
                continue
            label_key, strength = _faction_label_for(axis_key, s)
            sign = "+" if s >= 0 else ""
            faction_chips.append((label_key, f"{sign}{s:.2f}", strength))
        faction_chips.sort(key=lambda t: -abs(float(t[1])))
        faction_chips = faction_chips[:5]

        scored.append({
            "drep_id":          r["drep_id"],
            "given_name":       r.get("given_name") or "",
            "image_url":        r.get("image_url") or "",
            "drep_status":      r.get("drep_status") or "",
            "registered":       int(r.get("registered") or 0),
            "amount":           int(r.get("amount") or 0),
            "similarity_pct":   round(similarity * 100.0, 1),
            "match_dims":       len(diffs),
            "faction_chips":    faction_chips,
            "axis_vote_count":  int(r.get("axis_vote_count") or 0),
            "bio":              _format_bio(r.get("objectives"), r.get("motivations")),
            "links":            _format_links(r.get("references_json")),
        })

    # 類似度降順 → 比較 axis 多 → 委任量降順 で安定ソート
    scored.sort(key=lambda d: (-d["similarity_pct"], -d["match_dims"], -d["amount"]))
    return scored[:max(1, int(limit))]
