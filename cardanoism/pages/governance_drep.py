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
from cardanoism.components.drep_delegation_dialog import drep_delegation_dialog

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
    avatar = rx.cond(
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
    delegate_disabled = rx.hstack(
        rx.icon("zap", size=14, color="var(--gray-9)"),
        rx.text(
            AuthState.t["delegate_btn"],
            color="var(--gray-10)",
            style={
                "fontSize": "13px",
                "fontWeight": "600",
                "lineHeight": "1.0",
                "whiteSpace": "nowrap",
            },
        ),
        spacing="2",
        align="center",
        padding="8px 16px",
        border_radius="999px",
        background="var(--gray-3)",
        border="1.5px solid var(--gray-6)",
        cursor="not-allowed",
        style={
            "opacity": "0.7",
            "display": "inline-flex",
            "flexShrink": "0",
        },
    )
    delegate_button = rx.box(
        rx.cond(
            is_currently_delegated,
            delegated_badge,
            rx.cond(
                WalletState.connected,
                delegate_active,
                delegate_disabled,
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
    mobile_avatar = rx.cond(
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
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
