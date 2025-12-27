import logging
import os
import sys
import json
import mariadb
from typing import List, Dict, Any, Tuple
from contextlib import contextmanager
from time import perf_counter
import reflex as rx
import dataclasses

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
    """Fetch fund select options (value=id, label=label) from funds_new."""
    try:
        with get_db() as (cursor, _):
            cursor.execute(
                """
                SELECT id, label
                FROM funds_new
                WHERE label IN ('Fund 12', 'Fund 13', 'Fund 14', 'Fund 15')
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
                    
            asc_query = " ORDER BY fund_title DESC,CASE WHEN p.funding_status LIKE 'funded' THEN 0 ELSE 1 END, campaign_title_ja ASC, p.yes_votes_count DESC"
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
