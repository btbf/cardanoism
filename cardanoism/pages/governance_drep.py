"""
governance_drep.py
ガバナンス > DRep 一覧ページ（/governance/drep）

データソースは dreps テーブル（notify_worker.py --event drep_sync で同期）。
ページ側は DB を読むだけで Koios を叩かない。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.wallet_state import WalletState
from cardanoism.backend.drep_db import get_dreps, count_dreps, sum_total_delegation
from cardanoism.backend.fiat_db import get_fiat_rate
from cardanoism.backend.price import format_ada, format_jpy_short, format_usd_short
from cardanoism.components.governance_nav import governance_subnav
from cardanoism.components.breadcrumb import breadcrumb
from cardanoism.components.login_modal import login_modal
from cardanoism.components.drep_delegation_dialog import drep_delegation_dialog, drep_delegate_button

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 30


# ─── State ────────────────────────────────────────────────────────────────────


class DrepState(rx.State):
    load: bool = False
    error: str = ""

    inputed_value: str = ""
    search_query: str = ""
    sort: str = "amount_desc"
    only_registered: bool = True

    current_page: int = 1
    total_pages: int = 0
    total_items: int = 0
    start_page: int = 1
    end_page: int = 1
    middle_page: list[int] = []

    dreps: List[Dict[str, Any]] = []
    total_delegation_ada_display: str = "-"
    total_delegation_lovelace: int = 0

    def _fetch(self):
        offset = (self.current_page - 1) * ITEMS_PER_PAGE
        try:
            rate = get_fiat_rate() or {}
            ada_jpy = float(rate.get("ada_jpy") or 0)
            ada_usd = float(rate.get("ada_usd") or 0)

            # 総委任量を取得して、各 DRep のシェアを計算する
            total_lovelace = sum_total_delegation(only_registered=self.only_registered)
            self.total_delegation_lovelace = total_lovelace
            self.total_delegation_ada_display = format_ada(total_lovelace, integer=True) if total_lovelace else "0"

            rows = get_dreps(
                search=self.search_query,
                only_registered=self.only_registered,
                sort=self.sort,
                limit=ITEMS_PER_PAGE,
                offset=offset,
            )
            total = count_dreps(search=self.search_query, only_registered=self.only_registered)

            out: list[dict] = []
            for idx, r in enumerate(rows):
                amount = int(r.get("amount") or 0)
                ada = amount / 1_000_000
                jpy_d = format_jpy_short(ada * ada_jpy) if ada_jpy else ""
                usd_d = format_usd_short(ada * ada_usd) if ada_usd else ""
                share_pct = (amount / total_lovelace * 100.0) if total_lovelace > 0 else 0.0
                if share_pct >= 1.0:
                    share_display = f"{share_pct:.2f}"
                elif share_pct > 0:
                    share_display = f"{share_pct:.3f}"
                else:
                    share_display = "0"
                drep_id = str(r.get("drep_id") or "")
                # スマホ用の短縮表示（先頭 14 + ... + 末尾 8）
                if len(drep_id) > 24:
                    drep_id_short = f"{drep_id[:14]}...{drep_id[-8:]}"
                else:
                    drep_id_short = drep_id
                out.append({
                    "rank":          str(offset + idx + 1),
                    "drep_id":       drep_id,
                    "drep_id_short": drep_id_short,
                    "given_name":    str(r.get("given_name") or ""),
                    "image_url":     str(r.get("image_url") or ""),
                    "drep_status":   str(r.get("drep_status") or ""),
                    "is_active":     "1" if r.get("active") else "",
                    "amount_ada":    format_ada(amount, integer=True) if amount else "0",
                    "amount_jpy":    jpy_d,
                    "amount_usd":    usd_d,
                    "share_pct":     share_display,
                })
            self.dreps = out
            self.total_items = total
            self.total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            self.start_page = max(1, self.current_page - 3)
            self.end_page   = min(self.total_pages, self.current_page + 3)
            self.middle_page = list(range(self.start_page, self.end_page + 1))
        except Exception as e:
            logger.exception("DrepState._fetch: %s", e)
            self.error = str(e)

    def on_load(self):
        self.load = False
        self.error = ""
        self.inputed_value = ""
        self.search_query = ""
        self.sort = "amount_desc"
        self.only_registered = True
        self.current_page = 1
        self._fetch()
        self.load = True

    def set_input(self, v: str):
        self.inputed_value = v
        self.search_query = v
        self.current_page = 1
        self._fetch()

    def set_sort(self, v: str):
        self.sort = v
        self.current_page = 1
        self._fetch()

    def set_page(self, p):
        try:
            self.current_page = int(p)
            self._fetch()
        except (TypeError, ValueError):
            pass
        return rx.call_script("window.scrollTo(0, 0)")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._fetch()
        return rx.call_script("window.scrollTo(0, 0)")

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._fetch()
        return rx.call_script("window.scrollTo(0, 0)")


# ─── DRep マッチング診断 State ─────────────────────────────────────────────────

# 質問の順番。各 index は drep_match.TOPIC_KEYS と同期した topic を表す。
# AI 分類のキーと一致させること（一致しないと user_vector が DRep プロファイルと
# 揃わずマッチング結果が崩れる）。
_DREP_MATCH_TOPIC_ORDER: tuple[str, ...] = (
    "core_dev", "research", "education", "community",
    "defi", "enterprise", "product", "governance",
)
_DREP_MATCH_TOTAL = len(_DREP_MATCH_TOPIC_ORDER)


class DrepMatchState(rx.State):
    """マッチング診断の view 状態と回答ベクトル / 結果を保持する。"""
    # view: "list" / "quiz" / "results"
    view: str = "list"
    # 現在の質問インデックス (0..N-1)
    current_question: int = 0
    # 各質問の回答: "yes" / "neutral" / "no" / "" (未回答)
    answers: list[str] = ["", "", "", "", "", "", "", ""]
    # 結果（compute_match の戻り値を str dict 化したもの。.split(",") で list 化）
    results: list[dict[str, str]] = []

    @rx.var
    def current_topic_key(self) -> str:
        idx = self.current_question
        if 0 <= idx < _DREP_MATCH_TOTAL:
            return _DREP_MATCH_TOPIC_ORDER[idx]
        return ""

    @rx.var
    def current_question_i18n_key(self) -> str:
        key = self.current_topic_key
        return "drep_match_q_" + key if key else ""

    @rx.var
    def progress_current(self) -> str:
        return str(self.current_question + 1)

    @rx.var
    def progress_total(self) -> str:
        return str(_DREP_MATCH_TOTAL)

    @rx.var
    def is_first_question(self) -> bool:
        return self.current_question == 0

    @rx.var
    def is_last_question(self) -> bool:
        return self.current_question == _DREP_MATCH_TOTAL - 1

    @rx.var
    def current_answer(self) -> str:
        idx = self.current_question
        if 0 <= idx < len(self.answers):
            return self.answers[idx]
        return ""

    @rx.var
    def can_submit(self) -> bool:
        # 最終問が回答済みであれば送信可
        if not self.is_last_question:
            return False
        return self.current_answer != ""

    @rx.var
    def progress_pct(self) -> str:
        """進行バー幅 (%、1 桁丸め)。"""
        if _DREP_MATCH_TOTAL <= 0:
            return "0"
        pct = (self.current_question + 1) / _DREP_MATCH_TOTAL * 100
        return f"{pct:.1f}"

    def set_view(self, view: str):
        if view in ("list", "quiz", "results"):
            self.view = view

    def start_quiz(self):
        """クイズを初期化して quiz view に切り替える。"""
        self.view = "quiz"
        self.current_question = 0
        self.answers = [""] * _DREP_MATCH_TOTAL
        self.results = []

    def answer(self, choice: str):
        """現在の質問に回答し、最終問でなければ次に進む。"""
        if choice not in ("yes", "neutral", "no"):
            return
        idx = self.current_question
        if 0 <= idx < len(self.answers):
            new = list(self.answers)
            new[idx] = choice
            self.answers = new
        if not self.is_last_question:
            self.current_question = idx + 1

    def prev_question(self):
        if self.current_question > 0:
            self.current_question -= 1

    def submit_quiz(self):
        """回答ベクトルから drep_match.compute_match を呼び、結果 view へ。"""
        from cardanoism.backend.drep_match import compute_match, TOPIC_KEYS
        user_vector: dict[str, float | None] = {}
        for i, topic in enumerate(TOPIC_KEYS):
            ans = self.answers[i] if i < len(self.answers) else ""
            if ans == "yes":
                user_vector[topic] = 1.0
            elif ans == "no":
                user_vector[topic] = 0.0
            else:
                user_vector[topic] = None  # neutral / 未回答 → 比較対象外
        try:
            raw = compute_match(user_vector, limit=5)
        except Exception as e:  # noqa: BLE001
            logger.warning("compute_match failed: %s", e)
            raw = []
        out: list[dict[str, str]] = []
        for r in raw:
            # 外部リンクは "icon|url,icon|url" の CSV にエンコード（UI で split + match）
            links_csv = ",".join(f"{icon}|{url}" for icon, url in r.get("links", []))
            out.append({
                "drep_id":        r["drep_id"],
                "given_name":     r["given_name"],
                "image_url":      r["image_url"],
                "bio":            r.get("bio") or "",
                "links_csv":      links_csv,
                "similarity_pct": f"{r['similarity_pct']:.1f}",
                "match_dims":     str(r["match_dims"]),
                "top_yes_csv":    ",".join(r["top_yes_topics"]),
                "top_no_csv":     ",".join(r["top_no_topics"]),
                "vote_count":     str(r["topic_vote_count"]),
            })
        self.results = out
        self.view = "results"


# ─── UI パーツ ────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return breadcrumb([("nav_governance", "/governance")], "gov_subnav_drep")


def _drep_card(d) -> rx.Component:
    """1 件の DRep カード。PC ではランク・プロフィール・ID・委任量を横一列に展開。"""
    rank_badge = rx.center(
        rx.text(
            "#", d["rank"],
            size="4", weight="bold", color="var(--gray-11)",
            style={"letterSpacing": "-0.02em"},
        ),
        min_width="56px",
        padding_x="8px",
        height="56px",
        border_radius="10px",
        background="var(--gray-4)",
        flex_shrink="0",
    )
    avatar = rx.link(
        rx.cond(
            d["image_url"] != "",
            rx.image(
                src=d["image_url"],
                width="56px",
                height="56px",
                border_radius="50%",
                style={"objectFit": "cover"},
                flex_shrink="0",
            ),
            rx.center(
                rx.icon("user-round", size=28, color="var(--gray-9)"),
                width="56px",
                height="56px",
                border_radius="50%",
                background="var(--gray-4)",
                flex_shrink="0",
            ),
        ),
        href="/drep/" + d["drep_id"],
        underline="none",
        style={"display": "inline-block", "lineHeight": 0},
    )
    status_badge = rx.cond(
        d["is_active"] != "",
        rx.badge(AuthState.t["drep_status_active"], color_scheme="green", variant="soft"),
        rx.badge(AuthState.t["drep_status_inactive"], color_scheme="gray", variant="soft"),
    )
    name_text = rx.link(
        rx.cond(
            d["given_name"] != "",
            rx.text(d["given_name"], size="4", weight="bold", color="var(--gray-12)",
                    style={"wordBreak": "break-word"}),
            rx.text(AuthState.t["drep_no_name"], size="4", weight="bold", color="var(--gray-10)"),
        ),
        href="/drep/" + d["drep_id"],
        underline="hover",
        color="inherit",
    )
    fiat = rx.cond(
        AuthState.language == "en",
        rx.cond(
            d["amount_usd"] != "",
            rx.text("(≈ ", d["amount_usd"], ")", size="1", color="var(--gray-10)"),
            rx.fragment(),
        ),
        rx.cond(
            d["amount_jpy"] != "",
            rx.text("(≈ ", d["amount_jpy"], ")", size="1", color="var(--gray-10)"),
            rx.fragment(),
        ),
    )
    # DRep ID（コピー用。末尾にコピーアイコンをインライン配置）
    # スマホでは短縮表示、PCではフル表示。コピー時は常にフル ID がコピーされる。
    _id_text_style = {
        "fontFamily": "var(--code-font-family, ui-monospace, monospace)",
        "fontSize": "11px",
        "color": "var(--gray-10)",
        "wordBreak": "break-all",
    }
    _copy_btn = rx.el.button(
        rx.icon("copy", size=12),
        on_click=[
            rx.set_clipboard(d["drep_id"]),
            rx.toast(
                AuthState.t["drep_id_copied"],
                position="top-center",
                style={
                    "background-color": "var(--indigo-11)",
                    "color": "white",
                    "border-radius": "0.5rem",
                },
            ),
        ],
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "verticalAlign": "middle",
            "marginLeft": "4px",
            "padding": "2px",
            "border": "none",
            "background": "transparent",
            "color": "var(--gray-10)",
            "cursor": "pointer",
        },
        _hover={"color": "var(--gray-12)"},
    )
    drep_id_block = rx.fragment(
        rx.mobile_only(
            rx.box(
                rx.el.span(d["drep_id_short"], style=_id_text_style),
                _copy_btn,
                style={"lineHeight": "1.5"},
                width="100%",
            ),
        ),
        rx.tablet_and_desktop(
            rx.box(
                rx.el.span(d["drep_id"], style=_id_text_style),
                _copy_btn,
                style={"lineHeight": "1.5"},
                width="100%",
            ),
        ),
    )
    # プロフィール（名前 + ステータス + DRep ID） — 左、広めに確保して DRep ID が 1 行に収まるように
    profile_col = rx.vstack(
        rx.hstack(name_text, status_badge, spacing="2", align="center", wrap="wrap"),
        drep_id_block,
        spacing="2",
        align_items="start",
        flex="2",
        min_width="420px",
    )
    # 委任量 — 中央（縮めて配置）
    delegation_col = rx.vstack(
        rx.text(AuthState.t["drep_delegated_label"], size="1", color="var(--gray-10)"),
        rx.hstack(
            rx.text(d["amount_ada"], size="5", weight="bold", color="var(--amber-11)"),
            rx.text("ADA", size="2", color="var(--gray-11)"),
            spacing="1", align="baseline",
        ),
        fiat,
        spacing="1",
        align_items="center",
        flex="1",
        min_width="160px",
    )
    # 影響力（シェア％）— 右端、大きく
    percentage_col = rx.vstack(
        rx.text(AuthState.t["drep_influence_label"], size="1", color="var(--gray-10)"),
        rx.hstack(
            rx.text(
                d["share_pct"],
                size="8", weight="bold", color="var(--blue-11)",
                style={"letterSpacing": "-0.02em"},
            ),
            rx.text("%", size="4", color="var(--blue-10)"),
            spacing="0", align="baseline",
        ),
        spacing="1",
        align_items="center",
        min_width="110px",
        flex_shrink="0",
    )

    # 委任状態の判定 (SPO と同パターン):
    #   - 接続中ウォレットの現在委任先 == このカードの DRep: 「委任中」 (amber バッジ、クリック不可)
    #   - 接続中: 「委任する」 (amber アクティブボタン)
    #   - 未接続: 「委任する」 (gray, disabled)
    is_currently_delegated = (
        WalletState.connected
        & (WalletState.current_delegated_drep_id == d["drep_id"])
    )
    delegated_badge = rx.hstack(
        rx.icon("circle-check", size=11, color="var(--amber-11)"),
        rx.text(
            AuthState.t["delegate_btn_currently"],
            size="1", weight="bold", color="var(--amber-12)",
            style={"whiteSpace": "nowrap"},
        ),
        spacing="2",
        align="center",
        padding="4px 12px 4px 10px",
        border_radius="999px",
        background="var(--amber-3)",
        border="1px solid var(--amber-8)",
        cursor="default",
        style={
            "boxShadow": "0 1px 3px rgba(245,158,11,0.18)",
            "display": "inline-flex",
            "flexShrink": "0",
        },
    )
    delegate_active = rx.el.button(
        rx.icon("zap", size=14, color="var(--amber-11)"),
        rx.text(
            AuthState.t["delegate_btn"],
            color="var(--amber-12)",
            style={
                "fontSize": "13px",
                "fontWeight": "700",
                "lineHeight": "1.0",
                "whiteSpace": "nowrap",
            },
        ),
        on_click=WalletState.request_delegate_to_drep(d["drep_id"]),
        cursor="pointer",
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "gap": "6px",
            "padding": "8px 16px",
            "borderRadius": "999px",
            "background": "transparent",
            "border": "1.5px solid var(--amber-8)",
            "transition": "background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease",
            "flexShrink": "0",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
        },
        _hover={
            "background": "var(--amber-3)",
            "border_color": "var(--amber-10)",
            "transform": "translateY(-1px)",
            "box_shadow": "0 4px 10px -2px rgba(245,158,11,0.25)",
        },
    )
    # 未認証用ボタン: 見た目は active と同じ amber スタイル。クリックで委任ではなく
    # 認証誘導モーダル (AuthState.show_auth_required_modal) を開く。
    delegate_prompt_auth = rx.el.button(
        rx.icon("zap", size=14, color="var(--amber-11)"),
        rx.text(
            AuthState.t["delegate_btn"],
            color="var(--amber-12)",
            style={
                "fontSize": "13px",
                "fontWeight": "700",
                "lineHeight": "1.0",
                "whiteSpace": "nowrap",
            },
        ),
        on_click=AuthState.open_auth_required_modal,
        cursor="pointer",
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "gap": "6px",
            "padding": "8px 16px",
            "borderRadius": "999px",
            "background": "transparent",
            "border": "1.5px solid var(--amber-8)",
            "transition": "background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease",
            "flexShrink": "0",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
        },
        _hover={
            "background": "var(--amber-3)",
            "border_color": "var(--amber-10)",
            "transform": "translateY(-1px)",
            "box_shadow": "0 4px 10px -2px rgba(245,158,11,0.25)",
        },
    )
    delegate_button = rx.box(
        rx.cond(
            is_currently_delegated,
            delegated_badge,
            rx.cond(
                WalletState.connected,
                delegate_active,
                # 未接続: active と同じ amber スタイル。クリックで認証誘導モーダル
                delegate_prompt_auth,
            ),
        ),
        flex_shrink="0",
    )

    # お気に入りトグル (heart アイコン、catalyst / GA と同パターン)
    fav_button = rx.box(
        rx.cond(
            AuthState.drep_favorite_ids.contains(d["drep_id"]),
            rx.icon("heart", size=22, color="var(--red-9)", style={"fill": "var(--red-9)"}),
            rx.icon("heart", size=22, color="var(--gray-8)"),
        ),
        on_click=AuthState.toggle_drep_favorite(d["drep_id"]),
        cursor="pointer",
        padding="6px",
        flex_shrink="0",
    )

    # ── スマホ専用レイアウト ───────────────────────────────────────────
    # 上から: 番号+アイコン(小) / 名前+ステータス / ID / 委任量 / 影響力+委任+♥
    mobile_rank = rx.center(
        rx.text(
            "#", d["rank"],
            size="2", weight="bold", color="var(--gray-11)",
            style={"letterSpacing": "-0.02em"},
        ),
        min_width="40px",
        padding_x="6px",
        height="40px",
        border_radius="8px",
        background="var(--gray-4)",
        flex_shrink="0",
    )
    mobile_avatar = rx.link(
        rx.cond(
            d["image_url"] != "",
            rx.image(
                src=d["image_url"],
                width="40px",
                height="40px",
                border_radius="50%",
                style={"objectFit": "cover"},
                flex_shrink="0",
            ),
            rx.center(
                rx.icon("user-round", size=20, color="var(--gray-9)"),
                width="40px",
                height="40px",
                border_radius="50%",
                background="var(--gray-4)",
                flex_shrink="0",
            ),
        ),
        href="/drep/" + d["drep_id"],
        underline="none",
        style={"display": "inline-block", "lineHeight": 0},
    )
    mobile_amount_row = rx.hstack(
        rx.text(AuthState.t["drep_delegated_label"], size="1", color="var(--gray-10)"),
        rx.text(d["amount_ada"], size="3", weight="bold", color="var(--amber-11)"),
        rx.text("ADA", size="1", color="var(--gray-11)"),
        fiat,
        spacing="2", align="baseline", wrap="wrap",
    )
    mobile_layout = rx.vstack(
        rx.hstack(mobile_rank, mobile_avatar, spacing="2", align="center"),
        rx.hstack(name_text, status_badge, spacing="2", align="center", wrap="wrap"),
        drep_id_block,
        mobile_amount_row,
        rx.hstack(
            rx.hstack(
                rx.text(AuthState.t["drep_influence_label"], size="1", color="var(--gray-10)"),
                rx.text(
                    d["share_pct"],
                    size="5", weight="bold", color="var(--blue-11)",
                    style={"letterSpacing": "-0.02em"},
                ),
                rx.text("%", size="2", color="var(--blue-10)"),
                spacing="1", align="baseline",
            ),
            rx.spacer(),
            delegate_button,
            fav_button,
            spacing="2", align="center", width="100%",
        ),
        spacing="3",
        align_items="stretch",
        width="100%",
    )

    return rx.box(
        rx.mobile_only(mobile_layout),
        rx.tablet_and_desktop(
            rx.hstack(
                rank_badge,
                avatar,
                profile_col,
                delegation_col,
                percentage_col,
                delegate_button,
                fav_button,
                align="center",
                spacing="3",
                wrap="wrap",
                width="100%",
            ),
        ),
        padding="14px 16px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="10px",
        background="var(--gray-2)",
        width="100%",
        _hover={"background": "var(--gray-3)"},
        transition="background 0.15s",
    )


def _filter_bar() -> rx.Component:
    return rx.hstack(
        rx.input(
            rx.cond(
                DrepState.inputed_value != "",
                rx.input.slot(
                    rx.icon(
                        "x",
                        size=16,
                        cursor="pointer",
                        on_click=DrepState.set_input(""),
                        style={"_hover": {"color": "var(--gray-12)"}},
                    ),
                    side="right",
                    color="var(--gray-9)",
                ),
                rx.fragment(),
            ),
            placeholder=AuthState.t["drep_search_placeholder"],
            size="3",
            max_length=100,
            value=DrepState.inputed_value,
            on_change=lambda v: DrepState.set_input(v).debounce(400),
            flex="1",
            min_width="0",
        ),
        rx.select.root(
            rx.select.trigger(),
            rx.select.content(
                rx.select.item(AuthState.t["drep_sort_amount_desc"], value="amount_desc"),
                rx.select.item(AuthState.t["drep_sort_amount_asc"],  value="amount_asc"),
                rx.select.item(AuthState.t["drep_sort_name_asc"],    value="name_asc"),
                rx.select.item(AuthState.t["drep_sort_active"],      value="active"),
            ),
            value=DrepState.sort,
            on_change=DrepState.set_sort,
            size="3",
        ),
        spacing="2", wrap="wrap", width="100%",
    )


def _pagination() -> rx.Component:
    def btn(page):
        is_active = page == DrepState.current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: DrepState.set_page(page),
            variant=rx.cond(is_active, "solid", "soft"),
            radius="full",
            size="2",
            padding_x="10px",
            class_name="md:inline-flex hidden",
            _hover={"cursor": "pointer"},
        )
    return rx.flex(
        rx.button(
            rx.icon(tag="chevron-left"),
            on_click=DrepState.prev_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=DrepState.current_page == 1,
            _hover={"cursor": "pointer"},
        ),
        rx.foreach(DrepState.middle_page, btn),
        rx.button(
            rx.icon(tag="chevron-right"),
            on_click=DrepState.next_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=DrepState.current_page == DrepState.total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="pagination gap-2",
        padding_top="1.5em",
        justify="end",
        align="center",
    )


# ─── マッチング診断 UI ────────────────────────────────────────────────────────


def _tab_button(view_key: str, label) -> rx.Component:
    """list / match タブ切り替えボタン。"""
    is_active = DrepMatchState.view == view_key if view_key == "list" else (
        (DrepMatchState.view == "quiz") | (DrepMatchState.view == "results")
    )
    return rx.el.button(
        rx.text(
            label,
            size="2",
            weight="bold",
            color=rx.cond(is_active, "var(--amber-12)", "var(--gray-11)"),
        ),
        on_click=DrepMatchState.set_view(view_key),
        cursor="pointer",
        style={
            "padding":      "7px 18px",
            "borderRadius": "9999px",
            "border":       rx.cond(is_active, "1px solid var(--amber-8)", "1px solid var(--gray-6)"),
            "background":   rx.cond(is_active, "var(--amber-3)", "transparent"),
            "whiteSpace":   "nowrap",
            "transition":   "background 0.15s, border-color 0.15s, color 0.15s",
        },
        _hover=rx.cond(
            is_active,
            {"background": "var(--amber-4)"},
            {"background": "var(--gray-3)", "border_color": "var(--gray-8)"},
        ),
    )


def _drep_match_tabs() -> rx.Component:
    return rx.hstack(
        _tab_button("list", AuthState.t["drep_tab_list"]),
        _tab_button("quiz", AuthState.t["drep_tab_match"]),
        spacing="2", wrap="wrap", padding_y="4px",
    )


def _answer_button(choice: str, label, color_scheme: str) -> rx.Component:
    """quiz の回答ボタン。現在の回答と一致したら強調表示。"""
    is_selected = DrepMatchState.current_answer == choice
    bg = {
        "amber":  ("var(--amber-3)",  "var(--amber-9)"),
        "gray":   ("var(--gray-3)",   "var(--gray-7)"),
        "red":    ("var(--red-3)",    "var(--red-9)"),
    }[color_scheme]
    txt = {
        "amber":  "var(--amber-12)",
        "gray":   "var(--gray-12)",
        "red":    "var(--red-12)",
    }[color_scheme]
    return rx.el.button(
        rx.text(label, size="3", weight="bold", color=txt),
        on_click=DrepMatchState.answer(choice),
        cursor="pointer",
        style={
            "padding":      "14px 24px",
            "borderRadius": "999px",
            "background":   rx.cond(is_selected, bg[0], "transparent"),
            "border":       rx.cond(is_selected, f"2px solid {bg[1]}", "1.5px solid var(--gray-6)"),
            "minWidth":     "120px",
            "transition":   "background 0.15s, border-color 0.15s",
        },
        _hover={"background": bg[0], "border_color": bg[1]},
    )


def _quiz_view() -> rx.Component:
    """質問カード。current_question_i18n_key を AuthState.t で動的引き。"""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(
                    AuthState.t["drep_match_progress"], " ",
                    DrepMatchState.progress_current,
                    " ", AuthState.t["drep_match_progress_of"], " ",
                    DrepMatchState.progress_total,
                    size="2", color="var(--gray-11)", weight="medium",
                ),
                rx.spacer(),
                # 進行バー
                rx.box(
                    rx.box(
                        width=DrepMatchState.progress_pct + "%",
                        height="100%",
                        background="var(--amber-9)",
                        border_radius="999px",
                        transition="width 0.3s",
                    ),
                    width="120px",
                    height="6px",
                    background="var(--gray-4)",
                    border_radius="999px",
                    overflow="hidden",
                ),
                width="100%", align="center",
            ),
            rx.heading(
                AuthState.t[DrepMatchState.current_question_i18n_key],
                size="5", weight="bold", color="var(--gray-12)",
                style={"lineHeight": "1.5"},
            ),
            # 回答ボタン群
            rx.hstack(
                _answer_button("yes", AuthState.t["drep_match_answer_yes"], "amber"),
                _answer_button("neutral", AuthState.t["drep_match_answer_neutral"], "gray"),
                _answer_button("no", AuthState.t["drep_match_answer_no"], "red"),
                spacing="3", wrap="wrap", justify="center", padding_y="12px",
            ),
            # 戻る / 診断する ボタン
            rx.hstack(
                rx.cond(
                    DrepMatchState.is_first_question,
                    rx.fragment(),
                    rx.button(
                        rx.icon("chevron-left", size=14),
                        rx.text(AuthState.t["drep_match_back_button"], size="2"),
                        on_click=DrepMatchState.prev_question,
                        variant="soft", color_scheme="gray", cursor="pointer",
                    ),
                ),
                rx.spacer(),
                rx.cond(
                    DrepMatchState.can_submit,
                    rx.button(
                        rx.text(AuthState.t["drep_match_submit_button"], size="3", weight="bold"),
                        rx.icon("arrow-right", size=14),
                        on_click=DrepMatchState.submit_quiz,
                        size="3", color_scheme="amber", variant="solid", cursor="pointer",
                    ),
                    rx.fragment(),
                ),
                width="100%", align="center", padding_top="8px",
            ),
            spacing="5", align_items="stretch", width="100%",
        ),
        padding="32px 28px",
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.04)"),
        width="100%",
        max_width="700px",
    )


def _topic_chip(key) -> rx.Component:
    """トピックキーを i18n ラベルで小さなチップ表示する。"""
    return rx.box(
        rx.text(
            AuthState.t["drep_topic_" + key],
            size="1", weight="medium",
            color="var(--gray-12)",
            style={"whiteSpace": "nowrap"},
        ),
        padding="3px 9px",
        border_radius="999px",
        background="var(--gray-3)",
        border="1px solid var(--gray-6)",
        style={"display": "inline-flex"},
    )


def _social_link_icon(item) -> rx.Component:
    """item は 'icon|url' 形式の Var[str]。CIP-119 references_json から作る外部リンク。

    Reflex の StringVar.split は maxsplit を受け付けないため単純 split を使用。
    URL に '|' が含まれる前提はない（CSV エンコード時に Python 側で除外可能）。
    """
    parts = item.split("|")
    icon_name = parts[0]
    url = parts[1]
    icon_comp = rx.match(
        icon_name,
        ("twitter",        rx.icon("twitter",        size=14, color="#1DA1F2")),
        ("github",         rx.icon("github",         size=14, color="var(--gray-12)")),
        ("send",           rx.icon("send",           size=14, color="#2AABEE")),
        ("youtube",        rx.icon("youtube",        size=14, color="#FF0000")),
        ("message-circle", rx.icon("message-circle", size=14, color="#5865F2")),
        ("linkedin",       rx.icon("linkedin",       size=14, color="#0A66C2")),
        rx.icon("globe", size=14, color="var(--gray-11)"),
    )
    return rx.link(
        rx.box(
            icon_comp,
            width="26px", height="26px",
            display="flex",
            align_items="center",
            justify_content="center",
            border_radius="999px",
            background="var(--gray-3)",
            style={"transition": "background 0.15s"},
            _hover={"background": "var(--amber-4)"},
        ),
        href=url,
        is_external=True,
        underline="none",
        custom_attrs={"title": url},
    )


def _match_result_card(r) -> rx.Component:
    """マッチ結果 1 件の DRep カード。

    ネスト link 防止のためカード本体は rx.box とし、name/avatar 行のみ
    /drep/<id> へのリンクにする。外部 SNS リンクは別行で独立に貼る。
    """
    avatar = rx.cond(
        r["image_url"] != "",
        rx.image(
            src=r["image_url"],
            width="56px", height="56px",
            border_radius="50%",
            style={"objectFit": "cover", "flexShrink": "0"},
            custom_attrs={"referrerpolicy": "no-referrer"},
        ),
        rx.center(
            rx.icon("user-round", size=28, color="var(--gray-9)"),
            width="56px", height="56px",
            border_radius="50%",
            background="var(--gray-4)",
            style={"flexShrink": "0"},
        ),
    )
    name_text = rx.cond(
        r["given_name"] != "",
        rx.text(r["given_name"], size="3", weight="bold", color="var(--gray-12)"),
        rx.text(AuthState.t["drep_no_name"], size="3", color="var(--gray-10)"),
    )
    # avatar + name + match% を 1 つの内部リンクにまとめる
    header_link = rx.link(
        rx.hstack(
            avatar,
            rx.vstack(
                name_text,
                rx.hstack(
                    rx.text(
                        AuthState.t["drep_match_results_match_label"], " ",
                        size="1", color="var(--gray-10)",
                    ),
                    rx.text(
                        r["similarity_pct"], "%",
                        size="5", weight="bold", color="var(--amber-11)",
                    ),
                    rx.text(
                        " · ",
                        AuthState.t["drep_match_results_data_count"], " ",
                        r["vote_count"], " ",
                        AuthState.t["drep_match_results_data_unit"],
                        size="1", color="var(--gray-10)",
                    ),
                    spacing="1", align="baseline", wrap="wrap",
                ),
                spacing="1", align_items="start", flex="1", min_width="0",
            ),
            spacing="3", align="center", width="100%",
        ),
        href="/drep/" + r["drep_id"],
        color="inherit",
        underline="none",
        style={"display": "block", "width": "100%"},
        _hover={"color": "var(--amber-11)"},
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(header_link, flex="1", min_width="0"),
                drep_delegate_button(r["drep_id"]),
                spacing="3", align="center", width="100%", wrap="wrap",
            ),
            # 自己紹介テキスト (CIP-119 objectives / motivations から)
            rx.cond(
                r["bio"] != "",
                rx.text(
                    r["bio"],
                    size="1", color="var(--gray-11)", line_height="1.6",
                    style={
                        "display": "-webkit-box",
                        "WebkitLineClamp": "3",
                        "WebkitBoxOrient": "vertical",
                        "overflow": "hidden",
                        "whiteSpace": "pre-wrap",
                    },
                ),
                rx.fragment(),
            ),
            # 外部 SNS / web リンク (CIP-119 references_json)
            rx.cond(
                r["links_csv"] != "",
                rx.hstack(
                    rx.foreach(r["links_csv"].split(","), _social_link_icon),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.fragment(),
            ),
            # トピック特徴
            rx.cond(
                r["top_yes_csv"] != "",
                rx.hstack(
                    rx.text(
                        AuthState.t["drep_match_results_active_in"],
                        size="1", color="var(--green-11)", weight="medium",
                        style={"flexShrink": "0"},
                    ),
                    rx.foreach(r["top_yes_csv"].split(","), _topic_chip),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.fragment(),
            ),
            rx.cond(
                r["top_no_csv"] != "",
                rx.hstack(
                    rx.text(
                        AuthState.t["drep_match_results_cautious_in"],
                        size="1", color="var(--red-11)", weight="medium",
                        style={"flexShrink": "0"},
                    ),
                    rx.foreach(r["top_no_csv"].split(","), _topic_chip),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.fragment(),
            ),
            spacing="3", align_items="stretch", width="100%",
        ),
        padding="18px 20px",
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.04)"),
        width="100%",
        _hover={
            "border_color": rx.color("amber", 8),
            "transform":    "translateY(-1px)",
        },
        style={"transition": "border-color 0.15s, transform 0.15s"},
    )


def _results_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading(AuthState.t["drep_match_results_heading"], size="5"),
            rx.spacer(),
            rx.button(
                rx.icon("rotate-cw", size=14),
                rx.text(AuthState.t["drep_match_restart_button"], size="2"),
                on_click=DrepMatchState.start_quiz,
                variant="soft", color_scheme="gray", cursor="pointer",
            ),
            width="100%", align="center", wrap="wrap",
        ),
        rx.cond(
            DrepMatchState.results,
            rx.vstack(
                rx.foreach(
                    DrepMatchState.results.to(list[dict[str, str]]),
                    _match_result_card,
                ),
                spacing="3", width="100%",
            ),
            rx.callout(
                AuthState.t["drep_match_results_no_match"],
                icon="info", color_scheme="gray",
            ),
        ),
        spacing="4", width="100%",
    )


def _match_view() -> rx.Component:
    """quiz と results を view に応じて切り替える親コンテナ。"""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading(AuthState.t["drep_match_heading"], size="6", weight="bold"),
                rx.badge(
                    AuthState.t["drep_match_beta_label"],
                    color_scheme="amber", variant="soft", size="2",
                    style={"alignSelf": "center"},
                ),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.text(
                AuthState.t["drep_match_intro"],
                size="2", color="var(--gray-10)",
            ),
            rx.callout(
                AuthState.t["drep_match_ai_disclaimer"],
                icon="triangle-alert",
                color_scheme="amber",
                size="1",
            ),
            rx.match(
                DrepMatchState.view,
                ("results", _results_view()),
                # quiz / その他は質問カード
                rx.center(_quiz_view(), width="100%", padding_y="12px"),
            ),
            spacing="4", align_items="stretch", width="100%",
        ),
        width="100%",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/governance/drep",
    title="DRep一覧 | ガバナンス | Cardanoism",
    on_load=DrepState.on_load,
)
def governance_drep_page() -> rx.Component:
    return rx.cond(
        DrepState.load,
        rx.box(
            login_modal(),
            # DRep 委任確認モーダル (1 ページに 1 度だけマウント)
            drep_delegation_dialog(),
            rx.vstack(
                _breadcrumb(),
                governance_subnav("drep"),
                _drep_match_tabs(),
                rx.match(
                    DrepMatchState.view,
                    ("quiz",    _match_view()),
                    ("results", _match_view()),
                    # default: "list" — 既存の DRep 一覧
                    rx.vstack(
                        _filter_bar(),
                        rx.hstack(
                            rx.text(AuthState.t["gov_search_results"], size="3"),
                            rx.text(DrepState.total_items, size="5", weight="bold", color="var(--amber-11)"),
                            rx.text(AuthState.t["gov_results_unit"], size="3"),
                            rx.spacer(),
                            rx.hstack(
                                rx.text(AuthState.t["drep_total_delegation_label"], size="2", color="var(--gray-10)"),
                                rx.text(DrepState.total_delegation_ada_display, size="3", weight="bold", color="var(--amber-11)"),
                                rx.text("ADA", size="1", color="var(--gray-10)"),
                                spacing="2", align="baseline",
                            ),
                            spacing="2", align="baseline", width="100%", wrap="wrap",
                        ),
                        rx.cond(
                            DrepState.dreps,
                            rx.vstack(
                                rx.foreach(DrepState.dreps.to(list[dict[str, str]]), _drep_card),
                                spacing="2", width="100%",
                            ),
                            rx.callout(AuthState.t["drep_empty"], icon="info", color_scheme="gray"),
                        ),
                        rx.cond(DrepState.dreps, _pagination(), rx.fragment()),
                        spacing="4", width="100%",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
