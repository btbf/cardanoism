"""
governance.py
ガバナンスアクションのフェッチ・翻訳・DB保存

Koios /proposal_list を全件取得 → governance_actions テーブルに upsert →
未翻訳レコードを OpenAI で日本語訳 → DB 更新

使い方:
  python governance.py                      # フェッチ + 未翻訳を翻訳
  python governance.py --no-translate       # フェッチのみ（翻訳スキップ）
  python governance.py --force              # 翻訳済みでも再翻訳
  python governance.py --limit 30           # 1回の翻訳上限件数
  python governance.py --workers 3          # 翻訳並列数
  python governance.py --sleep 0.5          # リクエスト間スリープ（秒）
  python governance.py --id TX_HASH         # 特定レコードのみ翻訳
  python governance.py --retry-metadata     # Ogmios後のメタデータ取得失敗分だけ再試行

環境変数:
  KOIOS_NETWORK   : mainnet (デフォルト) / preprod / preview
  GPT_API_KEY     : OpenAI API キー
  OPENAI_MODEL    : 使用モデル（デフォルト: gpt-4o-mini）
"""
import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
# シークレットは Infisical CLI で注入。.env は fallback (Infisical 値を上書きしない)。
load_dotenv(PROJECT_ROOT / "cardanoism" / ".env", override=False)

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.koios import get_proposal_list
from cardanoism.backend.sync_lock import SyncLockError, sync_job_lock
from cardanoism.translate import TranslateConfig, Translator

logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_TERMS_DIR = Path(__file__).resolve().parent.parent / "translate" / "terms"


# ============================================================
# 翻訳エンジン
# ============================================================

def build_translator() -> Translator:
    """OpenAI クライアントを使った Translator を初期化する。"""
    from openai import OpenAI, OpenAIError  # noqa: PLC0415

    config = TranslateConfig(
        keep_terms_path=_TERMS_DIR / "keep_terms.yaml",
        guidance_terms_path=_TERMS_DIR / "guidance_terms.yaml",
        title_terms_path=_TERMS_DIR / "title_terms.yaml",
    )
    client = OpenAI(api_key=os.getenv("GPT_API_KEY"))
    cache: dict[tuple, str] = {}
    cache_lock = Lock()

    def llm_translate(system_prompt: str, text: str) -> str:
        key = (system_prompt, text)
        with cache_lock:
            cached = cache.get(key)
        if cached is not None:
            return cached
        logger.debug("OpenAI リクエスト: model=%s chars=%d", OPENAI_MODEL, len(text))
        try:
            response = client.responses.create(
                model=OPENAI_MODEL,
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {"role": "user",   "content": [{"type": "input_text", "text": text}]},
                ],
            )
        except OpenAIError as exc:
            raise RuntimeError(f"OpenAI リクエスト失敗: {exc}") from exc
        translated = response.output_text.strip()
        with cache_lock:
            cache[key] = translated
        return translated

    return Translator(config, llm_translate)


# ============================================================
# Koios フェッチ
# ============================================================

def fetch_all_proposals() -> list[dict] | None:
    """Koios /proposal_list を全件取得する。失敗時は部分結果を返さない。"""
    return get_proposal_list()


# ============================================================
# データ変換
# ============================================================

def _parse_block_time(block_time) -> str | None:
    """Unix タイムスタンプ（整数）を DATETIME 文字列（UTC）に変換する。"""
    if block_time is None:
        return None
    try:
        return datetime.fromtimestamp(int(block_time), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return None


def _extract_action_anchor(item: dict, body: dict) -> tuple[str | None, str | None]:
    """Koios レスポンスから「action の anchor URL」を抽出する。

    NewConstitution 提案で、実際の憲法本文ドキュメントの URL を取り出す。
    Koios のバージョンや tag によって構造が変わるため、複数の経路を順に試す:
      1. item["proposed_action"]["contents"][*]["anchor"]["url"]
      2. item["anchor"]["url"] (フラット形式)
      3. meta_json.body.references[] でラベルが "Constitution" 系のもの
    Returns: (url, hash) どちらか欠ければ None。
    """
    proposal_type = (item.get("proposal_type") or "").strip()

    # (1) proposed_action.contents[*].anchor を探す
    pa = item.get("proposed_action") or {}
    if isinstance(pa, dict):
        contents = pa.get("contents")
        if isinstance(contents, list):
            for c in contents:
                if isinstance(c, dict):
                    anchor = c.get("anchor")
                    if isinstance(anchor, dict) and anchor.get("url"):
                        return (
                            str(anchor.get("url") or "") or None,
                            str(anchor.get("dataHash") or anchor.get("data_hash") or "") or None,
                        )

    # (2) item.anchor (フラット形式)
    anchor = item.get("anchor")
    if isinstance(anchor, dict) and anchor.get("url"):
        return (
            str(anchor.get("url") or "") or None,
            str(anchor.get("dataHash") or anchor.get("data_hash") or "") or None,
        )

    # (3) NewConstitution の場合は meta_json.body.references[] から
    #     "constitution" を含むラベルや type を持つエントリの URI を採用
    if proposal_type == "NewConstitution":
        refs = body.get("references") or []
        if isinstance(refs, list):
            for r in refs:
                if not isinstance(r, dict):
                    continue
                label = str(r.get("label") or r.get("@type") or "").lower()
                uri = r.get("uri") or r.get("url")
                if uri and ("constitution" in label or "憲法" in label):
                    return (str(uri), None)

    return (None, None)


def _extract_fields(item: dict) -> dict:
    """Koios レスポンスの1件を DB カラムに対応するフィールド辞書に変換する。"""
    from cardanoism.backend.spo_targets import compute_spo_target

    meta = item.get("meta_json") or {}
    body = meta.get("body") or {}
    refs = body.get("references") or []

    # CIP-100/108: authors は meta_json 直下。1 GA に複数いることがあるので name を配列で持つ。
    authors = meta.get("authors")
    author_names = None
    if isinstance(authors, list):
        names = [
            str(a.get("name")).strip()
            for a in authors
            if isinstance(a, dict) and a.get("name")
        ]
        if names:
            author_names = json.dumps(names, ensure_ascii=False)

    deposit = item.get("deposit")
    meta_is_valid = item.get("meta_is_valid")
    action_anchor_url, action_anchor_hash = _extract_action_anchor(item, body)
    spo_target = compute_spo_target(
        item.get("proposal_type") or "",
        item.get("proposed_action"),
    )

    # TreasuryWithdrawals の引き出し配列（[{amount, stake_address}, ...]）を集計
    withdrawal = item.get("withdrawal")
    withdrawal_total = None
    withdrawal_json = None
    if isinstance(withdrawal, list) and withdrawal:
        total = 0
        for w in withdrawal:
            try:
                total += int(w.get("amount") or 0)
            except (TypeError, ValueError):
                continue
        withdrawal_total = total
        withdrawal_json = json.dumps(withdrawal, ensure_ascii=False)

    return {
        "proposal_id":      item.get("proposal_id") or "",
        "proposal_tx_hash": item.get("proposal_tx_hash") or "",
        "proposal_index":   int(item.get("proposal_index") or 0),
        "proposal_type":    item.get("proposal_type") or "",
        "deposit":          int(deposit) if deposit is not None else None,
        "withdrawal_total_lovelace": withdrawal_total,
        "withdrawal_json":  withdrawal_json,
        "return_address":   item.get("return_address"),
        "proposed_epoch":   item.get("proposed_epoch"),
        "ratified_epoch":   item.get("ratified_epoch"),
        "enacted_epoch":    item.get("enacted_epoch"),
        "dropped_epoch":    item.get("dropped_epoch"),
        "expired_epoch":    item.get("expired_epoch"),
        "expiration":       item.get("expiration"),
        "block_time":       _parse_block_time(item.get("block_time")),
        "meta_url":         item.get("meta_url"),
        "meta_hash":        item.get("meta_hash"),
        "meta_is_valid":    int(meta_is_valid) if meta_is_valid is not None else None,
        "title":            body.get("title") or None,
        "abstract":         body.get("abstract") or None,
        "motivation":       body.get("motivation") or None,
        "rationale":        body.get("rationale") or None,
        "references_json":  json.dumps(refs, ensure_ascii=False) if refs else None,
        "authors_json":     author_names,
        "action_anchor_url":  action_anchor_url,
        "action_anchor_hash": action_anchor_hash,
        "spo_target":         spo_target,
    }


# ============================================================
# DB 操作
# ============================================================

def upsert_proposal(fields: dict) -> bool:
    """
    1件を governance_actions に upsert する。
    ON DUPLICATE KEY UPDATE で既存レコードのステータスを更新するが、
    翻訳済みの *_ja カラムは上書きしない（翻訳ロジックが管理する）。

    Returns:
        新規挿入された場合 True / 既存行が更新された場合 False。
        呼び出し元はこの戻り値を見て新規 GA のみ AI 分析キューに enqueue する。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            "SELECT 1 FROM governance_actions WHERE proposal_id = ? LIMIT 1",
            (fields["proposal_id"],),
        )
        existed = cursor.fetchone() is not None
        cursor.execute(
            """
            INSERT INTO governance_actions (
                proposal_id, proposal_tx_hash, proposal_index, proposal_type,
                deposit, withdrawal_total_lovelace, withdrawal_json, return_address,
                proposed_epoch, ratified_epoch, enacted_epoch,
                dropped_epoch, expired_epoch, expiration,
                block_time, meta_url, meta_hash, meta_is_valid,
                title, `abstract`, motivation, rationale, references_json,
                authors_json,
                action_anchor_url, action_anchor_hash,
                last_event_slot,
                spo_target
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?,
                ?, ?,
                ?,
                ?
            )
            ON DUPLICATE KEY UPDATE
                -- 全体方針: Koios 由来の値で上書きするが、Koios が NULL を返した場合は
                -- 既存値 (listener / 過去 Koios sync が書いた値) を保持するため COALESCE。
                -- 翻訳済み *_ja カラムだけは Koios sync では絶対に触らない (翻訳ロジック管理)。

                -- 不変フィールド (一度確定したら変わらない、Koios が正解)
                proposal_type             = COALESCE(VALUES(proposal_type),     proposal_type),
                deposit                   = COALESCE(VALUES(deposit),           deposit),
                return_address            = COALESCE(VALUES(return_address),    return_address),
                expiration                = COALESCE(VALUES(expiration),        expiration),
                block_time                = COALESCE(VALUES(block_time),        block_time),

                -- proposed_epoch は Koios が正解 (listener の slot 由来計算は Byron 遷移を考慮しても
                -- 補正のずれが出るため Koios の値で上書きする)
                proposed_epoch            = COALESCE(VALUES(proposed_epoch),    proposed_epoch),

                -- ステータスエポック (Koios が状態遷移を確定的に持つ)
                ratified_epoch            = VALUES(ratified_epoch),
                enacted_epoch             = VALUES(enacted_epoch),
                dropped_epoch             = VALUES(dropped_epoch),
                expired_epoch             = VALUES(expired_epoch),

                -- IPFS メタ情報 (Koios が meta_url から resolved 済みなので Koios が正解)
                meta_url                  = COALESCE(VALUES(meta_url),          meta_url),
                meta_hash                 = COALESCE(VALUES(meta_hash),         meta_hash),
                meta_is_valid             = COALESCE(VALUES(meta_is_valid),     meta_is_valid),

                -- 本文系 (listener bg task が IPFS から書く / Koios も meta_json で取得)
                -- どちらの経路でも同じソースなので Koios 値で上書き OK。NULL なら既存維持。
                title                     = COALESCE(VALUES(title),             title),
                `abstract`                = COALESCE(VALUES(`abstract`),        `abstract`),
                motivation                = COALESCE(VALUES(motivation),        motivation),
                rationale                 = COALESCE(VALUES(rationale),         rationale),
                references_json           = COALESCE(VALUES(references_json),   references_json),

                -- 引き出し情報 / authors / action anchor
                withdrawal_total_lovelace = VALUES(withdrawal_total_lovelace),
                withdrawal_json           = VALUES(withdrawal_json),
                authors_json              = VALUES(authors_json),
                action_anchor_url         = VALUES(action_anchor_url),
                action_anchor_hash        = VALUES(action_anchor_hash),

                -- last_event_slot は listener が書いた値を保持 (Koios 由来 NULL で上書きしない)
                last_event_slot           = COALESCE(VALUES(last_event_slot), last_event_slot),
                -- spo_target も同様。listener が確定値を持つので上書き優先 (NULL なら既存維持)
                spo_target                = COALESCE(VALUES(spo_target), spo_target),
                updated_at                = NOW()
            """,
            (
                fields["proposal_id"],     fields["proposal_tx_hash"], fields["proposal_index"],
                fields["proposal_type"],
                fields["deposit"],         fields["withdrawal_total_lovelace"],
                fields["withdrawal_json"], fields["return_address"],
                fields["proposed_epoch"],  fields["ratified_epoch"],   fields["enacted_epoch"],
                fields["dropped_epoch"],   fields["expired_epoch"],    fields["expiration"],
                fields["block_time"],      fields["meta_url"],         fields["meta_hash"],
                fields["meta_is_valid"],
                fields["title"],           fields["abstract"],
                fields["motivation"],      fields["rationale"],        fields["references_json"],
                fields.get("authors_json"),
                fields.get("action_anchor_url"), fields.get("action_anchor_hash"),
                fields.get("last_event_slot"),
                fields.get("spo_target"),
            ),
        )
        conn.commit()
    return not existed


# ============================================================
# Ogmios 提案メタデータの取得・再試行
# ============================================================

_META_RETRY_LIMIT = 8
_META_RETRY_BASE_MINUTES = 15
_META_RETRY_MAX_MINUTES = 24 * 60


@dataclass(frozen=True)
class ProposalMetadataFetchResult:
    """提案メタデータ1件の取得結果。``row`` は翻訳ターゲット形式。"""

    row: dict | None
    fetched: bool


def _metadata_retry_delay_minutes(attempt: int) -> int:
    """失敗回数に応じた指数バックオフ（15分〜24時間）を返す。"""
    exponent = max(0, int(attempt) - 1)
    return min(
        _META_RETRY_BASE_MINUTES * (2 ** exponent),
        _META_RETRY_MAX_MINUTES,
    )


def _proposal_translation_row(cursor, proposal_id: str) -> dict | None:
    cursor.execute(
        "SELECT id, proposal_id, proposal_tx_hash, title, `abstract`, motivation, rationale, "
        "title_ja, abstract_ja, motivation_ja, rationale_ja "
        "FROM governance_actions WHERE proposal_id = ? LIMIT 1",
        (proposal_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def fetch_and_save_proposal_metadata(
    proposal_id: str,
    meta_url: str | None,
    meta_hash: str | bytes | None = None,
) -> ProposalMetadataFetchResult:
    """CIP-100/108 メタデータを取得し、本文と再試行状態を保存する。

    Ogmios listener から新規提案時に即時実行し、失敗した場合は
    ``meta_fetch_next_at`` を指数バックオフで設定する。HTTP/IPFS から JSON
    オブジェクトを取得できた時点を成功とし、任意フィールドが欠けた文書を
    無期限に再取得し続けない。
    """
    if not meta_url:
        with get_db() as (cursor, _):
            return ProposalMetadataFetchResult(
                row=_proposal_translation_row(cursor, proposal_id),
                fetched=False,
            )

    from cardanoism.backend.vote_meta_fetch import fetch_vote_metadata_json, _extract_str

    meta: dict | None = None
    fetch_error: str | None = None
    try:
        candidate = fetch_vote_metadata_json(meta_url, expected_hash=meta_hash)
        if isinstance(candidate, dict) and isinstance(candidate.get("body"), dict):
            meta = candidate
        else:
            fetch_error = "metadata fetch returned no valid JSON body"
    except Exception as exc:  # noqa: BLE001
        fetch_error = f"{type(exc).__name__}: {exc}"

    title = abstract = motivation = rationale = None
    references_json = authors_json = None
    if meta is not None:
        body = meta.get("body") or {}
        if isinstance(body, dict):
            title = _extract_str(body.get("title")) or None
            abstract = _extract_str(body.get("abstract")) or None
            motivation = _extract_str(body.get("motivation")) or None
            rationale = _extract_str(body.get("rationale")) or None
            references = body.get("references")
            if isinstance(references, list) and references:
                references_json = json.dumps(references, ensure_ascii=False)

        authors = meta.get("authors")
        if isinstance(authors, list):
            names = [
                _extract_str(author.get("name"))
                for author in authors
                if isinstance(author, dict)
            ]
            names = [name for name in names if name]
            if names:
                authors_json = json.dumps(names, ensure_ascii=False)

    with get_db() as (cursor, conn):
        cursor.execute(
            "SELECT meta_fetch_attempts FROM governance_actions "
            "WHERE proposal_id = ? LIMIT 1 FOR UPDATE",
            (proposal_id,),
        )
        state = cursor.fetchone()
        if not state:
            conn.commit()
            return ProposalMetadataFetchResult(row=None, fetched=meta is not None)

        attempts = int(state.get("meta_fetch_attempts") or 0) + 1
        if meta is not None:
            cursor.execute(
                """
                UPDATE governance_actions
                   SET title             = COALESCE(?, title),
                       `abstract`        = COALESCE(?, `abstract`),
                       motivation        = COALESCE(?, motivation),
                       rationale         = COALESCE(?, rationale),
                       references_json   = COALESCE(?, references_json),
                       authors_json      = COALESCE(?, authors_json),
                       meta_fetch_attempts = ?,
                       meta_fetch_next_at  = NULL,
                       meta_fetched_at     = NOW(),
                       meta_fetch_error    = NULL,
                       updated_at          = NOW()
                 WHERE proposal_id = ?
                """,
                (
                    title,
                    abstract,
                    motivation,
                    rationale,
                    references_json,
                    authors_json,
                    attempts,
                    proposal_id,
                ),
            )
        else:
            next_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                minutes=_metadata_retry_delay_minutes(attempts)
            )
            cursor.execute(
                """
                UPDATE governance_actions
                   SET meta_fetch_attempts = ?,
                       meta_fetch_next_at  = ?,
                       meta_fetch_error    = ?,
                       updated_at          = NOW()
                 WHERE proposal_id = ?
                """,
                (attempts, next_at, (fetch_error or "unknown error")[:500], proposal_id),
            )
        row = _proposal_translation_row(cursor, proposal_id)
        conn.commit()

    if meta is None:
        logger.warning(
            "proposal metadata fetch failed: proposal_id=%s attempt=%d next_at=%s error=%s",
            proposal_id,
            attempts,
            next_at.isoformat(timespec="seconds"),
            fetch_error,
        )
    return ProposalMetadataFetchResult(row=row, fetched=meta is not None)


def fetch_metadata_retry_targets(limit: int = 50) -> list[dict]:
    """再試行期限に達した未取得メタデータだけをDBから取得する。"""
    safe_limit = max(1, min(int(limit), 500))
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, meta_url, meta_hash
              FROM governance_actions
             WHERE meta_url IS NOT NULL
               AND title IS NULL
               AND meta_fetched_at IS NULL
               AND meta_fetch_attempts < ?
               AND (meta_fetch_next_at IS NULL OR meta_fetch_next_at <= NOW())
             ORDER BY proposed_epoch DESC, id DESC
             LIMIT ?
            """,
            (_META_RETRY_LIMIT, safe_limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def retry_missing_proposal_metadata(limit: int = 50) -> list[dict]:
    """未取得分だけを再試行し、取得できた翻訳ターゲット行を返す。"""
    targets = fetch_metadata_retry_targets(limit)
    logger.info("proposal metadata retry targets: %d", len(targets))
    recovered: list[dict] = []
    for target in targets:
        proposal_id = str(target.get("proposal_id") or "")
        try:
            result = fetch_and_save_proposal_metadata(
                proposal_id,
                target.get("meta_url"),
                target.get("meta_hash"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "proposal metadata retry failed unexpectedly: proposal_id=%s: %s",
                proposal_id,
                exc,
            )
            continue
        if result.fetched and result.row:
            recovered.append(result.row)
    logger.info("proposal metadata retry recovered: %d/%d", len(recovered), len(targets))
    return recovered


def get_proposal_info_from_db(
    proposal_tx_hash: str,
    proposal_index: int = 0,
) -> dict | None:
    """投票通知用の提案情報をローカルDBから返す。"""
    if not proposal_tx_hash:
        return None
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT proposal_id, proposal_type, title, title_ja
              FROM governance_actions
             WHERE proposal_tx_hash = ? AND proposal_index = ?
             LIMIT 1
            """,
            (proposal_tx_hash, int(proposal_index)),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        "title": row.get("title_ja") or row.get("title") or None,
        "proposal_id": row.get("proposal_id") or None,
        "proposal_type": row.get("proposal_type") or None,
    }


def fetch_translation_targets(
    limit: int,
    tx_hash: str | None = None,
    force: bool = False,
) -> list[dict]:
    """翻訳が必要なレコードを DB から取得する。"""
    cols = ("id", "proposal_tx_hash", "title", "`abstract`", "motivation", "rationale",
            "title_ja", "abstract_ja", "motivation_ja", "rationale_ja")
    select = f"SELECT {', '.join(cols)} FROM governance_actions"

    with get_db() as (cursor, _):
        if tx_hash:
            cursor.execute(f"{select} WHERE proposal_tx_hash = ?", (tx_hash,))
        elif force:
            cursor.execute(
                f"{select} WHERE title IS NOT NULL ORDER BY proposed_epoch DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor.execute(
                f"{select} "
                "WHERE title IS NOT NULL "
                "  AND (title_ja IS NULL OR abstract_ja IS NULL "
                "       OR motivation_ja IS NULL OR rationale_ja IS NULL) "
                "ORDER BY proposed_epoch DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in cursor.fetchall()]


def save_translation(row_id: int, updates: dict):
    """翻訳結果を DB に保存する。"""
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    params = list(updates.values()) + [row_id]
    with get_db() as (cursor, conn):
        cursor.execute(
            f"UPDATE governance_actions SET {set_clause} WHERE id = ?",
            params,
        )
        conn.commit()


# ============================================================
# 翻訳
# ============================================================

def _translate_one(translator: Translator, row: dict, force: bool) -> dict | None:
    """
    1件分のフィールドを翻訳して更新辞書を返す。
    翻訳不要（既訳かつ force=False）の場合は None を返す。

    リクエスト数削減のため motivation + rationale をバッチ翻訳する。
    """
    updates: dict[str, str] = {}

    def needs(field_ja: str) -> bool:
        return force or not row.get(field_ja)

    # タイトル（短文）
    if needs("title_ja") and row.get("title"):
        updates["title_ja"] = translator.translate_title(row["title"])

    # abstract（単独・長文）
    if needs("abstract_ja") and row.get("abstract"):
        updates["abstract_ja"] = translator.translate_overview(row["abstract"])

    # motivation + rationale（バッチ翻訳：1リクエストで2フィールド）
    need_mot = needs("motivation_ja") and bool(row.get("motivation"))
    need_rat = needs("rationale_ja")  and bool(row.get("rationale"))
    if need_mot and need_rat:
        mot_ja, rat_ja = translator.translate_overview_pair(
            row["motivation"], row["rationale"]
        )
        updates["motivation_ja"] = mot_ja
        updates["rationale_ja"]  = rat_ja
    elif need_mot:
        updates["motivation_ja"] = translator.translate_overview(row["motivation"])
    elif need_rat:
        updates["rationale_ja"]  = translator.translate_overview(row["rationale"])

    return updates if updates else None


def run_translation(
    translator: Translator,
    rows: list[dict],
    workers: int,
    force: bool,
    sleep_secs: float,
):
    """翻訳対象レコードを並列処理して DB に保存する。"""
    if not rows:
        logger.info("翻訳対象なし")
        return

    logger.info("翻訳開始: %d 件 (workers=%d)", len(rows), workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_translate_one, translator, row, force): row
            for row in rows
        }
        for future in as_completed(futures):
            row = futures[future]
            tx_short = (row.get("proposal_tx_hash") or "")[:16]
            try:
                updates = future.result()
            except Exception as exc:
                logger.error("翻訳失敗 tx=%s: %s", tx_short, exc)
                continue
            if not updates:
                logger.debug("翻訳スキップ tx=%s", tx_short)
                continue
            save_translation(row["id"], updates)
            logger.info("翻訳完了 tx=%s fields=%s", tx_short, list(updates.keys()))
            if sleep_secs:
                time.sleep(sleep_secs)


# ============================================================
# エントリポイント
# ============================================================

def main(argv: list[str] | None = None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="ガバナンスアクションのフェッチ・翻訳・DB保存")
    parser.add_argument("--no-translate", action="store_true",
                        help="翻訳をスキップしてフェッチのみ実行する")
    parser.add_argument("--force",  action="store_true",
                        help="翻訳済みレコードも再翻訳する")
    parser.add_argument("--limit",   type=int,   default=50,
                        help="1回の翻訳上限件数（デフォルト: 50）")
    parser.add_argument("--workers", type=int,   default=3,
                        help="翻訳並列数（デフォルト: 3）")
    parser.add_argument("--sleep",   type=float, default=0.0,
                        help="翻訳リクエスト間のスリープ秒数")
    parser.add_argument("--id", metavar="TX_HASH",
                        help="指定した proposal_tx_hash のみ翻訳対象にする")
    parser.add_argument(
        "--retry-metadata",
        action="store_true",
        help="Koios全件取得を行わず、期限に達した提案メタデータだけ再試行する",
    )
    args = parser.parse_args(argv)

    if args.retry_metadata:
        logger.info("=== 提案メタデータ再試行開始 ===")
        recovered_rows = retry_missing_proposal_metadata(args.limit)
        proposal_ids = [
            str(row.get("proposal_id"))
            for row in recovered_rows
            if row.get("proposal_id") and row.get("title")
        ]
        if proposal_ids:
            try:
                from cardanoism.backend.governance_ai_db import bulk_enqueue
                queued = bulk_enqueue(proposal_ids)
                logger.info("AI 分析キューに enqueue: %d 件", queued)
            except Exception as exc:
                logger.warning("AI enqueue 失敗 (継続): %s", exc)

        if args.no_translate or not recovered_rows:
            if args.no_translate:
                logger.info("--no-translate 指定のため翻訳スキップ")
            logger.info("=== 提案メタデータ再試行完了 ===")
            return

        translator = build_translator()
        run_translation(
            translator,
            recovered_rows,
            args.workers,
            args.force,
            args.sleep,
        )
        logger.info("=== 提案メタデータ再試行完了 ===")
        return

    # ── フェッチ ──────────────────────────────────────────
    logger.info("=== フェッチ開始 ===")
    proposals = fetch_all_proposals()
    if proposals is None:
        logger.error("Koios /proposal_list の完全取得に失敗したためDB更新を中止します")
        raise SystemExit(2)
    logger.info("フェッチ完了: %d 件", len(proposals))

    upserted = 0
    errors = 0
    new_proposal_ids: list[str] = []
    for item in proposals:
        try:
            fields = _extract_fields(item)
            if not fields["proposal_id"]:
                continue
            is_new = upsert_proposal(fields)
            if is_new:
                new_proposal_ids.append(fields["proposal_id"])
            upserted += 1
        except Exception as exc:
            errors += 1
            logger.error("upsert 失敗 proposal_id=%s: %s", item.get("proposal_id", "?"), exc)
    logger.info("DB upsert 完了: %d 件 (新規 %d / エラー %d 件)",
                upserted, len(new_proposal_ids), errors)

    # 新規 GA を AI 分析キューに enqueue。失敗してもメインフローは中断しない。
    if new_proposal_ids:
        try:
            from cardanoism.backend.governance_ai_db import bulk_enqueue
            queued = bulk_enqueue(new_proposal_ids)
            logger.info("AI 分析キューに enqueue: %d 件", queued)
        except Exception as exc:
            logger.warning("AI enqueue 失敗 (継続): %s", exc)

    if args.no_translate:
        logger.info("--no-translate 指定のため翻訳スキップ")
        return

    # ── 翻訳 ──────────────────────────────────────────────
    logger.info("=== 翻訳開始 ===")
    translator = build_translator()
    rows = fetch_translation_targets(args.limit, args.id, args.force)
    logger.info("翻訳対象: %d 件", len(rows))
    run_translation(translator, rows, args.workers, args.force, args.sleep)
    logger.info("=== 完了 ===")


def run_cli(argv: list[str] | None = None) -> None:
    """Run the governance refresh under the same lock for cron and listener."""
    try:
        with sync_job_lock("governance", timeout=0) as acquired:
            if not acquired:
                logger.info(
                    "governance refresh skipped because another process is running"
                )
                return
            main(argv)
    except SyncLockError as exc:
        logger.error("governance refresh aborted because its lock is unavailable: %s", exc)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    run_cli()
