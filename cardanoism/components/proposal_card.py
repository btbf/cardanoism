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
    color: rx.Var[str] = "var(--rs-yellow-500)"
    size: str = "xs"


proposal_rating = CatalystRating.create

# Neon pulse animation for "in progress" badges.
NEON_PULSE_STYLE = rx.html(
    """
    <style>
      @keyframes neon-pulse {
        0%   { box-shadow: 0 0 0 0 rgba(99,102,241,0.55); }
        70%  { box-shadow: 0 0 0 12px rgba(99,102,241,0); }
        100% { box-shadow: 0 0 0 0 rgba(99,102,241,0); }
      }
      .neon-pulse {
        animation: neon-pulse 1.6s ease-in-out infinite;
      }
    </style>
    """
)


def ProjectRating(value_rate) -> rx.Component:
    """Stars for detail page (kept for proposal_detail)."""
    return rx.box(proposal_rating(value="5", defaultValue=value_rate))


def status_badge(proposal: Dict[str, Any]) -> rx.Component:
    """Status pill aligned with Fund badge sizing."""
    funding_status = proposal.get("funding_status", "")
    project_status = proposal.get("project_status", "")
    return rx.cond(
        funding_status == "funded",
        rx.match(
            project_status,
            ("in_progress", rx.badge("進行中", variant="solid", size="2", radius="full", background_color="var(--color-primary-200)", color="white", class_name="neon-pulse")),
            ("complete", rx.badge("完了", variant="surface", size="2", radius="full", background_color="var(--color-primary-300)", color="var(--color-primary-100)")),
            rx.badge("採択", variant="surface", size="2", radius="full", background_color="var(--color-primary-300)", color="var(--color-primary-100)"),
        ),
        rx.match(
            funding_status,
            ("not_approved", rx.badge("不採択", variant="surface", size="2", radius="full", background_color="var(--color-bg-300)", color="var(--color-text-200)")),
            ("over_budget", rx.badge("申請不備", variant="surface", size="2", radius="full", background_color="var(--color-bg-300)", color="var(--color-text-200)")),
            ("pending", rx.badge("投票期間中", variant="surface", size="2", radius="full", background_color="var(--color-primary-300)", color="var(--color-primary-100)")),
            rx.badge("進行中", variant="solid", size="2", radius="full", background_color="var(--color-primary-200)", color="white", class_name="neon-pulse"),
        ),
    )


def pill(text: str, icon: str, scheme: str = "indigo") -> rx.Component:
    return rx.badge(
        rx.hstack(
            rx.icon(icon, size=14, color="var(--color-primary-100)"),
            rx.text(text, size="1", color="var(--color-primary-100)"),
            spacing="1",
            align="center",
        ),
        variant="surface",
        radius="full",
        size="2",
        background_color="var(--color-primary-300)",
    )


def fund_label(proposal: Dict[str, Any]):
    """Return fund title (expected to be always set)."""
    return proposal["fund_title"]


def campaign_label(proposal: Dict[str, Any]):
    """Return campaign title (ja if present, else fallback)."""
    return rx.cond(
        proposal.get("campaign_title_ja"),
        proposal.get("campaign_title_ja"),
        proposal.get("campaign_title", ""),
    )


def fund_progress_bar(proposal: Dict[str, Any]) -> rx.Component:
    """Progress bar for funded proposals using precomputed fund_percent."""
    return rx.cond(
        proposal["funding_status"] == "funded",
        rx.hstack(
            rx.text("資金調達率", size="2", color="var(--gray-10)"),
            rx.box(
                rx.progress(
                    value=proposal["fund_percent"],
                    height="10px",
                    color_scheme="green",
                ),
                width="160px",
            ),
            rx.text(f"{proposal['fund_percent']}%", size="2", color="var(--green-11)", weight="bold"),
            spacing="2",
            align="center",
        ),
        rx.box(),
    )


def score_star(label: str, value: Any) -> rx.Component:
    """Compact star score display for modal."""
    star_value = rx.cond(value, value, 0)
    display_value = rx.cond(value, value, "-")
    return rx.hstack(
        rx.text(label, size="2", color="var(--gray-10)"),
        proposal_rating(value="5", defaultValue=star_value, size="xs"),
        rx.text(display_value, size="2", color="var(--gray-11)"),
        spacing="2",
        align="center",
    )


def score_panel(label: str, value: Any, color: str) -> rx.Component:
    """Tinted card for score display to improve readability."""
    star_value = rx.cond(value, value, 0)
    display_value = rx.cond(value, value, "-")
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(label, size="1", color=f"var(--{color}-11)", weight="medium"),
                rx.box(
                    proposal_rating(value="5", defaultValue=star_value, size={14}),
                    style={"transform": "scale(0.8) translateY(-1.5px)"},
                ),
                rx.text(display_value, size="1", color="var(--gray-12)", weight="bold"),
                spacing="1",
                align="center",
            ),
            spacing="1",
            align_items="start",
        ),
        padding="5px",
        
        border=f"1px solid var(--{color}-4)",
        background_color="var(--gray-1)",
        border_radius="6px",
        width="100%",
    )

def html_section(title: str, content: Any) -> rx.Component:
    """Render stored HTML (already sanitized upstream) inside modal sections."""
    safe_content = rx.cond(content, content, "")
    return rx.vstack(
        rx.box(
            rx.hstack(
                rx.icon("bookmark", size=14, color="white"),
                rx.text(
                    title,
                    size="1",
                    color="white",
                    weight="bold",
                    class_name="tracking-wide text-[12px] uppercase",
                    style={"letterSpacing": "0.08em"},
                ),
                spacing="2",
                align="center",
            ),
            padding_x="12px",
            padding_y="8px",
            background_color="var(--indigo-10)",
            border_radius="6px",
            width="100%",
        ),
        rx.box(
            rx.html(safe_content),
            class_name=(
                "text-[16px] leading-7 text-[var(--gray-11)] prose max-w-none "
                "prose-strong:text-[var(--indigo-12)] dark:prose-strong:text-[var(--indigo-12)]"
            ),
            width="100%",
        ),
        spacing="1",
        width="100%",
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


    fund_progress = fund_progress_bar(proposal)

    mobile_footer = rx.vstack(
        rx.hstack(
            rx.hstack(
            rx.icon("user", size=16, color="var(--color-text-200)"),
            rx.text(proposal["user_name"], size="2", color="var(--color-text-200)"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.icon("coins", size=16, color="var(--color-primary-200)"),
            rx.text(
                f"{proposal['currency_symbol']} {proposal['amount_requested_comma']}",
                size="3",
                weight="bold",
                color="var(--color-primary-100)",
            ),
            rx.text(proposal["currency"], size="2", color="var(--color-text-200)"),
            fund_progress,
            spacing="2",
            align="center",
        ),
            spacing="3",
            align="center",
            justify="start",
            wrap="wrap",
            width="100%",
        ),
        spacing="2",
        width="100%",
    )

    desktop_footer = rx.hstack(
        rx.hstack(
            rx.icon("user", size=16, color="var(--gray-9)"),
            rx.text(proposal["user_name"], size="2", color="var(--gray-10)"),
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
        rx.hstack(
            fund_progress,
            spacing="2",
            align="center",
        ),
        justify="start",
        align="center",
        spacing="3",
        wrap="wrap",
        width="100%",
    )

    page_icon = rx.box(
        rx.icon("expand", size=20, color="var(--color-primary-200)"),
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
                        status_badge(proposal),
                        pill(f"{fund_label(proposal)}", "layers", "indigo"),
                        pill(campaign_label(proposal), "flag", "gray"),
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
                ),
                rx.text(proposal["title"], size="2", color="var(--gray-9)", class_name="mt-0"),
            rx.text(
                description,
                size="3",
                color="var(--gray-10)",
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
            "bg-[var(--color-bg-200)] border border-[var(--color-border)] "
            "hover:border-[var(--color-primary-200)] "
            "hover:shadow-[0_0_6px_rgba(79,169,255,0.12)] "
            "dark:bg-[var(--color-bg-200)] dark:border-[var(--color-border)] "
            "dark:hover:border-[var(--color-primary-200)] "
            "dark:hover:shadow-[0_0_8px_rgba(0,0,0,0.22)]"
        ),
        on_click=lambda: [AppState.open_modal(proposal), AppState.load_modal_detail(proposal["uuid"])],
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
        rx.icon("expand", size=16, color="var(--color-primary-200)"),
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
                    status_badge(proposal),
                    pill(f"{fund_label(proposal)}", "layers", "indigo"),
                    pill(campaign_label(proposal), "flag", "gray"),
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
                ),
                rx.text(proposal["title"], size="2", color="var(--gray-9)", class_name="mt-0"),
            rx.text(
                description,
                size="2",
                color="var(--gray-10)",
                line_height="1.6",
                text_wrap="wrap",
                class_name="line-clamp-3 mt-1",
            ),
                rx.vstack(
                    rx.hstack(
                        rx.hstack(
                            rx.icon("user", size=14, color="var(--gray-9)"),
                            rx.text(proposal["user_name"], size="2", color="var(--gray-10)"),
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
            "bg-[var(--color-bg-200)] border border-[var(--color-border)] "
            "hover:border-[var(--color-primary-200)] "
            "hover:shadow-[0_0_6px_rgba(79,169,255,0.12)] "
            "dark:bg-[var(--color-bg-200)] dark:border-[var(--color-border)] "
            "dark:hover:border-[var(--color-primary-200)] "
            "dark:hover:shadow-[0_0_8px_rgba(0,0,0,0.22)]"
        ),
        on_click=lambda: [AppState.open_modal(proposal), AppState.load_modal_detail(proposal["uuid"])],
        cursor="pointer",
    )


def detail_modal() -> rx.Component:
    p = AppState.modal_proposal
    return rx.dialog.root(
        rx.dialog.content(
            rx.html(
                """
                <style>
                .proposal-modal a {
                  color: var(--color-primary-200) !important;
                  text-decoration: underline;
                }
                .proposal-modal a:hover {
                  color: var(--color-primary-100) !important;
                }
                .proposal-modal ::-webkit-scrollbar {
                  width: 8px;
                  height: 8px;
                }
                .proposal-modal ::-webkit-scrollbar-track {
                  background: var(--color-bg-200);
                }
                .proposal-modal ::-webkit-scrollbar-thumb {
                  background: var(--color-border);
                  border-radius: 9999px;
                }
                .proposal-modal ::-webkit-scrollbar-thumb:hover {
                  background: var(--color-primary-200);
                }
                .proposal-modal {
                  background: var(--color-bg-100);
                  color: var(--color-text-200);
                  border: 1px solid var(--color-border);
                  scrollbar-color: var(--color-border) var(--color-bg-200);
                  scrollbar-width: thin;
                }
                </style>
                """
            ),
            rx.vstack(
                rx.hstack(
                    rx.vstack(
            rx.text(
                p.get("title_ja", "提案詳細"),
                size="5",
                weight="bold",
                width="100%",
                color="var(--color-primary-100)",
                style={"wordBreak": "break-word"},
            ),
            rx.text(
                p.get("title", ""),
                size="2",
                color="var(--color-text-200)",
                width="100%",
                style={"wordBreak": "break-word"},
            ),
                        spacing="1",
                        align_items="start",
                    ),
                    rx.icon_button("x", on_click=AppState.close_modal, variant="ghost"),
                    justify="between",
                    align="start",
                    width="100%",
                ),
            rx.hstack(
                status_badge(p),
                pill(f"{fund_label(p)}", "layers", "primary"),
                pill(campaign_label(p), "flag", "primary"),
                rx.hstack(
                    rx.text(p.get("user_name", ""), size="2", color="var(--color-text-200)"),
                    rx.text(
                        f"{p.get('currency_symbol','')} {p.get('amount_requested_comma','')}",
                        size="3",
                        weight="bold",
                        color="var(--color-primary-100)",
                    ),
                    rx.link(
                        rx.hstack(
                            rx.text("Project Catalyst", size="2", weight="medium", color="var(--color-text-200)"),
                            rx.icon("external-link", size=16, color="var(--color-text-200)"),
                            spacing="1",
                            align="center",
                        ),
                        href=p.get("projectcatalyst_link", ""),
                            underline="auto",
                            is_external=True,
                            style={"text-decoration": "none !important"},
                        ),
                        spacing="3",
                        align="center",
                    ),
                    spacing="2",
                    wrap="wrap",
                ),
                rx.divider(),
                rx.cond(
                    AppState.modal_loading,
                    rx.flex(
                        rx.spinner(size="3"),
                        justify="center",
                        align="center",
                        width="100%",
                        flex="1",
                        padding_y="20px",
                    ),
                    rx.flex(
                        rx.tablet_and_desktop(
                            rx.grid(
                                score_panel("提案整合性", p.get("alignment_score"), "primary"),
                                score_panel("実現可能性", p.get("feasibility_score"), "primary"),
                                score_panel("監査可能性", p.get("auditability_score"), "primary"),
                                columns={"base": "1", "md": "3"},
                                spacing="4",
                                width="100%",
                            ),
                        ),
                        rx.divider(margin_y="6px"),
                        rx.box(
                            rx.vstack(
                                rx.vstack(
                                    rx.text("課題", size="2", color="var(--color-text-200)"),
                                    rx.text(p.get("problem_ja", ""), size="3", line_height="1.6", color="var(--color-text-200)"),
                                    spacing="1",
                                    width="100%",
                                    padding_top="8px",
                                ),
                                rx.vstack(
                                    rx.text("解決策", size="2", color="var(--color-text-200)"),
                                    rx.text(p.get("solution_ja", ""), size="3", line_height="1.6", color="var(--color-text-200)"),
                                    spacing="1",
                                    width="100%",
                                ),
                                html_section("解決策", p.get("detail_solution_ja", "")),
                                html_section("エコシステムインパクト", p.get("impact_ja", "")),
                                html_section("実現可能性", p.get("capability_feasibility_ja", "")),
                                html_section("マイルストーン", p.get("project_milestones_ja", "")),
                                html_section("リソース", p.get("resources_ja", "")),
                                html_section("予算とコスト", p.get("budget_costs_ja", "")),
                                html_section("コストパフォーマンス", p.get("value_for_money_ja", "")),
                                rx.mobile_only(
                                    rx.vstack(
                                        score_panel("提案整合性", p.get("alignment_score"), "primary"),
                                        score_panel("実現可能性", p.get("feasibility_score"), "primary"),
                                        score_panel("監査可能性", p.get("auditability_score"), "primary"),
                                        spacing="1",
                                        width="100%",
                                        justify="center",
                                    ),
                                ),
                                spacing="3",
                                width="100%",
                            ),
                            flex="1",
                            min_height="0",
                            overflow_y="auto",
                            padding_right="6px",
                            width="100%",
                        ),
                        direction="column",
                        gap="4",
                        width="100%",
                        flex="1",
                        min_height="0",
                    ),
                ),
                rx.button(
                    "閉じる",
                    on_click=AppState.close_modal,
                    width="100%",
                    variant="soft",
                    background_color="var(--color-primary-300)",
                    color="var(--color-primary-100)",
                    _hover={"background_color": "var(--color-primary-200)", "color": "white"},
                ),
                spacing="3",
                width="100%",
                align_items="stretch",
                height="100%",
                min_height="0",
            ),
            max_width="900px",
            max_height="95vh",
            width="95vw",
            class_name=(
                "proposal-modal "
                "shadow-xl rounded-2xl "
                "border border-[var(--color-border)] "
                "bg-[var(--color-bg-100)] text-[var(--color-text-200)] "
                "dark:border-[var(--color-border)] "
                "dark:bg-[var(--color-bg-100)] dark:text-[var(--color-text-200)] "
            ),
            style={"display": "flex", "flexDirection": "column"},
        ),
        open=AppState.modal_open,
        modal=False,
    )


def card_foreach_dict() -> rx.Component:
    return rx.box(
        NEON_PULSE_STYLE,
        detail_modal(),
        rx.cond(
            AppState.load,
            rx.fragment(
                rx.mobile_only(
                    rx.grid(
                        rx.foreach(AppState.proposals, proposal_grid),
                        columns={"base": "1"},
                        spacing="4",
                    )
                ),
                rx.tablet_and_desktop(
                    rx.cond(
                        AppState.view_mode == "grid",
                        rx.grid(
                            rx.foreach(AppState.proposals, proposal_grid),
                            columns={"base": "1", "md": "2", "lg": "2"},
                            spacing="4",
                        ),
                        rx.foreach(AppState.proposals, proposal_list),
                    )
                ),
            ),
            rx.flex(
                rx.spinner(size="3"),
                justify="center",
                align="center",
                width="100%",
                padding_y="20px",
            ),
        ),
    )
