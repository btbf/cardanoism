import argparse
import logging
import re
from typing import Any, Dict, List

from db_connect import dbConnect

TARGET_COLUMNS: List[str] = [
    "solution",
    "solution_ja",
    "impact",
    "impact_ja",
    "capability_feasibility",
    "capability_feasibility_ja",
    "project_milestones",
    "project_milestones_ja",
    "resources",
    "resources_ja",
    "budget_costs",
    "budget_costs_ja",
    "value_for_money",
    "value_for_money_ja",
]

REMOVE_PATTERNS = [
    re.compile(
        r'<dt class="mb-1">\s*(Answer|回答|答え)\s*[：:]\s*</dt>',
        re.IGNORECASE,
    ),
]

DD_OPEN_TAG = re.compile(r"<dd>", re.IGNORECASE)
DD_CLOSE_TAG = re.compile(r"</dd>", re.IGNORECASE)
MILESTONE_DT_PATTERN = re.compile(
    r'<dt class="mb-1">\s*(マイルストーン\s*\d+\s*:[^<]*)</dt>',
    re.IGNORECASE,
)
BR_PARAGRAPH_PATTERN = re.compile(r"<p>\s*<br\s*/?>\s*</p>", re.IGNORECASE)
DD_CUSTOM_FIELDS_TEXTAREA_PATTERN = re.compile(
    r'<dd\s+class="custom-fields"\s+data-field-type="TEXTAREA">', re.IGNORECASE
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clean HTML artifacts from proposal_detail_new text columns "
            "(dd/dt replacements, milestone tags, and stray breaks)."
        )
    )
    parser.add_argument(
        "--uuid",
        help="Process only the specified proposal uuid",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N rows (after any uuid filter)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process rows without writing updates to the database",
    )
    return parser.parse_args()


def normalize_spaces(text: str) -> str:
    """Replace non-breaking spaces to make regex whitespace matches reliable."""
    return text.replace("&nbsp;", " ").replace("\u00a0", " ")


def clean_html_fragment(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value

    cleaned = normalize_spaces(value)
    for pattern in REMOVE_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    cleaned = DD_CUSTOM_FIELDS_TEXTAREA_PATTERN.sub(
        '<div class="custom-fields" data-field-type="TEXTAREA">', cleaned
    )
    cleaned = MILESTONE_DT_PATTERN.sub(r'<div class="mb-1">\1</div>', cleaned)
    cleaned = DD_OPEN_TAG.sub("<div>", cleaned)
    cleaned = DD_CLOSE_TAG.sub("</div>", cleaned)
    cleaned = BR_PARAGRAPH_PATTERN.sub("", cleaned)
    return cleaned


def fetch_rows(cursor, uuid: str | None = None, limit: int | None = None) -> List[Dict[str, Any]]:
    base_sql = "SELECT uuid, " + ", ".join(TARGET_COLUMNS) + " FROM proposal_detail_new"
    params: List[Any] = []
    if uuid:
        base_sql += " WHERE uuid = ?"
        params.append(uuid)
    if limit:
        base_sql += " LIMIT ?"
        params.append(limit)
    cursor.execute(base_sql, params)
    return cursor.fetchall()


def process_rows(cursor, uuid: str | None = None, limit: int | None = None) -> Dict[str, int]:
    rows = fetch_rows(cursor, uuid=uuid, limit=limit)
    total_rows = len(rows)
    updated_rows = 0
    updated_fields = 0

    for index, row in enumerate(rows, start=1):
        updates: Dict[str, Any] = {}
        for column in TARGET_COLUMNS:
            original = row.get(column)
            cleaned = clean_html_fragment(original)
            if cleaned != original:
                updates[column] = cleaned

        if not updates:
            continue

        set_clause = ", ".join(f"{col} = ?" for col in updates.keys())
        params = list(updates.values()) + [row["uuid"]]
        cursor.execute(
            f"UPDATE proposal_detail_new SET {set_clause} WHERE uuid = ?",
            params,
        )
        updated_rows += 1
        updated_fields += len(updates)

        if updated_rows % 100 == 0:
            logging.info("Updated %s rows so far (row %s of %s)", updated_rows, index, total_rows)

    return {
        "processed_rows": total_rows,
        "updated_rows": updated_rows,
        "updated_fields": updated_fields,
    }


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cursor, conn = dbConnect()
    try:
        summary = process_rows(cursor, uuid=args.uuid, limit=args.limit)
        if args.dry_run:
            conn.rollback()
            logging.info("Dry-run enabled; rolled back changes.")
        else:
            conn.commit()
            logging.info("Committed updates to proposal_detail_new.")
    finally:
        cursor.close()
        conn.close()

    logging.info(
        "Processing complete: %s processed, %s updated rows, %s fields",
        summary["processed_rows"],
        summary["updated_rows"],
        summary["updated_fields"],
    )


if __name__ == "__main__":
    main()
