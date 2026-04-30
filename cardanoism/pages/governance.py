"""
governance.py
ガバナンスアクション 一覧ページ・個別詳細ページ
"""
import reflex as rx
from typing import Dict, List

from cardanoism.templates import template
from cardanoism.backend.db_connect import GovernanceState
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.governance_card import (
    governance_modal,
    ga_cards_view,
    governance_detail_content,
)
from cardanoism.components.proposal_card import STATUS_DOT_STYLE
from cardanoism.components.componets import top_button_component
from cardanoism.components.login_modal import login_modal
from cardanoism.components.governance_nav import governance_subnav


# ─── react-select ──────────────────────────────────────────────────────────────

class _ReactSelect(rx.Component):
    library = "react-select"
    tag = "Select"


class GovSelect(_ReactSelect):
    is_default = True
    classNamePrefix: rx.Var[str]
    isClearable: rx.Var[bool] = True
    isMulti: rx.Var[bool]
    placeholder: rx.Var[str]
    options: rx.Var[List[Dict[str, str]]]
    defaultValue: rx.Var[List[Dict[str, str]]]
    onChange: rx.EventHandler[lambda value: [value]]


gov_select = GovSelect.create

FILTER_CSS = """
<style>
:where(html, body) .gov-filter__control {
  background-color: var(--slate-2) !important;
  border-color: var(--gray-4) !important;
  color: var(--slate-12) !important;
}
:where(html, body) .gov-filter__menu,
:where(html, body) .gov-filter__menu-list {
  background-color: var(--slate-1) !important;
  color: var(--slate-12) !important;
  z-index: 1002 !important;
}
:where(html, body) .gov-filter__menu-portal { z-index: 1002 !important; }
:where(html, body) .gov-filter__option { color: var(--slate-12) !important; }
:where(html, body) .gov-filter__option--is-focused {
  background-color: var(--amber-7) !important;
  color: var(--slate-12) !important;
}
:where(html, body) .gov-filter__placeholder { color: var(--slate-10) !important; }
:where(html, body) .gov-filter__multi-value {
  background-color: var(--amber-3) !important;
  color: var(--amber-11) !important;
}
:where(html, body) .gov-filter__multi-value__label { color: var(--amber-11) !important; }
:where(html, body) .gov-filter__indicator-separator { display: none !important; }
:where(html, body) .gov-filter__control--is-focused {
  box-shadow: 0 0 0 2px var(--amber-7) !important;
}
:where(html.dark, body.dark) .gov-filter__control {
  background-color: var(--slate-3) !important;
  border-color: var(--slate-1) !important;
}
:where(html.dark, body.dark) .gov-filter__menu,
:where(html.dark, body.dark) .gov-filter__menu-list {
  background-color: var(--slate-2) !important;
}
.ga-mobile-filter-accordion {
  border-top: 1px solid var(--gray-4);
  border-bottom: 1px solid var(--gray-4);
  overflow: visible;
  position: relative;
  z-index: 1;
}
.ga-mobile-filter-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0;
  color: var(--blue-10);
  font-weight: 600;
  background-color: var(--gray-1);
  border: none;
}
.ga-mobile-filter-trigger::after {
  content: "+";
  font-size: 16px;
  line-height: 1;
  color: var(--blue-10);
}
.ga-mobile-filter-trigger[data-state="open"]::after { content: "-"; }
.ga-filter-accordion-content {
  overflow: visible !important;
  padding: 4px 0;
}
</style>
"""



# ─── パンくずリスト ────────────────────────────────────────────────────────────

def gov_breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["gov_subnav_actions"], size="2", weight="medium"),
        spacing="2",
        align="center",
        width="100%",
        padding_top="15px",
        padding_bottom="0px",
    )


def gov_breadcrumb_detail() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.link(AuthState.t["gov_subnav_actions"], href="/governance/ga_proposals",
                size="2", underline="hover", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["gov_breadcrumb_detail"], size="2", weight="medium"),
        spacing="2",
        align="center",
        width="100%",
        padding_top="15px",
        padding_bottom="0px",
    )


# ─── フィルター ────────────────────────────────────────────────────────────────

def gov_filters() -> rx.Component:
    # モバイル用（別インスタンス）
    mobile_selects = rx.vstack(
        gov_select(
            classNamePrefix="gov-filter",
            options=AuthState.gov_type_options,
            placeholder=AuthState.t["gov_filter_type_placeholder"],
            defaultValue=GovernanceState.filter_type_selected,
            onChange=lambda value: GovernanceState.set_filter_types(value),
            isMulti=True,
            styles=None,
            theme=None,
            width="100%",
        ),
        gov_select(
            classNamePrefix="gov-filter",
            options=AuthState.gov_status_options,
            placeholder=AuthState.t["gov_filter_status_placeholder"],
            defaultValue=GovernanceState.filter_status_selected,
            onChange=lambda value: GovernanceState.set_filter_statuses(value),
            isMulti=True,
            styles=None,
            theme=None,
            width="100%",
        ),
        spacing="2",
        width="100%",
        padding_y="4px",
    )

    # デスクトップ用（別インスタンス）
    desktop_selects = rx.flex(
        rx.box(
            gov_select(
                classNamePrefix="gov-filter",
                options=AuthState.gov_type_options,
                placeholder=AuthState.t["gov_filter_type_placeholder"],
                defaultValue=GovernanceState.filter_type_selected,
                onChange=lambda value: GovernanceState.set_filter_types(value),
                isMulti=True,
                styles=None,
                theme=None,
                width="100%",
            ),
            width=["100%", "100%", "49%", "49%", "49%"],
        ),
        rx.box(
            gov_select(
                classNamePrefix="gov-filter",
                options=AuthState.gov_status_options,
                placeholder=AuthState.t["gov_filter_status_placeholder"],
                defaultValue=GovernanceState.filter_status_selected,
                onChange=lambda value: GovernanceState.set_filter_statuses(value),
                isMulti=True,
                styles=None,
                theme=None,
                width="100%",
            ),
            width=["100%", "100%", "49%", "49%", "49%"],
        ),
        width="100%",
        spacing="2",
        wrap="wrap",
        row_gap="8px",
    )

    return rx.vstack(
        rx.html(FILTER_CSS),
        rx.box(
            rx.input(
                placeholder=AuthState.t["gov_filter_search_placeholder"],
                size="3",
                max_length=100,
                value=GovernanceState.search_query,
                on_change=lambda v: GovernanceState.set_inputed_value(v).debounce(500),
                width="100%",
            ),
            width="100%",
        ),
        rx.mobile_only(
            rx.accordion.root(
                rx.accordion.item(
                    header=rx.accordion.trigger(
                        rx.text(AuthState.t["gov_filter_expand"], size="3"),
                        class_name="ga-mobile-filter-trigger",
                    ),
                    content=rx.accordion.content(
                        mobile_selects,
                        class_name="ga-filter-accordion-content",
                        width="100%",
                    ),
                    value="ga-filters",
                    padding="0px",
                ),
                type="multiple",
                collapsible=True,
                width="100%",
                radius="none",
                variant="ghost",
                class_name="ga-mobile-filter-accordion",
                padding_x="0px",
            ),
            width="100%",
        ),
        rx.tablet_and_desktop(desktop_selects, width="100%"),
        spacing="2",
        width="100%",
        padding_bottom="16px",
    )


# ─── ヘッダー ──────────────────────────────────────────────────────────────────

def gov_header() -> rx.Component:
    return rx.flex(
        rx.flex(
            rx.text(AuthState.t["gov_search_results"], size="4"),
            rx.text(GovernanceState.total_items, size="6", weight="bold", color="var(--amber-11)"),
            rx.text(AuthState.t["gov_results_unit"], size="4"),
            align_items="baseline",
            spacing="2",
            margin_left="4px",
        ),
        rx.tablet_and_desktop(
            rx.hstack(
                rx.button(
                    rx.icon("list"),
                    variant=rx.cond(GovernanceState.view_mode == "list", "solid", "soft"),
                    color_scheme=None,
                    background_color=rx.cond(GovernanceState.view_mode == "list", "var(--amber-7)", "var(--gray-3)"),
                    color=rx.cond(GovernanceState.view_mode == "list", "var(--gray-12)", "var(--gray-10)"),
                    _hover={"background_color": "var(--amber-7)", "color": "var(--gray-12)"},
                    size="2",
                    on_click=GovernanceState.set_view_mode("list"),
                    cursor="pointer",
                ),
                rx.button(
                    rx.icon("layout-grid"),
                    variant=rx.cond(GovernanceState.view_mode == "grid", "solid", "soft"),
                    color_scheme=None,
                    background_color=rx.cond(GovernanceState.view_mode == "grid", "var(--amber-7)", "var(--gray-3)"),
                    color=rx.cond(GovernanceState.view_mode == "grid", "var(--gray-12)", "var(--gray-10)"),
                    _hover={"background_color": "var(--amber-7)", "color": "var(--gray-12)"},
                    size="2",
                    on_click=GovernanceState.set_view_mode("grid"),
                    cursor="pointer",
                ),
                spacing="2",
            ),
        ),
        width="100%",
        justify_content="space-between",
        align_items="center",
        display="flex",
    )


# ─── ページネーション ──────────────────────────────────────────────────────────

def gov_pagination() -> rx.Component:
    def create_page_button(page):
        is_active = page == GovernanceState.current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: GovernanceState.set_page(page),
            variant=rx.cond(is_active, "solid", "soft"),
            radius="full",
            size="2",
            padding_x="10px",
            class_name="md:inline-flex hidden",
            _hover={"cursor": "pointer"},
        )

    def create_ellipsis():
        return rx.button(
            "...",
            radius="full",
            size="2",
            variant="soft",
            class_name="md:inline-flex hidden",
            background="none",
            _hover={"background-color": "none"},
        )

    return rx.flex(
        rx.button(
            rx.icon(tag="chevron-left"),
            on_click=GovernanceState.prev_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=GovernanceState.current_page == 1,
            _hover={"cursor": "pointer"},
        ),
        rx.cond(
            GovernanceState.start_page > 1,
            rx.box(
                create_page_button(1),
                rx.cond(GovernanceState.start_page > 2, create_ellipsis()),
            ),
        ),
        rx.foreach(GovernanceState.middle_page, create_page_button),
        rx.cond(
            GovernanceState.end_page < GovernanceState.total_pages,
            rx.box(
                rx.cond(GovernanceState.end_page < GovernanceState.total_pages - 1, create_ellipsis()),
                create_page_button(GovernanceState.total_pages),
            ),
        ),
        rx.button(
            rx.icon(tag="chevron-right"),
            on_click=GovernanceState.next_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=GovernanceState.current_page == GovernanceState.total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="pagination gap-2",
        padding_top="2em",
        justify="end",
        align="center",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────

@template(
    route="/governance/ga_proposals",
    title="GA 提案一覧 | Cardanoism",
    on_load=GovernanceState.on_load,
)
def governance_page() -> rx.Component:
    no_results = rx.card(
        rx.vstack(
            rx.icon("circle-off", size=28),
            rx.text(AuthState.t["gov_no_results"]),
            spacing="2",
            align="center",
        ),
        width="100%",
    )

    return rx.cond(
        GovernanceState.load,
        rx.box(
            STATUS_DOT_STYLE,
            login_modal(),
            governance_modal(),
            rx.vstack(
                gov_breadcrumb(),
                governance_subnav("actions"),
                gov_filters(),
                gov_header(),
                rx.cond(
                    GovernanceState.actions,
                    ga_cards_view(GovernanceState.view_mode),
                    no_results,
                ),
                rx.cond(GovernanceState.actions, top_button_component(), rx.fragment()),
                rx.cond(GovernanceState.actions, gov_pagination(), rx.fragment()),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="20px"),
    )


@template(
    route="/governance/[id]",
    title="ガバナンスアクション | Cardanoism",
    on_load=GovernanceState.load_detail_page_with_lang,
)
def governance_detail_page() -> rx.Component:
    return rx.cond(
        GovernanceState.load,
        rx.box(
            STATUS_DOT_STYLE,
            login_modal(),
            rx.vstack(
                gov_breadcrumb_detail(),
                rx.cond(
                    GovernanceState.modal_action,
                    rx.card(
                        governance_detail_content(GovernanceState.modal_action),
                        width="100%",
                        padding="24px",
                        background_color="var(--gray-3)",
                    ),
                    rx.callout(
                        AuthState.t["gov_no_results"],
                        icon="info",
                        color_scheme="gray",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="20px"),
    )
