import argparse
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from openai import OpenAI, OpenAIError

from db_connect import dbConnect
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from translate import TranslateConfig, Translator


OPENAI_MODEL = "gpt-5-mini"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate proposals_new columns after import."
    )
    parser.add_argument(
        "--fund",
        default="",
        help="Fund identifier (UUID or number like 12). Leave blank for all funds.",
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Max records to translate in one run."
    )
    parser.add_argument(
        "--sleep", type=float, default=0.0, help="Sleep seconds between translations."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate even if target columns already have values.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of concurrent translation workers.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log per-field translation actions.",
    )
    return parser.parse_args()


def build_translator() -> Translator:
    base_dir = Path(__file__).resolve().parents[1]
    config = TranslateConfig(
        keep_terms_path=base_dir / "translate" / "terms" / "keep_terms.yaml",
        guidance_terms_path=base_dir / "translate" / "terms" / "guidance_terms.yaml",
        title_terms_path=base_dir / "translate" / "terms" / "title_terms.yaml",
    )
    client = OpenAI(api_key=os.getenv("GPT_API_KEY"))
    cache: Dict[tuple[str, str], str] = {}
    cache_lock = Lock()

    def llm_translate(system_prompt: str, text: str) -> str:
        key = (system_prompt, text)
        with cache_lock:
            cached = cache.get(key)
        if cached is not None:
            return cached
        logging.info("OpenAI request start: model=%s input_chars=%s", OPENAI_MODEL, len(text))
        try:
            response = client.responses.create(
                model=OPENAI_MODEL,
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {"role": "user", "content": [{"type": "input_text", "text": text}]},
                ],
            )
        except OpenAIError as exc:
            raise RuntimeError(f"OpenAI request failed: {exc}") from exc
        logging.info("OpenAI request done: model=%s output_chars=%s", OPENAI_MODEL, len(response.output_text or ""))
        translated = response.output_text.strip()
        with cache_lock:
            cache[key] = translated
        return translated

    return Translator(config, llm_translate)


def fetch_columns(cursor, table: str) -> List[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?
        """,
        (table,),
    )
    return [row["COLUMN_NAME"] for row in cursor.fetchall()]


def is_uuid(value: str) -> bool:
    return bool(
        value
        and len(value) == 36
        and value.count("-") == 4
    )


def resolve_fund_uuid(cursor, fund_arg: str) -> Optional[str]:
    if not fund_arg:
        return None
    if is_uuid(fund_arg):
        return fund_arg

    normalized = fund_arg.strip().lower()
    candidates = {normalized}
    if normalized.isdigit():
        candidates.add(f"fund-{normalized}")
    if normalized.startswith("fund-"):
        candidates.add(normalized.replace("fund-", ""))

    for candidate in candidates:
        cursor.execute("SELECT id FROM funds_new WHERE LOWER(slug) = ? LIMIT 1", (candidate,))
        row = cursor.fetchone()
        if row:
            return row.get("id")
    return None


def build_select_query(
    columns: List[str], limit: int, force: bool, fund_uuid: Optional[str]
) -> str:
    base_cols = [
        "uuid",
        "title",
        "title_ja",
        "problem",
        "problem_ja",
        "solution",
        "solution_ja",
    ]
    if "idea_raw_html" in columns:
        base_cols.append("idea_raw_html")
    if "idea_semantic_blocks" in columns:
        base_cols.append("idea_semantic_blocks")
    if "idea_semantic_blocks_ja" in columns:
        base_cols.append("idea_semantic_blocks_ja")
    if "idea_semantic_blocks_ai" in columns:
        base_cols.append("idea_semantic_blocks_ai")

    where_parts: List[str] = []
    if not force:
        where_parts.append("(title_ja IS NULL OR title_ja = '')")
        where_parts.append("(problem_ja IS NULL OR problem_ja = '')")
        where_parts.append("(solution_ja IS NULL OR solution_ja = '')")
        if "idea_semantic_blocks" in columns:
            if "idea_semantic_blocks_ja" in columns:
                where_parts.append(
                    "(idea_semantic_blocks_ja IS NULL OR idea_semantic_blocks_ja = '')"
                )
            if "idea_semantic_blocks_ai" in columns:
                where_parts.append(
                    "(idea_semantic_blocks_ai IS NULL OR idea_semantic_blocks_ai = '')"
                )

    where_clause = ""
    if where_parts:
        where_clause = "WHERE (" + " OR ".join(where_parts) + ")"
    if "idea_semantic_blocks" in columns:
        semantic_clause = (
            "idea_semantic_blocks IS NOT NULL AND idea_semantic_blocks <> '' "
            "AND TRIM(idea_semantic_blocks) <> '[]'"
        )
        if where_clause:
            where_clause = f"{where_clause} AND {semantic_clause}"
        else:
            where_clause = f"WHERE {semantic_clause}"
    if "idea_raw_html" in columns:
        raw_clause = (
            "idea_raw_html IS NOT NULL AND TRIM(idea_raw_html) <> '' "
            "AND LOWER(TRIM(idea_raw_html)) <> 'null'"
        )
        if where_clause:
            where_clause = f"{where_clause} AND {raw_clause}"
        else:
            where_clause = f"WHERE {raw_clause}"

    if fund_uuid:
        fund_clause = "fund_uuid = ?"
        if where_clause:
            where_clause = f"{where_clause} AND {fund_clause}"
        else:
            where_clause = f"WHERE {fund_clause}"

    return f"""
        SELECT {", ".join(base_cols)}
        FROM proposals_new
        {where_clause}
        ORDER BY uuid
        LIMIT {limit}
    """.strip()


def parse_semantic_blocks_json(
    raw_json: Optional[str], debug: bool, uuid: str
) -> Optional[List[Dict[str, Any]]]:
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        logging.warning("Failed to decode semantic blocks JSON for %s.", uuid)
        return None
    if not isinstance(data, list):
        logging.warning("Semantic blocks JSON is not a list for %s.", uuid)
        return None
    if not data:
        if debug:
            logging.info("Skipping semantic_blocks for %s (empty list).", uuid)
        return None
    return data


def translate_semantic_blocks_with_ai(
    translator: Translator, data: List[Dict[str, Any]], debug: bool, uuid: str
) -> tuple[Optional[str], Optional[str]]:
    if not data:
        return None, None
    if debug:
        titles = [str(b.get("semantic_title") or b.get("title")) for b in data if b.get("semantic_title") or b.get("title")]
        logging.info("semantic_blocks titles for %s: %s", uuid, titles)
    translated_blocks, ai_blocks = translator.translate_semantic_blocks_with_ai(data)
    translated_json = json.dumps(translated_blocks, ensure_ascii=False) if translated_blocks else None
    ai_json = json.dumps(ai_blocks, ensure_ascii=False) if ai_blocks else None
    return translated_json, ai_json


def build_updates(
    translator: Translator,
    row: Dict[str, Any],
    columns: List[str],
    force: bool,
    debug: bool,
) -> Optional[Dict[str, Any]]:
    updates: Dict[str, Any] = {}

    title = row.get("title") or ""
    if title and (force or not row.get("title_ja")):
        if debug:
            logging.info("Translating title for %s", row.get("uuid"))
        updates["title_ja"] = translator.translate_title(title)
    elif debug:
        logging.info("Skipping title for %s (already translated or empty)", row.get("uuid"))

    problem = row.get("problem") or ""
    solution = row.get("solution") or ""
    needs_problem = bool(problem) and (force or not row.get("problem_ja"))
    needs_solution = bool(solution) and (force or not row.get("solution_ja"))
    if needs_problem or needs_solution:
        if debug:
            logging.info("Translating problem+solution for %s", row.get("uuid"))
        problem_text = problem if needs_problem else ""
        solution_text = solution if needs_solution else ""
        translated_problem, translated_solution = translator.translate_overview_pair(
            problem_text, solution_text
        )
        if needs_problem:
            updates["problem_ja"] = translated_problem
        if needs_solution:
            updates["solution_ja"] = translated_solution
    elif debug:
        logging.info("Skipping problem/solution for %s (already translated or empty)", row.get("uuid"))

    has_semantic = "idea_semantic_blocks" in columns
    has_semantic_ja = "idea_semantic_blocks_ja" in columns
    has_semantic_ai = "idea_semantic_blocks_ai" in columns
    needs_ja = has_semantic_ja and (force or not row.get("idea_semantic_blocks_ja"))
    needs_ai = has_semantic_ai and (force or not row.get("idea_semantic_blocks_ai"))
    if has_semantic and (needs_ja or needs_ai):
        translated_blocks = None
        ai_blocks = None
        semantic_data = parse_semantic_blocks_json(
            row.get("idea_semantic_blocks"), debug, row.get("uuid")
        )
        if not semantic_data:
            if debug:
                logging.info(
                    "Skipping semantic_blocks for %s (empty/invalid).",
                    row.get("uuid"),
                )
        else:
            if debug:
                logging.info(
                    "Translating semantic_blocks for %s (needs_ja=%s needs_ai=%s)",
                    row.get("uuid"),
                    needs_ja,
                    needs_ai,
                )
            translated_blocks, ai_blocks = translate_semantic_blocks_with_ai(
                translator, semantic_data, debug, row.get("uuid")
            )
        if needs_ja and translated_blocks:
            updates["idea_semantic_blocks_ja"] = translated_blocks
        if needs_ai and ai_blocks:
            updates["idea_semantic_blocks_ai"] = ai_blocks
        if debug and (needs_ja or needs_ai) and any(
            k.startswith("idea_semantic_blocks") for k in updates.keys()
        ):
            logging.info(
                "semantic_blocks update keys for %s: %s",
                row.get("uuid"),
                sorted([k for k in updates.keys() if k.startswith("idea_semantic_blocks")]),
            )
    elif debug and has_semantic and (has_semantic_ja or has_semantic_ai):
        logging.info(
            "Skipping semantic_blocks for %s (needs_ja=%s needs_ai=%s has_ai_col=%s)",
            row.get("uuid"),
            needs_ja,
            needs_ai,
            has_semantic_ai,
        )

    return updates or None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()

    translator = build_translator()

    cursor, conn = dbConnect()
    try:
        columns = fetch_columns(cursor, "proposals_new")
        fund_uuid = resolve_fund_uuid(cursor, args.fund)
        query = build_select_query(columns, args.limit, args.force, fund_uuid)
        if args.debug:
            logging.info("Select query: %s", query)
        if fund_uuid:
            cursor.execute(query, (fund_uuid,))
        else:
            cursor.execute(query)
        rows = cursor.fetchall()
        logging.info("Fetched %s records for translation.", len(rows))
        if args.debug:
            for row in rows:
                logging.info(
                    "Row uuid=%s raw_html=%s semantic_len=%s title_ja=%s problem_ja=%s solution_ja=%s semantic_ja=%s semantic_ai=%s",
                    row.get("uuid"),
                    bool(row.get("idea_raw_html")),
                    len((row.get("idea_semantic_blocks") or "").strip()),
                    bool(row.get("title_ja")),
                    bool(row.get("problem_ja")),
                    bool(row.get("solution_ja")),
                    bool(row.get("idea_semantic_blocks_ja")),
                    bool(row.get("idea_semantic_blocks_ai")),
                )

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    build_updates, translator, row, columns, args.force, args.debug
                ): row
                for row in rows
                if row.get("uuid")
            }
            for future in as_completed(futures):
                row = futures[future]
                uuid = row.get("uuid")
                try:
                    updates = future.result()
                except Exception as exc:  # pylint: disable=broad-except
                    logging.error("Translation failed for %s: %s", uuid, exc)
                    continue
                if not updates:
                    continue
                set_clause = ", ".join(f"{col} = ?" for col in updates.keys())
                params = list(updates.values()) + [uuid]
                cursor.execute(
                    f"UPDATE proposals_new SET {set_clause} WHERE uuid = ?",
                    params,
                )
                conn.commit()
                logging.info("Updated %s with %s fields.", uuid, len(updates))
                if args.sleep:
                    time.sleep(args.sleep)
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
