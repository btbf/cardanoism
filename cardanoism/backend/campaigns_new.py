import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Tuple

import requests
from openai import OpenAI, OpenAIError

from db_connect import dbConnect

API_URL = "https://www.catalystexplorer.com/api/campaigns"
COLUMN_ORDER = [
    "id",
    "title",
    "title_jp",
    "fund_uuid",
    "slug",
    "excerpt",
    "excerpt_jp",
    "amount",
    "launched_at",
    "awarded_at",
    "color",
    "label",
]
DATETIME_FIELDS = {"launched_at", "awarded_at"}
DECIMAL_FIELDS = {"amount"}
SLUG_PREFIX_PATTERN = re.compile(r"f\d+-", re.IGNORECASE)
SLUG_SUFFIX_PATTERN = re.compile(r"-f\d+", re.IGNORECASE)
TITLE_F_PREFIX_PATTERN = re.compile(r"^\s*[Ff]\s*\d+\s*[:：]\s*")

TRANSLATION_MODEL = "gpt-4.1-mini"
TITLE_PROMPT = (
    "You translate English Project Catalyst challenge titles into concise Japanese "
    "headlines. Keep terminology accurate for blockchain contexts and always render "
    '"Cardano" as カルダノ Output only the translated headline.'
)
EXCERPT_PROMPT = (
    "You translate Challenge descriptions from English to natural Japanese. Preserve "
    "line breaks and meaning exactly, render \"Cardano\" as カルダノ and reply with "
    "only the translated text."
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

openai_client = OpenAI(api_key=os.getenv("GPT_API_KEY"))
translation_cache: Dict[Tuple[str, str], str] = {}


def fetch_all_campaigns() -> List[Dict[str, Any]]:
    campaigns: List[Dict[str, Any]] = []
    page = 1

    while True:
        logging.info("Fetching campaigns page %s", page)
        response = requests.get(API_URL, params={"page": page}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        campaigns.extend(data)
        logging.info("Fetched %s campaign records from page %s", len(data), page)

        meta = payload.get("meta") or {}
        if meta.get("current_page", page) >= meta.get("last_page", page):
            break
        page += 1

    return campaigns


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    timestamp = str(value).replace("Z", "+00:00")
    dt = datetime.fromisoformat(timestamp)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def normalize_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def clean_slug(slug: str | None) -> str:
    if not slug:
        return ""
    cleaned = SLUG_PREFIX_PATTERN.sub("", slug)
    cleaned = SLUG_SUFFIX_PATTERN.sub("", cleaned)
    return cleaned


def strip_title_f_prefix(title: str | None) -> str:
    if not title:
        return ""
    return TITLE_F_PREFIX_PATTERN.sub("", title).strip()


def slugify_url_limited(text: str, max_length: int = 200) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text).lower()
    text = re.sub(r"([a-zA-Z])&([a-zA-Z])", r"\1and\2", text)

    replacements = {
        "&": " and ",
        ">>>": " greatergreatergreater ",
        "<<<": " lesslessless ",
        "->": " to ",
        "|": "or",
        "/": "",
        "：": "",
        ":": "",
        ".": "",
        "_": "",
    }
    for key, value in replacements.items():
        text = text.replace(key, value)

    text = re.sub(r"([a-zA-Z])\.(\d)", r"\1\2", text)
    text = re.sub(r"(\d)\.(\d)", r"\1\2", text)
    text = re.sub(r"[’']", "", text)

    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_length]


def normalize_for_compare(column: str, value: Any) -> Any:
    if column in DATETIME_FIELDS:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        return parse_datetime(value)
    if column in DECIMAL_FIELDS:
        if value in (None, ""):
            return None
        if isinstance(value, Decimal):
            return value
        return normalize_decimal(value)
    return value


def translate_text(kind: str, text: str, prompt: str) -> str | None:
    if not text:
        return None
    cache_key = (kind, text)
    if cache_key in translation_cache:
        return translation_cache[cache_key]

    try:
        response = openai_client.chat.completions.create(
            model=TRANSLATION_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        translated = response.choices[0].message.content.strip()
        if kind == "title":
            translated = translated.replace("：", ":")
            translated = translated.translate(str.maketrans("", "", "、。，．,."))
        translation_cache[cache_key] = translated
        if kind == "title":
            logging.info("Translated title: %s -> %s", text, translated)
        return translated
    except OpenAIError as error:
        print(f"Translation error ({kind}): {error}")
        return None


def transform_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    fund_uuid = None
    original_title = raw.get("title") or ""
    cleaned_title = strip_title_f_prefix(original_title)
    return {
        "id": raw.get("id"),
        "title": cleaned_title or original_title,
        "slug": slugify_url_limited(cleaned_title or ""),
        "excerpt": raw.get("excerpt"),
        "amount": normalize_decimal(raw.get("amount")),
        "launched_at": parse_datetime(raw.get("launched_at")),
        "awarded_at": parse_datetime(raw.get("awarded_at")),
        "color": raw.get("color"),
        "label": raw.get("label"),
        "fund_uuid": fund_uuid,
        "_original_title": original_title,
    }


def fetch_existing_campaigns(cursor) -> Dict[str, Dict[str, Any]]:
    cursor.execute("SELECT * FROM campaigns_new")
    rows = cursor.fetchall()
    return {row["id"]: row for row in rows}


def load_fund_slug_map(cursor) -> Dict[str, str]:
    cursor.execute("SELECT id, slug FROM funds_new")
    rows = cursor.fetchall()
    return {row["id"]: row["slug"] for row in rows}


def match_fund_uuid(title: str, fund_slug_map: Dict[str, str]) -> str | None:
    if not title:
        return None
    match = re.match(r"\s*[Ff]?\s*(\d+)", title)
    if not match:
        return None
    number = match.group(1)
    target_slug = number.lower()
    for fund_id, slug in fund_slug_map.items():
        if not slug:
            continue
        slug_l = slug.lower()
        if slug_l == target_slug or slug_l == f"fund-{target_slug}":
            return fund_id
    return None


def build_insert_params(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(record[column] for column in COLUMN_ORDER)


def diff_record(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    for column, value in incoming.items():
        if column == "id":
            continue
        if column.startswith("_"):
            continue
        if normalize_for_compare(column, existing.get(column)) != normalize_for_compare(
            column, value
        ):
            updates[column] = value
    return updates


def has_changed(new_value: Any, current_value: Any) -> bool:
    return (new_value or "") != (current_value or "")


def enrich_with_translations(
    record: Dict[str, Any], existing: Dict[str, Any] | None
) -> None:
    title_changed = has_changed(record.get("title"), existing.get("title") if existing else None)
    excerpt_changed = has_changed(record.get("excerpt"), existing.get("excerpt") if existing else None)

    if not existing or title_changed:
        record["title_jp"] = translate_text("title", record.get("title", ""), TITLE_PROMPT)
    else:
        record["title_jp"] = existing.get("title_jp")

    if not existing or excerpt_changed:
        record["excerpt_jp"] = translate_text(
            "excerpt", record.get("excerpt") or "", EXCERPT_PROMPT
        )
    else:
        record["excerpt_jp"] = existing.get("excerpt_jp")


def save_campaigns(records: List[Dict[str, Any]]) -> Dict[str, int]:
    cursor, conn = dbConnect()
    existing = fetch_existing_campaigns(cursor)
    fund_slug_map = load_fund_slug_map(cursor)

    insert_sql = f"""
        INSERT INTO campaigns_new ({", ".join(COLUMN_ORDER)})
        VALUES ({", ".join(["?"] * len(COLUMN_ORDER))})
    """.strip()

    inserted = 0
    updated = 0

    for record in records:
        if not record.get("id"):
            continue

        # assign fund_uuid by matching Fund number in original title to funds_new.slug
        if not record.get("fund_uuid"):
            record["fund_uuid"] = match_fund_uuid(
                record.get("_original_title") or record.get("title") or "",
                fund_slug_map,
            )

        current = existing.get(record["id"])
        enrich_with_translations(record, current)

        if current is None:
            cursor.execute(insert_sql, build_insert_params(record))
            inserted += 1
            existing[record["id"]] = record
            continue

        changes = diff_record(current, record)
        if not changes:
            continue

        set_clause = ", ".join(f"{column} = ?" for column in changes.keys())
        params = list(changes.values()) + [record["id"]]
        cursor.execute(f"UPDATE campaigns_new SET {set_clause} WHERE id = ?", params)
        updated += 1
        existing[record["id"]].update(changes)

    conn.commit()
    cursor.close()
    conn.close()

    return {"processed": len(records), "inserted": inserted, "updated": updated}


def main():
    api_data = fetch_all_campaigns()
    structured = [transform_record(item) for item in api_data]
    summary = save_campaigns(structured)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
