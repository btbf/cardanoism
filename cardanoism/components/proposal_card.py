import reflex as rx
from typing import Dict, Any
from cardanoism.backend.db_connect import AppState
from cardanoism import styles


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

STATUS_DOT_STYLE = rx.html(
    """
    <style>
      @keyframes status-dot-blink {
        0%   { opacity: 1; transform: scale(1); }
        50%  { opacity: 0.35; transform: scale(0.8); }
        100% { opacity: 1; transform: scale(1); }
      }
      .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 9999px;
        display: inline-block;
        vertical-align: middle;
      }
      .status-dot.blink {
        animation: status-dot-blink 1.7s ease-in-out infinite;
      }
    </style>
    """
)


def ProjectRating(value_rate) -> rx.Component:
    """Stars for detail page (kept for proposal_detail)."""
    return rx.box(proposal_rating(value="5", defaultValue=value_rate))


def badge_with_dot(label: str, dot_color: str, *, bg: str | None = None, text_color: str | None = None, blink: bool = False) -> rx.Component:
    """Badge with leading colored dot; optional blink for active states."""
    dot_class = "status-dot blink" if blink else "status-dot"
    return rx.badge(
        rx.hstack(
            rx.box(
                class_name=dot_class,
                background_color=dot_color,
                width="8px",
                height="8px",
                border="1px solid rgba(255,255,255,0.55)",
            ),
            rx.text(label, size="1"),
            spacing="1",
            align="center",
        ),
        variant="surface",
        radius="full",
        size="1",
        background_color=bg,
        color=text_color,
        padding_x="8px",
        padding_y="4px",
    )


def status_badge(proposal: Dict[str, Any]) -> rx.Component:
    """Status pill aligned with Fund badge sizing."""
    funding_status = proposal.get("funding_status", "")
    project_status = proposal.get("project_status", "")
    # color palette
    blue = "#073ff4"
    indigo = "#4b0082"
    gray = "#808080"
    gray_text = "var(--gray-11)"
    green = "#22c55e"
    badge_bg = None  # use solid color per status
    return rx.cond(
        funding_status == "funded",
        rx.match(
            project_status,
            ("in_progress", badge_with_dot("進行中", "white", bg=blue, text_color="white", blink=True)),
            ("complete", badge_with_dot("完了", "white", bg=indigo, text_color="white")),
            badge_with_dot("採択", "white", bg=indigo, text_color="white"),
        ),
        rx.match(
            funding_status,
            ("not_approved", badge_with_dot("不採択", "white", bg=gray, text_color="white")),
            ("over_budget", badge_with_dot("申請不備", "white", bg=gray, text_color="white")),
            ("pending", badge_with_dot("投票期間中", "white", bg=green, text_color="white", blink=True)),
            badge_with_dot("進行中", "white", bg=blue, text_color="white", blink=True),
        ),
    )


def catalyst_id_badge(proposal: Dict[str, Any]) -> rx.Component:
    """Catalyst ID badge (shown when available)."""
    return rx.cond(
        proposal.get("catalyst_id"),
        rx.badge(
            rx.text(f"ID {proposal.get('catalyst_id')}", size="1", color="var(--gray-12)"),
            variant="surface",
            radius="full",
            size="2",
            color_scheme="gray",
        ),
        rx.box(),
    )


def pill(text: str, icon: str, scheme: str) -> rx.Component:
    return rx.badge(
        rx.hstack(
            rx.icon(icon, size=14),
            rx.text(text, size="1"),
            spacing="1",
            align="center",
        ),
        variant="surface",
        radius="full",
        size="2",
        color_scheme=scheme,
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
                    color_scheme="indigo",
                ),
                width="160px",
            ),
            rx.text(f"{proposal['fund_percent']}%", size="2", color="var(--indigo-11)", weight="bold"),
            rx.cond(
                proposal["milestones_link"],
                rx.link(
                        rx.hstack(
                            rx.text("進捗状況を見る", size="2", weight="medium"),
                            rx.icon("external-link", size=16),
                            spacing="1",
                            align="center",
                        ),
                    href=proposal["milestones_link"],
                    is_external=True,
                    underline="auto",
                    color="var(--amber-11)",
                ),
                rx.box(),
            ),
            rx.hstack(
                rx.tooltip(
                    rx.hstack(
                        rx.icon("wallet", size=14, color="var(--gray-10)"),
                        rx.text("投票", size="1", color="var(--gray-10)"),
                        rx.text(proposal.get("unique_wallets_display", "0"), size="2", color="var(--gray-10)"),
                        spacing="1",
                        align="center",
                    ),
                    content="投票ウォレット数",
                ),
                rx.tooltip(
                    rx.hstack(
                        rx.icon("thumbs-up", size=14, color="var(--gray-10)"),
                        rx.text("賛成", size="1", color="var(--gray-10)"),
                        rx.text(proposal.get("yes_votes_count_display", "0"), size="2", color="var(--gray-10)"),
                        spacing="1",
                        align="center",
                    ),
                    content="賛成票数",
                ),
                rx.tooltip(
                    rx.hstack(
                        rx.icon("hand", size=14, color="var(--gray-10)"),
                        rx.text("棄権", size="1", color="var(--gray-10)"),
                        rx.text(proposal.get("abstain_votes_count_display", "0"), size="2", color="var(--gray-10)"),
                        spacing="1",
                        align="center",
                    ),
                    content="棄権票数",
                ),
                spacing="3",
                align="center",
                wrap="wrap",
            ),
            spacing="2",
            align="center",
            wrap="wrap",
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

def html_section(title: str | None, content: Any, *, show_title: bool = True) -> rx.Component:
    """Render stored HTML (already sanitized upstream) inside modal sections."""
    safe_content = rx.cond(content, content, "")
    content_box = rx.box(
        rx.html(safe_content),
        class_name=(
            "text-[16px] leading-7 prose max-w-none prose-strong:text-[var(--gray-12)] dark:prose-strong:text-[var(--gray-12)] ",
        ),
        width="100%",
        padding_x="8px",
        color="var(--sand-a12)",
    )
    header = None
    if show_title and title:
        header = rx.box(
            rx.text(
                title,
                size="3",
                color=rx.color_mode_cond(light="white", dark="black"),
                weight="bold",
                class_name="tracking-wide uppercase",
                style={"letterSpacing": "0.08em"},
            ),
            padding_x="12px",
            padding_y="8px",
            background_color=rx.color_mode_cond(light="var(--blue-12)", dark="var(--gray-11)"),
            border_radius="6px",
            width="100%",
        )
    return rx.vstack(
        *([header] if header else []),
        content_box,
        spacing="1",
        width="100%",
    )


def semantic_block_section(block: Dict[str, Any]) -> rx.Component:
    title = block.get("semantic_title", "")
    html = block.get("html", "")
    return rx.vstack(
        rx.el.h2(
            title,
            class_name=(
                "text-[16px] md:text-[16px] font-semibold tracking-tight "
                "text-[var(--gray-12)] pb-1 border-b border-[var(--gray-5)] "
                "border-l-4 border-[var(--gray-6)] pl-3"
            ),
        ),
        html_section(None, html, show_title=False),
        spacing="2",
        width="100%",
    )


def semantic_blocks_by_view(view: Any, raw: Any, ja: Any, ai: Any) -> rx.Var:
    return rx.match(
        view,
        ("raw", raw),
        ("ja", ja),
        ("ai", ai),
        ja,
    )


def semantic_toggle_button(label: str, value: str, current: Any, on_click) -> rx.Component:
    is_active = current == value
    bubble_button = rx.button(
        label,
        size="2",
        radius="full",
        variant=rx.cond(is_active, "solid", "soft"),
        color_scheme=rx.cond(is_active, "blue", "gray"),
        padding_x="14px",
        padding_y="7px",
        class_name=(
            "transition-all duration-200 "
            "shadow-[0_6px_16px_rgba(0,0,0,0.08)] hover:shadow-[0_8px_18px_rgba(0,0,0,0.12)] "
            "text-[13px] "
        ),
        on_click=on_click,
        cursor="pointer",
    )
    return bubble_button


def semantic_toggle_group(*children: rx.Component) -> rx.Component:
    return rx.hstack(
        *children,
        spacing="2",
        align="end",
        margin_y="6px",
    )


def semantic_toggle_bar(
    *children: rx.Component,
    top: str = "0px",
    center: bool = True,
    panel_background: str | None = None,
    panel_padding: str = "0px 14px",
    panel_radius: str = "9999px",
    z_index: str = "10",
) -> rx.Component:
    inner = semantic_toggle_group(*children)
    if panel_background:
        inner = rx.box(
            inner,
            background_color=panel_background,
            padding=panel_padding,
            border_radius=panel_radius,
        )
    if center:
        inner = rx.center(inner)
    return rx.box(
        inner,
        position="sticky",
        top=top,
        z_index=z_index,
        padding_y="6px",
        width="100%",
        background_color="transparent",
    )


def semantic_toggle_panel(
    *children: rx.Component,
    panel_background: str | None = "var(--gray-2)",
    panel_padding: str = "8px 18px",
    panel_radius: str = "9999px",
    center: bool = True,
) -> rx.Component:
    inner = semantic_toggle_group(*children)
    if panel_background:
        inner = rx.box(
            inner,
            background_color=panel_background,
            padding=panel_padding,
            border_radius=panel_radius,
        )
    if center:
        inner = rx.center(inner)
    return inner


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
            rx.icon("user", size=16, color="var(--gray-9)"),
            rx.text(proposal["user_name"], size="2", color="var(--gray-9)"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.text(
                f"{proposal['currency_symbol']} {proposal['amount_requested_comma']}",
                size="3",
                weight="bold",
                color="var(--indigo-11)",
            ),
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
            rx.text(proposal["user_name"], size="2", color="var(--gray-9)"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
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

    # page_icon = rx.box(
    #     rx.icon("expand", size=20),
    #     position="absolute",
    #     right="0px",
    #     bottom="0px",
    #     border_radius="full",
    #     pointer_events="none",
    # )

    return rx.card(
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.hstack(
                        status_badge(proposal),
                        catalyst_id_badge(proposal),
                        pill(f"{fund_label(proposal)}", "layers", "yellow"),
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
                    line_height="1.2",
                    color="var(--gray-12)",
                ),
                rx.text(proposal["title"], size="2", color="var(--gray-9)", class_name="mt-0"),
            rx.text(
                description,
                size="3",
                line_height="1.6",
                text_wrap="wrap",
                class_name="mt-2",
                color="var(--gray-12)",
            ),
                rx.mobile_and_tablet(mobile_footer),
                rx.desktop_only(desktop_footer),
                spacing="3",
                width="100%",
            ),
            #page_icon,
            position="relative",
            width="100%",
        ),
        width="100%",
        margin_bottom="1.5em",
        padding="18px",
        background_color="var(--gray-3)",
        class_name=rx.color_mode_cond(
            light=(
            "transition-all duration-300 overflow-hidden "
            "hover:shadow-[0_0_8px_rgba(0,0,0,0.22)] "
            ),
            dark=(
            "transition-all duration-300 overflow-hidden "
            "hover:shadow-[0_0_6px_rgba(229,229,229,229.12)]"
            ),
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
        rx.icon("expand", size=16),
        position="absolute",
        right="0px",
        bottom="0px",
        border_radius="full",
        pointer_events="none",
    )
    content_block = rx.vstack(
        rx.hstack(
            status_badge(proposal),
            catalyst_id_badge(proposal),
            pill(f"{fund_label(proposal)}", "layers", "yellow"),
            pill(campaign_label(proposal), "flag", "gray"),
            spacing="2",
            wrap="wrap",
            align="center",
        ),
        rx.text(
            proposal["title_ja"],
            size="3",
            weight="bold",
            color="var(--gray-12)",
        ),
        rx.text(proposal["title"], size="2", color="var(--gray-9)", class_name="mt-0"),
        rx.text(
            description,
            size="2",
            color="var(--gray-12)",
            line_height="1.6",
            text_wrap="wrap",
            class_name="line-clamp-3 mt-1",
        ),
        spacing="3",
        width="100%",
    )

    footer_block = rx.vstack(
        rx.hstack(
            rx.hstack(
                rx.icon("user", size=14, color="var(--gray-9)"),
                rx.text(proposal["user_name"], size="2", color="var(--gray-10)"),
                spacing="2",
                align="center",
            ),
            rx.hstack(
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
    )

    return rx.card(
        rx.box(
            rx.vstack(
                content_block,
                footer_block,
                spacing="3",
                width="100%",
                height="100%",
                justify="between",
            ),
            page_icon,
            position="relative",
            width="100%",
            height="100%",
        ),
        background_color="var(--gray-3)",
        class_name=rx.color_mode_cond(
            light=(
            "transition-all duration-300 overflow-hidden "
            "hover:shadow-[0_0_8px_rgba(0,0,0,0.22)] "
            ),
            dark=(
            "transition-all duration-300 overflow-hidden "
            "hover:shadow-[0_0_6px_rgba(229,229,229,229.12)]"
            ),
        ),
        on_click=lambda: [AppState.open_modal(proposal), AppState.load_modal_detail(proposal["uuid"])],
        cursor="pointer",
    )


def modal_history_script() -> rx.Component:
    return rx.script(
        """
        if (!window.__proposalModalHistory) {
          window.__proposalModalHistory = true;
          window.proposalModalPush = (uuid, state) => {
            history.pushState(
              { scrollY: window.scrollY, search: state.search, filter: state.filter },
              "",
              `/catalyst/proposals/${uuid}`
            );
          };
          window.proposalModalReplace = (state) => {
            history.replaceState(
              { scrollY: window.scrollY, search: state.search, filter: state.filter },
              "",
              window.location.pathname + window.location.search
            );
          };
          window.addEventListener("popstate", (event) => {
            if (window.reflex) {
              window.reflex.send({
                state: "AppState",
                event: "on_popstate",
                data: event.state,
              });
            }
          });
        }
        """
    )


def detail_modal() -> rx.Component:
    p = AppState.modal_proposal
    return rx.dialog.root(
        rx.dialog.content(
            rx.html(
                """
                <style>
                .proposal-modal a {
                  color: var(--amber-11) !important;
                  text-decoration: underline;
                }
                .proposal-modal a:hover {
                  color: var(--amber-9) !important;
                }
                .proposal-modal ::-webkit-scrollbar {
                  width: 8px;
                  height: 8px;
                }
                .proposal-modal ::-webkit-scrollbar-track {
                  background: var(--gray-3);
                }
                .proposal-modal ::-webkit-scrollbar-thumb {
                  background: var(--gray-6);
                  border-radius: 9999px;
                }
                .proposal-modal ::-webkit-scrollbar-thumb:hover {
                  background: var(--gray-7);
                }
                .proposal-modal {
                  #color: var(--gray-11);
                  border: 1px solid var(--slate-6);
                  scrollbar-color: var(--gray-5) var(--gray-3);
                  scrollbar-width: thin;
                  font-family: """
                + styles.font_family
                + """;
                }
                @media (max-width: 768px) {
                  .rt-DialogContent.proposal-modal {
                    position: fixed !important;
                    inset: 0 !important;
                    margin: 0 !important;
                    transform: none !important;
                  }
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
                            style={"wordBreak": "break-word"},
                        ),
                        rx.text(
                            p.get("title", ""),
                            size="2",
                            width="100%",
                            style={"wordBreak": "break-word"},
                        ),
                        spacing="1",
                        align_items="start",
                    ),
                    rx.button(
                        rx.icon("x"),
                        variant="solid",
                        color_scheme=None,
                        color="var(--gray-12)",
                        background_color="var(--amber-9)",
                        _hover={"background_color": "var(--amber-6)"},
                        size="2",
                        on_click=AppState.close_modal,
                        cursor="pointer",
                    ),
                    justify="between",
                    align="start",
                    width="100%",
                ),
                rx.hstack(
                    status_badge(p),
                    catalyst_id_badge(p),
                    pill(f"{fund_label(p)}", "layers", "yellow"),
                    pill(campaign_label(p), "flag", "gray"),
                    spacing="2",
                    wrap="wrap",
                ),
                rx.hstack(
                    rx.text(p.get("user_name", ""), size="2", color="var(--gray-9)"),
                    rx.text(
                        f"{p.get('currency_symbol','')} {p.get('amount_requested_comma')}",
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
                        href=p.get("projectcatalyst_link", ""),
                            underline="auto",
                            is_external=True,
                            style={"text-decoration": "none !important"},
                    ),
                    spacing="2",
                    wrap="wrap",
                    align="center",
                ),
                fund_progress_bar(p),
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
                        rx.box(
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
                            rx.vstack(
                                semantic_toggle_bar(
                                    semantic_toggle_button(
                                        "英語原文",
                                        "raw",
                                        AppState.modal_semantic_view,
                                        lambda: AppState.set_modal_semantic_view("raw"),
                                    ),
                                    semantic_toggle_button(
                                        "日本語翻訳",
                                        "ja",
                                        AppState.modal_semantic_view,
                                        lambda: AppState.set_modal_semantic_view("ja"),
                                    ),
                                    semantic_toggle_button(
                                        "AI要約",
                                        "ai",
                                        AppState.modal_semantic_view,
                                        lambda: AppState.set_modal_semantic_view("ai"),
                                    ),
                                    top="0px",
                                    panel_background="var(--gray-2)",
                                    panel_padding="8px 18px",
                                    panel_radius="9999px",
                                    z_index="6",
                                ),
                                rx.cond(
                                    AppState.modal_semantic_view == "ai",
                                    rx.box(),
                                    rx.cond(
                                        AppState.modal_semantic_view == "raw",
                                        rx.vstack(
                                            rx.el.h2(
                                                "課題",
                                                class_name=(
                                                    "text-[16px] md:text-[16px] font-semibold tracking-tight "
                                                    "text-[var(--gray-12)] pb-1 border-b border-[var(--gray-5)] "
                                                    "border-l-4 border-[var(--gray-6)] pl-3"
                                                ),
                                            ),
                                            rx.text(p.get("problem", ""), size="3", line_height="1.6", color="var(--sand-a12)", padding_x="8px"),
                                            spacing="1",
                                            width="100%",
                                            padding_top="8px",
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
                                            rx.text(p.get("problem_ja", ""), size="3", line_height="1.6", color="var(--sand-a12)", padding_x="8px"),
                                            spacing="1",
                                            width="100%",
                                            padding_top="8px",
                                        ),
                                    ),
                                ),
                                rx.cond(
                                    AppState.modal_semantic_view == "ai",
                                    rx.box(),
                                    rx.cond(
                                        AppState.modal_semantic_view == "raw",
                                        rx.vstack(
                                            rx.el.h2(
                                                "解決策",
                                                class_name=(
                                                    "text-[16px] md:text-[16px] font-semibold tracking-tight "
                                                    "text-[var(--gray-12)] pb-1 border-b border-[var(--gray-5)] "
                                                    "border-l-4 border-[var(--gray-6)] pl-3"
                                                ),
                                            ),
                                            rx.text(p.get("solution", ""), size="3", line_height="1.6", color="var(--sand-a12)", padding_x="8px"),
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
                                            rx.text(p.get("solution_ja", ""), size="3", line_height="1.6", color="var(--sand-a12)", padding_x="8px"),
                                            spacing="1",
                                            width="100%",
                                        ),
                                    ),
                                ),
                                rx.foreach(
                                    semantic_blocks_by_view(
                                        AppState.modal_semantic_view,
                                        AppState.modal_semantic_blocks_raw,
                                        AppState.modal_semantic_blocks_ja,
                                        AppState.modal_semantic_blocks_ai,
                                    ),
                                    semantic_block_section,
                                ),
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
                    background_color="var(--amber-9)",
                    color="var(--gray-12)",
                    cursor="pointer",
                    _hover={"background_color": "var(--amber-6)"},
                ),
                spacing="3",
                width="100%",
                align_items="stretch",
                height="100%",
                min_height="0",
            ),
            max_width=["100vw", "100vw", "900px"],
            max_height=["100vh", "100vh", "95vh"],
            width=["100vw", "100vw", "95vw"],
            height=["100vh", "100vh", "auto"],
            padding="20px",
            class_name=(
                "proposal-modal "
                "shadow-xl rounded-2xl "
                "border"
            ),
            style={"display": "flex", "flexDirection": "column"},
        ),
        open=AppState.modal_open,
        modal=False,
    )


def card_foreach_dict() -> rx.Component:
    return rx.box(
        STATUS_DOT_STYLE,
        modal_history_script(),
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
