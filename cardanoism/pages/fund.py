import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.db_connect import AppState, FundListState
from cardanoism.components.proposal_card import card_foreach_dict
from cardanoism.components.proposal_pagenation import pagination_component
from cardanoism.components.componets import top_button_component


class ReactSelectLib(rx.Component):
    library = "react-select"
    tag = "Select"


class CatalystChallengeSelect(ReactSelectLib):
    is_default = True
    classNamePrefix: rx.Var[str]
    isClearable: rx.Var[bool] = True
    isMulti: rx.Var[bool]
    placeholder: rx.Var[str]
    options: rx.Var[list[dict[str, str]]]
    controlShouldRenderValue: rx.Var[bool] = True
    defaultValue: rx.Var[list[dict[str, str]]]
    onChange: rx.EventHandler[lambda value: [value]]


challegeFilter = CatalystChallengeSelect.create

FUNDING_STATUS_OPTIONS = [
    {"value": "funded", "label": "採択"},
    {"value": "not_approved", "label": "不採択"},
    {"value": "over_budget", "label": "申請不備"},
    {"value": "pending", "label": "投票期間中"},
]

PROJECT_STATUS_OPTIONS = [
    {"value": "in_progress", "label": "進行中"},
    {"value": "complete", "label": "完了"},
]

FILTER_THEME_CSS = """
<style>
:where(html, body) .filter__control {
  background-color: var(--slate-2) !important;
  border-color: var(--gray-4) !important;
  color: var(--slate-12) !important;
}
:where(html, body) .filter__menu,
:where(html, body) .filter__menu-list {
  background-color: var(--slate-1) !important;
  color: var(--slate-12) !important;
}
:where(html, body) .filter__option { color: var(--slate-12) !important; }
:where(html, body) .filter__option--is-focused {
  background-color: var(--amber-7) !important;
  color: var(--slate-12) !important;
}
:where(html, body) .filter__placeholder {
  color: var(--slate-10) !important;
}
:where(html, body) .filter__multi-value {
  background-color: var(--amber-3) !important;
  color: var(--amber-11) !important;
}
:where(html, body) .filter__multi-value__label { color: var(--amber-11) !important; }
:where(html, body) .filter__multi-value__label:hover { background-color: var(--amber-4) !important; }
:where(html, body) .filter__indicator-separator { display: none !important; }
:where(html, body) .filter__control--is-focused { box-shadow: 0 0 0 2px var(--amber-7) !important; }

:where(html.dark, body.dark) .filter__control {
  background-color: var(--slate-3) !important;
  border-color: var(--slate-1) !important;
  color: var(--slate-12) !important;
}
:where(html.dark, body.dark) .filter__menu,
:where(html.dark, body.dark) .filter__menu-list {
  background-color: var(--slate-2) !important;
  border-color: var(--slate-7) !important;
  color: var(--slate-12) !important;
}
</style>
"""

def stat_chip(icon: str, label: str, value: str | int) -> rx.Component:
    """Compact stat block used in fund headers."""
    return rx.box(
        rx.hstack(
            rx.box(
                rx.icon(icon, size=16, color=rx.color("slate", 12)),
                padding="8px",
                background_color=rx.color("slate", 3),
                border_radius="full",
                shadow="0 6px 18px rgba(0, 0, 0, 0.08)",
            ),
            rx.vstack(
                rx.text(label.upper(), size="1", color=rx.color("slate", 10), weight="medium", letter_spacing="0.06em"),
                rx.text(value, size="4", weight="bold", color=rx.color("slate", 12), text_wrap="nowrap"),
                spacing="1",
                align_items="start",
            ),
            spacing="3",
            align="center",
        ),
        padding="12px",
        border_radius="14px",
        background_color=rx.color("slate", 2),
        border=f"1px solid {rx.color('slate', 6)}",
        width="100%",
        shadow="0 10px 25px rgba(0, 0, 0, 0.05)",
    )


def fund_card(fund: dict) -> rx.Component:
    """Fund summary card linking to proposal list."""
    label = fund["display_label"]
    title = fund["display_title"]
    amount = fund["display_amount_comma"]
    currency_symbol = fund["display_currency_symbol"]
    proposals = fund["display_proposals"]
    funded = fund["display_funded"]
    completed = fund["display_completed"]
    href = fund["path"]

    amount_box = rx.box(
        rx.hstack(
            rx.hstack(
                rx.icon("coins", size=18, color=rx.color("slate", 11)),
                rx.text("総額", size="2", color=rx.color("slate", 10)),
                spacing="2",
                align="center",
            ),
            rx.text(f"{currency_symbol} {amount}".strip(), size="5", weight="bold", color=rx.color("slate", 12)),
            justify="between",
            align="center",
            width="100%",
        ),
        padding="12px",
        border_radius="14px",
        background_color="var(--gray-1)",
        border=f"1px solid {rx.color('slate', 6)}",
        width="100%",
    )

    stats_box = rx.box(
        rx.hstack(
            rx.vstack(
                rx.text("提案数", size="2", color=rx.color("slate", 10), text_align="center"),
                rx.text(proposals, size="4", weight="bold", color=rx.color("slate", 12), text_align="center"),
                spacing="1",
                align_items="center",
                width="33%",
            ),
            rx.divider(orientation="vertical", height="40px", border_color=rx.color("slate", 6)),
            rx.vstack(
                rx.text("採択", size="2", color=rx.color("slate", 10), text_align="center"),
                rx.text(funded, size="4", weight="bold", color=rx.color("slate", 12), text_align="center"),
                spacing="1",
                align_items="center",
                width="33%",
            ),
            rx.divider(orientation="vertical", height="40px", border_color=rx.color("slate", 6)),
            rx.vstack(
                rx.text("完了", size="2", color=rx.color("slate", 10), text_align="center"),
                rx.text(completed, size="4", weight="bold", color=rx.color("slate", 12), text_align="center"),
                spacing="1",
                align_items="center",
                width="33%",
            ),
            spacing="3",
            justify="between",
            width="100%",
            wrap="nowrap",
            align="center",
        ),
        padding="12px",
        border_radius="14px",
        background_color="var(--gray-1)",
        border=f"1px solid {rx.color('slate', 6)}",
        width="100%",
    )

    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.heading(title, size="5", color=rx.color("slate", 12)),
                #rx.badge(fund["display_status"], variant="soft", radius="full", color_scheme="gray",size="2"),
                justify="between",
                width="100%",
            ),
            amount_box,
            stats_box,
            rx.box(
                rx.link(
                    rx.button(
                        "Fund提案を見る",
                        variant="solid",
                        color_scheme=None,
                        size="2",
                        width="100%",
                        padding_x="12px",
                        padding_y="10px",
                        border_radius="8px",
                        cursor="pointer",
                    ),
                    href=href,
                    width="100%",
                    display="block",
                ),
                width="100%",
                margin_top="auto",
            ),
            spacing="4",
            align_items="stretch",
            width="100%",
        ),
        variant="ghost",
        background=rx.color_mode_cond(
            rx.color("slate", 2),
            rx.color("slate", 3),
        ),
        border=f"1px solid {rx.color('slate', 6)}",
        shadow="0px 14px 35px -24px rgba(0, 0, 0, 0.16)",
        padding="20px",
        height="auto",
    )


def fund_hero() -> rx.Component:
    """Hero block for fund landing page."""
    return rx.box(
        rx.vstack(
            rx.text("Catalyst Funds", size="3", color=rx.color("slate", 11), weight="medium", letter_spacing="0.08em"),
            rx.heading("ファンド別", size="8", color=rx.color("slate", 12), line_height="1.1"),
            rx.text(
                "Fundごとの提案状況と実績をまとめました。気になるFundを選んで提案を探してみましょう。",
                size="3",
                color=rx.color("slate", 10),
                max_width="720px",
            ),
            rx.hstack(
                rx.link(rx.button("Catalyst一覧に戻る", variant="soft", color_scheme=None, size="3",
                                   background_color=rx.color("slate", 3), color=rx.color("slate", 12),
                                   _hover={"background_color": rx.color("amber", 10), "color": "white"}),href="/catalyst"),
                #rx.link(rx.button("�ŐV��Fund������", variant="solid", color_scheme=None, size="3",
                #                   background_color=rx.color("amber", 10), color="white",
                #                   _hover={"background_color": rx.color("amber", 9)}), href="/catalyst/funds"),
                spacing="3",
                wrap="wrap",
                cursor="pointer",
            ),
            spacing="3",
            align_items="start",
        ),
        padding="25px",
        border_radius="16px",
        background=(
            "radial-gradient(circle at 20% 20%, rgba(0,113,201,0.18), transparent 35%),"
            "radial-gradient(circle at 80% 0%, rgba(255,193,7,0.22), transparent 35%),"
            f"linear-gradient(135deg, {rx.color('slate', 2)}, rgba(0,0,0,0.05))"
        ),
        border=f"1px solid {rx.color('slate', 6)}",
        shadow="0px 20px 60px -40px rgba(59, 91, 219, 0.45)",
        width="100%",
    )


def empty_fund_state() -> rx.Component:
    """Shown when no fund data is available."""
    return rx.card(
        rx.vstack(
            rx.icon("folder-x", size=32, color=rx.color("slate", 10)),
            rx.heading("ファンド別", size="5"),
            rx.text("Fundごとの提案状況と実績をまとめました。気になるFundを選んで提案を探してみましょう", color=rx.color("slate", 10), text_align="center"),
            rx.link(rx.button("Catalyst一覧に戻る", variant="soft", color_scheme=None,
                               background_color=rx.color("amber", 4), color=rx.color("amber", 11),
                               _hover={"background_color": rx.color("amber", 10), "color": "white"}), href="/catalyst"),
            spacing="3",
            align="center",
        ),
        width="100%",
        align="center",
    )


def fund_header_detail() -> rx.Component:
    """Header block for individual fund pages."""
    fund = AppState.fund_meta
    stats_box = rx.box(
        rx.hstack(
            rx.vstack(
                rx.text("提案数", size="2", color=rx.color("slate", 10), text_align="center"),
                rx.text(fund.get("display_proposals", fund.get("proposals_count", 0)), size="4", weight="bold", color=rx.color("slate", 12), text_align="center"),
                spacing="1",
                align_items="center",
                width="33%",
            ),
            rx.divider(orientation="vertical", height="40px", border_color=rx.color("slate", 6)),
            rx.vstack(
                rx.text("採択", size="2", color=rx.color("slate", 10), text_align="center"),
                rx.text(fund.get("display_funded", fund.get("funded_proposals_count", 0)), size="4", weight="bold", color=rx.color("slate", 12), text_align="center"),
                spacing="1",
                align_items="center",
                width="33%",
            ),
            rx.divider(orientation="vertical", height="40px", border_color=rx.color("slate", 6)),
            rx.vstack(
                rx.text("完了", size="2", color=rx.color("slate", 10), text_align="center"),
                rx.text(fund.get("display_completed", fund.get("completed_proposals_count", 0)), size="4", weight="bold", color=rx.color("slate", 12), text_align="center"),
                spacing="1",
                align_items="center",
                width="33%",
            ),
            spacing="3",
            justify="between",
            width="100%",
            wrap="nowrap",
            align="center",
        ),
        padding="12px",
        border_radius="14px",
        background_color=rx.color("slate", 2),
        border=f"1px solid {rx.color('slate', 6)}",
        width=["100%", "100%", "50%", "50%", "50%"],
    )
    return rx.card(
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.hstack(
                            rx.badge(
                                fund.get("display_label", fund.get("label", "Fund")),
                                variant="solid",
                                radius="full",
                                background_color=rx.color("amber", 10),
                                color="white",
                            ),
                            rx.badge(
                                fund.get("display_status", fund.get("status", "")),
                                variant="soft",
                                radius="full",
                                background_color=rx.color("amber", 4),
                                color=rx.color("amber", 11),
                            ),
                            spacing="2",
                            wrap="wrap",
                        ),
                        rx.hstack(
                            rx.heading(fund.get("display_title", fund.get("title", fund.get("label", ""))), size="7", color=rx.color("amber", 11)),
                            rx.text(
                                f"{fund.get('display_currency_symbol', fund.get('currency_symbol',''))} {fund.get('display_amount_comma', fund.get('amount_comma','-'))}".strip(),
                                size="5",
                                weight="bold",
                                color=rx.color("amber", 11),
                            ),
                            spacing="3",
                            align="center",
                            wrap="wrap",
                        ),
                    ),
                    stats_box,
                    flex_direction=["column", "column", "row", "row", "row"],
                    justify="between",
                    align="start",
                    width="100%",
                ),
                #rx.text(fund.get("display_description", fund.get("description", "Fund")), size="3", color=rx.color("slate", 10), max_width="900px"),
                spacing="4",
                width="100%",
            ),
        ),
        background=rx.color_mode_cond(
            f"linear-gradient(135deg, rgba(255,193,7,0.14), rgba(255,193,7,0.08))",
            f"linear-gradient(135deg, rgba(255,193,7,0.16), rgba(255,193,7,0.10))",
        ),
        border=f"1px solid {rx.color('slate', 6)}",
        shadow="0px 20px 60px -40px rgba(59, 91, 219, 0.45)",
        width="100%",
    )


def fund_breadcrumb() -> rx.Component:
    """Simple breadcrumb for fund detail pages."""
    fund = AppState.fund_meta
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none",color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.link(rx.text("Catalyst", size="2"), href="/catalyst", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.link(rx.text("Funds", size="2"), href="/catalyst/funds", underline="none",color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(fund.get("display_title", fund.get("title", fund.get("label", ""))), size="2", weight="medium"),
        spacing="2",
        align="center",
        width="100%",
        padding_top="8px",
        padding_bottom="12px",
    )


def proposal_controls() -> rx.Component:
    """Small toolbar for fund detail proposal list."""
    return rx.hstack(
        rx.hstack(
            rx.text(AppState.total_items, size="6", weight="bold", color="var(--amber-11)"),
            rx.text("件", size="4"),
            spacing="2",
            align="baseline",
        ),
        rx.tablet_and_desktop(
            rx.hstack(
                rx.button(
                    rx.icon("list"),
                    variant=rx.cond(AppState.view_mode == "list", "solid", "soft"),
                    color_scheme=None,
                    background_color=rx.cond(
                        AppState.view_mode == "list",
                            "var(--amber-7)",
                            "var(--gray-3)",
                    ),
                    color=rx.cond(
                        AppState.view_mode == "list",
                            "var(--gray-12)",
                            "var(--gray-10)",
                    ),
                    _hover={
                        "background_color": rx.cond(
                            AppState.view_mode == "list",
                                "var(--amber-7)",
                                "var(--amber-7)",
                        ),
                        "color": "var(--gray-12)",
                    },
                    size="2",
                    on_click=AppState.set_view_mode("list"),
                    cursor="pointer",
                ),
                rx.button(
                    rx.icon("layout-grid"),
                    variant=rx.cond(AppState.view_mode == "grid", "solid", "soft"),
                    color_scheme=None,
                    background_color=rx.cond(
                        AppState.view_mode == "grid",
                            "var(--amber-7)",
                            "var(--gray-3)",
                    ),
                    color=rx.cond(
                        AppState.view_mode == "grid",
                            "var(--gray-12)",
                            "var(--gray-10)",
                    ),
                    _hover={
                        "background_color": rx.cond(
                            AppState.view_mode == "grid",
                                "var(--amber-7)",
                                "var(--amber-7)",
                        ),
                        "color": "var(--gray-12)",
                    },
                    size="2",
                    on_click=AppState.set_view_mode("grid"),
                    cursor="pointer",
                ),
                spacing="2",
                align_items="center",
            ),
        ),
        justify="between",
        align="center",
        width="100%",
        wrap="wrap",
    )

@template(route="/catalyst/funds", title="Catalyst Funds", on_load=FundListState.on_load)
def fund() -> rx.Component:
    """Fund landing page with list of all funds."""
    content = rx.vstack(
        fund_hero(),
        rx.cond(
            FundListState.load,
            rx.cond(
                FundListState.funds,
                rx.grid(
                    rx.foreach(FundListState.funds, lambda fund: fund_card(fund)),
                    columns={"base": "1", "md": "2", "lg": "3"},
                    spacing="6",
                    width="100%",
                ),
                empty_fund_state(),
            ),
            rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="20px"),
        ),
        spacing="6",
        width="100%",
        padding_x=["12px", "16px"],
        align_items="stretch",
    )
    return rx.box(
        content,
        width="100%",
        max_width="1130px",
        margin_x="auto",
    )


@template(route="/catalyst/funds/[fund]", title="Catalyst Fund | Cardanoism", on_load=AppState.load_fund_page)
def fund_detail() -> rx.Component:
    """Fund detail page showing proposals scoped to the selected fund."""
    loading_view = rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="20px")
    no_proposals_view = rx.card(
        rx.vstack(
            rx.icon("circle-off", size=28),
            rx.text("提案が見つかりませんでした"),
            spacing="2",
            align="center",
        ),
        width="100%",
    )

    ready = AppState.load & (AppState.fund_route_slug != "")
    filters = rx.vstack(
        rx.html(FILTER_THEME_CSS),
        rx.flex(
            rx.box(
                rx.input(
                    placeholder="キーワードを入力..(タイトル、タグ、提案情報など)",
                    size="3",
                    max_length=100,
                    value=AppState.search_query,
                    on_change=lambda value: AppState.set_inputed_value(value).debounce(500),
                    width="100%",
                ),
                width=["100%", "100%", "49.5%", "49.5%", "49.5%"],
            ),
            challegeFilter(
                options=AppState.challenge_options,
                classNamePrefix="filter",
                placeholder="チャレンジを選択",
                defaultValue=AppState.selected_challenge_filters,
                onChange=lambda value: AppState.set_selected_chllenge_value(value),
                isMulti=True,
                styles=None,
                theme=None,
                width=["100%", "100%", "49.5%", "49.5%", "49.5%"],
            ),
            width="100%",
            spacing="2",
            justify="between",
            direction={"base": "column", "md": "row"},
            flex_wrap="wrap",
            row_gap="10px",
        ),
        rx.flex(
            challegeFilter(
                options=FUNDING_STATUS_OPTIONS,
                classNamePrefix="filter",
                placeholder="資金調達ステータス",
                defaultValue=AppState.selected_funding_status_filters,
                onChange=lambda value: AppState.set_selected_fundingStatus_value(value),
                isMulti=True,
                styles=None,
                theme=None,
                width=["100%", "100%", "49.5%", "49.5%", "49.5%"],
            ),
            challegeFilter(
                options=PROJECT_STATUS_OPTIONS,
                classNamePrefix="filter",
                placeholder="プロジェクト進捗",
                defaultValue=AppState.selected_project_status_filters,
                onChange=lambda value: AppState.set_selected_projectStatus_value(value),
                isMulti=True,
                styles=None,
                theme=None,
                width=["100%", "100%", "49.5%", "49.5%", "49.5%"],
            ),
            width="100%",
            spacing="2",
            justify="between",
            direction={"base": "column", "md": "row"},
            flex_wrap="wrap",
            row_gap="10px",
        ),
        spacing="2",
        width="100%",
        padding_bottom="20px",
    )

    return rx.box(
        rx.cond(
            ready,
            rx.cond(
                AppState.fund_ids,
                rx.vstack(
                    fund_breadcrumb(),
                    fund_header_detail(),
                    filters,
                    proposal_controls(),
                    rx.cond(AppState.proposals, card_foreach_dict(), no_proposals_view),
                    rx.cond(AppState.proposals, top_button_component(), rx.fragment()),
                    rx.cond(AppState.proposals, pagination_component(AppState), rx.fragment()),
                    spacing="4",
                    width="100%",
                ),
                empty_fund_state(),
            ),
            loading_view,
        ),
        width="100%",
        max_width="1130px",
    )

