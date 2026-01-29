import argparse
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from playwright.sync_api import sync_playwright

from db_connect import get_db
from parser import html_to_semantic_blocks


URL_TIMEOUT_MS = 30000
WAIT_TIMEOUT_MS = 10000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape proposal detail pages into proposals_new columns."
    )
    parser.add_argument(
        "--fund",
        type=int,
        default=None,
        help="Filter by fund_id (integer).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of proposals to scrape.",
    )
    parser.add_argument(
        "--id",
        type=str,
        default=None,
        help="Filter by uuid or catalyst_id (comma-separated).",
    )
    parser.add_argument(
        "--bat",
        action="store_true",
        help="Batch mode: update project_status only.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing data.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug info per proposal.",
    )
    return parser.parse_args()


def _parse_ids(value: Optional[str]) -> Tuple[List[str], List[int]]:
    if not value:
        return [], []
    parts = [part.strip() for part in value.split(",") if part.strip()]
    uuids: List[str] = []
    catalyst_ids: List[int] = []
    for part in parts:
        if part.isdigit():
            catalyst_ids.append(int(part))
        else:
            uuids.append(part)
    return uuids, catalyst_ids


def _safe_text(locator) -> str:
    if locator.count():
        return locator.first.inner_text().strip()
    return ""


def _parse_int(value: str) -> Optional[int]:
    if not value:
        return None
    text = value.strip()
    match = re.fullmatch(r"([\d,]+(?:\.\d+)?)([Mm])?", text)
    if match:
        number = float(match.group(1).replace(",", ""))
        if match.group(2):
            return int(round(number * 1_000_000))
        return int(round(number))
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _extract_currency(value: str) -> Tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    code = "".join(re.findall(r"[A-Za-z]+", value)).upper()
    if not code:
        return None, None
    symbol_map = {"ADA": "₳", "USD": "$", "USDM": "$"}
    return code, symbol_map.get(code)


def extract_metadata(page) -> Dict[str, Any]:
    proposal_id_text = _safe_text(
        page.locator("span.sc-95b88e77-4.CLJHW strong")
    ).lstrip("#")
    status_text = _safe_text(
        page.locator("a.sc-95b88e77-10.eAKgfG:has-text('Status:') strong")
    )
    country_text = _safe_text(
        page.locator("a.sc-95b88e77-10.eAKgfG:has-text('Country:') strong")
    )
    currency_text = _safe_text(page.locator("div.sc-d01be8b9-7.hQOaha strong"))
    currency_code, currency_symbol = _extract_currency(currency_text)
    milestones_link = ""
    if proposal_id_text:
        milestones_link = (
            f"https://milestones.projectcatalyst.io/projects/{proposal_id_text}"
        )

    return {
        "proposal_id": _parse_int(proposal_id_text),
        "status": status_text or None,
        "country": country_text or None,
        "currency": currency_code,
        "currency_symbol": currency_symbol,
        "milestones_link": milestones_link or None,
    }


def scrape_proposal(page, url: str, debug: bool = False) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    page.goto(url, wait_until="networkidle", timeout=URL_TIMEOUT_MS)

    buttons = page.locator("button").filter(has_text="Read more")
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        if btn.is_visible():
            btn.click()
            page.wait_for_timeout(300)

    page.wait_for_selector("div[aria-expanded='true'], main", timeout=WAIT_TIMEOUT_MS)
    metadata = extract_metadata(page)

    expanded = page.locator("div[aria-expanded='true']")
    raw_html_parts = []
    for i in range(expanded.count()):
        raw_html_parts.append(expanded.nth(i).inner_html())
    if raw_html_parts:
        raw_html = "\n".join(raw_html_parts)
    else:
        raw_html = page.locator("main").inner_html()

    team_section_html = ""
    team_section = page.locator("section#team")
    if team_section.count():
        team_section_html = team_section.first.evaluate("el => el.outerHTML")
    if team_section_html and team_section_html not in raw_html:
        raw_html = f"{raw_html}\n{team_section_html}" if raw_html else team_section_html

    semantic_blocks = html_to_semantic_blocks(raw_html)

    if debug:
        print(f"url: {url}")
        print(f"raw_html length: {len(raw_html)}")
        print(f"semantic_blocks: {len(semantic_blocks)}")

    return raw_html, semantic_blocks, metadata


def resolve_fund_uuid(fund_number: int) -> Optional[str]:
    candidates = {
        str(fund_number).strip().lower(),
        f"fund-{fund_number}".lower(),
        f"fund {fund_number}".lower(),
    }
    with get_db() as (cursor, _):
        for candidate in candidates:
            cursor.execute(
                "SELECT id FROM funds_new WHERE LOWER(slug) = ? OR LOWER(label) = ? OR LOWER(title) = ? LIMIT 1",
                [candidate, candidate, candidate],
            )
            row = cursor.fetchone()
            if row:
                return row["id"]
    return None


def fetch_targets(
    fund_uuid: Optional[str],
    limit: Optional[int],
    uuids: List[str],
    catalyst_ids: List[int],
    force: bool,
    bat: bool,
) -> List[Dict[str, Any]]:
    base_query = (
        "SELECT uuid, projectcatalyst_link "
        "FROM proposals_new "
        "WHERE projectcatalyst_link IS NOT NULL AND projectcatalyst_link <> '' "
    )
    params: List[Any] = []
    if not force and not bat:
        base_query += " AND (idea_raw_html IS NULL OR idea_raw_html = '')"
    if uuids or catalyst_ids:
        id_clauses = []
        if uuids:
            placeholders = ",".join(["?"] * len(uuids))
            id_clauses.append(f"uuid IN ({placeholders})")
            params.extend(uuids)
        if catalyst_ids:
            placeholders = ",".join(["?"] * len(catalyst_ids))
            id_clauses.append(f"catalyst_id IN ({placeholders})")
            params.extend(catalyst_ids)
        base_query += " AND (" + " OR ".join(id_clauses) + ")"
    if fund_uuid is not None:
        base_query += " AND fund_uuid = ?"
        params.append(fund_uuid)
    base_query += " ORDER BY uuid"
    if limit is not None:
        base_query += " LIMIT ?"
        params.append(limit)

    with get_db() as (cursor, _):
        cursor.execute(base_query, params)
        return cursor.fetchall()


def update_proposal(
    uuid: str,
    raw_html: str,
    semantic_blocks: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    bat: bool = False,
) -> None:
    if bat:
        update_query = """
            UPDATE proposals_new
            SET
                project_status = ?,
                currency = ?,
                currency_symbol = ?
            WHERE uuid = ?
        """
        params = [
            metadata.get("status"),
            metadata.get("currency"),
            metadata.get("currency_symbol"),
            uuid,
        ]
    else:
        semantic_json = json.dumps(semantic_blocks, ensure_ascii=True)
        update_query = """
            UPDATE proposals_new
            SET
                idea_raw_html = ?,
                idea_semantic_blocks = ?,
                catalyst_id = ?,
                project_status = ?,
                project_country = ?,
                currency = ?,
                currency_symbol = ?,
                milestones_link = ?
            WHERE uuid = ?
        """
        params = [
            raw_html,
            semantic_json,
            metadata.get("proposal_id"),
            metadata.get("status"),
            metadata.get("country"),
            metadata.get("currency"),
            metadata.get("currency_symbol"),
            metadata.get("milestones_link"),
            uuid,
        ]
    with get_db() as (cursor, conn):
        cursor.execute(update_query, params)
        conn.commit()



def run() -> None:
    args = parse_args()
    fund_uuid = None
    if args.fund is not None:
        fund_uuid = resolve_fund_uuid(args.fund)
        if not fund_uuid:
            print(f"No matching fund_uuid for fund number: {args.fund}")
            return
    uuids, catalyst_ids = _parse_ids(args.id)
    targets = fetch_targets(
        fund_uuid,
        args.limit,
        uuids,
        catalyst_ids,
        args.force,
        args.bat,
    )
    if not targets:
        print("No targets found.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for row in targets:
            uuid = row.get("uuid")
            url = row.get("projectcatalyst_link")
            if not uuid or not url:
                continue
            page = browser.new_page()
            try:
                raw_html, blocks, metadata = scrape_proposal(page, url, debug=args.debug)
                update_proposal(uuid, raw_html, blocks, metadata, bat=args.bat)
                print(f"updated: {uuid}")
            except Exception as exc:
                print(f"error: {uuid} ({url}) -> {exc}")
            finally:
                page.close()
        browser.close()


if __name__ == "__main__":
    run()
