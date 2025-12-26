import reflex as rx
from typing import List, Dict, Any

from cardanoism.backend.db_connect import ProposalAppState
from cardanoism.components.proposal_card import (
    status_badge,
    pill,
    fund_label,
    campaign_label,
    score_panel,
    semantic_block_section,
    semantic_blocks_by_view,
    semantic_toggle_button,
    semantic_toggle_group,
    semantic_toggle_bar,
    catalyst_id_badge,
)


def proposal_detail(proposal: Dict[str, Any]) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text(
                        rx.cond(proposal["title_ja"], proposal["title_ja"], "提案"),
                        size={"base": "6", "md": "5"},
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
                catalyst_id_badge(proposal),
                pill(f"{fund_label(proposal)}", "layers", "yellow"),
                pill(campaign_label(proposal), "flag", "gray"),
                spacing="2",
                wrap="wrap",
            ),
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
                spacing="2",
                wrap="wrap",
                align="center",
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
            semantic_toggle_bar(
                semantic_toggle_button(
                    "英語原文",
                    "raw",
                    ProposalAppState.semantic_view,
                    lambda: ProposalAppState.set_semantic_view("raw"),
                ),
                semantic_toggle_button(
                    "日本語翻訳",
                    "ja",
                    ProposalAppState.semantic_view,
                    lambda: ProposalAppState.set_semantic_view("ja"),
                ),
                semantic_toggle_button(
                    "AI要約",
                    "ai",
                    ProposalAppState.semantic_view,
                    lambda: ProposalAppState.set_semantic_view("ai"),
                ),
                top="5.5em",
                panel_background="var(--gray-2)",
                panel_padding="8px 18px",
                panel_radius="9999px",
                z_index="3",
            ),
            rx.vstack(
                rx.cond(
                    ProposalAppState.semantic_view == "ai",
                    rx.box(),
                    rx.cond(
                        ProposalAppState.semantic_view == "raw",
                        rx.vstack(
                            rx.el.h2(
                                "課題",
                                class_name=(
                                    "text-[16px] md:text-[16px] font-semibold tracking-tight "
                                    "text-[var(--gray-12)] pb-1 border-b border-[var(--gray-5)] "
                                    "border-l-4 border-[var(--gray-6)] pl-3"
                                ),
                            ),
                            rx.text(proposal.get("problem", ""), size="3", line_height="1.6", color="var(--sand-a12)", padding_x="8px"),
                            spacing="1",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.el.h2(
                                "課題",
                                class_name=(
                                    "text-[16px] md:text-[16px] font-semibold tracking-tight "
                                    "text-[var(--gray-12)] pb-1 border-b border-[var(--gray-5)] "
                                    "border-l-4 border-[var(--gray-6)] pl-3"
                                ),
                            ),
                            rx.text(proposal.get("problem_ja", ""), size="3", line_height="1.6", color="var(--sand-a12)", padding_x="8px"),
                            spacing="1",
                            width="100%",
                        ),
                    ),
                ),
                rx.cond(
                    ProposalAppState.semantic_view == "ai",
                    rx.box(),
                    rx.cond(
                        ProposalAppState.semantic_view == "raw",
                        rx.vstack(
                            rx.el.h2(
                                "解決策",
                                class_name=(
                                    "text-[16px] md:text-[16px] font-semibold tracking-tight "
                                    "text-[var(--gray-12)] pb-1 border-b border-[var(--gray-5)] "
                                    "border-l-4 border-[var(--gray-6)] pl-3"
                                ),
                            ),
                            rx.text(proposal.get("solution", ""), size="3", line_height="1.6", color="var(--sand-a12)", padding_x="8px"),
                            spacing="1",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.el.h2(
                                "解決策",
                                class_name=(
                                    "text-[16px] md:text-[16px] font-semibold tracking-tight "
                                    "text-[var(--gray-12)] pb-1 border-b border-[var(--gray-5)] "
                                    "border-l-4 border-[var(--gray-6)] pl-3"
                                ),
                            ),
                            rx.text(proposal.get("solution_ja", ""), size="3", line_height="1.6", color="var(--sand-a12)", padding_x="8px"),
                            spacing="1",
                            width="100%",
                        ),
                    ),
                ),
                rx.foreach(
                    semantic_blocks_by_view(
                        ProposalAppState.semantic_view,
                        ProposalAppState.semantic_blocks_raw,
                        ProposalAppState.semantic_blocks_ja,
                        ProposalAppState.semantic_blocks_ai,
                    ),
                    semantic_block_section,
                ),
                spacing="3",
                width="100%",
            ),
            spacing="4",
            width="100%",
            align_items="stretch",
        ),
        width="100%",
        padding="24px",
        background_color="var(--gray-3)",
        #border=f"1px solid var(--slate-6)",
        style={"overflow": "visible"},
        #border_radius="16px",
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
