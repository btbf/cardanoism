import reflex as rx
from typing import Dict, List

from cardanoism.templates import template
from cardanoism.backend.db_connect import AppState, ProposalAppState, get_fund_options
from cardanoism.components.proposal_card import card_foreach_dict
from cardanoism.components.proposal_detail import detail_foreach_dict
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

FUND_SELECT_DARK_CSS = """
<style>
@media (prefers-color-scheme: dark) {
  .filter__control {
    background-color: var(--color-surface) !important;
    border-color: var(--gray-a7) !important;
    border-width: 1.4px !important;
  }
  .filter__menu {
    background-color: var(--gray-3) !important;
  }
  .filter__option--is-focused {
    background-color: var(--accent-10) !important;
  }
  .filter__placeholder {
    color: var(--gray-10) !important;
    font-weight: 450 !important;
  }
  .filter__multi-value {
    background-color: var(--accent-9) !important;
    }
  .filter__multi-value__label {
    color: var(--glay-4) !important;
    }
   .filter__multi-value__label:hover {
    color: var(--gray-a12) !important;
    background-color: var(--accent-10) !important;
}
</style>
"""


@template(route="/catalyst/", title="カタリスト", on_load=AppState.on_load)
def catalyst() -> rx.Component:
    filters = rx.vstack(
        rx.html(FUND_SELECT_DARK_CSS),
        rx.box(
            rx.input(
                placeholder="キーワード検索...(Ideascale番号・タイトルなど)",
                size="3",
                max_length=100,
                on_change=lambda value: AppState.set_inputed_value(value).debounce(300),
                width="100%",
            ),
            width="100%",
        ),
        rx.flex(
            challegeFilter(
                classNamePrefix="filter",
                options=FUND_SELECT_OPTIONS,
                placeholder="ファンド",
                onChange=lambda value: AppState.set_selected_fund_value(value),
                isMulti=True,
                styles=None,
                theme=None,
                width=["100%", "100%", "49.5%", "49.5%", "49.5%"],
            ),
            challegeFilter(
                options=AppState.challenge_options,
                classNamePrefix="filter",
                placeholder="チャレンジ",
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
                placeholder="資金状況",
                onChange=lambda value: AppState.set_selected_fundingStatus_value(value),
                isMulti=True,
                styles=None,
                theme=None,
                width=["100%", "100%", "49.5%", "49.5%", "49.5%"],
            ),
            challegeFilter(
                options=PROJECT_STATUS_OPTIONS,
                classNamePrefix="filter",
                placeholder="プロジェクト状況",
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
        padding_y="20px",
    )

    header = rx.flex(
        rx.flex(
            rx.text(AppState.total_items, size="6", weight="bold", color="var(--indigo-11)"),
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
                    color_scheme="indigo",
                    size="2",
                    on_click=lambda: AppState.set_view_mode("list"),
                ),
                rx.button(
                    rx.icon("layout-grid"),
                    variant=rx.cond(AppState.view_mode == "grid", "solid", "soft"),
                    color_scheme="indigo",
                    size="2",
                    on_click=lambda: AppState.set_view_mode("grid"),
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

    return rx.cond(
        AppState.load,
        rx.box(
            rx.vstack(
                filters,
                header,
                card_foreach_dict(),
                top_button_component(),
                pagination_component(AppState),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.box(rx.spinner(size="3"), padding_y="15px"),
    )


@template(route="/catalyst/[proposal_id]", title="カタリスト | 詳細", on_load=ProposalAppState.on_load)
def proposal_detail_page():
    return rx.vstack(
        detail_foreach_dict(),
        margin_top="15px",
    )
