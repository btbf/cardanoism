import reflex as rx
from typing import Dict, List

from cardanoism.templates import template
from cardanoism.components.proposal_card import card_foreach_dict
from cardanoism.components.proposal_detail import detail_foreach_dict
from cardanoism.components.proposal_pagenation import pagination_component
from cardanoism.components.componets import top_button_component
from cardanoism.backend.db_connect import AppState, ProposalAppState


class ReactSelectLib(rx.Component):
    library = "react-select"
    tag = "Select"


class CatalystChallengeSelect(ReactSelectLib):
    is_default = True
    isClearable = True
    isMulti: rx.Var[bool]
    placeholder: rx.Var[str]
    options: rx.Var[List[Dict[str, str]]]
    defaultValue: rx.Var[Dict[str, str]]
    onChange: rx.EventHandler[lambda value: [value]]


challegeFilter = CatalystChallengeSelect.create

FUND_SELECT_OPTIONS = [
    {"value": "147", "label": "Fund 14"},
    {"value": "146", "label": "Fund 13"},
    {"value": "139", "label": "Fund 12"},
]

CHALLENGE_OPTIONS = [
    {"value": "153", "label": "F14 カルダノユースケース パートナー&製品"},
    {"value": "154", "label": "F14 カルダノユースケース コンセプト"},
    {"value": "155", "label": "F14 カルダノオープン エコシステム"},
    {"value": "156", "label": "F14 カルダノオープン 開発者"},
    {"value": "146", "label": "F13 カルダノオープン 開発者"},
    {"value": "147", "label": "F13 カルダノオープン エコシステム"},
    {"value": "149", "label": "F13 カルダノユースケース コンセプト"},
    {"value": "150", "label": "F13 カルダノユースケース 製品"},
    {"value": "151", "label": "F13 カルダノパートナー 企業"},
    {"value": "152", "label": "F13 カルダノパートナー 成長"},
    {"value": "142", "label": "F12 パートナーと実世界の統合"},
    {"value": "143", "label": "F12 使用事例 コンセプト"},
    {"value": "144", "label": "F12 使用事例 MVP"},
    {"value": "145", "label": "F12 使用事例 製品"},
    {"value": "140", "label": "F12 カルダノオープン 開発者"},
    {"value": "141", "label": "F12 カルダノオープン エコシステム"},
]

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


@template(route="/catalyst/", title="カタリストファンド", on_load=AppState.on_load)
def catalyst() -> rx.Component:
    filters = rx.vstack(
        rx.box(
            rx.input(
                placeholder="全文検索...(IdeascaleNo、タイトル、課題、解決策など)",
                size="3",
                max_length=100,
                on_change=lambda value: AppState.set_inputed_value(value),
                width="100%",
            ),
            width="100%",
        ),
        rx.flex(
            challegeFilter(
                options=FUND_SELECT_OPTIONS,
                placeholder="ファンド",
                onChange=lambda value: AppState.set_selected_fund_value(value),
                isMulti=True,
                width=["100%", "100%", "48%", "24%", "24%"],
            ),
            challegeFilter(
                options=CHALLENGE_OPTIONS,
                placeholder="チャレンジ",
                onChange=lambda value: AppState.set_selected_chllenge_value(value),
                isMulti=True,
                width=["100%", "100%", "48%", "24%", "24%"],
            ),
            challegeFilter(
                options=FUNDING_STATUS_OPTIONS,
                placeholder="投票ステータス",
                onChange=lambda value: AppState.set_selected_fundingStatus_value(value),
                isMulti=True,
                width=["100%", "100%", "48%", "24%", "24%"],
            ),
            challegeFilter(
                options=PROJECT_STATUS_OPTIONS,
                placeholder="プロジェクト進捗",
                onChange=lambda value: AppState.set_selected_projectStatus_value(value),
                isMulti=True,
                width=["100%", "100%", "48%", "24%", "24%"],
            ),
            width="100%",
            spacing="2",
            justify="between",
            display=["block", "block", "flex", "flex", "flex"],
            flex_wrap="wrap",
            row_gap="10px",
        ),
        spacing="2",
        width="100%",
        padding_y="20px",
    )

    header = rx.flex(
        rx.flex(
            rx.text(AppState.total_items, size="6", weight="bold", trim="end", color_scheme="crimson"),
            rx.text("件"),
            spacing="2",
            align_items="baseline",
            margin_left="5px",
        ),
        rx.desktop_only(
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
            ),
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
            #margin_x="auto",
        ),
        rx.box(
            rx.spinner(size="3"),
            padding_y="15px",
        ),
    )


@template(route="/catalyst/[proposal_id]", title="カタリストファンド | 詳細", on_load=ProposalAppState.on_load)
def proposal_detail_page() -> rx.Component:
    return rx.vstack(
        detail_foreach_dict(),
        margin_top="15px",
    )
