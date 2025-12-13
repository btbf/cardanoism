import argparse
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests
from openai import OpenAI, OpenAIError

from db_connect import dbConnect

API_URL = "https://www.catalystexplorer.com/api/v1/proposals"
PER_PAGE = 60
INCLUDE = "campaign,fund,team,meta_data"

COLUMN_ORDER = [
    "id",
    "uuid",
    "fund_uuid",
    "campaign_uuid",
    "user_id",
    "fund_id",
    "challenge_id",
    "title",
    "title_ja",
    "user_name",
    "projectcatalyst_link",
    "ideascale_link",
    "ideascale_user",
    "ideascale_id",
    "amount_requested",
    "amount_received",
    "project_status",
    "funding_status",
    "yes_votes_count",
    "no_votes_count",
    "abstain_votes_count",
    "unique_wallets",
    "problem",
    "problem_ja",
    "solution",
    "solution_ja",
    "currency_symbol",
    "currency",
    "alignment_score",
    "feasibility_score",
    "auditability_score",
    "tags",
    "slug",
]

EXCLUDE_UPDATE_FIELDS = {
    "title",
    "title_ja",
    "problem",
    "problem_ja",
    "solution",
    "solution_ja",
    "ideascale_link",
    "ideascale_user",
    "ideascale_id",
    "fund_id",
}

TITLE_PROMPT = (
    "You translate English Project Catalyst proposal titles into concise Japanese "
    "headlines. Keep terminology accurate for blockchain contexts and always render "
    '"Cardano" as カルダノ. Output only the translated headline.'
)
DETAIL_PROMPT = (
    "You translate Project Catalyst proposal text to natural Japanese. Preserve meaning "
    "and structure, render \"Cardano\" as カルダノ, and reply with only the translation."
)

openai_client = OpenAI(api_key=os.getenv("GPT_API_KEY"))
translation_cache: Dict[Tuple[str, str], str] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import proposals into proposals_new from Catalyst Explorer API."
    )
    parser.add_argument(
        "--fund",
        default="",
        help="Fund identifier (UUID or number like 12). Leave blank for all funds.",
    )
    return parser.parse_args()


def is_uuid(value: str) -> bool:
    return re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        value,
        re.IGNORECASE,
    ) is not None


def resolve_fund_uuid(conn, fund_arg: str) -> Optional[str]:
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

    cursor = conn.cursor(dictionary=True)
    for candidate in candidates:
        cursor.execute("SELECT id FROM funds_new WHERE LOWER(slug) = ?", (candidate,))
        row = cursor.fetchone()
        if row:
            cursor.close()
            logging.info("Resolved fund '%s' to id %s", fund_arg, row["id"])
            return row["id"]
    cursor.close()
    logging.warning("Could not resolve fund '%s'; importing all funds.", fund_arg)
    return None


def fetch_all_proposals(fund_id: str) -> List[Dict[str, Any]]:
    proposals: List[Dict[str, Any]] = []
    page = 1

    while True:
        params: Dict[str, Any] = {
            "page": page,
            "per_page": PER_PAGE,
            "include": INCLUDE,
        }
        if fund_id:
            params["filter[fund_id]"] = fund_id

        logging.info("Fetching proposals page %s params=%s", page, params)
        response = requests.get(API_URL, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        meta = payload.get("meta") or {}

        proposals.extend(data)
        logging.info(
            "Fetched %s proposals (page=%s last_page=%s)",
            len(data),
            meta.get("current_page", page),
            meta.get("last_page"),
        )

        if meta.get("current_page", page) >= meta.get("last_page", page):
            break
        page += 1

    return proposals


def make_slug(title: Optional[str]) -> str:
    if not title:
        return ""
    # Replace any non-alphanumeric character with hyphen, collapse repeats, lower-case
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-").lower()


def to_int(value: Any) -> Optional[int]:
    if value in (None, "", "null"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> Optional[float]:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def serialize_tags(value: Any) -> Optional[str]:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def extract_team(proposal: Dict[str, Any]) -> Dict[str, Any]:
    team_obj = proposal.get("team") or {}
    if isinstance(team_obj, list):
        if team_obj:
            return team_obj[0]
        return {}
    if isinstance(team_obj, dict):
        return team_obj
    return {}


def translate_text(kind: str, text: str) -> Optional[str]:
    if not text:
        return None
    cache_key = (kind, text)
    if cache_key in translation_cache:
        return translation_cache[cache_key]

    prompt = TITLE_PROMPT if kind == "title" else DETAIL_PROMPT
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
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
            logging.info("Translated title: %s -> %s", text, translated)
        translation_cache[cache_key] = translated
        return translated
    except OpenAIError as error:
        logging.error("Translation error for %s: %s", kind, error)
        return None


def normalize_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    campaign = raw.get("campaign") or {}
    fund = raw.get("fund") or {}
    team = extract_team(raw)
    meta = raw.get("meta_data") or {}
    chain_proposal_id = meta.get("chain_proposal_id")

    record: Dict[str, Any] = {
        # idはAUTO_INCREMENT想定のため明示セットしない
        "id": None,
        "uuid": raw.get("id"),
        "fund_uuid": fund.get("id"),
        "campaign_uuid": campaign.get("id"),
        "user_id": to_int(team.get("id") or raw.get("user_id")),
        "fund_id": to_int(raw.get("fund_id")),
        "challenge_id": to_int(raw.get("challenge_id") or raw.get("campaign_id")),
        "title": raw.get("title"),
        "title_ja": None,
        "user_name": team.get("name") or raw.get("user_name"),
        "projectcatalyst_link": None,
        "ideascale_link": raw.get("ideascale_link"),
        "ideascale_user": raw.get("ideascale_user"),
        "ideascale_id": raw.get("ideascale_id"),
        "amount_requested": to_int(raw.get("amount_requested")),
        "amount_received": to_int(raw.get("amount_received")),
        "project_status": raw.get("status") or raw.get("project_status"),
        "funding_status": raw.get("funding_status"),
        "yes_votes_count": to_int(raw.get("yes_votes_count")),
        "no_votes_count": to_int(raw.get("no_votes_count")),
        "abstain_votes_count": to_int(raw.get("abstain_votes_count")),
        "unique_wallets": to_int(raw.get("unique_wallets") or meta.get("unique_wallets")),
        "problem": raw.get("problem"),
        "problem_ja": None,
        "solution": raw.get("solution"),
        "solution_ja": None,
        "currency_symbol": raw.get("currency_symbol"),
        "currency": raw.get("currency"),
        "alignment_score": to_float(meta.get("alignment_score")),
        "feasibility_score": to_float(meta.get("feasibility_score")),
        "auditability_score": to_float(meta.get("auditability_score")),
        "tags": serialize_tags(raw.get("tags")),
        "slug": make_slug(raw.get("title")),
        "_chain_proposal_id": meta.get("chain_proposal_id"),
    }

    return record


def fetch_existing(conn) -> Dict[str, Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM proposals_new")
    rows = cursor.fetchall()
    cursor.close()
    return {row["uuid"]: row for row in rows if row.get("uuid")}


def load_slug_maps(conn) -> Tuple[Dict[str, str], Dict[str, str]]:
    fund_map: Dict[str, str] = {}
    campaign_map: Dict[str, str] = {}
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, slug FROM funds_new")
    for row in cursor.fetchall():
        fund_map[row["id"]] = row.get("slug") or ""
    cursor.execute("SELECT id, slug FROM campaigns_new")
    for row in cursor.fetchall():
        campaign_map[row["id"]] = row.get("slug") or ""
    cursor.close()
    return fund_map, campaign_map


def build_projectcatalyst_link(record: Dict[str, Any], fund_map: Dict[str, str], campaign_map: Dict[str, str]) -> Optional[str]:
    fund_slug = fund_map.get(record.get("fund_uuid") or "")
    campaign_slug = campaign_map.get(record.get("campaign_uuid") or "")
    proj_slug = record.get("slug") or ""
    if fund_slug and campaign_slug and proj_slug:
        return f"https://projectcatalyst.io/funds/{fund_slug}/{campaign_slug}/{proj_slug}"
    return None


def build_insert_tuple(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(record.get(column) for column in COLUMN_ORDER)


def diff_record(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    for column, value in incoming.items():
        if column in EXCLUDE_UPDATE_FIELDS:
            continue
        if column not in existing:
            continue
        if value is None:
            continue
        if existing.get(column) != value:
            updates[column] = value
    return updates


def enrich_translations(record: Dict[str, Any], existing: Optional[Dict[str, Any]]) -> None:
    if existing:
        record["title_ja"] = existing.get("title_ja")
        record["problem_ja"] = existing.get("problem_ja")
        record["solution_ja"] = existing.get("solution_ja")
        return

    record["title_ja"] = translate_text("title", record.get("title") or "")
    record["problem_ja"] = translate_text("problem", record.get("problem") or "")
    record["solution_ja"] = translate_text("solution", record.get("solution") or "")


def save_records(records: List[Dict[str, Any]]) -> Dict[str, int]:
    cursor, conn = dbConnect()
    existing_map = fetch_existing(conn)
    fund_map, campaign_map = load_slug_maps(conn)

    insert_sql = f"""
        INSERT INTO proposals_new ({", ".join(COLUMN_ORDER)})
        VALUES ({", ".join(["?"] * len(COLUMN_ORDER))})
    """.strip()

    inserted = 0
    updated = 0

    for record in records:
        uuid = record.get("uuid")
        if not uuid:
            continue

        record["projectcatalyst_link"] = build_projectcatalyst_link(record, fund_map, campaign_map)

        current = existing_map.get(uuid)
        enrich_translations(record, current)

        if current is None:
            cursor.execute(insert_sql, build_insert_tuple(record))
            inserted += 1
            existing_map[uuid] = record.copy()
            continue

        changes = diff_record(current, record)
        if not changes:
            continue

        set_clause = ", ".join(f"{col} = ?" for col in changes.keys())
        params = list(changes.values()) + [uuid]
        cursor.execute(
            f"UPDATE proposals_new SET {set_clause} WHERE uuid = ?", params
        )
        updated += 1
        existing_map[uuid].update(changes)

    conn.commit()
    cursor.close()
    conn.close()

    return {"processed": len(records), "inserted": inserted, "updated": updated}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    cursor, conn = dbConnect()
    cursor.close()
    fund_uuid = resolve_fund_uuid(conn, args.fund)
    conn.close()

    proposals = fetch_all_proposals(fund_uuid or "")
    normalized = [normalize_record(item) for item in proposals]
    normalized = [item for item in normalized if item is not None]
    logging.info("Fetched %s proposals after normalization (fund=%s)", len(normalized), fund_uuid or "all")
    summary = save_records(normalized)
    logging.info("DB save summary: %s", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
