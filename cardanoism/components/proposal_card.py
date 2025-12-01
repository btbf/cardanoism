import reflex as rx
from typing import Dict, Any
from cardanoism.backend.db_connect import AppState


class ReactStarLib(rx.Component):
    """RSuite Rate wrapper for compatibility with detail view."""

    library = "rsuite"
    tag = "Rate"

    def add_imports(self):
        return {"": "rsuite/Rate/styles/index.css"}


class CatalystRating(ReactStarLib):
    defaultValue: float
    allowHalf: bool = True
    readOnly: bool = True
    color: str = "yellow"
    size: str = "xs"


proposal_rating = CatalystRating.create


def ProjectRating(value_rate) -> rx.Component:
    """Stars for detail page (kept for proposal_detail)."""
    return rx.box(proposal_rating(value="5", defaultValue=value_rate))


def status_badge(status: str) -> rx.Component:
    """Status pill aligned with Fund badge sizing."""
    return rx.match(
        status,
        ("funded", rx.badge("採択", variant="surface", size="2", color_scheme="green", radius="full")),
        ("not_approved", rx.badge("不採択", variant="surface", size="2", color_scheme="red", radius="full")),
        ("over_budget", rx.badge("申請不備", variant="surface", size="2", color_scheme="red", radius="full")),
        ("pending", rx.badge("投票期間中", variant="surface", size="2", color_scheme="iris", radius="full")),
        rx.badge("進行中", variant="surface", size="2", color_scheme="gray", radius="full"),
    )


def pill(text: str, icon: str, scheme: str = "indigo") -> rx.Component:
    return rx.badge(
        rx.hstack(rx.icon(icon, size=14), rx.text(text, size="1"), spacing="1", align="center"),
        variant="surface",
        color_scheme=scheme,
        radius="full",
        size="2",
    )


def fund_progress_bar(proposal: Dict[str, Any]) -> rx.Component:
    """Progress bar for funded proposals using precomputed fund_percent."""
    return rx.cond(
        proposal["funding_status"] == "funded",
        rx.box(
            rx.progress(
                value=proposal["fund_percent"],
                height="10px",
                color_scheme="green",
            ),
            rx.hstack(
                rx.text("取得率", size="2", color="var(--gray-10)"),
                rx.text(f"{proposal['fund_percent']}%", size="2", color="var(--green-11)", weight="bold"),
                spacing="2",
                align="center",
            ),
            spacing="1",
            width="100%",
        ),
        rx.box(),
    )


def proposal_list(proposal: Dict[str, Any]) -> rx.Component:
    description = rx.cond(
        proposal["solution_ja"],
        proposal["solution_ja"],
        rx.cond(
            proposal["problem_ja"],
            proposal["problem_ja"],
            proposal["title"],
        ),
    )

    rating_display = rx.cond(
        proposal["alignment_score"],
        rx.hstack(
            rx.icon("star", size=16, color="var(--amber-9)"),
            rx.text(proposal["alignment_score"], size="2", weight="bold", color="var(--amber-11)"),
            spacing="1",
            align="center",
        ),
        rx.hstack(
            rx.icon("star", size=16, color="var(--gray-8)"),
            rx.text("評価集計中", size="2", color="var(--gray-9)"),
            spacing="1",
            align="center",
        ),
    )

    fund_progress = fund_progress_bar(proposal)

    mobile_footer = rx.vstack(
        rx.hstack(
            rx.hstack(
                rx.icon("user", size=16, color="var(--gray-9)"),
                rx.text(proposal["applicant_name"], size="2", color="var(--gray-10)"),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                rx.icon("coins", size=16, color="var(--indigo-9)"),
                rx.text(
                    f"{proposal['currency_symbol']} {proposal['amount_requested_comma']}",
                    size="3",
                    weight="bold",
                    color="var(--indigo-11)",
                ),
                rx.text(proposal["currency"], size="2", color="var(--gray-9)"),
                spacing="2",
                align="center",
            ),
            spacing="3",
            align="center",
            justify="start",
            wrap="wrap",
            width="100%",
        ),
        rx.hstack(
            rating_display,
            justify="start",
            align="center",
            width="100%",
        ),
        fund_progress,
        spacing="2",
        width="100%",
    )

    desktop_footer = rx.hstack(
        rx.hstack(
            rx.icon("user", size=16, color="var(--gray-9)"),
            rx.text(proposal["applicant_name"], size="2", color="var(--gray-10)"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.icon("coins", size=16, color="var(--indigo-9)"),
            rx.text(
                f"{proposal['currency_symbol']} {proposal['amount_requested_comma']}",
                size="3",
                weight="bold",
                color="var(--indigo-11)",
            ),
            rx.text(proposal["currency"], size="2", color="var(--gray-9)"),
            spacing="2",
            align="center",
        ),
        rating_display,
        fund_progress,
        justify="start",
        align="center",
        spacing="3",
        wrap="wrap",
        width="100%",
    )

    page_icon = rx.box(
        rx.icon("expand", size=20, color="var(--indigo-9)"),
        position="absolute",
        right="0px",
        bottom="0px",
        border_radius="full",
        pointer_events="none",
    )

    return rx.card(
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.hstack(
                        status_badge(proposal["funding_status"]),
                        pill(f"Fund {proposal['fund_id']}", "layers", "indigo"),
                        pill(proposal["challenge_title_ja"], "flag", "gray"),
                        spacing="2",
                        wrap="wrap",
                        align="center",
                    ),
                    justify="between",
                    width="100%",
                ),
                rx.text(
                    proposal["title_ja"],
                    size="4",
                    weight="bold",
                    color="var(--indigo-12)",
                    line_height="1.2",
                    class_name="hover:text-indigo-10 transition-colors cursor-pointer",
                    on_click=lambda: AppState.open_modal(proposal),
                ),
                rx.text(proposal["title"], size="2", color="var(--gray-9)", class_name="mt-0"),
                rx.text(
                    description,
                    size="3",
                    color="var(--gray-11)",
                    line_height="1.6",
                    text_wrap="wrap",
                    class_name="mt-2",
                ),
                rx.mobile_and_tablet(mobile_footer),
                rx.desktop_only(desktop_footer),
                spacing="3",
                width="100%",
            ),
            page_icon,
            position="relative",
            width="100%",
        ),
        width="100%",
        margin_bottom="1.5em",
        padding="18px",
        class_name=(
            "transition-all duration-300 overflow-hidden "
            "bg-white border border-[rgba(0,0,0,0.05)] "
            "hover:shadow-[0_10px_22px_rgba(64,87,255,0.10)] "
            "hover:border-[rgba(99,132,255,0.28)]"
        ),
        on_click=lambda: AppState.open_modal(proposal),
        cursor="pointer",
    )


def proposal_grid(proposal: Dict[str, Any]) -> rx.Component:
    description = rx.cond(
        proposal["solution_ja"],
        proposal["solution_ja"],
        rx.cond(
            proposal["problem_ja"],
            proposal["problem_ja"],
            proposal["title"],
        ),
    )
    fund_progress = fund_progress_bar(proposal)
    page_icon = rx.box(
        rx.icon("expand", size=16, color="var(--indigo-9)"),
        position="absolute",
        right="0px",
        bottom="0px",
        border_radius="full",
        pointer_events="none",
    )
    return rx.card(
        rx.box(
            rx.vstack(
                rx.hstack(
                    status_badge(proposal["funding_status"]),
                    pill(f"Fund {proposal['fund_id']}", "layers", "indigo"),
                    pill(proposal["challenge_title_ja"], "flag", "gray"),
                    spacing="2",
                    wrap="wrap",
                    align="center",
                ),
                rx.text(
                    proposal["title_ja"],
                    size="3",
                    weight="bold",
                    color="var(--indigo-12)",
                    class_name="hover:text-indigo-10 transition-colors cursor-pointer",
                    on_click=lambda: AppState.open_modal(proposal),
                ),
                rx.text(proposal["title"], size="2", color="var(--gray-9)", class_name="mt-0"),
                rx.text(
                    description,
                    size="2",
                    color="var(--gray-11)",
                    line_height="1.6",
                    text_wrap="wrap",
                    class_name="line-clamp-3 mt-1",
                ),
                rx.vstack(
                    rx.hstack(
                        rx.hstack(
                            rx.icon("user", size=14, color="var(--gray-9)"),
                            rx.text(proposal["applicant_name"], size="2", color="var(--gray-10)"),
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.icon("coins", size=14, color="var(--indigo-9)"),
                            rx.text(
                                f"{proposal['currency_symbol']} {proposal['amount_requested_comma']}",
                                size="3",
                                weight="bold",
                                color="var(--indigo-11)",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.icon("star", size=14, color="var(--amber-9)"),
                            rx.text(
                                rx.cond(
                                    proposal["alignment_score"],
                                    proposal["alignment_score"],
                                    "評価集計中",
                                ),
                                size="2",
                                color="var(--gray-10)",
                            ),
                            spacing="1",
                            align="center",
                        ),
                        justify="start",
                        align="center",
                        spacing="3",
                        wrap="wrap",
                        width="100%",
                    ),
                    fund_progress,
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
            ),
            page_icon,
            position="relative",
            width="100%",
        ),
        class_name=(
            "transition-all duration-300 overflow-hidden "
            "bg-white border border-[rgba(0,0,0,0.05)] "
            "hover:shadow-[0_8px_18px_rgba(64,87,255,0.08)] "
            "hover:border-[rgba(99,132,255,0.28)]"
        ),
        on_click=lambda: AppState.open_modal(proposal),
        cursor="pointer",
    )


def detail_modal() -> rx.Component:
    p = AppState.modal_proposal
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text(p.get("title_ja", "提案詳細"), size="5", weight="bold"),
                        rx.text(p.get("title", ""), size="2", color="var(--gray-10)"),
                        spacing="1",
                        align_items="start",
                    ),
                    rx.icon_button("x", on_click=AppState.close_modal, variant="ghost"),
                    justify="between",
                    align="start",
                    width="100%",
                ),
                rx.hstack(
                    status_badge(p.get("funding_status", "")),
                    pill(f"Fund {p.get('fund_id', '')}", "layers", "indigo"),
                    pill(p.get("challenge_title_ja", ""), "flag", "gray"),
                    spacing="2",
                    wrap="wrap",
                ),
                rx.divider(),
                rx.grid(
                    rx.vstack(
                        rx.text("申請者", size="2", color="var(--gray-10)"),
                        rx.text(p.get("applicant_name", ""), weight="bold"),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("要求額", size="2", color="var(--gray-10)"),
                        rx.text(f"{p.get('currency_symbol','')} {p.get('amount_requested_comma','')}", weight="bold", color="var(--indigo-11)"),
                        spacing="1",
                    ),
                    columns={"base": "1", "md": "2"},
                    gap="3",
                    width="100%",
                ),
                rx.text(p.get("solution_ja", p.get("problem_ja", "")), size="3", line_height="1.8"),
                rx.button("閉じる", on_click=AppState.close_modal, width="100%", variant="soft"),
                spacing="3",
                width="100%",
            ),
            max_width="720px",
            width="90vw",
            class_name="shadow-xl border border-[rgba(0,0,0,0.08)] rounded-2xl",
            style={},
        ),
        open=AppState.modal_open,
        modal=False,
    )


def card_foreach_dict() -> rx.Component:
    return rx.box(
        detail_modal(),
        rx.cond(
            AppState.load,
            rx.cond(
                AppState.view_mode == "grid",
                rx.grid(
                    rx.foreach(AppState.proposals, proposal_grid),
                    columns={"base": "1", "md": "2", "lg": "2"},
                    spacing="4",
                ),
                rx.foreach(AppState.proposals, proposal_list),
            ),
            rx.spinner(size="3"),
        ),
    )
