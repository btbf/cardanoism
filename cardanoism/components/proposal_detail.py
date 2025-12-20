import reflex as rx
from typing import List, Dict, Any

from cardanoism.backend.db_connect import ProposalAppState
from cardanoism.components.proposal_card import (
    status_badge,
    pill,
    fund_label,
    campaign_label,
    score_panel,
    html_section,
)


def proposal_detail(proposal: Dict[str, Any]) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text(
                        rx.cond(proposal["title_ja"], proposal["title_ja"], "提案"),
                        size="6",
                        weight="bold",
                        width="100%",
                        style={"wordBreak": "break-word"},
                    ),
                    rx.text(
                        rx.cond(proposal["title"], proposal["title"], ""),
                        size="2",
                        width="100%",
                        style={"wordBreak": "break-word"},
                    ),
                    spacing="1",
                    align_items="start",
                    width="100%",
                ),
                justify="between",
                align="start",
                width="100%",
            ),
            rx.hstack(
                status_badge(proposal),
                pill(f"{fund_label(proposal)}", "layers", "yellow"),
                pill(campaign_label(proposal), "flag", "gray"),
                rx.hstack(
                    rx.text(rx.cond(proposal["user_name"], proposal["user_name"], ""), size="2", color="var(--gray-9)"),
                    rx.text(
                        f"{proposal['currency_symbol']} {proposal['amount_requested_comma']}",
                        size="3",
                        weight="bold",
                        color="var(--indigo-11)",
                    ),
                    rx.link(
                        rx.hstack(
                            rx.text("Project Catalyst", size="2", weight="medium"),
                            rx.icon("external-link", size=16),
                            spacing="1",
                            align="center",
                        ),
                        href=proposal.get("projectcatalyst_link", ""),
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
            rx.grid(
                score_panel("アラインメント", proposal.get("alignment_score"), "primary"),
                score_panel("実現可能性", proposal.get("feasibility_score"), "primary"),
                score_panel("監査可能性", proposal.get("auditability_score"), "primary"),
                columns={"base": "1", "md": "3"},
                spacing="4",
                width="100%",
            ),
            rx.divider(margin_y="6px"),
            rx.vstack(
                rx.vstack(
                    rx.text("課題", size="2", color="var(--gray-12)", weight="bold"),
                    rx.text(proposal.get("problem_ja", ""), size="3", line_height="1.6", color="var(--gray-11)"),
                    spacing="1",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("解決策", size="2", color="var(--gray-12)", weight="bold"),
                    rx.text(proposal.get("solution_ja", ""), size="3", line_height="1.6", color="var(--gray-11)"),
                    spacing="1",
                    width="100%",
                ),
                html_section("解決策", proposal.get("detail_solution_ja", "")),
                html_section("エコシステムへの影響", proposal.get("impact_ja", "")),
                html_section("実現可能性", proposal.get("capability_feasibility_ja", "")),
                html_section("マイルストーン", proposal.get("project_milestones_ja", "")),
                html_section("リソース", proposal.get("resources_ja", "")),
                html_section("予算とコスト", proposal.get("budget_costs_ja", "")),
                html_section("コストパフォーマンス", proposal.get("value_for_money_ja", "")),
                spacing="3",
                width="100%",
            ),
            spacing="4",
            width="100%",
            align_items="stretch",
        ),
        width="100%",
        padding="24px",
        background_color="var(--gray-2)",
        border=f"1px solid var(--slate-6)",
        border_radius="16px",
    )


def detail_foreach_dict() -> rx.Component:
    return rx.box(
        rx.cond(
            ProposalAppState.load,
            rx.cond(
                ProposalAppState.proposal,
                rx.foreach(ProposalAppState.proposal, proposal_detail),
                rx.callout(
                    "提案が見つかりませんでした",
                    icon="info",
                    color_scheme="blue",
                ),
            ),
            rx.spinner(size="3"),
        )
    )
