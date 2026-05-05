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
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
# シークレットは Infisical CLI で注入。.env は fallback (Infisical 値を上書きしない)。
load_dotenv(PROJECT_ROOT / "cardanoism" / ".env", override=False)

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.koios import _get
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

def fetch_all_proposals() -> list[dict]:
    """Koios /proposal_list を全件取得する（ページネーション対応）。"""
    all_records: list[dict] = []
    offset = 0
    limit = 1000
    while True:
        data = _get("/proposal_list", params={"offset": offset, "limit": limit})
        if not data or not isinstance(data, list):
            break
        all_records.extend(data)
        logger.info("フェッチ中: offset=%d 取得=%d 累計=%d", offset, len(data), len(all_records))
        if len(data) < limit:
            break
        offset += limit
    return all_records


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
    meta = item.get("meta_json") or {}
    body = meta.get("body") or {}
    refs = body.get("references") or []

    deposit = item.get("deposit")
    meta_is_valid = item.get("meta_is_valid")
    action_anchor_url, action_anchor_hash = _extract_action_anchor(item, body)

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
        "action_anchor_url":  action_anchor_url,
        "action_anchor_hash": action_anchor_hash,
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
                action_anchor_url, action_anchor_hash,
                last_event_slot
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?,
                ?
            )
            ON DUPLICATE KEY UPDATE
                -- ステータスエポック + 引き出し情報 + action anchor を更新
                ratified_epoch            = VALUES(ratified_epoch),
                enacted_epoch             = VALUES(enacted_epoch),
                dropped_epoch             = VALUES(dropped_epoch),
                expired_epoch             = VALUES(expired_epoch),
                withdrawal_total_lovelace = VALUES(withdrawal_total_lovelace),
                withdrawal_json           = VALUES(withdrawal_json),
                action_anchor_url         = VALUES(action_anchor_url),
                action_anchor_hash        = VALUES(action_anchor_hash),
                -- last_event_slot は listener が書いた値を保持 (Koios 由来 NULL で上書きしない)
                last_event_slot           = COALESCE(VALUES(last_event_slot), last_event_slot),
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
                fields.get("action_anchor_url"), fields.get("action_anchor_hash"),
                fields.get("last_event_slot"),
            ),
        )
        conn.commit()
    return not existed


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

def main():
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
    args = parser.parse_args()

    # ── フェッチ ──────────────────────────────────────────
    logger.info("=== フェッチ開始 ===")
    proposals = fetch_all_proposals()
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


if __name__ == "__main__":
    main()
