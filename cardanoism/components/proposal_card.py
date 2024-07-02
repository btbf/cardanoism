import reflex as rx
from typing import List, Dict
from cardanoism.backend.db_connect import AppState


def proposal_list(proposal: List[Dict[str, str]]):
    return rx.card(
        rx.inset(
            rx.box(
                rx.flex(
                    rx.flex(
                        rx.badge(f"""Ideascale-ID : {proposal["ideascale_id"]}""", variant="solid", size="2", color_scheme="indigo",),
                        rx.tooltip(
                            rx.text(f"""{proposal["challenge_title_ja"]}""", color_scheme="gray", size="3"),
                            content=f"""{proposal["challenge_title"]}"""
                        ),
                        spacing="5",
                        justify="center",
                        display=["block","block","block","flex","flex"]
                    ),
                    rx.link(
                        rx.flex(
                            rx.text(
                                "Ideascaleを開く",
                                size="3",
                            ),
                            rx.icon("square-arrow-out-up-right", size=15),
                            direction="row",
                            gap="1",
                            align="center",
                            spacing="1",
                            #padding="8px",
                            #color="gray",
                        ),
                        href=proposal["ideascale_link"],
                        target="blank",
                        color_scheme="cyan",
                        underline="none",
                        high_contrast=True,
                    ),
                    justify_content="space-between",
                ),
                padding="8px",
            ),
            rx.blockquote(
                proposal["title"],
                size="3",
                margin_top="8px",
                margin_bottom="12px",
                weight="light",
                text_wrap="wrap",
            ),
            rx.tablet_and_desktop(
                rx.link(
                    rx.heading(
                    proposal["title_ja"],
                    as_="h2",
                    #size="5",
                    margin_top="8px",
                    margin_bottom="12px",
                    weight="medium",
                    text_wrap="wrap",
                    font_family = "Noto Sans JP",
                    ),
                    href=f"""/catalyst/{proposal["ideascale_id"]}""",
                    is_external=True,
                ),
            ),
            rx.mobile_only(
                rx.link(
                    rx.heading(
                        proposal["title_ja"],
                        #as_="h2",
                        size="4",
                        margin_top="8px",
                        margin_bottom="12px",
                        weight="medium",
                        font_family = "Noto Sans JP",
                    ),
                    href=f"""/catalyst/{proposal["ideascale_id"]}""",
                    is_external=True,
                ),
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
                                content=proposal["ideascale_user"],
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
                        #rx.badge("課題", variant="soft", size="3", color_scheme="tomato", radius="medium"),
                        rx.text(
                            proposal["headline_problem_ja"],
                            size="3", 
                            padding="8px",
                            text_wrap="wrap",
                        ),
                        #spacing="3",
                        margin_top="8px",
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
                            padding="8px",
                            text_wrap="wrap",
                        ),
                        #spacing="3",
                        margin_top="25px",
                        direction="column",
                        display=["block","block","block","flex","flex"]
                    ),
                    padding=["8px", "8px", "15px", "15px", "15px" ],
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
                    #rx.badge("レビュアー評価", variant="surface", size="3", color_scheme="gold", radius="none",),
                    rx.text(
                        "エコシステム影響度",
                        weight="bold",
                        size="3",
                    ),
                    rx.flex(
                        rx.text(f"""{proposal["alignment_score"]} / 5""")
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                        # rx.icon("star-half", color="gold", stroke_width=2.5,),
                    ),
                    rx.text(
                        "実現可能性",
                        weight="bold",
                        size="3",
                    ),
                    rx.flex(
                        rx.text(f"""{proposal["feasibility_score"]} / 5""")
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                    ),
                    rx.text(
                        "コストパフォーマンス",
                        weight="bold",
                        size="3",
                    ),     
                    rx.flex(
                        rx.text(f"""{proposal["feasibility_score"]} / 5""")
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                        # rx.icon("star", color="gold", stroke_width=2.5,),
                    ),          
                    columns="3",
                    spacing="3",
                    padding="8px",
                    margin_top="10px",
                    flex_direction="column",
                    #display=["none", "none", "flex", "flex", "flex"],
                ),
                flex_direction=["column","column","row","row","row"],
                width=["100%","100%","40%","40%","40%"],
            ),
        display=["block","block","block","flex","flex"]
        ),
        rx.inset(
            rx.link(
                rx.button("詳細を見る", width="100%", size="3", variant="soft", color_scheme="indigo", ),
                href=f"""/catalyst/{proposal["ideascale_id"]}""",
                is_external=True,
            ),
            side="bottom",
            #background_color="var(--accent-3)",
        ),
        width="100%",
        font_family = "Noto Sans JP",
        margin_bottom="1.5em"
    )


def card_foreach_dict():
    return rx.box(
        rx.cond(
            AppState.load,
            rx.foreach(AppState.proposals, proposal_list),
            rx.spinner(size="3"),
        ),  
    )
