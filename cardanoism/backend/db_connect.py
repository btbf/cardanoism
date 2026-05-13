import asyncio
import logging
import os
import re
import sys
import json
import mariadb
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple
from contextlib import contextmanager
from time import perf_counter
import reflex as rx
import dataclasses

# 概要冒頭の URL／リンクブロックを除去するための正規表現群。
# 順に適用 → 変化が無くなるまでループするので、複数パターンが連続していても剥がせる。
_LEADING_LINK_PATTERNS = [
    # **... URL/markdown link ...**  （太字内に URL 含むブロック。例: "**Proposal as pdf: [...](...)**"）
    re.compile(r"^\s*\*\*[^*\n]*?(?:https?://|\]\()[^*\n]*?\*\*\s*", re.IGNORECASE),
    # *... URL/markdown link ...*    （斜体内に URL 含むブロック）
    re.compile(r"^\s*\*[^*\n]*?(?:https?://|\]\()[^*\n]*?\*\s*", re.IGNORECASE),
    # **label** [text](url)          （太字ラベル + 直後のマークダウンリンク）
    re.compile(r"^\s*\*\*[^*\n]+?\*\*\s*\[[^\]\n]*\]\([^)\s]+\)\s*", re.IGNORECASE),
    # **label** url                  （太字ラベル + 直後の素 URL）
    re.compile(r"^\s*\*\*[^*\n]+?\*\*\s*https?://\S+\s*", re.IGNORECASE),
    # [text](url)                    （素のマークダウンリンク。短いラベル + コロンが先行する場合も許容）
    re.compile(r"^\s*(?:[^\[\n]{0,60}?:\s*)?\[[^\]\n]*\]\([^)\s]+\)\s*", re.IGNORECASE),
    # 素の URL                        （短いラベル + コロンが先行する場合も許容）
    re.compile(r"^\s*(?:[\w][^\n:]{0,60}?:\s*)?https?://\S+\s*", re.IGNORECASE),
]


def _strip_leading_urls(text: str) -> str:
    """文字列の先頭にある URL ／マークダウンリンクブロックを取り除く。
    "**Proposal as pdf: [URL](URL)** 本文..." のような典型ケース、および複数連続パターンに対応する。
    GA 一覧カードで abstract 冒頭の URL/リンクが line-clamp 領域を食い潰す問題を回避する用途。
    """
    if not text:
        return text
    while True:
        prev = text
        for pat in _LEADING_LINK_PATTERNS:
            text = pat.sub("", text, count=1)
        if text == prev:
            break
    return text.lstrip()

logger = logging.getLogger(__name__)
# Ensure debug logs appear even if the app does not configure logging.
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

POOL_SIZE = 10

# One-time warmup flag
_warmed_up = False

try:
    pool = mariadb.ConnectionPool(
        pool_name="cardanoism_pool",
        pool_size=POOL_SIZE,
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
    )
except mariadb.Error as e:
    logger.error("Error creating MariaDB pool: %s", e)
    sys.exit(1)

#Connect to MariaDB Platform
def dbConnect():
    try:
        conn = pool.get_connection()
    except mariadb.Error as e:
        print(f"Error getting connection from pool: {e}")
        sys.exit(1)

    #Get Cursor
    cursor = conn.cursor(dictionary=True)
    return cursor, conn

@contextmanager
def get_db():
    """Context manager that yields (cursor, conn) and always closes them."""
    cursor, conn = dbConnect()
    try:
        yield cursor, conn
    finally:
        try:
            cursor.close()
        finally:
            conn.close()


def warm_up():
    """Lightweight query to warm up connection pool/metadata."""
    try:
        with get_db() as (cursor, _):
            cursor.execute("SELECT 1")
            cursor.fetchone()
            logger.debug("Warm-up query executed.")
    except Exception as e:
        logger.debug("Warm-up query failed (non-fatal): %s", e)


def ensure_warm():
    """Ensure warm-up runs only once per process."""
    global _warmed_up
    if not _warmed_up:
        warm_up()
        _warmed_up = True

def get_fund_options() -> List[Dict[str, str]]:
    """Fetch fund select options (value=id, label=label) from funds_new.
    Fund 15 はカタリストページから一旦非表示にする。
    """
    try:
        with get_db() as (cursor, _):
            cursor.execute(
                """
                SELECT id, label
                FROM funds_new
                WHERE label IN ('Fund 12', 'Fund 13', 'Fund 14')
                ORDER BY launched_at DESC
                """
            )
            rows = cursor.fetchall()
            return [{"value": row["id"], "label": row.get("label") or row["id"]} for row in rows]
    except Exception as e:
        logger.error("Failed to load fund options: %s", e)
        return []


def normalize_fund_key(value: Any) -> str:
    """Normalize fund key/slug for matching (case-insensitive, strip fund- prefix)."""
    text = str(value or "").strip().lower()
    for prefix in ("fund-", "fund ", "fund"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.replace("_", "").replace(" ", "")


def format_count_display(value: Any) -> str:
    """Format counts with rounding rules for UI display."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0
    abs_number = abs(number)
    if abs_number >= 100_000_000:
        oku_value = round(number / 100_000_000, 2)
        oku_text = f"{oku_value:.2f}".rstrip("0").rstrip(".")
        return f"{oku_text}億"
    if abs_number >= 1_000_000:
        rounded = int(round(number / 1_000_000)) * 1_000_000
        man_value = int(round(rounded / 10_000))
        return f"{man_value}万"
    if abs_number >= 1_000:
        thousand_value = int(round(number / 1_000)) * 1_000
        return f"{thousand_value:,}"
    return f"{int(round(number)):,}"


def parse_semantic_blocks(value: Any) -> List[Dict[str, Any]]:
    """Parse idea_semantic_blocks_ja JSON into a list of dicts."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:
            return []
    try:
        parsed = json.loads(value)
    except Exception:
        logger.debug("Failed to parse idea_semantic_blocks_ja", exc_info=True)
        return []
    return parsed if isinstance(parsed, list) else []


def build_detail_query(include_raw: bool, include_ja: bool, include_ai: bool) -> str:
    """Build detail query with optional semantic block columns."""
    semantic_select = ""
    if include_raw:
        semantic_select += ",\n            p.idea_semantic_blocks"
    if include_ja:
        semantic_select += ",\n            p.idea_semantic_blocks_ja"
    if include_ai:
        semantic_select += ",\n            p.idea_semantic_blocks_ai"
    return f"""
        SELECT
            p.uuid,
            p.catalyst_id,
            p.fund_uuid,
            p.campaign_uuid,
            p.user_name,
            p.projectcatalyst_link,
            p.title,
            p.title_ja,
            p.problem,
            p.problem_ja,
            p.solution,
            p.solution_ja,
            p.milestones_link,
            p.amount_requested,
            p.amount_received,
            p.yes_votes_count,
            p.abstain_votes_count,
            p.unique_wallets,
            p.project_status,
            p.funding_status,
            p.currency_symbol,
            p.currency,
            p.tags,
            p.slug,
            p.alignment_score,
            p.feasibility_score,
            p.auditability_score,
            c.title as campaign_title,
            c.title_jp as campaign_title_ja,
            f.title as fund_title,
            pd.headline_problem_ja,
            pd.headline_solution_ja,
            pd.solution_ja as detail_solution_ja,
            pd.impact_ja,
            pd.capability_feasibility_ja,
            pd.project_milestones_ja,
            pd.resources_ja,
            pd.budget_costs_ja,
            pd.value_for_money_ja{semantic_select}
        FROM proposals_new p
        INNER JOIN campaigns_new c ON p.campaign_uuid = c.id
        LEFT JOIN funds_new f ON p.fund_uuid = f.id
        LEFT JOIN proposal_detail_new pd ON p.uuid = pd.uuid
        WHERE p.uuid = ?
        """


def build_proposal_query(include_semantic: bool) -> str:
    """Build proposal detail page query with optional idea_semantic_blocks_ja column."""
    semantic_select = ""
    return f"""
            SELECT p.*,
            c.title as campaign_title,
            c.title_jp as campaign_title_ja,
            f.title as fund_title,
            pd.title as proposal_title,
            pd.title_ja as proposal_title_ja,
            pd.headline_problem_ja,
            pd.applicant_name,
            pd.project_duration,
            pd.headline_solution_ja,
            pd.open_source,
            pd.tag,
            pd.solution_ja as detail_solution_ja,
            pd.impact,
            pd.impact_ja,
            pd.capability_feasibility,
            pd.capability_feasibility_ja,
            pd.project_milestones,
            pd.project_milestones_ja,
            pd.resources,
            pd.resources_ja,
            pd.budget_costs,
            pd.budget_costs_ja,
            pd.value_for_money,
            pd.value_for_money_ja{semantic_select}
            FROM proposals_new p
            INNER JOIN campaigns_new c
            ON p.campaign_uuid = c.id
            LEFT JOIN funds_new f
            ON p.fund_uuid = f.id
            INNER JOIN proposal_detail_new pd
            ON p.uuid = pd.uuid
            WHERE p.uuid = ?
            """


def fetch_funds() -> List[Dict[str, Any]]:
    """Load fund records for list/detail views."""
    try:
        with get_db() as (cursor, _):
            cursor.execute(
                """
                SELECT
                    id,
                    title,
                    label,
                    slug,
                    description,
                    status,
                    currency,
                    currency_symbol,
                    amount,
                    launched_at,
                    proposals_count,
                    funded_proposals_count,
                    completed_proposals_count,
                    hero_img_url,
                    banner_img_url
                FROM funds_new
                WHERE id IN (
                    SELECT DISTINCT fund_uuid
                    FROM proposals_new
                    WHERE fund_uuid IS NOT NULL
                )
                  AND (label IS NULL OR label <> 'Fund 15')
                ORDER BY launched_at DESC
                """
            )
            rows = cursor.fetchall()
            for row in rows:
                # Cache common bool-ish helpers to avoid Var truthiness in the UI layer
                row["has_label"] = bool(row.get("label"))
                row["has_title"] = bool(row.get("title"))
                row["has_description"] = bool(row.get("description"))
                row["has_slug"] = bool(row.get("slug"))
                row["has_id"] = bool(row.get("id"))
                # Precompute display fields to avoid client-side conditional issues
                label = row.get("label") or row.get("title") or "Fund"
                title = row.get("title") or label
                description = row.get("description") or "Fundごとの提案状況を確認できます。"
                try:
                    amount_comma = f"{int(float(row.get('amount') or 0)):,}"
                except Exception:
                    amount_comma = "-"

                row["display_label"] = label
                row["display_title"] = title
                row["display_description"] = description
                row["display_amount_comma"] = amount_comma
                row["display_currency_symbol"] = row.get("currency_symbol") or ""
                row["display_proposals"] = row.get("proposals_count") or 0
                row["display_funded"] = row.get("funded_proposals_count") or 0
                row["display_completed"] = row.get("completed_proposals_count") or 0
                row["display_status"] = row.get("status") or "active"

                slug = (row.get("slug") or "").strip()
                row_id = str(row.get("id") or "").strip()
                if slug:
                    row["path"] = f"/catalyst/funds/{slug}"
                elif row_id:
                    row["path"] = f"/catalyst/funds/{row_id}"
                else:
                    row["path"] = "/catalyst"
            return rows
    except Exception as e:
        logger.error("Failed to load funds list: %s", e)
        return []


def find_fund_record(identifier: str) -> Dict[str, Any]:
    """Find a single fund by slug/label/id; fallback to newest fund."""
    records = fetch_funds()
    if not records:
        return {}
    key_raw = str(identifier or "").strip()
    key_norm = normalize_fund_key(identifier)
    for record in records:
        record_id = str(record.get("id") or "").strip()
        if record_id and (record_id == key_raw):
            return record
        if normalize_fund_key(record.get("slug")) == key_norm:
            return record
        if normalize_fund_key(record.get("label")) == key_norm:
            return record
        if normalize_fund_key(record.get("title")) == key_norm:
            return record
    return records[0]
# @dataclasses.dataclass
# class ProposalsVar:
#     id: int
#     user_id: int
#     fund_id: int
#     challenge_id: int 
#     title: str
#     title_ja: str
#     ideascale_link: str
#     ideascale_user: str
#     ideascale_id: int
#     amount_requested: int
#     amount_received: int
#     project_status: str
#     funding_status: str
#     yes_votes_count: int
#     no_votes_count: int
#     abstain_votes_count: int
#     unique_wallets: int
#     problem: str
#     problem_ja: str
#     solution: str
#     solution_ja: str
#     currency_symbol: str
#     currency: str
#     alignment_score: float
#     feasibility_score: float
#     auditability_score: float
#     tags: str
#     challenge_title: str
#     challenge_title_ja: str
#     headline_problem_ja: str
#     applicant_name: str
#     project_duration: str
#     headline_solution_ja: str
#     open_source: str
#     tag: str
#     proposul_fund_percent: float
#     amount_requested_comma: str
#     yes_votes_count_comma: str
#     abstain_votes_count_comma: str
#     unique_wallets_comma: str
    

class AppState(rx.State):
    proposals: List[Dict[str, Any]] = []
    #proposals: List[Dict[str, ProposalsVar]] = []
    proposal_columns_cache: List[str] = []
    challenge_options: List[Dict[str, str]] = []
    current_page: int = 1
    items_per_page: int = 30
    page_number: list[int]
    pagenation_number: list[int]
    total_pages: int = 0
    total_items: int = 0
    inputed_value: str = ""
    start_page: int = 1
    end_page: int = 1
    middle_page: list[int] = []
    load: bool = False
    challenge_ids: List[str] = []
    fund_ids: List[str] = []
    funding_statuses: List[str] = []
    project_statuses: List[str] = []
    view_mode: str = "list"
    search_query: str = ""
    modal_open: bool = False
    modal_proposal: Dict[str, Any] = {}
    modal_semantic_blocks: List[Dict[str, Any]] = []
    modal_semantic_blocks_raw: List[Dict[str, Any]] = []
    modal_semantic_blocks_ja: List[Dict[str, Any]] = []
    modal_semantic_blocks_ai: List[Dict[str, Any]] = []
    modal_semantic_view: str = "ja"
    modal_loading: bool = False
    modal_pending_uuid: str = ""
    selected_proposal_uuid: str | None = None
    scroll_position: int = 0
    filter_params: Dict[str, Any] = {}
    last_list_path: str = ""
    fund_route_slug: str = ""
    fund_meta: Dict[str, Any] = {}
    fund_page_loading: bool = True
    
    def _default_filter_params(self) -> Dict[str, Any]:
        return {
            "funds": [],
            "challenges": [],
            "funding_statuses": [],
            "project_statuses": [],
        }

    def _sync_filter_params_defaults(self) -> None:
        if not isinstance(self.filter_params, dict):
            self.filter_params = self._default_filter_params()
            return
        defaults = self._default_filter_params()
        for key, value in defaults.items():
            self.filter_params.setdefault(key, value)

    def _history_state_payload(self) -> Dict[str, Any]:
        self._sync_filter_params_defaults()
        return {"search": self.search_query, "filter": self.filter_params}

    def _history_replace_script(self) -> rx.event.EventHandler:
        payload = json.dumps(self._history_state_payload(), ensure_ascii=True)
        return rx.call_script(
            "const state = "
            f"{payload};"
            "if (window.proposalModalReplace) {"
            "  window.proposalModalReplace(state);"
            "} else {"
            "  history.replaceState("
            "    { scrollY: window.scrollY, search: state.search, filter: state.filter },"
            "    '',"
            "    window.location.pathname + window.location.search"
            "  );"
            "}"
        )

    def _history_push_script(self, uuid: str) -> rx.event.EventHandler | None:
        if not uuid:
            return None
        payload = json.dumps(self._history_state_payload(), ensure_ascii=True)
        return rx.call_script(
            "const state = "
            f"{payload};"
            "if (window.proposalModalPush) {"
            f"  window.proposalModalPush({json.dumps(uuid)}, state);"
            "} else {"
            "  history.pushState("
            "    { scrollY: window.scrollY, search: state.search, filter: state.filter },"
            "    '',"
            f"    `/catalyst/proposals/{uuid}`"
            "  );"
            "}"
        )

    def _apply_filter_params(self) -> None:
        self._sync_filter_params_defaults()
        self.fund_ids = self._normalize_selection(self.filter_params.get("funds"))
        self.challenge_ids = self._normalize_selection(self.filter_params.get("challenges"))
        self.funding_statuses = self._normalize_selection(self.filter_params.get("funding_statuses"))
        self.project_statuses = self._normalize_selection(self.filter_params.get("project_statuses"))

    @rx.var
    def selected_fund_filters(self) -> List[Dict[str, str]]:
        self._sync_filter_params_defaults()
        return self.filter_params.get("funds", [])

    @rx.var
    def selected_challenge_filters(self) -> List[Dict[str, str]]:
        self._sync_filter_params_defaults()
        return self.filter_params.get("challenges", [])

    @rx.var
    def selected_funding_status_filters(self) -> List[Dict[str, str]]:
        self._sync_filter_params_defaults()
        return self.filter_params.get("funding_statuses", [])

    @rx.var
    def selected_project_status_filters(self) -> List[Dict[str, str]]:
        self._sync_filter_params_defaults()
        return self.filter_params.get("project_statuses", [])

    def _reset_query_state(self):
        """Reset filters and pagination before a fresh query."""
        self.proposals = []
        self.challenge_ids = []
        self.fund_ids = []
        self.funding_statuses = []
        self.project_statuses = []
        self.inputed_value = ""
        self.current_page = 1
        self.items_per_page = 30
        self.page_number = []
        self.pagenation_number = []
        self.total_pages = 0
        self.total_items = 0
        self.start_page = 1
        self.end_page = 1
        self.middle_page = []
        self.view_mode = "list"
        self.search_query = ""
        self.modal_open = False
        self.modal_proposal = {}
        self.modal_loading = False
        self.modal_pending_uuid = ""
        self.selected_proposal_uuid = None
        self.scroll_position = 0
        self.filter_params = self._default_filter_params()
        self.last_list_path = ""
        self.load = False
        self.fund_meta = {}
        self.fund_route_slug = ""
        self.fund_page_loading = True
    
    def on_load(self):
        # super().__init__()
        ensure_warm()
        logger.debug("AppState on_load start")
        self._reset_query_state()
        # preload challenge options (all funds)
        self.load_challenge_options()
        self.data_fetch()
        return self._history_replace_script()

    def load_detail_page(self):
        """Initialize state for proposal detail pages based on route param."""
        self._reset_query_state()
        self.modal_proposal = {}
        self.modal_loading = True
        path = self.router.url.path or ""
        path_parts = [part for part in path.split("/") if part]
        target_uuid = path_parts[-1] if path_parts else ""
        self.modal_pending_uuid = target_uuid
        self.selected_proposal_uuid = target_uuid or None
        if not target_uuid:
            self.modal_loading = False
            return self._history_replace_script()
        self.load_modal_detail(target_uuid)
        return self._history_replace_script()

    def load_fund_page(self):
        """Initialize state for fund detail pages based on route param."""
        self._reset_query_state()
        # Clear any leftover fund filter/results before resolving the new fund.
        self.fund_ids = []
        self.proposals = []
        self.fund_page_loading = True
        self.load = False
        path = self.router.url.path or ""
        path_parts = [part for part in path.split("/") if part]
        self.fund_route_slug = path_parts[-1] if path_parts else ""
        self.fund_meta = find_fund_record(self.fund_route_slug)
        fund_id = self.fund_meta.get("id")
        if not fund_id:
            self.load = True
            self.fund_page_loading = False
            return self._history_replace_script()
        try:
            self.fund_meta["amount_comma"] = f"{int(float(self.fund_meta.get('amount') or 0)):,}"
        except Exception:
            self.fund_meta["amount_comma"] = ""
        self.fund_ids = [str(fund_id)]
        self.filter_params["funds"] = [
            {
                "value": str(fund_id),
                "label": self.fund_meta.get("label")
                or self.fund_meta.get("title")
                or str(fund_id),
            }
        ]
        self.load_challenge_options(self.fund_ids)
        self.data_fetch()
        self.fund_page_loading = False
        return self._history_replace_script()
        
    def data_fetch(self):
        t0 = perf_counter()
        with get_db() as (cursor, conn):
            logger.debug("DB connection opened: cursor=%s, conn=%s", cursor, conn)
            
            base_from = """
        FROM proposals_new p
        INNER JOIN campaigns_new c
            ON p.campaign_uuid = c.id
        LEFT JOIN funds_new f
            ON p.fund_uuid = f.id
        """

            data_query = """
        SELECT
            p.id,
            p.uuid,
            p.catalyst_id,
            p.fund_uuid,
            p.campaign_uuid,
            p.user_name,
            p.title,
            p.title_ja,
            p.amount_requested,
            p.amount_received,
            p.yes_votes_count,
            p.abstain_votes_count,
            p.unique_wallets,
            p.project_status,
            p.funding_status,
            p.milestones_link,
            p.problem_ja,
            p.solution_ja,
            p.currency_symbol,
            p.currency,
            p.tags,
            p.slug,
            c.title as campaign_title,
            c.title_jp as campaign_title_ja,
            f.title as fund_title
        """
            data_query += base_from
        
            where_conditions: List[str] = ["1=1"]
            params: List[Any] = []
            # Fund 15 はカタリストページから非表示にする（一時的措置）
            where_conditions.append("(f.label IS NULL OR f.label <> 'Fund 15')")
            if self.fund_ids:
                clause, clause_params = self._build_in_clause("p.fund_uuid", self.fund_ids)
                where_conditions.append(clause)
                params.extend(clause_params)
            if self.challenge_ids:
                clause, clause_params = self._build_in_clause("p.campaign_uuid", self.challenge_ids)
                where_conditions.append(clause)
                params.extend(clause_params)
            if self.funding_statuses:
                clause, clause_params = self._build_in_clause("p.funding_status", self.funding_statuses)
                where_conditions.append(clause)
                params.extend(clause_params)
            if self.project_statuses:
                clause, clause_params = self._build_in_clause("p.project_status", self.project_statuses)
                where_conditions.append(clause)
                params.extend(clause_params)
            where_query = f" WHERE {' AND '.join(where_conditions)}"
            data_query += where_query
                
            search_clause = ""
            search_params: List[Any] = []
            if self.inputed_value:
                # LIKE検索対象をインデックス（FULLTEXT含む）設定済みカラムに限定
                proposal_like_columns = [
                    "user_name",
                    "catalyst_id",
                    "title",
                    "title_ja",
                    "problem",
                    "problem_ja",
                    "solution",
                    "solution_ja",
                    "tags",
                ]
                search_value = f"%{str(self.inputed_value)}%"
                where_clause_parts = [f"p.{column} LIKE ?" for column in proposal_like_columns]
                search_clause = " OR ".join(where_clause_parts)
                search_params = [search_value] * len(where_clause_parts)
                data_query += f" AND ({search_clause})"
            data_params = params + search_params
                    
            asc_query = " ORDER BY fund_title DESC,CASE WHEN p.funding_status LIKE 'funded' THEN 0 ELSE 1 END, p.yes_votes_count DESC"
            limit_query = f" LIMIT {self.items_per_page} OFFSET {(self.current_page - 1) * self.items_per_page}"
            
            #データ取得クエリ
            query = data_query + asc_query + limit_query
            tq = perf_counter()
            logger.debug("Executing data query: %s | params=%s", query, data_params)
            cursor.execute(query, data_params)
            self.proposals = cursor.fetchall()
            t_query = perf_counter()
            # add computed fund percent for UI use
            for p in self.proposals:
                p["fund_title"] = p.get("fund_title") or p.get("fund_uuid") or ""
                p["campaign_title_ja"] = p.get("campaign_title_ja") or p.get("campaign_title") or ""
                # format numbers for display
                p["amount_requested_comma"] = f"{int(p.get('amount_requested') or 0):,}"
                p["yes_votes_count_comma"] = f"{int(p.get('yes_votes_count') or 0):,}"
                p["abstain_votes_count_comma"] = f"{int(p.get('abstain_votes_count') or 0):,}"
                p["unique_wallets_comma"] = f"{int(p.get('unique_wallets') or 0):,}"
                p["yes_votes_count_display"] = format_count_display(p.get("yes_votes_count"))
                p["abstain_votes_count_display"] = format_count_display(p.get("abstain_votes_count"))
                p["unique_wallets_display"] = format_count_display(p.get("unique_wallets"))
                try:
                    amt_req = float(p.get("amount_requested") or 0)
                    amt_recv = float(p.get("amount_received") or 0)
                    p["fund_percent"] = round((amt_recv / amt_req) * 100, 1) if amt_req else 0.0
                except Exception:
                    p["fund_percent"] = 0.0
            t_format = perf_counter()

            # 総件数を常に取得
            count_query = "SELECT COUNT(*) AS total_items " + base_from + where_query
            if self.inputed_value:
                count_query += f" AND ({search_clause})"
            count_params = params + search_params
            logger.debug("Executing count query: %s | params=%s", count_query, count_params)
            cursor.execute(count_query, count_params)
            total_row = cursor.fetchone() or {}
            t_count = perf_counter()
            try:
                self.total_items = int(total_row.get("total_items", 0))
            except Exception:
                self.total_items = 0
            logger.debug(
                "Timing: query=%.3fms format=%.3fms count=%.3fms total=%.3fms | total items=%s",
                (t_query - tq) * 1000,
                (t_format - t_query) * 1000,
                (t_count - t_format) * 1000,
                (t_count - t0) * 1000,
                self.total_items,
            )
        
        #ページネーション変数
        self.total_pages = (self.total_items + self.items_per_page - 1) // self.items_per_page
        self.start_page = max(1, self.current_page - 3)
        self.end_page = min(self.total_pages, self.current_page + 3)
        self.middle_page = list(range(self.start_page, self.end_page + 1))
        logger.debug("Pagination pages: %s", self.middle_page)
        self.load = True
    
    
    #--------フィルター関数群----------------
    def _build_in_clause(self, column: str, values: List[str]) -> Tuple[str, List[str]]:
        sanitized = [str(v) for v in values if v]
        if not sanitized:
            return "1=1", []
        placeholders = ", ".join(["?"] * len(sanitized))
        return f"{column} IN ({placeholders})", sanitized
    
    def _normalize_selection(self, value: Any) -> List[str]:
        selections: List[str] = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("value"):
                    selections.append(str(item["value"]))
        elif isinstance(value, dict) and value.get("value"):
            selections.append(str(value["value"]))
        return selections
    
    def _refresh_after_filter_change(self):
        self.current_page = 1
        self.data_fetch()

    def set_view_mode(self, mode: str):
        """Switch between list and grid views."""
        self.view_mode = mode

    def open_modal(self, proposal: Dict[str, Any]):
        """Open detail modal then fetch full detail in a follow-up event."""
        base_proposal = proposal or {}
        base_proposal.setdefault("idea_semantic_blocks", [])
        base_proposal.setdefault("idea_semantic_blocks_ja", [])
        base_proposal.setdefault("idea_semantic_blocks_ai", [])
        self.modal_loading = True
        self.modal_open = True
        self.modal_pending_uuid = base_proposal.get("uuid", "")
        self.selected_proposal_uuid = self.modal_pending_uuid or None
        self.modal_proposal = base_proposal
        self.modal_semantic_blocks_raw = base_proposal.get("idea_semantic_blocks") or []
        self.modal_semantic_blocks_ja = base_proposal.get("idea_semantic_blocks_ja") or []
        self.modal_semantic_blocks_ai = base_proposal.get("idea_semantic_blocks_ai") or []
        self.modal_semantic_blocks = self.modal_semantic_blocks_ja
        self.last_list_path = self.router.url.path or ""
        return self._history_push_script(self.modal_pending_uuid)

    def load_modal_detail(self, uuid: str | None = None):
        """Requery full detail for modal after open."""
        target_uuid = uuid or self.modal_pending_uuid
        if not target_uuid:
            self.modal_loading = False
            return

        detail_query = build_detail_query(include_raw=True, include_ja=True, include_ai=True)

        try:
            with get_db() as (cursor, conn):
                try:
                    cursor.execute(detail_query, [target_uuid])
                except mariadb.ProgrammingError as e:
                    error_text = str(e)
                    if "Unknown column" in error_text and "idea_semantic_blocks" in error_text:
                        include_raw = "idea_semantic_blocks'" not in error_text
                        include_ja = "idea_semantic_blocks_ja" not in error_text
                        include_ai = "idea_semantic_blocks_ai" not in error_text
                        cursor.execute(
                            build_detail_query(
                                include_raw=include_raw,
                                include_ja=include_ja,
                                include_ai=include_ai,
                            ),
                            [target_uuid],
                        )
                    else:
                        raise
                row = cursor.fetchone()
                if row:
                    row = {**(self.modal_proposal or {}), **row}
                    row["idea_semantic_blocks"] = parse_semantic_blocks(row.get("idea_semantic_blocks"))
                    row["idea_semantic_blocks_ja"] = parse_semantic_blocks(row.get("idea_semantic_blocks_ja"))
                    row["idea_semantic_blocks_ai"] = parse_semantic_blocks(row.get("idea_semantic_blocks_ai"))
                    self.modal_semantic_blocks_raw = row.get("idea_semantic_blocks") or []
                    self.modal_semantic_blocks_ja = row.get("idea_semantic_blocks_ja") or []
                    self.modal_semantic_blocks_ai = row.get("idea_semantic_blocks_ai") or []
                    self.modal_semantic_blocks = self.modal_semantic_blocks_ja
                    row["fund_title"] = row.get("fund_title") or row.get("fund_uuid") or ""
                    row["campaign_title_ja"] = row.get("campaign_title_ja") or row.get("campaign_title") or ""
                    row["amount_requested_comma"] = f"{int(row.get('amount_requested') or 0):,}"
                    row["yes_votes_count_display"] = format_count_display(row.get("yes_votes_count"))
                    row["abstain_votes_count_display"] = format_count_display(row.get("abstain_votes_count"))
                    row["unique_wallets_display"] = format_count_display(row.get("unique_wallets"))
                    try:
                        amt_req = float(row.get("amount_requested") or 0)
                        amt_recv = float(row.get("amount_received") or 0)
                        row["fund_percent"] = round((amt_recv / amt_req) * 100, 1) if amt_req else 0.0
                    except Exception:
                        row["fund_percent"] = 0.0
                    self.modal_proposal = row
                else:
                    self.modal_proposal = self.modal_proposal or {}
        except Exception as e:
            logger.exception("Failed to load modal proposal (uuid=%s): %s", target_uuid, e)
        finally:
            self.modal_loading = False
            self.modal_pending_uuid = ""

    def close_modal(self):
        """Close detail modal."""
        self.modal_open = False
        self.modal_proposal = {}
        self.modal_semantic_blocks = []
        self.modal_semantic_blocks_raw = []
        self.modal_semantic_blocks_ja = []
        self.modal_semantic_blocks_ai = []
        self.modal_loading = False
        self.modal_pending_uuid = ""
        self.selected_proposal_uuid = None
        target_path = self.last_list_path or "/catalyst"
        return rx.call_script(
            "if (window.location.pathname.startsWith('/catalyst/proposals/')) {"
            "  if (history.state) {"
            "    history.back();"
            "  } else {"
            f"    history.replaceState(null, '', '{target_path}');"
            "  }"
            "}"
        )

    def set_modal_semantic_view(self, view: str):
        self.modal_semantic_view = view
        if view == "raw":
            self.modal_semantic_blocks = self.modal_semantic_blocks_raw
        elif view == "ai":
            self.modal_semantic_blocks = self.modal_semantic_blocks_ai
        else:
            self.modal_semantic_blocks = self.modal_semantic_blocks_ja

    def reset_semantic_view_for_language(self, language: str):
        default_view = "raw" if language == "en" else "ja"
        self.set_modal_semantic_view(default_view)

    def on_popstate(self, event_state: Dict[str, Any] | None):
        event_state = event_state or {}
        filters_changed = False

        if self.modal_open:
            self.modal_open = False
            self.modal_proposal = {}
            self.modal_loading = False
            self.modal_pending_uuid = ""
            self.selected_proposal_uuid = None

        if "search" in event_state:
            incoming_search = event_state.get("search") or ""
            if incoming_search != self.search_query:
                self.search_query = incoming_search
                self.inputed_value = incoming_search
                filters_changed = True

        if "filter" in event_state:
            incoming_filters = event_state.get("filter") or self._default_filter_params()
            if incoming_filters != self.filter_params:
                self.filter_params = incoming_filters
                self._sync_filter_params_defaults()
                self._apply_filter_params()
                self.load_challenge_options(self.fund_ids)
                filters_changed = True

        if "scrollY" in event_state:
            try:
                self.scroll_position = int(event_state.get("scrollY") or 0)
            except Exception:
                self.scroll_position = 0

        if filters_changed:
            self.current_page = 1
            self.data_fetch()

        return rx.call_script(
            "if (window.location.pathname.startsWith('/catalyst/proposals/')) {"
            "  window.location.reload();"
            "  return;"
            "}"
            "if (history.state && history.state.scrollY !== undefined) {"
            "  window.scrollTo(0, history.state.scrollY);"
            "}"
        )
    
    def set_selected_chllenge_value(self, value):
        logger.debug("Challenge filter change: %s", value)
        self.challenge_ids = self._normalize_selection(value)
        self._sync_filter_params_defaults()
        self.filter_params["challenges"] = value or []
        self._refresh_after_filter_change()
        return self._history_replace_script()
    
    def set_selected_fund_value(self, value):
        self.fund_ids = self._normalize_selection(value)
        self._sync_filter_params_defaults()
        self.filter_params["funds"] = value or []
        # reload challenge options based on selected funds
        self.load_challenge_options(self.fund_ids)
        self._refresh_after_filter_change()
        return self._history_replace_script()
        
    def set_selected_fundingStatus_value(self, value):
        self.funding_statuses = self._normalize_selection(value)
        self._sync_filter_params_defaults()
        self.filter_params["funding_statuses"] = value or []
        self._refresh_after_filter_change()
        return self._history_replace_script()
    
    def set_selected_projectStatus_value(self, value):
        self.project_statuses = self._normalize_selection(value)
        self._sync_filter_params_defaults()
        self.filter_params["project_statuses"] = value or []
        self._refresh_after_filter_change()
        return self._history_replace_script()
        
    def set_inputed_value(self, value: str):
        self.inputed_value = value
        self.search_query = value
        self.current_page = 1
        # call directly; UI debounce should be handled on the client side
        self.data_fetch()
        return self._history_replace_script()
    
    def load_challenge_options(self, fund_ids: List[str] | None = None):
        # Show no challenges until a fund is selected
        if not fund_ids:
            self.challenge_options = []
            return
        params: List[Any] = []
        query = """
            SELECT id, label, title, title_jp, fund_uuid, launched_at
            FROM campaigns_new
        """
        clause, clause_params = self._build_in_clause("fund_uuid", fund_ids)
        query += f" WHERE {clause}"
        params.extend(clause_params)
        query += " ORDER BY launched_at DESC"
        try:
            with get_db() as (cursor, _):
                cursor.execute(query, params)
                rows = cursor.fetchall()
                options: List[Dict[str, str]] = []
                for row in rows:
                    label = row.get("label") or row.get("title_jp") or row.get("title") or ""
                    options.append({"value": row["id"], "label": label})
                self.challenge_options = options
        except Exception as e:
            logger.error("Failed to load challenge options: %s", e)
            self.challenge_options = []
        
    #--------------------------------------------------
    
    #--------ページネーション関数群----------------------
    
    def go_to_page(self, page: int):
        self.current_page = page
        self.data_fetch()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")

    def set_page(self, page: int):
        if 1 <= page <= self.total_pages:
            self.current_page = page
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")
            
            
    
    #--------------------------------------------------
            
class ProposalAppState(rx.State):
    proposal: List[Dict[str, Any]] = []
    semantic_blocks: List[Dict[str, Any]] = []
    semantic_blocks_raw: List[Dict[str, Any]] = []
    semantic_blocks_ja: List[Dict[str, Any]] = []
    semantic_blocks_ai: List[Dict[str, Any]] = []
    semantic_view: str = "ja"
    ideascale_id: str
    load: bool = False
    
    def on_load(self):
        path = self.router.url.path or ""
        path_parts = [part for part in path.split("/") if part]
        self.ideascale_id = path_parts[-1] if path_parts else ""
        # UUID前提になったため数値チェックは不要だが互換のため残しつつ同処理
        if self.ideascale_id.isdecimal():
            self.data_fetch()
        else:
            self.data_fetch()
            # self.proposal = ""
        
    def data_fetch(self):
        with get_db() as (cursor, conn):
            logger.debug("AppState data_fetch start")
            logger.debug("DB connection opened: cursor=%s, conn=%s", cursor, conn)
            
            proposal_query = build_proposal_query(include_semantic=True)
            
            logger.debug("Executing proposal query: %s | params=%s", proposal_query, [self.ideascale_id])
            try:
                cursor.execute(proposal_query, [self.ideascale_id])
            except mariadb.ProgrammingError as e:
                if "Unknown column" in str(e) and "idea_semantic_blocks_ja" in str(e):
                    cursor.execute(build_proposal_query(include_semantic=False), [self.ideascale_id])
                else:
                    raise
            self.proposal = cursor.fetchall()
            for p in self.proposal:
                p["idea_semantic_blocks"] = parse_semantic_blocks(p.get("idea_semantic_blocks"))
                p["idea_semantic_blocks_ja"] = parse_semantic_blocks(p.get("idea_semantic_blocks_ja"))
                p["idea_semantic_blocks_ai"] = parse_semantic_blocks(p.get("idea_semantic_blocks_ai"))
                p["fund_title"] = p.get("fund_title") or p.get("fund_uuid") or ""
                p["campaign_title_ja"] = p.get("campaign_title_ja") or p.get("campaign_title") or ""
                p["amount_requested_comma"] = f"{int(p.get('amount_requested') or 0):,}"
                p["yes_votes_count_comma"] = f"{int(p.get('yes_votes_count') or 0):,}"
                p["abstain_votes_count_comma"] = f"{int(p.get('abstain_votes_count') or 0):,}"
                p["unique_wallets_comma"] = f"{int(p.get('unique_wallets') or 0):,}"
                p["yes_votes_count_display"] = format_count_display(p.get("yes_votes_count"))
                p["abstain_votes_count_display"] = format_count_display(p.get("abstain_votes_count"))
                p["unique_wallets_display"] = format_count_display(p.get("unique_wallets"))
                try:
                    amt_req = float(p.get("amount_requested") or 0)
                    amt_recv = float(p.get("amount_received") or 0)
                    p["fund_percent"] = round((amt_recv / amt_req) * 100, 1) if amt_req else 0.0
                except Exception:
                    p["fund_percent"] = 0.0
            if self.proposal:
                self.semantic_blocks_raw = self.proposal[0].get("idea_semantic_blocks", [])
                self.semantic_blocks_ja = self.proposal[0].get("idea_semantic_blocks_ja", [])
                self.semantic_blocks_ai = self.proposal[0].get("idea_semantic_blocks_ai", [])
                self.semantic_blocks = self.semantic_blocks_ja
            else:
                self.semantic_blocks_raw = []
                self.semantic_blocks_ja = []
                self.semantic_blocks_ai = []
                self.semantic_blocks = []
            self.load = True
            logger.debug("Proposal detail loaded: %s", self.proposal)

    def set_semantic_view(self, view: str):
        self.semantic_view = view
        if view == "raw":
            self.semantic_blocks = self.semantic_blocks_raw
        elif view == "ai":
            self.semantic_blocks = self.semantic_blocks_ai
        else:
            self.semantic_blocks = self.semantic_blocks_ja


class FundListState(rx.State):
    funds: List[Dict[str, Any]] = []
    load: bool = False

    def on_load(self):
        self.load = False
        self.funds = fetch_funds()
        self.load = True


# ─── Governance Actions ───────────────────────────────────────────────────────

_GA_STATUS_SQL = (
    "CASE"
    " WHEN enacted_epoch IS NOT NULL THEN 'enacted'"
    " WHEN ratified_epoch IS NOT NULL THEN 'ratified'"
    " WHEN dropped_epoch IS NOT NULL THEN 'dropped'"
    " WHEN expired_epoch IS NOT NULL THEN 'expired'"
    " ELSE 'active'"
    " END"
)

_GA_STATUS_SQL_GA = (
    "CASE"
    " WHEN ga.enacted_epoch IS NOT NULL THEN 'enacted'"
    " WHEN ga.ratified_epoch IS NOT NULL THEN 'ratified'"
    " WHEN ga.dropped_epoch IS NOT NULL THEN 'dropped'"
    " WHEN ga.expired_epoch IS NOT NULL THEN 'expired'"
    " ELSE 'active'"
    " END"
)

_GA_TYPE_LABELS: Dict[str, str] = {
    "ParameterChange":    "プロトコル変更",
    "TreasuryWithdrawals": "国庫引き出し",
    "HardForkInitiation": "ハードフォーク",
    "InfoAction":         "情報提案",
    "NewCommittee":       "委員会変更",
    "NewConstitution":    "新憲法",
    "NoConfidence":       "不信任",
}

_GA_TYPE_COLORS: Dict[str, str] = {
    "ParameterChange":    "blue",
    "TreasuryWithdrawals": "amber",
    "HardForkInitiation": "tomato",
    "InfoAction":         "gray",
    "NewCommittee":       "violet",
    "NewConstitution":    "green",
    "NoConfidence":       "crimson",
}


# ネットワーク別エポック長（notify_worker.py と同じ定義）
_EPOCH_SECONDS: dict[str, int] = {
    "mainnet": 432_000,
    "preprod": 432_000,
    "preview":  86_400,
}
_KOIOS_NETWORK = os.getenv("KOIOS_NETWORK", "mainnet").lower()
_EPOCH_DURATION = timedelta(seconds=_EPOCH_SECONDS.get(_KOIOS_NETWORK, 432_000))


# 日付表示は JST に固定（日本人ユーザー想定）
_DISPLAY_TZ = timezone(timedelta(hours=9))
_DISPLAY_TZ_LABEL = "JST"


def _epoch_to_display(epoch, ref_epoch, ref_dt: datetime | None) -> str:
    """エポック番号を 'Epoch NNN（YYYY/MM/DD JST）' 形式に変換する。
    ref_epoch/ref_dt（block_time, UTC）を基準に差分×エポック長で日付を算出し、
    JST に変換した上で TZ 略語を付与する。
    """
    if epoch is None:
        return ""
    try:
        n = int(epoch)
        if ref_dt is not None and ref_epoch is not None:
            dt = ref_dt + _EPOCH_DURATION * (n - int(ref_epoch))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_local = dt.astimezone(_DISPLAY_TZ)
            return f"Epoch {n}（{dt_local.strftime('%Y/%m/%d')} {_DISPLAY_TZ_LABEL}）"
        return f"Epoch {n}"
    except (ValueError, TypeError):
        return str(epoch)


def _epoch_to_date(epoch, ref_epoch, ref_dt: datetime | None) -> str:
    """エポック番号を日付だけ 'YYYY/MM/DD JST' 形式に変換する。

    Epoch 番号を出さず、ダッシュボードの未投票/締切 GA バッジのように
    限られたスペースで「いつまで」だけ示したい場面で使う。
    """
    if epoch is None or ref_dt is None or ref_epoch is None:
        return ""
    try:
        n = int(epoch)
        dt = ref_dt + _EPOCH_DURATION * (n - int(ref_epoch))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_local = dt.astimezone(_DISPLAY_TZ)
        return f"{dt_local.strftime('%Y/%m/%d')} {_DISPLAY_TZ_LABEL}"
    except (ValueError, TypeError):
        return ""


def _attach_voting_summary(row: Dict[str, Any], protocol_params: dict | None) -> None:
    """行に voting_summary 表示用フィールドを追加する。
    row に drep_yes_pct / pool_yes_pct / committee_yes_pct 等が含まれている想定。
    見つからなければデフォルト（空値）を入れる。
    """
    from cardanoism.backend.params_db import thresholds_for_type, voters_for_type

    def _pct(v, default=0.0):
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    ptype = row.get("proposal_type") or ""
    thresholds = thresholds_for_type(ptype, protocol_params or {})
    voters = voters_for_type(ptype)

    drep_yes = _pct(row.get("drep_yes_pct"))
    drep_no = _pct(row.get("drep_no_pct"))
    pool_yes = _pct(row.get("pool_yes_pct"))
    pool_no = _pct(row.get("pool_no_pct"))
    cc_yes = _pct(row.get("committee_yes_pct"))
    cc_no = _pct(row.get("committee_no_pct"))

    has_any = (row.get("drep_yes_pct") is not None
               or row.get("pool_yes_pct") is not None
               or row.get("committee_yes_pct") is not None)

    def _th_pct(role):
        t = thresholds.get(role)
        return round(float(t) * 100.0, 1) if t is not None else None

    drep_th = _th_pct("drep")
    pool_th = _th_pct("pool")
    cc_th = _th_pct("committee")

    def _status(yes, th):
        if th is None:
            return "none"
        return "passed" if yes >= th else "failed"

    def _applicable(role):
        v = voters.get(role, True)
        if v is True:
            return "yes"
        if v is False:
            return "no"
        return str(v)

    def _donut(yes, no):
        # 色覚多様性対応: 賛成=青 / 反対=オレンジ / 棄権=グレー (Wong 2011 パレット系)
        y_end = yes
        n_end = yes + no
        return (
            f"conic-gradient("
            f"var(--blue-9) 0% {y_end:.2f}%, "
            f"var(--orange-9) {y_end:.2f}% {n_end:.2f}%, "
            f"var(--gray-5) {n_end:.2f}% 100%)"
        )

    row.update({
        "has_voting_summary": "1" if has_any else "",
        "drep_yes_pct":       f"{drep_yes:.1f}",
        "drep_yes_pct_donut": f"{drep_yes:.0f}",
        "drep_no_pct":        f"{drep_no:.1f}",
        "drep_abstain_pct":   f"{max(0.0, 100.0 - drep_yes - drep_no):.1f}",
        "drep_threshold_pct": f"{drep_th:.1f}" if drep_th is not None else "",
        "drep_status":        _status(drep_yes, drep_th),
        "drep_donut_bg":      _donut(drep_yes, drep_no),
        "drep_applicable":    _applicable("drep"),
        "pool_yes_pct":       f"{pool_yes:.1f}",
        "pool_yes_pct_donut": f"{pool_yes:.0f}",
        "pool_no_pct":        f"{pool_no:.1f}",
        "pool_abstain_pct":   f"{max(0.0, 100.0 - pool_yes - pool_no):.1f}",
        "pool_threshold_pct": f"{pool_th:.1f}" if pool_th is not None else "",
        "pool_status":        _status(pool_yes, pool_th),
        "pool_donut_bg":      _donut(pool_yes, pool_no),
        "pool_applicable":    _applicable("pool"),
        "cc_yes_pct":         f"{cc_yes:.1f}",
        "cc_yes_pct_donut":   f"{cc_yes:.0f}",
        "cc_no_pct":          f"{cc_no:.1f}",
        "cc_abstain_pct":     f"{max(0.0, 100.0 - cc_yes - cc_no):.1f}",
        "cc_threshold_pct":   f"{cc_th:.1f}" if cc_th is not None else "",
        "cc_status":          _status(cc_yes, cc_th),
        "cc_donut_bg":        _donut(cc_yes, cc_no),
        "cc_applicable":      _applicable("committee"),
    })


def _format_ga_row(row: Dict[str, Any], fiat_rate: Dict[str, float] | None = None) -> Dict[str, Any]:
    """governance_actions 行にUI表示用フィールドを追加する。
    fiat_rate に {"ada_jpy": float, "ada_usd": float} を渡すと withdrawal の JPY/USD 文字列も生成する。
    """
    from cardanoism.backend.price import format_ada, format_jpy_short, format_usd_short

    deposit = row.get("deposit")
    try:
        ada = int(deposit) / 1_000_000 if deposit is not None else None
        row["deposit_ada"] = f"{int(ada):,}" if ada is not None else ""
    except Exception:
        row["deposit_ada"] = ""

    ptype = row.get("proposal_type") or ""
    row["proposal_type_display"] = _GA_TYPE_LABELS.get(ptype, ptype)
    row["proposal_type_color"]   = _GA_TYPE_COLORS.get(ptype, "gray")

    status = row.get("ga_status") or "active"
    row["ga_status"] = status

    # TreasuryWithdrawals の引き出し情報
    row["is_treasury_withdrawal"] = (ptype == "TreasuryWithdrawals")
    wtotal = row.get("withdrawal_total_lovelace")
    row["withdrawal_total_ada_display"] = ""
    row["withdrawal_total_jpy_display"] = ""
    row["withdrawal_total_usd_display"] = ""
    row["withdrawal_list"] = []
    if wtotal is not None:
        try:
            total_lovelace = int(wtotal)
            row["withdrawal_total_ada_display"] = format_ada(total_lovelace, integer=True)
            if fiat_rate:
                total_ada = total_lovelace / 1_000_000
                ada_jpy = fiat_rate.get("ada_jpy") or 0.0
                ada_usd = fiat_rate.get("ada_usd") or 0.0
                if ada_jpy:
                    row["withdrawal_total_jpy_display"] = format_jpy_short(total_ada * ada_jpy)
                if ada_usd:
                    row["withdrawal_total_usd_display"] = format_usd_short(total_ada * ada_usd)
        except (TypeError, ValueError):
            pass

    wjson_raw = row.get("withdrawal_json")
    if isinstance(wjson_raw, str) and wjson_raw:
        try:
            items = json.loads(wjson_raw) or []
        except Exception:
            items = []
        wlist = []
        for w in items if isinstance(items, list) else []:
            try:
                amount_lovelace = int(w.get("amount") or 0)
            except (TypeError, ValueError):
                amount_lovelace = 0
            addr = str(w.get("stake_address") or "")
            entry = {
                "stake_address": addr,
                "stake_address_short": (addr[:10] + "..." + addr[-6:]) if len(addr) > 20 else addr,
                "amount_ada_display": format_ada(amount_lovelace, integer=True),
                "amount_jpy_display": "",
                "amount_usd_display": "",
            }
            if fiat_rate:
                amount_ada = amount_lovelace / 1_000_000
                ada_jpy = fiat_rate.get("ada_jpy") or 0.0
                ada_usd = fiat_rate.get("ada_usd") or 0.0
                if ada_jpy:
                    entry["amount_jpy_display"] = format_jpy_short(amount_ada * ada_jpy)
                if ada_usd:
                    entry["amount_usd_display"] = format_usd_short(amount_ada * ada_usd)
            wlist.append(entry)
        row["withdrawal_list"] = wlist

    # title / abstract / motivation / rationale は UI で AuthState.language に基づき ja/en 分岐する。
    # DB 側で事前に *_display を決め打ちすると言語切替が効かなくなるので、原文カラムをそのまま渡す。
    # 一覧カード用には冒頭 URL を取り除いた縮約版を別フィールドで持つ（詳細表示は原文のまま）。
    row["abstract_card"]    = _strip_leading_urls(str(row.get("abstract") or ""))
    row["abstract_ja_card"] = _strip_leading_urls(str(row.get("abstract_ja") or ""))

    refs_raw = row.get("references_json")
    if "references_list" not in row:
        if refs_raw and isinstance(refs_raw, str):
            try:
                parsed = json.loads(refs_raw)
                row["references_list"] = parsed if isinstance(parsed, list) else []
            except Exception:
                row["references_list"] = []
        else:
            row["references_list"] = []

    # block_time を基準点としてエポック→日付を相対計算
    ref_dt: datetime | None = None
    block_time_raw = row.get("block_time")
    if block_time_raw:
        try:
            bt_str = str(block_time_raw)[:19]  # "YYYY-MM-DD HH:MM:SS"
            ref_dt = datetime.strptime(bt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    proposed = row.get("proposed_epoch")
    row["proposed_epoch_display"] = _epoch_to_display(proposed, proposed, ref_dt)
    row["expiration_display"]     = _epoch_to_display(row.get("expiration"), proposed, ref_dt)

    tx  = row.get("proposal_tx_hash") or ""
    idx = row.get("proposal_index") or 0
    row["govtool_url"] = f"https://gov.tools/governance_actions/{tx}%23{idx}" if tx else ""

    return row


class GovernanceState(rx.State):
    actions: List[Dict[str, Any]] = []
    current_page: int = 1
    items_per_page: int = 20
    total_pages: int = 0
    total_items: int = 0
    start_page: int = 1
    end_page: int = 1
    middle_page: list[int] = []
    load: bool = False

    inputed_value: str = ""
    search_query: str = ""
    filter_type_selected: List[Dict[str, str]] = []
    filter_status_selected: List[Dict[str, str]] = []
    filter_types: List[str] = []
    filter_statuses: List[str] = []

    view_mode: str = "list"

    modal_open: bool = False
    modal_action: Dict[str, Any] = {}
    modal_action_refs: List[Dict[str, Any]] = []
    modal_votes: List[Dict[str, Any]] = []
    modal_cc_votes: List[Dict[str, Any]] = []
    modal_loading: bool = False
    last_list_path: str = ""

    # 現行憲法（最新の enacted NewConstitution）
    current_constitution: Dict[str, Any] = {}

    # ── GA AI 分析（A 方針: ファクト整理ツール）────────────────────────────────
    modal_ai_status: str = ""                    # ""=未ロード / "none"=対象外 / pending / analyzing / analyzed / failed
    modal_ai_data: Dict[str, str] = {}           # スカラフィールド（summary_ja/en, model_id, elapsed_pending）
    # AI 抽出の関連憲法条文（スコア無し）。各 entry: key/label_ja/label_en/quote_ja/quote_en/why_relevant_ja/why_relevant_en
    modal_ai_articles: List[Dict[str, str]] = []
    # AI 抽出の提案ファクト。各 entry: label_ja/label_en/value
    modal_ai_facts: List[Dict[str, str]] = []
    # ルールベース自動チェック。各 entry: label_ja/label_en/status/detail_ja/detail_en
    modal_ai_rule_checks: List[Dict[str, str]] = []
    modal_ai_last_error: str = ""

    # ── ログインユーザーの委任先 DRep 投票 + 投票期限 ──────────────────────────
    # 各 entry: nickname / address_short / drep_id / drep_name / vote / rationale / has_voted
    modal_user_drep_votes: List[Dict[str, str]] = []
    # 投票期限の残日数 + 状態（"active" / "urgent" / "ended"）
    modal_deadline_days: int = 0
    modal_deadline_status: str = ""

    # ── WHERE 句構築 ──────────────────────────────────────────────────────────

    def _build_where(self) -> tuple[str, list]:
        # data_fetch の select_sql は proposal_voting_summary を LEFT JOIN しており、
        # proposal_type カラムが両テーブルに存在するため `ga.` 接頭辞が必須（ambiguous エラー回避）。
        # count_sql 側は ga 単独だが、同じ where_sql を使い回すので一貫して prefix を付ける。
        conditions = ["1=1"]
        params: list = []
        if self.inputed_value:
            sv = f"%{self.inputed_value}%"
            conditions.append(
                "(ga.title LIKE ? OR ga.title_ja LIKE ? OR ga.`abstract` LIKE ? OR ga.abstract_ja LIKE ?)"
            )
            params.extend([sv, sv, sv, sv])
        if self.filter_types:
            placeholders = ", ".join(["?"] * len(self.filter_types))
            conditions.append(f"ga.proposal_type IN ({placeholders})")
            params.extend(self.filter_types)
        if self.filter_statuses:
            parts = []
            for s in self.filter_statuses:
                if s == "active":
                    parts.append(
                        "(ga.ratified_epoch IS NULL AND ga.enacted_epoch IS NULL"
                        " AND ga.dropped_epoch IS NULL AND ga.expired_epoch IS NULL)"
                    )
                elif s == "ratified":
                    parts.append("ga.ratified_epoch IS NOT NULL")
                elif s == "enacted":
                    parts.append("ga.enacted_epoch IS NOT NULL")
                elif s == "dropped":
                    parts.append("ga.dropped_epoch IS NOT NULL")
                elif s == "expired":
                    parts.append("ga.expired_epoch IS NOT NULL")
            if parts:
                conditions.append(f"({' OR '.join(parts)})")
        return " AND ".join(conditions), params

    # ── データ取得 ────────────────────────────────────────────────────────────

    def data_fetch(self):
        where_sql, params = self._build_where()
        offset = (self.current_page - 1) * self.items_per_page
        # governance_actions に voting_summary を LEFT JOIN（集計カラムを一緒に取得）
        # WHERE の各テーブル接頭辞を補うため、条件は governance_actions 基準で記述する想定。
        select_sql = (
            "SELECT ga.id, ga.proposal_id, ga.proposal_tx_hash, ga.proposal_index, ga.proposal_type,"
            " ga.proposed_epoch, ga.ratified_epoch, ga.enacted_epoch, ga.dropped_epoch, ga.expired_epoch,"
            " ga.expiration, ga.block_time, ga.deposit, ga.withdrawal_total_lovelace, ga.withdrawal_json,"
            " ga.meta_url, ga.title, ga.`abstract`, ga.title_ja, ga.abstract_ja,"
            f" {_GA_STATUS_SQL_GA} AS ga_status,"
            " vs.drep_yes_pct, vs.drep_no_pct, vs.pool_yes_pct, vs.pool_no_pct,"
            " vs.committee_yes_pct, vs.committee_no_pct"
            " FROM governance_actions ga"
            " LEFT JOIN proposal_voting_summary vs ON ga.proposal_id = vs.proposal_id"
            f" WHERE {where_sql}"
            # 提出順 (新しい順)。同一 Tx 内 (= 同じ proposal_tx_hash) は
            # proposal_index ASC で並べる (1 Tx に複数 GA が含まれるケース対応)。
            " ORDER BY ga.block_time DESC, ga.proposed_epoch DESC, ga.proposal_index ASC"
            f" LIMIT {self.items_per_page} OFFSET {offset}"
        )
        count_sql = f"SELECT COUNT(*) AS cnt FROM governance_actions ga WHERE {where_sql}"
        try:
            from cardanoism.backend.fiat_db import get_fiat_rate
            from cardanoism.backend.params_db import get_protocol_params
            fiat_rate = get_fiat_rate()
            protocol_params = get_protocol_params()
            with get_db() as (cursor, _):
                cursor.execute(select_sql, params)
                rows = [dict(r) for r in cursor.fetchall()]
                out: list[dict] = []
                for r in rows:
                    formatted = _format_ga_row(r, fiat_rate)
                    _attach_voting_summary(formatted, protocol_params)
                    out.append(formatted)
                self.actions = out
                cursor.execute(count_sql, params)
                self.total_items = int((cursor.fetchone() or {}).get("cnt", 0))
        except Exception as e:
            logger.exception("GovernanceState.data_fetch: %s", e)
            self.actions = []
            self.total_items = 0
        self.total_pages = max(1, (self.total_items + self.items_per_page - 1) // self.items_per_page)
        self.start_page  = max(1, self.current_page - 3)
        self.end_page    = min(self.total_pages, self.current_page + 3)
        self.middle_page = list(range(self.start_page, self.end_page + 1))
        self.load = True

    def _load_full_action(self, proposal_id: str) -> None:
        """proposal_id を指定して governance_actions の全カラムを modal_action に読み込む。
        proposal_tx_hash は 1 Tx に複数 GA を含められるためユニークではない。proposal_id を使う。
        """
        try:
            from cardanoism.backend.fiat_db import get_fiat_rate
            from cardanoism.backend.vote_db import get_votes_by_proposal
            from cardanoism.backend.voting_summary_db import get_voting_summary
            from cardanoism.backend.params_db import get_protocol_params
            fiat_rate = get_fiat_rate()
            with get_db() as (cursor, _):
                cursor.execute(
                    f"SELECT *, {_GA_STATUS_SQL} AS ga_status"
                    " FROM governance_actions WHERE proposal_id = ?",
                    (proposal_id,),
                )
                row = cursor.fetchone()
                if row:
                    formatted = _format_ga_row(dict(row), fiat_rate)
                    self.modal_action_refs = formatted.get("references_list", [])

                    # 投票集計と閾値を共通ヘルパーでマージ
                    summary = get_voting_summary(proposal_id) or {}
                    protocol_params = get_protocol_params()
                    # 集計カラムを row に反映してから _attach_voting_summary に渡す
                    for k in ("drep_yes_pct", "drep_no_pct",
                              "pool_yes_pct", "pool_no_pct",
                              "committee_yes_pct", "committee_no_pct"):
                        formatted[k] = summary.get(k)
                    _attach_voting_summary(formatted, protocol_params)
                    self.modal_action = formatted

                    # 投票期限カウントダウン（日数 / 状態）を計算
                    self._compute_deadline(formatted)

            # 投票一覧を整形して modal_votes にセット
            votes = get_votes_by_proposal(proposal_id)
            votes_out: list[dict] = []
            for v in votes:
                vid = str(v.get("voter_id") or "")
                if len(vid) > 24:
                    vid_short = f"{vid[:12]}...{vid[-8:]}"
                else:
                    vid_short = vid
                bt = v.get("block_time")
                bt_display = bt.strftime("%Y-%m-%d %H:%M") if bt else ""
                role = str(v.get("voter_role") or "")
                drep_name = str(v.get("drep_name") or "").strip()
                voter_name = drep_name if (role == "DRep" and drep_name) else ""
                votes_out.append({
                    "id":              str(v.get("id") or ""),
                    "voter_role":      role,
                    "voter_id":        vid,
                    "voter_id_short":  vid_short,
                    "voter_name":      voter_name,
                    "vote":            str(v.get("vote") or ""),
                    "block_time":      bt_display,
                    "rationale":       str(v.get("rationale") or ""),
                    "rationale_ja":    str(v.get("rationale_ja") or ""),
                })
            self.modal_votes = votes_out
            # CC は固定メンバーなので、authorized な全員を表示する。
            # 投票済みのメンバーには投票を結合、未投票には空文字の vote をセット。
            from cardanoism.backend.params_db import get_active_cc_members
            cc_members = get_active_cc_members()
            # cc_hot_id または cc_cold_id のどちらで Koios が voter_id を返すか不定のため両方でマッチ
            cc_vote_map: dict[str, dict] = {}
            for v in votes_out:
                if v["voter_role"] == "ConstitutionalCommittee":
                    cc_vote_map[v["voter_id"]] = v
            cc_out: list[dict] = []
            for m in cc_members:
                hot_id = str(m.get("cc_hot_id") or "")
                cold_id = str(m.get("cc_cold_id") or "")
                matched = cc_vote_map.get(hot_id) or cc_vote_map.get(cold_id)
                display_name = str(m.get("display_name") or "").strip()
                # 表示用 ID は hot 優先、短縮
                show_id = hot_id or cold_id
                if len(show_id) > 24:
                    show_id_short = f"{show_id[:12]}...{show_id[-8:]}"
                else:
                    show_id_short = show_id
                cc_out.append({
                    "cc_cold_id":     cold_id,
                    "cc_hot_id":      hot_id,
                    "display_name":   display_name,
                    "show_id_short":  show_id_short,
                    "vote":           matched["vote"] if matched else "",
                    "block_time":     matched["block_time"] if matched else "",
                    "has_voted":      "1" if matched else "",
                })
            self.modal_cc_votes = cc_out

            # AI 分析結果をロード（行が無ければ "none" 状態）
            self._load_ai_analysis(proposal_id)
        except Exception as e:
            logger.exception("GovernanceState._load_full_action(id=%s): %s", proposal_id, e)

    def _compute_deadline(self, action: Dict[str, Any]) -> None:
        """proposal の expiration エポックから残日数 / 状態を State に格納する。

        - 既に ratified/enacted/dropped/expired のいずれかなら status='ended'
        - active で残 7 日以下なら status='urgent'
        - active で残 8 日以上なら status='active'
        """
        # 既に決着済みなら ended
        for k in ("ratified_epoch", "enacted_epoch", "dropped_epoch", "expired_epoch"):
            if action.get(k):
                self.modal_deadline_status = "ended"
                self.modal_deadline_days = 0
                return

        expiration = action.get("expiration")
        if expiration is None:
            self.modal_deadline_status = ""
            self.modal_deadline_days = 0
            return

        try:
            exp_ep = int(expiration)
        except (TypeError, ValueError):
            self.modal_deadline_status = ""
            self.modal_deadline_days = 0
            return

        # 現在エポックを Shelley genesis から計算（mainnet 基準）
        import time
        SHELLEY_EPOCH = 208
        SHELLEY_UNIX = 1_596_059_091
        EPOCH_SECONDS = 432_000  # 5 日
        current_ep = SHELLEY_EPOCH + (int(time.time()) - SHELLEY_UNIX) // EPOCH_SECONDS

        eps_remaining = exp_ep - int(current_ep)
        days_remaining = max(0, eps_remaining * 5)

        if eps_remaining <= 0:
            self.modal_deadline_status = "ended"
            self.modal_deadline_days = 0
        elif days_remaining <= 7:
            self.modal_deadline_status = "urgent"
            self.modal_deadline_days = days_remaining
        else:
            self.modal_deadline_status = "active"
            self.modal_deadline_days = days_remaining

    @rx.event
    async def load_user_drep_votes(self):
        """ログイン中ユーザーの委任先 DRep 投票を modal_user_drep_votes に格納する。
        cross-state 参照（AuthState.is_logged_in / user_id）が必要なため async event。
        """
        proposal_id = str(self.modal_action.get("proposal_id") or "")
        if not proposal_id:
            self.modal_user_drep_votes = []
            return

        # AuthState から user_id を取得
        try:
            from cardanoism.backend.auth_state import AuthState
            auth = await self.get_state(AuthState)
        except Exception as e:
            logger.warning("load_user_drep_votes: get_state failed: %s", e)
            self.modal_user_drep_votes = []
            return

        if not getattr(auth, "is_logged_in", False) or not getattr(auth, "user_id", 0):
            self.modal_user_drep_votes = []
            return

        try:
            from cardanoism.backend.auth_db import get_stake_addresses
            addresses = get_stake_addresses(auth.user_id)
        except Exception as e:
            logger.warning("load_user_drep_votes: get_stake_addresses failed: %s", e)
            self.modal_user_drep_votes = []
            return

        out: list[dict[str, str]] = []
        for addr in addresses:
            drep_id = str(addr.get("delegated_drep_id") or "").strip()
            if not drep_id:
                continue
            nickname = str(addr.get("nickname") or "")
            address = str(addr.get("address") or "")
            address_short = address if len(address) <= 22 else f"{address[:14]}...{address[-8:]}"
            drep_name = str(addr.get("delegated_drep_name") or "")

            # proposal_votes で投票を引く
            try:
                with get_db() as (cursor, _):
                    cursor.execute(
                        """
                        SELECT vote, rationale, rationale_ja
                        FROM proposal_votes
                        WHERE proposal_id = ? AND voter_role = 'DRep' AND voter_id = ?
                        ORDER BY block_time DESC
                        LIMIT 1
                        """,
                        (proposal_id, drep_id),
                    )
                    vote_row = cursor.fetchone()
            except Exception as e:
                logger.warning("load_user_drep_votes: query failed: %s", e)
                vote_row = None

            if vote_row:
                rationale = (
                    str(vote_row.get("rationale_ja") or "").strip()
                    or str(vote_row.get("rationale") or "").strip()
                )
                rationale_short = rationale if len(rationale) <= 200 else rationale[:200] + "..."
                out.append({
                    "nickname":      nickname,
                    "address_short": address_short,
                    "drep_id":       drep_id,
                    "drep_name":     drep_name,
                    "vote":          str(vote_row.get("vote") or ""),
                    "rationale":     rationale,
                    "rationale_short": rationale_short,
                    "has_voted":     "1",
                })
            else:
                out.append({
                    "nickname":      nickname,
                    "address_short": address_short,
                    "drep_id":       drep_id,
                    "drep_name":     drep_name,
                    "vote":          "",
                    "rationale":     "",
                    "rationale_short": "",
                    "has_voted":     "",
                })
        self.modal_user_drep_votes = out

    def retry_ai_analysis(self):
        """failed 状態の AI 分析を pending に戻して再実行を促す。
        ga_ai_worker.py が pending を拾って analyzing → analyzed に進める。
        """
        proposal_id = str(self.modal_action.get("proposal_id") or "")
        if not proposal_id:
            return
        try:
            with get_db() as (cursor, conn):
                cursor.execute(
                    """
                    UPDATE governance_ai_analysis
                    SET status = 'pending',
                        worker_id = NULL,
                        started_at = NULL,
                        last_error = NULL
                    WHERE proposal_id = ? AND status = 'failed'
                    """,
                    (proposal_id,),
                )
                conn.commit()
            # State を再ロード（pending として表示される）
            self._load_ai_analysis(proposal_id)
        except Exception as e:
            logger.exception("retry_ai_analysis: %s", e)
            return
        if self.modal_ai_status in ("pending", "analyzing"):
            return GovernanceState.poll_ai_status

    @rx.event(background=True)
    async def poll_ai_status(self):
        """pending / analyzing 中に N 秒間隔で State を更新する背景タスク。
        - 別 GA に移動した / 終了状態に達した / 上限ポーリング数に達した → 停止
        - 5 秒間隔で最大 30 分（360 回）ポーリング
        """
        async with self:
            proposal_id = str(self.modal_action.get("proposal_id") or "")
            if not proposal_id or self.modal_ai_status not in ("pending", "analyzing"):
                return

        poll_interval = 5
        max_polls = 360  # 30 分上限
        for _ in range(max_polls):
            await asyncio.sleep(poll_interval)
            async with self:
                current_pid = str(self.modal_action.get("proposal_id") or "")
                if current_pid != proposal_id:
                    return
                if self.modal_ai_status not in ("pending", "analyzing"):
                    return
                self._load_ai_analysis(proposal_id)

    def _load_ai_analysis(self, proposal_id: str) -> None:
        """governance_ai_analysis から分析結果を取得して State に展開する。
        行が存在しない場合は modal_ai_status='none' をセットして終了。
        新スキーマ: ファクト整理ベース（スコア / verdict / KPI なし）。
        """
        # 既存値をクリア
        self.modal_ai_status = ""
        self.modal_ai_data = {}
        self.modal_ai_articles = []
        self.modal_ai_facts = []
        self.modal_ai_rule_checks = []
        self.modal_ai_last_error = ""

        try:
            from cardanoism.backend.governance_ai_db import get_analysis
            row = get_analysis(proposal_id)
        except Exception as e:
            logger.exception("_load_ai_analysis: %s", e)
            return

        if row is None:
            self.modal_ai_status = "none"
            return

        status = str(row.get("status") or "")
        self.modal_ai_status = status
        self.modal_ai_last_error = str(row.get("last_error") or "")

        # 分析中・キュー待ちの場合は経過秒数も渡す（pending 状態の表示用）
        enqueued = row.get("enqueued_at")
        from datetime import datetime
        now = datetime.now()
        elapsed_pending = ""
        if status == "pending" and enqueued:
            try:
                elapsed_pending = str(max(0, int((now - enqueued).total_seconds())))
            except Exception:
                elapsed_pending = ""

        self.modal_ai_data = {
            "summary_ja":      str(row.get("constitution_summary_ja") or ""),
            "summary_en":      str(row.get("constitution_summary_en") or ""),
            "model_id":        str(row.get("model_id") or ""),
            "elapsed_pending": elapsed_pending,
        }

        # articles: スコア無しの関連条文リスト
        articles_raw = row.get("articles_json") or []
        articles_out: list[dict[str, str]] = []
        for a in articles_raw if isinstance(articles_raw, list) else []:
            if not isinstance(a, dict):
                continue
            articles_out.append({
                "key":              str(a.get("key") or ""),
                "label_ja":         str(a.get("label_ja") or ""),
                "label_en":         str(a.get("label_en") or ""),
                "quote_ja":         str(a.get("quote_ja") or ""),
                "quote_en":         str(a.get("quote_en") or ""),
                "why_relevant_ja":  str(a.get("why_relevant_ja") or a.get("comment_ja") or ""),
                "why_relevant_en":  str(a.get("why_relevant_en") or a.get("comment_en") or ""),
            })
        self.modal_ai_articles = articles_out

        # proposal_facts: AI 抽出の提案ファクト
        # 新スキーマ: value_ja / value_en（言語別）。後方互換: 単一 value
        facts_raw = row.get("proposal_facts_json") or []
        facts_out: list[dict[str, str]] = []
        for f in facts_raw if isinstance(facts_raw, list) else []:
            if not isinstance(f, dict):
                continue
            value_legacy = str(f.get("value") or "")
            facts_out.append({
                "label_ja": str(f.get("label_ja") or ""),
                "label_en": str(f.get("label_en") or ""),
                "value_ja": str(f.get("value_ja") or "") or value_legacy,
                "value_en": str(f.get("value_en") or "") or value_legacy,
            })
        self.modal_ai_facts = facts_out

        # rule_checks: ルールベース自動チェック
        rules_raw = row.get("rule_checks_json") or []
        rules_out: list[dict[str, str]] = []
        for r in rules_raw if isinstance(rules_raw, list) else []:
            if not isinstance(r, dict):
                continue
            rules_out.append({
                "label_ja":  str(r.get("label_ja") or ""),
                "label_en":  str(r.get("label_en") or ""),
                "status":    str(r.get("status") or "na"),
                "detail_ja": str(r.get("detail_ja") or ""),
                "detail_en": str(r.get("detail_en") or ""),
            })
        self.modal_ai_rule_checks = rules_out

    # ── ページロード ──────────────────────────────────────────────────────────

    def on_load(self):
        ensure_warm()
        self.load = False
        self.actions = []
        self.current_page = 1
        self.total_pages = 0
        self.total_items = 0
        self.inputed_value = ""
        self.search_query = ""
        self.filter_type_selected = []
        self.filter_status_selected = []
        self.filter_types = []
        self.filter_statuses = []
        self.view_mode = "list"
        self.modal_open = False
        self.modal_action = {}
        self.modal_action_refs = []
        self.modal_loading = False
        self.last_list_path = ""
        self._load_current_constitution()
        self.data_fetch()

    def _load_current_constitution(self) -> None:
        """最新の enacted NewConstitution を current_constitution にロードする。"""
        try:
            with get_db() as (cursor, _):
                cursor.execute(
                    """
                    SELECT proposal_id, proposal_tx_hash, proposal_index,
                           title, title_ja, `abstract`, abstract_ja,
                           proposed_epoch, ratified_epoch, enacted_epoch,
                           block_time, meta_url, meta_hash
                    FROM governance_actions
                    WHERE proposal_type = 'NewConstitution'
                      AND enacted_epoch IS NOT NULL
                    ORDER BY enacted_epoch DESC
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()
                if row:
                    d = dict(row)
                    self.current_constitution = {
                        "proposal_id":    str(d.get("proposal_id") or ""),
                        "title":          str(d.get("title") or ""),
                        "title_ja":       str(d.get("title_ja") or ""),
                        "abstract":       str(d.get("abstract") or ""),
                        "abstract_ja":    str(d.get("abstract_ja") or ""),
                        "enacted_epoch":  int(d.get("enacted_epoch") or 0),
                        "meta_url":       str(d.get("meta_url") or ""),
                    }
                else:
                    self.current_constitution = {}
        except Exception as e:
            logger.exception("_load_current_constitution: %s", e)
            self.current_constitution = {}

    def load_detail_page(self):
        """個別ページ /governance/[proposal_id] のロード処理。"""
        self.load = False
        self.modal_action = {}
        self.modal_action_refs = []
        self.modal_user_drep_votes = []
        path = self.router.url.path or ""
        parts = [p for p in path.split("/") if p]
        proposal_id = parts[-1] if parts else ""
        if proposal_id:
            self._load_full_action(proposal_id)
        self.load = True
        events: list = [GovernanceState.load_user_drep_votes]
        if self.modal_ai_status in ("pending", "analyzing"):
            events.append(GovernanceState.poll_ai_status)
        return events

    async def load_detail_page_with_lang(self):
        """後方互換のため残すが、言語は AuthState.language に一本化されたため初期化処理は不要。"""
        return self.load_detail_page()

    # ── モーダル ──────────────────────────────────────────────────────────────

    def open_modal(self, action: Dict[str, Any]):
        self.modal_open = True
        self.modal_loading = True
        self.modal_action = action
        self.modal_action_refs = []
        self.modal_user_drep_votes = []
        self.last_list_path = self.router.url.path or ""
        proposal_id = str(action.get("proposal_id", ""))
        self._load_full_action(proposal_id)
        self.modal_loading = False
        events: list = [rx.call_script(
            f"history.pushState(null, '', '/governance/{proposal_id}');"
        ), GovernanceState.load_user_drep_votes]
        if self.modal_ai_status in ("pending", "analyzing"):
            events.append(GovernanceState.poll_ai_status)
        return events

    def handle_modal_change(self, open: bool):
        if not open:
            self.modal_open = False
            self.modal_action = {}
            self.modal_action_refs = []
            target = self.last_list_path or "/governance"
            # /governance/<id> （GA detail）のときだけ戻る。/governance, /governance/constitution,
            # /governance/treasury, /governance/drep などの静的ルートは対象外。
            return rx.call_script(
                "(() => {"
                "  const p = window.location.pathname;"
                "  const known = new Set(["
                "    '/governance', '/governance/',"
                "    '/governance/constitution', '/governance/constitution/',"
                "    '/governance/treasury', '/governance/treasury/',"
                "    '/governance/drep', '/governance/drep/'"
                "  ]);"
                "  if (!p.startsWith('/governance/') || known.has(p)) return;"
                "  if (p.startsWith('/governance/drep/')) return;"
                "  if (history.state !== null) { history.back(); }"
                f"  else {{ history.replaceState(null, '', '{target}'); }}"
                "})();"
            )

    def set_view_mode(self, mode: str):
        self.view_mode = mode

    # ── フィルター ────────────────────────────────────────────────────────────

    def set_inputed_value(self, value: str):
        self.inputed_value = value
        self.search_query = value
        self.current_page = 1
        self.data_fetch()

    def set_filter_types(self, value):
        if isinstance(value, list):
            self.filter_type_selected = value
            self.filter_types = [
                str(item["value"])
                for item in value
                if isinstance(item, dict) and item.get("value")
            ]
        else:
            self.filter_type_selected = []
            self.filter_types = []
        self.current_page = 1
        self.data_fetch()

    def set_filter_statuses(self, value):
        if isinstance(value, list):
            self.filter_status_selected = value
            self.filter_statuses = [
                str(item["value"])
                for item in value
                if isinstance(item, dict) and item.get("value")
            ]
        else:
            self.filter_status_selected = []
            self.filter_statuses = []
        self.current_page = 1
        self.data_fetch()

    # ── ページネーション ──────────────────────────────────────────────────────

    def set_page(self, page: int):
        if 1 <= page <= self.total_pages:
            self.current_page = page
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")
