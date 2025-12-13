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
    defaultValue: rx.Var[dict[str, str]]
    onChange: rx.EventHandler[lambda value: [value]]


challegeFilter = CatalystChallengeSelect.create


def stat_chip(icon: str, label: str, value: str | int) -> rx.Component:
    """Compact stat block used in fund headers."""
    return rx.box(
        rx.hstack(
            rx.box(
                rx.icon(icon, size=16, color="white"),
                padding="8px",
                background_color="var(--color-primary-200)",
                border_radius="full",
                shadow="0 6px 18px rgba(76, 81, 191, 0.25)",
            ),
            rx.vstack(
                rx.text(label.upper(), size="1", color="var(--color-text-200)", weight="medium", letter_spacing="0.06em"),
                rx.text(value, size="4", weight="bold", color="var(--color-primary-100)", text_wrap="nowrap"),
                spacing="1",
                align_items="start",
            ),
            spacing="3",
            align="center",
        ),
        padding="12px",
        border_radius="14px",
        background_color="var(--color-bg-200)",
        border="1px solid var(--color-border)",
        width="100%",
        shadow="0 10px 25px rgba(76, 81, 191, 0.10)",
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

    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.badge(label, variant="solid", radius="full", background_color="var(--color-primary-200)", color="white"),
                rx.badge(fund["display_status"], variant="soft", radius="full", background_color="var(--color-primary-300)", color="var(--color-primary-100)"),
                justify="between",
                width="100%",
            ),
            rx.heading(title, size="4", color="var(--color-primary-100)"),
            rx.box(
                rx.hstack(
                    rx.hstack(
                        rx.icon("coins", size=18, color="var(--color-primary-100)"),
                        rx.text("総額", size="2", color="var(--color-text-200)"),
                        spacing="2",
                        align="center",
                    ),
                    rx.text(f"{currency_symbol} {amount}".strip(), size="5", weight="bold", color="var(--color-primary-100)"),
                    justify="between",
                    align="center",
                    width="100%",
                ),
                padding="12px",
                border_radius="14px",
                background_color="var(--color-primary-300)",
                border="1px solid var(--color-border)",
                width="100%",
            ),
            rx.box(
                rx.hstack(
                    rx.vstack(
                        rx.text("提案数", size="2", color="var(--color-text-200)", text_align="center"),
                        rx.text(proposals, size="4", weight="bold", color="var(--color-primary-100)", text_align="center"),
                        spacing="1",
                        align_items="center",
                        width="33%",
                    ),
                    rx.divider(orientation="vertical", height="40px", border_color="var(--color-border)"),
                    rx.vstack(
                        rx.text("採用", size="2", color="var(--color-text-200)", text_align="center"),
                        rx.text(funded, size="4", weight="bold", color="var(--color-primary-100)", text_align="center"),
                        spacing="1",
                        align_items="center",
                        width="33%",
                    ),
                    rx.divider(orientation="vertical", height="40px", border_color="var(--color-border)"),
                    rx.vstack(
                        rx.text("確定", size="2", color="var(--color-text-200)", text_align="center"),
                        rx.text(completed, size="4", weight="bold", color="var(--color-primary-100)", text_align="center"),
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
                background_color="var(--color-bg-200)",
                border="1px solid var(--color-border)",
                width="100%",
            ),
            rx.box(
                rx.link(
                    rx.button(
                        "Fundを見る",
                        variant="solid",
                        color_scheme=None,
                        size="2",
                        width="100%",
                        padding_x="12px",
                        padding_y="10px",
                        border_radius="8px",
                        background_color="var(--color-primary-200)",
                        color="white",
                        _hover={"background_color": "var(--color-primary-300)"},
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
            "linear-gradient(135deg, var(--color-bg-200), rgba(0,113,201,0.12))",
            "linear-gradient(135deg, var(--color-bg-200), rgba(0,113,201,0.12))",
        ),
        border="1px solid var(--color-border)",
        shadow="0px 14px 35px -24px rgba(76, 81, 191, 0.40)",
        padding="20px",
        height="auto",
    )


def fund_hero() -> rx.Component:
    """Hero block for fund landing page."""
    return rx.box(
        rx.vstack(
            rx.text("Catalyst Funds", size="3", color="var(--color-primary-200)", weight="medium", letter_spacing="0.08em"),
            rx.heading("ファンド別にカタリストを探そう", size="8", color="var(--color-primary-100)", line_height="1.1"),
            rx.text(
                "Fundごとの提案状況と実績をまとめました。気になるFundを選んで提案を探してみましょう。",
                size="3",
                color="var(--color-text-200)",
                max_width="720px",
            ),
            rx.hstack(
                rx.link(rx.button("Catalyst一覧に戻る", variant="soft", color_scheme=None, size="3",
                                   background_color="var(--color-primary-300)", color="var(--color-primary-100)",
                                   _hover={"background_color": "var(--color-primary-200)", "color": "white"}), href="/catalyst"),
                rx.link(rx.button("最新のFundを見る", variant="solid", color_scheme=None, size="3",
                                   background_color="var(--color-primary-200)", color="white",
                                   _hover={"background_color": "var(--color-primary-300)"}), href="/catalyst/funds"),
                spacing="3",
                wrap="wrap",
            ),
            spacing="3",
            align_items="start",
        ),
        padding="28px",
        border_radius="16px",
        background=(
            "radial-gradient(circle at 20% 20%, rgba(0,113,201,0.18), transparent 35%),"
            "radial-gradient(circle at 80% 0%, rgba(0,113,201,0.22), transparent 35%),"
            "linear-gradient(135deg, var(--color-bg-200), rgba(0,113,201,0.16))"
        ),
        border="1px solid var(--color-border)",
        shadow="0px 20px 60px -40px rgba(59, 91, 219, 0.45)",
        width="100%",
    )


def empty_fund_state() -> rx.Component:
    """Shown when no fund data is available."""
    return rx.card(
        rx.vstack(
            rx.icon("folder-x", size=32, color="var(--color-text-200)"),
            rx.heading("ファンド情報が見つかりません", size="5"),
            rx.text("Fundが見つかりませんでした。同期後に再度お試しください", color="var(--color-text-200)", text_align="center"),
            rx.link(rx.button("Catalystトップへ", variant="soft", color_scheme=None,
                               background_color="var(--color-primary-300)", color="var(--color-primary-100)",
                               _hover={"background_color": "var(--color-primary-200)", "color": "white"}), href="/catalyst"),
            spacing="3",
            align="center",
        ),
        width="100%",
        align="center",
    )


def fund_header_detail() -> rx.Component:
    """Header block for individual fund pages."""
    fund = AppState.fund_meta
    return rx.card(
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.badge(
                        fund.get("display_label", fund.get("label", "Fund")),
                        variant="solid",
                        radius="full",
                        background_color="var(--color-primary-200)",
                        color="white",
                    ),
                    rx.badge(
                        fund.get("display_status", fund.get("status", "")),
                        variant="soft",
                        radius="full",
                        background_color="var(--color-primary-300)",
                        color="var(--color-primary-100)",
                    ),
                    spacing="2",
                    wrap="wrap",
                ),
                rx.hstack(
                    rx.heading(fund.get("display_title", fund.get("title", fund.get("label", ""))), size="7", color="var(--color-primary-100)"),
                    rx.text(
                        f"{fund.get('display_currency_symbol', fund.get('currency_symbol',''))} {fund.get('display_amount_comma', fund.get('amount_comma','-'))}".strip(),
                        size="5",
                        weight="bold",
                        color="var(--color-primary-100)",
                    ),
                    spacing="3",
                    align="center",
                    wrap="wrap",
                ),
                rx.text(fund.get("display_description", fund.get("description", "Fundに紐づく提案一覧")), size="3", color="var(--color-text-200)", max_width="900px"),
                rx.flex(
                    stat_chip("layers", "提案数", fund.get("display_proposals", fund.get("proposals_count", 0))),
                    stat_chip("award", "採用", fund.get("display_funded", fund.get("funded_proposals_count", 0))),
                    stat_chip("check", "確定", fund.get("display_completed", fund.get("completed_proposals_count", 0))),
                    wrap="wrap",
                    gap="3",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            rx.box(
                challegeFilter(
                    options=AppState.challenge_options,
                    classNamePrefix="filter",
                    placeholder="キャンペーンを選択",
                    onChange=lambda value: AppState.set_selected_chllenge_value(value),
                    isMulti=True,
                    width="320px",
                ),
                position="absolute",
                top="16px",
                right="16px",
                z_index=2000,
                width=["100%", "340px"],
                style={"overflow": "visible"},
            ),
            position="relative",
            width="100%",
            style={"overflow": "visible"},
        ),
        background=rx.color_mode_cond(
            "linear-gradient(135deg, rgba(0,113,201,0.14), rgba(79,169,255,0.08))",
            "linear-gradient(135deg, rgba(0,113,201,0.16), rgba(79,169,255,0.10))",
        ),
        border="1px solid var(--color-border)",
        shadow="0px 20px 60px -40px rgba(59, 91, 219, 0.45)",
        width="100%",
        style={"overflow": "visible"},
    )


def fund_breadcrumb() -> rx.Component:
    """Simple breadcrumb for fund detail pages."""
    fund = AppState.fund_meta
    return rx.hstack(
        rx.link(rx.hstack(rx.icon("home", size=16), rx.text("HOME", size="2")), href="/", underline="none"),
        rx.icon("chevron-right", size=14, color="var(--color-text-200)"),
        rx.link(rx.text("Catalyst", size="2"), href="/catalyst", underline="none"),
        rx.icon("chevron-right", size=14, color="var(--color-text-200)"),
        rx.link(rx.text("Funds", size="2"), href="/catalyst/funds", underline="none"),
        rx.icon("chevron-right", size=14, color="var(--color-text-200)"),
        rx.text(fund.get("display_title", fund.get("title", fund.get("label", ""))), size="2", color="var(--color-text-200)"),
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
            rx.text(AppState.total_items, size="6", weight="bold", color="var(--color-primary-100)"),
            rx.text("????", size="3", color="var(--color-text-200)"),
            spacing="2",
            align="baseline",
        ),
        rx.hstack(
            rx.button(
                rx.icon("list"),
                variant=rx.cond(AppState.view_mode == "list", "solid", "soft"),
                color_scheme=None,
                background_color=rx.cond(
                    AppState.view_mode == "list",
                    "var(--color-primary-200)",
                    "var(--color-bg-200)",
                ),
                color=rx.cond(
                    AppState.view_mode == "list",
                    "white",
                    "var(--color-text-200)",
                ),
                _hover={
                    "background_color": rx.cond(
                        AppState.view_mode == "list",
                        "var(--color-primary-300)",
                        "var(--color-primary-300)",
                    ),
                    "color": "var(--color-primary-100)",
                },
                size="2",
                on_click=lambda: AppState.set_view_mode("list"),
            ),
            rx.button(
                rx.icon("layout-grid"),
                variant=rx.cond(AppState.view_mode == "grid", "solid", "soft"),
                color_scheme=None,
                background_color=rx.cond(
                    AppState.view_mode == "grid",
                    "var(--color-primary-200)",
                    "var(--color-bg-200)",
                ),
                color=rx.cond(
                    AppState.view_mode == "grid",
                    "white",
                    "var(--color-text-200)",
                ),
                _hover={
                    "background_color": rx.cond(
                        AppState.view_mode == "grid",
                        "var(--color-primary-300)",
                        "var(--color-primary-300)",
                    ),
                    "color": "var(--color-primary-100)",
                },
                size="2",
                on_click=lambda: AppState.set_view_mode("grid"),
            ),
            spacing="2",
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
        max_width="1200px",
        margin_x="auto",
    )


@template(route="/catalyst/funds/[fund]", title="Catalyst Fund | 提案一覧", on_load=AppState.load_fund_page)
def fund_detail() -> rx.Component:
    """Fund detail page showing proposals scoped to the selected fund."""
    loading_view = rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="20px")
    no_proposals_view = rx.card(
        rx.vstack(
            rx.icon("circle-off", size=28, color="var(--color-text-200)"),
            rx.text("No proposals found for this fund", color="var(--color-text-200)"),
            spacing="2",
            align="center",
        ),
        width="100%",
    )

    current_route_fund = AppState.router.page.params.get("fund", "")
    ready = AppState.load & (AppState.fund_route_slug == current_route_fund)

    return rx.box(
        rx.cond(
            ready,
            rx.cond(
                AppState.fund_ids,
                rx.cond(
                    AppState.proposals,
                    rx.vstack(
                        fund_breadcrumb(),
                        fund_header_detail(),
                        proposal_controls(),
                        card_foreach_dict(),
                        top_button_component(),
                        pagination_component(AppState),
                        spacing="4",
                        width="100%",
                    ),
                    no_proposals_view,
                ),
                empty_fund_state(),
            ),
            loading_view,
        ),
        width="100%",
        max_width="1130px",
    )



