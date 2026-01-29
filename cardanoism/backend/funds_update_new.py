import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Tuple

import requests

from db_connect import dbConnect

API_URL = "https://www.catalystexplorer.com/api/v1/funds"
COLUMN_ORDER = [
    "id",
    "title",
    "slug",
    "label",
    "description",
    "status",
    "currency",
    "currency_symbol",
    "amount",
    "launched_at",
    "awarded_at",
    "assessment_started_at",
    "hero_img_url",
    "banner_img_url",
    "proposals_count",
    "funded_proposals_count",
    "completed_proposals_count",
]
DECIMAL_COLUMNS = {"amount"}
DATETIME_COLUMNS = {"launched_at", "awarded_at", "assessment_started_at"}
INT_COLUMNS = {
    "proposals_count",
    "funded_proposals_count",
    "completed_proposals_count",
}
SLUG_PATTERN = re.compile(r"fund-", re.IGNORECASE)


def clean_slug(value: Any) -> str:
    if not value:
        return ""
    return SLUG_PATTERN.sub("", str(value))


def fetch_all_funds() -> List[Dict[str, Any]]:
    """Fetch every fund page from the API."""
    results: List[Dict[str, Any]] = []
    page = 1

    while True:
        response = requests.get(API_URL, params={"page": page}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        meta = payload.get("meta") or {}
        results.extend(data)

        current_page = meta.get("current_page", page)
        last_page = meta.get("last_page", current_page)
        if current_page >= last_page:
            break
        page += 1

    return results


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value

    ts = str(value).replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def normalize_amount(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def normalize_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def transform_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    mapped: Dict[str, Any] = {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "slug": clean_slug(raw.get("slug")),
        "label": raw.get("label"),
        "description": raw.get("description"),
        "status": raw.get("status"),
        "currency": raw.get("currency"),
        "currency_symbol": raw.get("currency_symbol"),
        "amount": normalize_amount(raw.get("amount")),
        "launched_at": parse_datetime(raw.get("launched_at")),
        "awarded_at": parse_datetime(raw.get("awarded_at")),
        "assessment_started_at": parse_datetime(raw.get("assessment_started_at")),
        "hero_img_url": raw.get("hero_img_url"),
        "banner_img_url": raw.get("banner_img_url"),
        "proposals_count": normalize_int(raw.get("proposals_count")),
        "funded_proposals_count": normalize_int(raw.get("funded_proposals_count")),
        "completed_proposals_count": normalize_int(
            raw.get("completed_proposals_count")
        ),
    }

    return mapped


def format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")
    return parse_datetime(value).strftime("%Y-%m-%d %H:%M:%S.%f")


def normalize_for_compare(column: str, value: Any) -> Any:
    if column in DECIMAL_COLUMNS:
        return normalize_amount(value)
    if column in DATETIME_COLUMNS:
        return format_datetime(value)
    if column in INT_COLUMNS:
        return normalize_int(value)
    return value


def get_existing_funds(cursor) -> Dict[str, Dict[str, Any]]:
    cursor.execute("SELECT * FROM funds_new")
    rows = cursor.fetchall()
    return {row["id"]: row for row in rows}


def build_insert_tuple(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(record[column] for column in COLUMN_ORDER)


def diff_record(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    for column, value in incoming.items():
        if column == "id":
            continue
        current_value = existing.get(column)
        if normalize_for_compare(column, current_value) != normalize_for_compare(
            column, value
        ):
            updates[column] = value
    return updates


def save_funds(records: List[Dict[str, Any]]) -> None:
    db_cursor, db_conn = dbConnect()
    existing = get_existing_funds(db_cursor)

    inserted = 0
    updated = 0

    insert_sql = f"""
        INSERT INTO funds_new ({", ".join(COLUMN_ORDER)})
        VALUES ({", ".join(["?"] * len(COLUMN_ORDER))})
    """.strip()

    for record in records:
        fund_id = record["id"]
        if not fund_id:
            continue

        if fund_id not in existing:
            db_cursor.execute(insert_sql, build_insert_tuple(record))
            inserted += 1
            existing[fund_id] = record
            continue

        changes = diff_record(existing[fund_id], record)
        if not changes:
            continue

        set_clause = ", ".join(f"{column} = ?" for column in changes.keys())
        params = list(changes.values()) + [fund_id]
        db_cursor.execute(f"UPDATE funds_new SET {set_clause} WHERE id = ?", params)
        updated += 1
        existing[fund_id].update(changes)

    db_conn.commit()
    db_cursor.close()
    db_conn.close()

    print(
        json.dumps(
            {"processed": len(records), "inserted": inserted, "updated": updated},
            ensure_ascii=False,
        )
    )


def main():
    api_records = fetch_all_funds()
    structured_records = [transform_record(record) for record in api_records]
    save_funds(structured_records)


if __name__ == "__main__":
    main()
