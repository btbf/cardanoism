import reflex as rx
from typing import List, Dict

from cardanoism.backend.db_connect import ProposalAppState
from cardanoism.components.proposal_card import ProjectRating
from cardanoism import styles


def proposal_detail(proposal: Dict[str, int]):
    return rx.card(
        rx.inset(
            rx.box(
                rx.flex(
                    rx.flex(
                        #rx.badge(f"""Ideascale-ID : {proposal["ideascale_id"]}""", variant="solid", size="2", color_scheme="indigo",),
                        rx.match(
                            proposal["funding_status"],
                            ("funded", rx.badge("採択", variant="solid", size="2", color_scheme="green",)),
                            ("not_approved", rx.badge("不採択", variant="solid", size="2", color_scheme="red",)),
                            ("over_budget", rx.badge("申請不備", variant="solid", size="2", color_scheme="red",)),
                            ("pending", rx.badge("投票期間中", variant="solid", size="2", color_scheme="iris",)),
                        ),
                        rx.tooltip(
                            rx.text(f"""{proposal["challenge_title_ja"]}""", color_scheme="gray", size="3"),
                            content=f"""{proposal["challenge_title"]}"""
                        ),
                        spacing="5",
                        justify="center",
                        display=["block","block","block","flex","flex"]
                    ),
                    # rx.link(
                    #     rx.flex(
                    #         rx.text(
                    #             "Ideascaleを開く",
                    #             size="3",
                    #         ),
                    #         rx.icon("square-arrow-out-up-right", size=15),
                    #         direction="row",
                    #         gap="1",
                    #         align="center",
                    #         spacing="1",
                    #         #padding="8px",
                    #         #color="gray",
                    #     ),
                    #     href=str(proposal["ideascale_link"]),
                    #     target="blank",
                    #     color_scheme="cyan",
                    #     underline="none",
                    #     high_contrast=True,
                    # ),
                    justify_content="space-between",
                ),
                #padding="8px",
            ),
            rx.tablet_and_desktop(
                    rx.heading(
                        proposal["title_ja"],
                        as_="h2",
                        size="4",
                        margin_top="8px",
                        # margin_bottom="12px",
                        weight="medium",
                        text_wrap="wrap",
                        font_family = "Noto Sans JP",
                    ),
            ),
            rx.mobile_only(
                    rx.heading(
                        proposal["title_ja"],
                        #as_="h2",
                        size="4",
                        margin_top="8px",
                        # margin_bottom="12px",
                        weight="medium",
                        font_family = "Noto Sans JP",
                    ),
            ),
            rx.blockquote(
                proposal["title"],
                size="1",
                margin_top="8px",
                # margin_bottom="12px",
                weight="light",
                text_wrap="wrap",
            ),
            side="top",
            pb="current",
            background_color="var(--accent-2)",
            padding="12px",
        ),
        
        rx.flex(
            rx.box(
                rx.flex(
                    rx.box(
                        rx.flex(
                            rx.badge("提案者", variant="surface", size="2", color_scheme="gray", radius="full"),
                            rx.tooltip(
                                rx.text(proposal["applicant_name"]),
                                content=str({proposal["ideascale_user"]}),
                            ),
                            spacing="3",
                            padding="8px",
                        ),
                    ),
                    rx.box(
                        rx.flex(
                            rx.badge("要求額", variant="surface", size="2", color_scheme="gray", radius="full"),
                            rx.text(
                                f"""{proposal["currency_symbol"]} {proposal["amount_requested"]}""",
                                color_scheme="crimson",
                                weight="medium",
                                size="3",
                            ),
                            spacing="3",
                            padding="8px",
                        ),
                    
                    ),
                display=["block","block","block","flex","flex"]
                ),

                rx.divider(size="4"),
                rx.box(
                    rx.flex(
                        rx.callout("課題", icon="triangle_alert", color_scheme="red", size="1"),
                        rx.text(
                            proposal["problem_ja"],
                            size="3", 
                            padding="10px",
                            text_wrap="wrap",
                        ),
                        #spacing="3",
                        #margin_top="8px",
                        direction="column",
                        display=["block","block","block","flex","flex"]
                    ),
                    rx.flex(
                        rx.callout("解決策", icon="info", color_scheme="green", size="1"),
                        #rx.avatar(fallback="解決策", variant="soft", color_scheme="cyan"),
                        #rx.badge("提案", variant="soft", size="3", color_scheme="cyan", radius="medium"),
                        rx.text(
                            proposal["solution_ja"],
                            size="3",
                            padding="10px",
                            text_wrap="wrap",
                        ),
                        #spacing="3",
                        margin_top="10px",
                        direction="column",
                        display=["block","block","block","flex","flex"]
                    ),
                    padding=["8px", "8px", "12px", "12px", "12px" ],
                    width="100%"      
                ),
                width="100%"
            ),
            rx.box(
                rx.stack(
                    rx.box(
                        rx.callout("レビュアー評価", icon="award", color_scheme="blue", size="1"),
                        width="100%",
                    ),
                    
                    rx.cond(
                        ~proposal["alignment_score"],
                        rx.text(
                            "コミュニティレビュー中",
                            color_scheme="crimson",
                        ),
                        rx.box(
                            rx.text(
                            "エコシステム影響度",
                            weight="bold",
                            size="3",
                            ),
                            rx.flex(
                                ProjectRating(proposal["alignment_score"]),
                            ),
                            rx.text(
                                "実現可能性",
                                weight="bold",
                                size="3",
                            ),
                            rx.flex(
                                ProjectRating(proposal["feasibility_score"]),
                            ),
                            rx.text(
                                "コストパフォーマンス",
                                weight="bold",
                                size="3",
                            ),     
                            rx.flex(
                                ProjectRating(proposal["auditability_score"]),
                            ),
                        ),
                    ),
                          
                    columns="3",
                    spacing="3",
                    padding=[0,0,0,"8px","8px"],
                    margin_top="10px",
                    flex_direction="column",
                    #display=["none", "none", "flex", "flex", "flex"],
                ),
                flex_direction=["column","column","row","row","row"],
                width=["100%","100%","40%","40%","40%"],
            ),
        display=["block","block","block","flex","flex"]
        ),
        rx.divider(size="4", margin_bottom="10px"),
        rx.box(
            rx.section(
                rx.heading(
                    "解決策",
                    as_="h2",
                    padding_bottom="12px",
                    color_scheme="indigo",
                    ),
                rx.cond(
                    proposal["detail_solution_ja"],
                    rx.html(proposal["detail_solution_ja"]),
                    rx.html(proposal["solution"]),
                ),
                style=styles.section_style,
                size="1",
            ),
            rx.section(
                rx.heading(
                    "コミュニティへの影響度",
                    as_="h2",
                    padding_bottom="12px",
                    color_scheme="indigo",
                    ),
                rx.cond(
                    proposal["impact_ja"],
                    rx.html(proposal["impact_ja"]),
                    rx.html(proposal["impact"]),
                ),
                style=styles.section_style,
                size="1",
            ),
            rx.section(
                rx.heading(
                    "実現性と実行力",
                    as_="h2",
                    padding_bottom="12px",
                    color_scheme="indigo",
                    ),
                rx.cond(
                    proposal["capability_feasibility_ja"],
                    rx.html(proposal["capability_feasibility_ja"]),
                    rx.html(proposal["capability_feasibility"]),
                ),
                style=styles.section_style,
                size="1",
            ),
            rx.section(
                rx.heading(
                    "マイルストーン",
                    as_="h2",
                    padding_bottom="12px",
                    color_scheme="indigo",
                    ),
                rx.cond(
                    proposal["project_milestones_ja"],
                    rx.html(proposal["project_milestones_ja"]),
                    rx.html(proposal["project_milestones"]),
                ),
                style=styles.section_style,
                size="1",
            ),
            rx.section(
                rx.heading(
                    "コスト",
                    as_="h2",
                    padding_bottom="12px",
                    color_scheme="indigo",
                    ),
                rx.cond(
                    proposal["budget_costs_ja"],
                    rx.html(proposal["budget_costs_ja"]),
                    rx.html(proposal["budget_costs"]),
                ),
                style=styles.section_style,
                size="1",
            ),
            rx.section(
                rx.heading(
                    "プロジェクトリソース",
                    as_="h2",
                    padding_bottom="12px",
                    color_scheme="indigo",
                ),
                rx.cond(
                    proposal["resources_ja"],
                    rx.html(proposal["resources_ja"]),
                    rx.html(proposal["resources"]),
                ),
                style=styles.section_style,
                size="1",
            ),
            rx.section(
                rx.heading(
                    "費用対効果",
                    as_="h2",
                    padding_bottom="12px",
                    color_scheme="indigo"
                ),
                rx.cond(
                    proposal["value_for_money_ja"],
                    rx.html(proposal["value_for_money_ja"]),
                    rx.html(proposal["value_for_money"]),
                ),
                style=styles.section_style,
                size="1",
            ),
            width="100%",
            background_color="var(--accent-2)",
        ),
        rx.inset(
            rx.link(
                rx.button("閉じる", width="100%", size="3", variant="soft", color_scheme="indigo", on_click=rx.call_script("""window.close()""")),
            ),
            side="bottom",
            #background_color="var(--accent-3)",
        ),
        #margin_top="20px",
        width="100%",
        font_family = "Noto Sans JP"
    )



def detail_foreach_dict():
    return rx.box(
        rx.cond(
            ProposalAppState.load,
            rx.cond(
            ProposalAppState.proposal,
            rx.foreach(ProposalAppState.proposal, proposal_detail),
                rx.callout(
                    "提案書が見つかりません",
                    icon="info",
                    color_scheme="blue",
                ),
            ),
            rx.spinner(size="3")
        )
    )
