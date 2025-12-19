import reflex as rx
from typing import Dict, List

from cardanoism.templates import template
from cardanoism.backend.db_connect import AppState, get_fund_options
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
    options: rx.Var[List[Dict[str, str]]]
    controlShouldRenderValue: rx.Var[bool] = True
    defaultValue: rx.Var[Dict[str, str]]
    onChange: rx.EventHandler[lambda value: [value]]


challegeFilter = CatalystChallengeSelect.create

FUND_SELECT_OPTIONS = get_fund_options()

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


def catalyst_breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none",color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text("Catalyst", size="2", weight="medium"),
        spacing="2",
        align="center",
        width="100%",
        padding_top="15px",
        padding_bottom="0px",
    )


@template(route="/catalyst/", title="カタリスト | Cardanoism", on_load=AppState.on_load)
def catalyst() -> rx.Component:
    filters = rx.vstack(
        rx.html(FILTER_THEME_CSS),
        rx.box(
            rx.input(
                placeholder="キーワードを入力...(タイトル、タグ、提案者名など)",
                size="3",
                max_length=100,
                on_change=lambda value: AppState.set_inputed_value(value).debounce(500),
                width="100%",
            ),
            width="100%",
        ),
        rx.flex(
            challegeFilter(
                classNamePrefix="filter",
                options=FUND_SELECT_OPTIONS,
                placeholder="ファンドを選択",
                onChange=lambda value: AppState.set_selected_fund_value(value),
                isMulti=True,
                styles=None,
                theme=None,
                width=["100%", "100%", "49.5%", "49.5%", "49.5%"],
            ),
            challegeFilter(
                options=AppState.challenge_options,
                classNamePrefix="filter",
                placeholder="チャレンジを選択",
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

    header = rx.flex(
        rx.flex(
            rx.text(AppState.total_items, size="6", weight="bold", color="var(--amber-11)"),
            rx.text("件", size="4"),
            align_items="baseline",
            margin_left="5px",
            spacing="2",
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
                    on_click=lambda: AppState.set_view_mode("list"),
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
                    on_click=lambda: AppState.set_view_mode("grid"),
                    cursor="pointer",
                ),
                spacing="2",
                align_items="center",
            )
        ),
        width="100%",
        justify_content="space-between",
        align_items="center",
        display="flex",
    )
    no_proposals_view = rx.card(
        rx.vstack(
            rx.icon("circle-off", size=28),
            rx.text("提案が見つかりませんでした"),
            spacing="2",
            align="center",
        ),
        width="100%",
    )

    return rx.cond(
        AppState.load,
        rx.box(
            rx.vstack(
                catalyst_breadcrumb(),
                filters,
                header,
                rx.cond(AppState.proposals, card_foreach_dict(), no_proposals_view),
                rx.cond(AppState.proposals, top_button_component(), rx.fragment()),
                rx.cond(AppState.proposals, pagination_component(AppState), rx.fragment()),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="20px"),
    )
