import argparse
import csv
import json
import logging
import re
import sys
from typing import Any, Dict, List, Optional

import requests

API_URL = "https://www.catalystexplorer.com/api/v1/proposals"
PER_PAGE = 60
INCLUDE = "campaign,fund,team,meta_data"

COLUMN_ORDER = [
    "uuid",
    "fund_uuid",
    "campaign_uuid",
    "user_id",
    "fund_id",
    "challenge_id",
    "title",
    "user_name",
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
    "solution",
    "currency_symbol",
    "currency",
    "alignment_score",
    "feasibility_score",
    "auditability_score",
    "tags",
    "slug",
    "chain_proposal_id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export proposals from Catalyst Explorer API to CSV."
    )
    parser.add_argument(
        "--fund",
        default="",
        help="Fund identifier passed to filter[fund_id]. Leave blank for all funds.",
    )
    parser.add_argument(
        "--output",
        default="proposals_api.csv",
        help="Output CSV path.",
    )
    return parser.parse_args()


def is_uuid(value: str) -> bool:
    return re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        value,
        re.IGNORECASE,
    ) is not None


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


def normalize_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    campaign = raw.get("campaign") or {}
    fund = raw.get("fund") or {}
    team = extract_team(raw)
    meta = raw.get("meta_data") or {}

    record: Dict[str, Any] = {
        "uuid": raw.get("id"),
        "fund_uuid": fund.get("id"),
        "campaign_uuid": campaign.get("id"),
        "user_id": to_int(team.get("id") or raw.get("user_id")),
        "fund_id": to_int(raw.get("fund_id")),
        "challenge_id": to_int(raw.get("challenge_id") or raw.get("campaign_id")),
        "title": raw.get("title"),
        "user_name": team.get("name") or raw.get("user_name"),
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
        "solution": raw.get("solution"),
        "currency_symbol": raw.get("currency_symbol"),
        "currency": raw.get("currency"),
        "alignment_score": to_float(meta.get("alignment_score")),
        "feasibility_score": to_float(meta.get("feasibility_score")),
        "auditability_score": to_float(meta.get("auditability_score")),
        "tags": serialize_tags(raw.get("tags")),
        "slug": make_slug(raw.get("title")),
        "chain_proposal_id": meta.get("chain_proposal_id"),
    }

    return record


def write_csv(path: str, records: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMN_ORDER)
        writer.writeheader()
        for record in records:
            writer.writerow({column: record.get(column) for column in COLUMN_ORDER})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    fund_arg = args.fund.strip()
    if fund_arg and not is_uuid(fund_arg):
        logging.warning("Fund value is passed as-is: %s", fund_arg)

    proposals = fetch_all_proposals(fund_arg)
    normalized = [normalize_record(item) for item in proposals]
    normalized = [item for item in normalized if item is not None]

    write_csv(args.output, normalized)
    logging.info("Wrote %s rows to %s", len(normalized), args.output)
    print(json.dumps({"rows": len(normalized), "output": args.output}, ensure_ascii=False))


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
