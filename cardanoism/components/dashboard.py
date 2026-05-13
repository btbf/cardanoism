"""ログインユーザー向けトップダッシュボード (`/`)。

Phase A:
  - ヒーロー (welcome + 参加状況概観)
  - クイックアクション CTA グリッド
  - 委任先 SPO + DRep サマリー (リレー警告含む)
  - 委任先 DRep の直近投票
  - お気に入り (catalyst + governance)
  - 通知設定サマリー

Phase B:
  - エポック + トレジャリー残高ミニカード
  - 委任先プールの実績 (直近 5 ep ブロック数 + 7 ep 平均 APY)
  - 直近ステーキング報酬 (5 ep 別 + 累積)
  - 未投票 GA (本人 DRep / 委任先 DRep)
  - 締切が近い GA
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.dashboard_state import DashboardState


# ── 共通スタイル ────────────────────────────────

CARD_STYLE = dict(
    padding="16px 18px",
    border_radius="12px",
    border=f"1px solid {rx.color('gray', 4)}",
    background="var(--gray-1)",
    width="100%",
)


def _section_card(title, icon: str, body, action=None) -> rx.Component:
    """共通: タイトル + アイコン + 任意のアクションボタン + body のカード。"""
    head_items = [
        rx.icon(icon, size=16, color="var(--amber-11)"),
        rx.text(title, size="3", weight="bold", color="var(--gray-12)"),
        rx.spacer(),
    ]
    if action is not None:
        head_items.append(action)
    return rx.box(
        rx.vstack(
            rx.hstack(*head_items, spacing="2", align="center", width="100%"),
            body,
            spacing="3", align="stretch", width="100%",
        ),
        **CARD_STYLE,
    )


def _section_spinner() -> rx.Component:
    """セクション内データ取得中の中央スピナー。"""
    return rx.flex(
        rx.spinner(size="2"),
        justify="center", align="center",
        padding_y="20px", width="100%",
    )


# ── ヒーロー ────────────────────────────────────

def _hero_section() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.cond(
                    AuthState.avatar_url != "",
                    rx.avatar(src=AuthState.avatar_url, size="3", radius="full"),
                    rx.avatar(fallback=AuthState.username[:1], size="3", radius="full"),
                ),
                rx.vstack(
                    rx.text(
                        AuthState.t["dashboard_welcome"], " ",
                        AuthState.username,
                        size="5", weight="bold", color="var(--gray-12)",
                    ),
                    rx.text(
                        AuthState.t["dashboard_welcome_sub"],
                        size="2", color="var(--gray-10)",
                    ),
                    spacing="1", align_items="start",
                ),
                spacing="3", align="center",
            ),
            spacing="2", align_items="start", width="100%",
        ),
        padding="20px 22px",
        border_radius="14px",
        border=f"1px solid {rx.color('gray', 4)}",
        background=rx.color_mode_cond(
            "linear-gradient(135deg, var(--amber-2), var(--amber-1))",
            "linear-gradient(135deg, rgba(245,158,11,0.08), rgba(245,158,11,0.02))",
        ),
        width="100%",
    )


# ── クイックアクション ─────────────────────────

def _action_card(icon: str, label, sub, href: str) -> rx.Component:
    return rx.link(
        rx.box(
            rx.hstack(
                rx.icon(icon, size=20, color="var(--amber-11)", flex_shrink="0"),
                rx.vstack(
                    rx.text(label, size="2", weight="bold", color="var(--gray-12)"),
                    rx.text(sub, size="1", color="var(--gray-10)"),
                    spacing="0", align_items="start",
                ),
                spacing="3", align="center",
            ),
            padding="14px 16px",
            border_radius="10px",
            border=f"1px solid {rx.color('gray', 4)}",
            background="var(--gray-2)",
            width="100%",
            _hover={
                "border_color": rx.color("amber", 7),
                "background": rx.color("amber", 2),
            },
            style={"transition": "background 0.15s, border-color 0.15s"},
        ),
        href=href,
        underline="none",
        width="100%",
    )


def _quick_actions_section() -> rx.Component:
    return rx.box(
        rx.grid(
            _action_card(
                "users", AuthState.t["dashboard_action_drep"],
                AuthState.t["dashboard_action_drep_sub"], "/governance/drep",
            ),
            _action_card(
                "server", AuthState.t["dashboard_action_spo"],
                AuthState.t["dashboard_action_spo_sub"], "/staking/spo",
            ),
            _action_card(
                "wallet", AuthState.t["dashboard_action_stake_address"],
                AuthState.t["dashboard_action_stake_address_sub"], "/mypage?tab=stake",
            ),
            _action_card(
                "bell", AuthState.t["dashboard_action_notification"],
                AuthState.t["dashboard_action_notification_sub"], "/mypage?tab=notification",
            ),
            columns={"base": "1", "sm": "2", "md": "4"},
            spacing="3",
            width="100%",
        ),
        width="100%",
    )


# ── 委任サマリー ───────────────────────────────

def _delegation_row(d: rx.Var) -> rx.Component:
    """ステークアドレス 1 件の委任先サマリー行。"""
    pool_label = rx.cond(
        d["pool_id"] != "",
        rx.hstack(
            rx.icon("server", size=13, color="var(--gray-10)"),
            rx.text("SPO:", size="1", color="var(--gray-10)"),
            rx.text(
                rx.cond(
                    d["pool_ticker"] != "",
                    d["pool_ticker"],
                    rx.cond(d["pool_name"] != "", d["pool_name"], d["pool_id"][:12] + "…"),
                ),
                size="2", weight="medium", color="var(--gray-12)",
            ),
            rx.cond(
                d["relay_alive"] == "0",
                rx.badge(AuthState.t["dashboard_relay_warning"], color_scheme="red", variant="soft", size="1"),
                rx.fragment(),
            ),
            spacing="1", align="center", wrap="wrap",
        ),
        rx.hstack(
            rx.icon("server", size=13, color="var(--gray-9)"),
            rx.text("SPO:", size="1", color="var(--gray-10)"),
            rx.text(AuthState.t["dashboard_unset"], size="2", color="var(--gray-9)", style={"fontStyle": "italic"}),
            spacing="1", align="center",
        ),
    )

    drep_label = rx.cond(
        d["drep_id"] == "always_abstain",
        rx.hstack(
            rx.icon("user", size=13, color="var(--gray-10)"),
            rx.text("DRep:", size="1", color="var(--gray-10)"),
            rx.text(
                AuthState.t["drep_special_always_abstain"],
                size="2", weight="medium", color="var(--gray-11)",
            ),
            spacing="1", align="center",
        ),
        rx.cond(
            d["drep_id"] != "",
            rx.hstack(
                rx.icon("user", size=13, color="var(--gray-10)"),
                rx.text("DRep:", size="1", color="var(--gray-10)"),
                rx.text(
                    rx.cond(
                        d["drep_name"] != "",
                        d["drep_name"],
                        d["drep_id"][:14] + "…",
                    ),
                    size="2", weight="medium", color="var(--gray-12)",
                ),
                spacing="1", align="center",
            ),
            rx.hstack(
                rx.icon("user", size=13, color="var(--gray-9)"),
                rx.text("DRep:", size="1", color="var(--gray-10)"),
                rx.text(AuthState.t["dashboard_unset"], size="2", color="var(--gray-9)", style={"fontStyle": "italic"}),
                spacing="1", align="center",
            ),
        ),
    )

    verified_badge = rx.cond(
        d["verified"] == "1",
        rx.badge(
            rx.icon("circle-check", size=11),
            AuthState.t["dashboard_verified"],
            color_scheme="green", variant="soft", size="1",
        ),
        rx.badge(
            rx.icon("circle-alert", size=11),
            AuthState.t["dashboard_unverified"],
            color_scheme="amber", variant="soft", size="1",
        ),
    )

    return rx.box(
        rx.hstack(
            rx.icon("wallet", size=14, color="var(--amber-11)", flex_shrink="0"),
            rx.text(
                d["nickname"],
                size="2", weight="bold", color="var(--gray-12)",
                style={"whiteSpace": "nowrap"},
            ),
            verified_badge,
            rx.box(width="1px", height="14px", background="var(--gray-5)", flex_shrink="0"),
            pool_label,
            rx.box(width="1px", height="14px", background="var(--gray-5)", flex_shrink="0"),
            drep_label,
            spacing="3", align="center", wrap="wrap", width="100%",
        ),
        padding="10px 14px",
        border_radius="8px",
        background="var(--gray-2)",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )


def _delegations_section() -> rx.Component:
    inner = rx.cond(
        DashboardState.delegations.length() > 0,
        rx.vstack(
            rx.foreach(
                DashboardState.filtered_delegations,
                _delegation_row,
            ),
            spacing="2", align="stretch", width="100%",
        ),
        rx.hstack(
            rx.icon("wallet-minimal", size=16, color="var(--gray-9)"),
            rx.text(
                AuthState.t["dashboard_delegations_empty"],
                size="2", color="var(--gray-10)",
            ),
            rx.spacer(),
            rx.link(
                rx.button(
                    rx.icon("plus", size=14),
                    rx.text(AuthState.t["dashboard_register_stake"], size="2"),
                    color_scheme="amber", size="1", cursor="pointer",
                ),
                href="/mypage?tab=stake", underline="none",
            ),
            spacing="2", align="center", width="100%",
            padding="8px 4px",
        ),
    )
    body = rx.cond(DashboardState.delegations_loading, _section_spinner(), inner)
    return _section_card(
        AuthState.t["dashboard_delegations_title"],
        "compass",
        body,
        action=rx.link(
            rx.button(
                rx.icon("settings", size=12),
                rx.text(AuthState.t["dashboard_manage"], size="1"),
                variant="soft", color_scheme="gray", size="1", cursor="pointer",
            ),
            href="/mypage?tab=stake", underline="none",
        ),
    )


# ── DRep 直近投票 ──────────────────────────────

def _drep_vote_badge(vote_var: rx.Var) -> rx.Component:
    """vote 値に応じたバッジ。空文字 = 未投票 (rx.match の default で表示)。"""
    return rx.match(
        vote_var,
        ("Yes",
            rx.badge(AuthState.t["dashboard_vote_yes"], color_scheme="blue",
                     variant="solid", size="1")),
        ("No",
            rx.badge(AuthState.t["dashboard_vote_no"], color_scheme="orange",
                     variant="solid", size="1")),
        ("Abstain",
            rx.badge(AuthState.t["dashboard_vote_abstain"], color_scheme="gray",
                     variant="solid", size="1")),
        rx.badge(AuthState.t["dashboard_vote_unvoted"], color_scheme="gray",
                 variant="soft", size="1"),
    )


def _drep_vote_rationale_dialog(v: rx.Var) -> rx.Component:
    """投票理由ダイアログ。rationale が空なら trigger 自体表示しない。"""
    has_rationale = (v["rationale_ja"] != "") | (v["rationale"] != "")
    rationale_text = rx.cond(
        AuthState.language == "ja",
        rx.cond(v["rationale_ja"] != "", v["rationale_ja"], v["rationale"]),
        v["rationale"],
    )
    return rx.cond(
        has_rationale,
        rx.dialog.root(
            rx.dialog.trigger(
                rx.el.button(
                    rx.icon("message-square", size=11, color="var(--gray-10)"),
                    rx.text(AuthState.t["dashboard_vote_rationale"], size="1", color="var(--gray-11)"),
                    style={
                        "display": "inline-flex",
                        "alignItems": "center",
                        "gap": "4px",
                        "padding": "2px 8px",
                        "border": f"1px solid {rx.color('gray', 5)}",
                        "borderRadius": "999px",
                        "background": "transparent",
                        "cursor": "pointer",
                    },
                    _hover={"background": rx.color("gray", 3)},
                ),
            ),
            rx.dialog.content(
                rx.dialog.title(AuthState.t["dashboard_vote_rationale_title"], size="4"),
                rx.scroll_area(
                    rx.text(
                        rationale_text,
                        size="2", color="var(--gray-12)",
                        style={"whiteSpace": "pre-wrap", "lineHeight": "1.6"},
                    ),
                    type="auto", scrollbars="vertical",
                    style={"maxHeight": "60vh"},
                ),
                rx.flex(
                    rx.dialog.close(
                        rx.button(
                            AuthState.t["dashboard_vote_rationale_close"],
                            size="2", variant="soft", color_scheme="gray", cursor="pointer",
                        ),
                    ),
                    justify="end", margin_top="16px",
                ),
                max_width="640px",
            ),
        ),
        rx.fragment(),
    )


def _drep_vote_row(v: rx.Var) -> rx.Component:
    title = rx.cond(
        AuthState.language == "ja",
        rx.cond(v["title_ja"] != "", v["title_ja"], v["title"]),
        v["title"],
    )
    return rx.hstack(
        _drep_vote_badge(v["vote"]),
        rx.link(
            rx.text(
                rx.cond(title != "", title, v["proposal_id"][:24] + "…"),
                size="2", color="var(--gray-12)",
                style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
            ),
            href="/governance/" + v["proposal_id"],
            underline="hover",
            color="inherit",
            flex="1", min_width="0",
        ),
        _drep_vote_rationale_dialog(v),
        spacing="2", align="center", width="100%",
    )


def _drep_votes_section() -> rx.Component:
    inner = rx.cond(
        DashboardState.delegations.length() > 0,
        rx.vstack(
            rx.foreach(
                DashboardState.delegations.to(list[dict[str, str]]),
                _drep_votes_for_delegation,
            ),
            spacing="3", align="stretch", width="100%",
        ),
        rx.hstack(
            rx.text(
                AuthState.t["dashboard_drep_votes_empty"],
                size="2", color="var(--gray-10)",
            ),
            spacing="2", align="center", padding="8px 4px",
        ),
    )
    body = rx.cond(DashboardState.delegations_loading, _section_spinner(), inner)
    return _section_card(
        AuthState.t["dashboard_drep_votes_title"],
        "vote",
        body,
    )


def _drep_votes_for_delegation(d: rx.Var) -> rx.Component:
    """この stake_address の DRep の全 GA 投票状況を表示する (5 件/ページのページネーション付き)。
    drep_recent_votes[drep_id] には現在ページ分しか入っていない (サーバー側ページネーション)。
    """
    drep_id = d["drep_id"]
    votes_page = DashboardState.drep_recent_votes[drep_id]
    page_info = DashboardState.drep_votes_page_info[drep_id]

    header = rx.hstack(
        rx.icon("wallet", size=13, color="var(--amber-11)", flex_shrink="0"),
        rx.text(d["nickname"], size="1", color="var(--gray-10)", weight="medium"),
        rx.text("→", size="1", color="var(--gray-9)"),
        rx.icon("user", size=13, color="var(--gray-10)", flex_shrink="0"),
        rx.text(
            rx.cond(d["drep_name"] != "", d["drep_name"], d["drep_id"][:14] + "…"),
            size="2", weight="medium", color="var(--gray-12)",
        ),
        spacing="1", align="center", wrap="wrap",
    )

    # 総件数は page_info に入っているのでそれで条件分岐 (現在ページに 0 件
    # でも、別ページに件数があれば pagination を出す)
    pagination = rx.cond(
        page_info["total"] != "0",
        rx.hstack(
            rx.button(
                rx.icon("chevron-left", size=14),
                size="1",
                variant="soft",
                color_scheme="gray",
                disabled=page_info["has_prev"] == "",
                on_click=DashboardState.drep_votes_prev_page(drep_id),
                cursor="pointer",
            ),
            rx.text(
                page_info["page"] + " / " + page_info["total_pages"],
                size="1", color="var(--gray-10)",
            ),
            rx.button(
                rx.icon("chevron-right", size=14),
                size="1",
                variant="soft",
                color_scheme="gray",
                disabled=page_info["has_next"] == "",
                on_click=DashboardState.drep_votes_next_page(drep_id),
                cursor="pointer",
            ),
            rx.spacer(),
            rx.text(
                AuthState.t["dashboard_drep_votes_total"] + ": " + page_info["total"],
                size="1", color="var(--gray-9)",
            ),
            spacing="2", align="center", width="100%",
        ),
        rx.fragment(),
    )

    return rx.cond(
        (d["drep_id"] != "") & (d["drep_id"] != "always_abstain"),
        rx.vstack(
            header,
            rx.cond(
                votes_page.length() > 0,
                rx.vstack(
                    rx.foreach(votes_page.to(list[dict[str, str]]), _drep_vote_row),
                    spacing="1", align="stretch", width="100%",
                ),
                rx.text(
                    AuthState.t["dashboard_drep_no_votes"],
                    size="1", color="var(--gray-9)", style={"fontStyle": "italic"},
                ),
            ),
            pagination,
            spacing="2", align="stretch", width="100%",
        ),
        rx.fragment(),
    )


# ── お気に入り ─────────────────────────────────

def _favorite_link(label, href: str) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.icon("star", size=12, color="var(--amber-10)", flex_shrink="0"),
            rx.text(
                label,
                size="2", color="var(--gray-12)",
                style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                flex="1", min_width="0",
            ),
            spacing="2", align="center", width="100%",
        ),
        underline="hover",
        color="inherit",
        href=href,
        width="100%",
    )


def _catalyst_fav_row(f: rx.Var) -> rx.Component:
    title = rx.cond(
        AuthState.language == "ja",
        rx.cond(f["title_ja"] != "", f["title_ja"], f["title"]),
        f["title"],
    )
    return _favorite_link(title, "/proposals/" + f["proposal_uuid"])


def _governance_fav_row(f: rx.Var) -> rx.Component:
    title = rx.cond(
        AuthState.language == "ja",
        rx.cond(f["title_ja"] != "", f["title_ja"], f["title"]),
        f["title"],
    )
    return _favorite_link(title, "/governance/" + f["proposal_uuid"])


def _drep_fav_row(f: rx.Var) -> rx.Component:
    label = rx.cond(
        f["given_name"] != "",
        f["given_name"],
        f["drep_id"][:14] + "…",
    )
    return _favorite_link(label, "/drep/" + f["drep_id"])


def _pool_fav_row(f: rx.Var) -> rx.Component:
    # ticker → pool_name → 短縮 ID の順でフォールバック表示
    label = rx.cond(
        f["ticker"] != "",
        f["ticker"],
        rx.cond(f["pool_name"] != "", f["pool_name"], f["pool_id"][:14] + "…"),
    )
    # Pool 詳細ページが無いので /mypage?tab=favorites で個別カードを表示する
    return _favorite_link(label, "/mypage?tab=favorites")


def _favorites_section() -> rx.Component:
    catalyst_block = rx.vstack(
        rx.hstack(
            rx.icon("file-text", size=14, color="var(--gray-10)"),
            rx.text(AuthState.t["dashboard_favorites_catalyst"], size="2", weight="medium", color="var(--gray-12)"),
            rx.badge(DashboardState.catalyst_fav_count, color_scheme="amber", variant="soft", size="1"),
            spacing="2", align="center",
        ),
        rx.cond(
            DashboardState.catalyst_favorites.length() > 0,
            rx.vstack(
                rx.foreach(
                    DashboardState.catalyst_favorites.to(list[dict[str, str]]),
                    _catalyst_fav_row,
                ),
                spacing="1", align="stretch", width="100%",
            ),
            rx.text(
                AuthState.t["dashboard_favorites_empty"],
                size="1", color="var(--gray-9)", style={"fontStyle": "italic"},
            ),
        ),
        spacing="2", align="stretch", width="100%",
    )

    governance_block = rx.vstack(
        rx.hstack(
            rx.icon("gavel", size=14, color="var(--gray-10)"),
            rx.text(AuthState.t["dashboard_favorites_governance"], size="2", weight="medium", color="var(--gray-12)"),
            rx.badge(DashboardState.governance_fav_count, color_scheme="amber", variant="soft", size="1"),
            spacing="2", align="center",
        ),
        rx.cond(
            DashboardState.governance_favorites.length() > 0,
            rx.vstack(
                rx.foreach(
                    DashboardState.governance_favorites.to(list[dict[str, str]]),
                    _governance_fav_row,
                ),
                spacing="1", align="stretch", width="100%",
            ),
            rx.text(
                AuthState.t["dashboard_favorites_empty"],
                size="1", color="var(--gray-9)", style={"fontStyle": "italic"},
            ),
        ),
        spacing="2", align="stretch", width="100%",
    )

    drep_block = rx.vstack(
        rx.hstack(
            rx.icon("user", size=14, color="var(--gray-10)"),
            rx.text(AuthState.t["dashboard_favorites_drep"], size="2", weight="medium", color="var(--gray-12)"),
            rx.badge(DashboardState.drep_fav_count, color_scheme="amber", variant="soft", size="1"),
            spacing="2", align="center",
        ),
        rx.cond(
            DashboardState.drep_favorites.length() > 0,
            rx.vstack(
                rx.foreach(
                    DashboardState.drep_favorites.to(list[dict[str, str]]),
                    _drep_fav_row,
                ),
                spacing="1", align="stretch", width="100%",
            ),
            rx.text(
                AuthState.t["dashboard_favorites_empty"],
                size="1", color="var(--gray-9)", style={"fontStyle": "italic"},
            ),
        ),
        spacing="2", align="stretch", width="100%",
    )

    pool_block = rx.vstack(
        rx.hstack(
            rx.icon("server", size=14, color="var(--gray-10)"),
            rx.text(AuthState.t["dashboard_favorites_pool"], size="2", weight="medium", color="var(--gray-12)"),
            rx.badge(DashboardState.pool_fav_count, color_scheme="amber", variant="soft", size="1"),
            spacing="2", align="center",
        ),
        rx.cond(
            DashboardState.pool_favorites.length() > 0,
            rx.vstack(
                rx.foreach(
                    DashboardState.pool_favorites.to(list[dict[str, str]]),
                    _pool_fav_row,
                ),
                spacing="1", align="stretch", width="100%",
            ),
            rx.text(
                AuthState.t["dashboard_favorites_empty"],
                size="1", color="var(--gray-9)", style={"fontStyle": "italic"},
            ),
        ),
        spacing="2", align="stretch", width="100%",
    )

    inner = rx.grid(
        pool_block,
        drep_block,
        governance_block,
        catalyst_block,
        columns={"base": "1", "md": "2"},
        spacing="4",
        width="100%",
    )
    body = rx.cond(DashboardState.favorites_loading, _section_spinner(), inner)
    return _section_card(
        AuthState.t["dashboard_favorites_title"],
        "star",
        body,
        action=rx.link(
            rx.button(
                rx.icon("external-link", size=12),
                rx.text(AuthState.t["dashboard_view_all"], size="1"),
                variant="soft", color_scheme="gray", size="1", cursor="pointer",
            ),
            href="/mypage?tab=favorites", underline="none",
        ),
    )


# ── 通知サマリー ───────────────────────────────

def _notification_summary_section() -> rx.Component:
    def _channel_chip(label: str, key: str, icon: str) -> rx.Component:
        enabled = DashboardState.notification_channels[key] == "1"
        return rx.hstack(
            rx.icon(icon, size=12),
            rx.text(label, size="1"),
            rx.cond(
                enabled,
                rx.icon("circle-check", size=11, color="var(--green-10)"),
                rx.icon("circle-off", size=11, color="var(--gray-9)"),
            ),
            spacing="1", align="center",
            padding="4px 10px",
            border_radius="999px",
            border=f"1px solid {rx.color('gray', 5)}",
            background=rx.cond(enabled, rx.color("green", 2), "var(--gray-2)"),
            color=rx.cond(enabled, "var(--green-11)", "var(--gray-10)"),
        )

    inner = rx.hstack(
        _channel_chip("LINE", "line", "message-square"),
        _channel_chip("Email", "email", "mail"),
        _channel_chip("Telegram", "telegram", "send"),
        spacing="2", align="center", wrap="wrap",
    )
    body = rx.cond(DashboardState.notifications_loading, _section_spinner(), inner)
    return _section_card(
        AuthState.t["dashboard_notifications_title"],
        "bell",
        body,
        action=rx.link(
            rx.button(
                rx.icon("settings", size=12),
                rx.text(AuthState.t["dashboard_manage"], size="1"),
                variant="soft", color_scheme="gray", size="1", cursor="pointer",
            ),
            href="/mypage?tab=notification", underline="none",
        ),
    )


# ── エポック + トレジャリーミニカード (Phase B) ──

def _epoch_treasury_section() -> rx.Component:
    epoch_box = rx.vstack(
        rx.hstack(
            rx.icon("clock", size=14, color="var(--blue-11)"),
            rx.text(AuthState.t["dashboard_epoch_label"], size="1", color="var(--gray-10)"),
            spacing="1", align="center",
        ),
        rx.hstack(
            rx.text("Epoch", size="2", color="var(--gray-10)"),
            rx.text(DashboardState.current_epoch_str, size="6", weight="bold", color="var(--gray-12)"),
            spacing="2", align="baseline",
        ),
        rx.cond(
            DashboardState.next_epoch_in_label != "",
            rx.text(
                AuthState.t["dashboard_next_epoch_in"], " ", DashboardState.next_epoch_in_label,
                size="1", color="var(--gray-10)",
            ),
            rx.fragment(),
        ),
        spacing="0", align_items="start",
    )
    treasury_box = rx.vstack(
        rx.hstack(
            rx.icon("landmark", size=14, color="var(--amber-11)"),
            rx.text(AuthState.t["dashboard_treasury_label"], size="1", color="var(--gray-10)"),
            spacing="1", align="center",
        ),
        rx.hstack(
            rx.text(DashboardState.treasury_balance_ada, size="5", weight="bold", color="var(--gray-12)"),
            rx.text("ADA", size="2", color="var(--gray-10)"),
            spacing="1", align="baseline",
        ),
        rx.cond(
            DashboardState.treasury_epoch_str != "",
            rx.text(
                "ep ", DashboardState.treasury_epoch_str, " " , AuthState.t["dashboard_treasury_at_epoch"],
                size="1", color="var(--gray-10)",
            ),
            rx.fragment(),
        ),
        spacing="0", align_items="start",
    )
    inner = rx.grid(
        epoch_box,
        treasury_box,
        columns={"base": "1", "sm": "2"},
        spacing="4",
        width="100%",
    )
    return rx.box(
        rx.cond(
            DashboardState.epoch_treasury_loading,
            _section_spinner(),
            inner,
        ),
        padding="14px 18px",
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 4)}",
        background=rx.color_mode_cond(
            "linear-gradient(135deg, var(--blue-2), var(--amber-1))",
            "linear-gradient(135deg, rgba(59,130,246,0.06), rgba(245,158,11,0.04))",
        ),
        width="100%",
    )


# ── プール実績 (Phase B) ───────────────────────

def _pool_metric(label, value, unit: str = "", emphasis: bool = False) -> rx.Component:
    """プール実績カードの 1 メトリクス (label + value + unit)。"""
    value_color = "var(--blue-11)" if emphasis else "var(--gray-12)"
    return rx.vstack(
        rx.text(label, size="1", color="var(--gray-10)", style={"whiteSpace": "nowrap"}),
        rx.hstack(
            rx.text(value, size="2", weight="bold", color=value_color),
            rx.cond(
                unit != "",
                rx.text(unit, size="1", color="var(--gray-10)"),
                rx.fragment(),
            ),
            spacing="1", align="baseline",
        ),
        spacing="0", align_items="start", min_width="0",
    )


def _pool_perf_row(p: rx.Var) -> rx.Component:
    """委任先プール 1 件の実績カード (ヘッダ + メトリクスグリッド)。"""
    # ヘッダ: nickname → ticker → pool_name (1 行)
    # ウォレット名 (nickname) は財布アイコンで統一 (人アイコンの DRep と区別)
    header = rx.hstack(
        rx.icon("wallet", size=16, color="var(--amber-11)", flex_shrink="0"),
        rx.text(
            p["nickname"],
            size="2", weight="medium", color="var(--gray-11)",
            style={"whiteSpace": "nowrap"},
        ),
        rx.icon("chevron-right", size=12, color="var(--gray-8)", flex_shrink="0"),
        rx.cond(
            p["ticker"] != "",
            rx.badge(p["ticker"], variant="solid", color_scheme="amber", radius="full", size="1"),
            rx.fragment(),
        ),
        rx.cond(
            p["pool_name"] != "",
            rx.text(
                p["pool_name"],
                size="3", weight="bold", color="var(--gray-12)",
                style={
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap",
                    "maxWidth": "320px",
                },
            ),
            rx.fragment(),
        ),
        rx.spacer(),
        rx.cond(
            p["is_saturated"] == "1",
            rx.badge(AuthState.t["staking_badge_saturated"], color_scheme="red", variant="soft", size="1"),
            rx.cond(
                p["is_saturated"] == "warn",
                rx.badge(AuthState.t["staking_badge_warning"], color_scheme="amber", variant="soft", size="1"),
                rx.fragment(),
            ),
        ),
        # 報酬 popover (累積 + 直近 5ep をクリックで展開)
        _rewards_popover(p),
        spacing="2", align="center", width="100%", wrap="wrap",
    )

    # メトリクスグリッド (live_stake / 飽和率 / 委任者数 / margin / fixed_cost / 5ep / APY)
    metrics = rx.grid(
        _pool_metric(
            AuthState.t["staking_metric_stake"],
            rx.cond(AuthState.language == "ja", p["stake_ada_ja"], p["stake_ada_en"]),
            "ADA",
            emphasis=True,
        ),
        _pool_metric(
            AuthState.t["staking_metric_saturation"],
            p["saturation_pct"], "%",
        ),
        _pool_metric(
            AuthState.t["staking_metric_delegators"],
            p["delegators"],
        ),
        _pool_metric(
            AuthState.t["staking_metric_margin"],
            p["margin_pct"], "%",
        ),
        _pool_metric(
            AuthState.t["staking_metric_fixed_cost"],
            p["fixed_cost_ada"], "ADA",
        ),
        _pool_metric(
            AuthState.t["staking_metric_recent5ep"],
            p["history_total"],
            emphasis=True,
        ),
        _pool_metric(
            AuthState.t["staking_metric_apy"],
            p["apy_avg"], "%",
            emphasis=True,
        ),
        columns={"base": "2", "sm": "3", "md": "4", "lg": "7"},
        spacing="3",
        width="100%",
    )

    return rx.box(
        rx.vstack(
            header,
            metrics,
            spacing="3", align="stretch", width="100%",
        ),
        padding="14px 16px",
        border_radius="10px",
        background="var(--gray-2)",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )


def _pool_performances_section() -> rx.Component:
    inner = rx.cond(
        DashboardState.pool_performances.length() > 0,
        rx.vstack(
            rx.foreach(
                DashboardState.filtered_pool_performances,
                _pool_perf_row,
            ),
            spacing="2", align="stretch", width="100%",
        ),
        rx.text(
            AuthState.t["dashboard_pool_perf_empty"],
            size="2", color="var(--gray-10)",
        ),
    )
    body = rx.cond(DashboardState.pool_perf_loading, _section_spinner(), inner)
    return _section_card(
        AuthState.t["dashboard_pool_perf_title"],
        "trending-up",
        body,
    )


# ── 報酬 popover (プール実績カード内に埋め込み) ───

def _reward_recent_row(r: rx.Var) -> rx.Component:
    """popover 内: エポック別 1 行 (合算)。通常委任者用。"""
    return rx.hstack(
        rx.text("Epoch", size="1", color="var(--gray-10)"),
        rx.text(r["epoch_no"], size="1", weight="medium", color="var(--gray-12)"),
        rx.spacer(),
        rx.text(r["amount_ada"], size="2", weight="bold", color="var(--green-11)"),
        rx.text("ADA", size="1", color="var(--gray-10)"),
        spacing="2", align="baseline", width="100%",
        padding="4px 8px",
        border_radius="6px",
        background="var(--gray-2)",
    )


def _reward_recent_row_spo(r: rx.Var) -> rx.Component:
    """popover 内: エポック別 1 行 (SPO 用 / leader 報酬のみ表示)。"""
    return rx.hstack(
        rx.icon("crown", size=10, color="var(--amber-11)"),
        rx.text("Epoch", size="1", color="var(--gray-10)"),
        rx.text(r["epoch_no"], size="1", weight="medium", color="var(--gray-12)"),
        rx.spacer(),
        rx.text(r["leader_ada"], size="2", weight="bold", color="var(--amber-11)"),
        rx.text("ADA", size="1", color="var(--gray-10)"),
        spacing="2", align="baseline", width="100%",
        padding="4px 8px",
        border_radius="6px",
        background="var(--gray-2)",
    )


def _rewards_popover(p: rx.Var) -> rx.Component:
    """委任先プール実績カード右上に置く「報酬」popover ボタン。

    通知 OFF (= キャッシュなし) の場合は CTA、それ以外は累積 + 直近 5ep を表示。
    SPO の場合は member / leader 分離表示。
    """
    addr = p["address"]
    is_spo = p["is_spo"] != ""
    is_missing = DashboardState.rewards_missing_addresses.contains(addr)
    rewards = DashboardState.rewards_by_address[addr]
    total_ada = DashboardState.total_rewards_by_address[addr]
    total_leader = DashboardState.total_rewards_leader_by_address[addr]

    trigger = rx.popover.trigger(
        rx.el.button(
            rx.icon("coins", size=12, color="var(--amber-11)"),
            rx.text(
                AuthState.t["dashboard_rewards_btn"],
                size="1", color="var(--amber-12)",
                style={"whiteSpace": "nowrap"},
            ),
            style={
                "display": "inline-flex",
                "alignItems": "center",
                "gap": "4px",
                "padding": "4px 10px",
                "border": f"1px solid {rx.color('amber', 7)}",
                "borderRadius": "999px",
                "background": "transparent",
                "cursor": "pointer",
                "transition": "background 0.15s",
            },
            _hover={"background": rx.color("amber", 3)},
        ),
    )

    missing_content = rx.vstack(
        rx.hstack(
            rx.icon("info", size=14, color="var(--amber-11)"),
            rx.text(
                AuthState.t["dashboard_rewards_missing_note"],
                size="2", color="var(--gray-11)", line_height="1.5",
            ),
            spacing="2", align="start",
        ),
        rx.link(
            rx.button(
                rx.icon("bell", size=12),
                rx.text(AuthState.t["dashboard_rewards_enable_notify"], size="2"),
                color_scheme="amber", size="2", cursor="pointer",
            ),
            href="/mypage?tab=notification", underline="none",
        ),
        spacing="3", align="stretch", width="100%",
    )

    # 累積表示: SPO は leader 累積のみ、通常委任者は合算
    total_block = rx.cond(
        is_spo,
        rx.hstack(
            rx.icon("crown", size=14, color="var(--amber-11)"),
            rx.text(AuthState.t["dashboard_rewards_leader"], size="1", color="var(--amber-11)"),
            rx.spacer(),
            rx.text(total_leader, size="3", weight="bold", color="var(--amber-11)"),
            rx.text("ADA", size="1", color="var(--gray-10)"),
            spacing="2", align="baseline", width="100%",
        ),
        rx.hstack(
            rx.text(AuthState.t["dashboard_rewards_total"], size="1", color="var(--gray-10)"),
            rx.spacer(),
            rx.text(total_ada, size="3", weight="bold", color="var(--gray-12)"),
            rx.text("ADA", size="1", color="var(--gray-10)"),
            spacing="2", align="baseline", width="100%",
        ),
    )

    recent_block = rx.cond(
        rewards.length() > 0,
        rx.cond(
            is_spo,
            rx.vstack(
                rx.foreach(rewards.to(list[dict[str, str]]), _reward_recent_row_spo),
                spacing="2", align="stretch", width="100%",
            ),
            rx.vstack(
                rx.foreach(rewards.to(list[dict[str, str]]), _reward_recent_row),
                spacing="1", align="stretch", width="100%",
            ),
        ),
        rx.text(
            AuthState.t["dashboard_rewards_empty_short"],
            size="1", color="var(--gray-9)", style={"fontStyle": "italic"},
        ),
    )

    data_content = rx.vstack(
        total_block,
        rx.divider(),
        rx.text(AuthState.t["dashboard_rewards_recent"], size="1", color="var(--gray-10)", weight="medium"),
        recent_block,
        spacing="3", align="stretch", width="100%",
    )

    fetching_content = rx.hstack(
        rx.spinner(size="2"),
        rx.text(
            AuthState.t["dashboard_rewards_fetching"],
            size="2", color="var(--gray-11)",
        ),
        spacing="2", align="center", padding_y="6px",
    )

    return rx.popover.root(
        trigger,
        rx.popover.content(
            rx.cond(
                AuthState.rewards_backfilling,
                fetching_content,
                rx.cond(is_missing, missing_content, data_content),
            ),
            min_width="280px",
            max_width="360px",
            padding="14px 16px",
            side="bottom",
            align="end",
        ),
    )


# ── 未投票 GA (Phase B) ────────────────────────

def _ga_link_row(g: rx.Var) -> rx.Component:
    """未投票 GA 1 件: 締切日付 + タイトル + DRep 投票率バー。"""
    title = rx.cond(
        AuthState.language == "ja",
        rx.cond(g["title_ja"] != "", g["title_ja"], g["title"]),
        g["title"],
    )
    deadline_badge = rx.cond(
        g["expiration_date"] != "",
        rx.badge(
            AuthState.t["dashboard_ga_deadline_label"],
            g["expiration_date"],
            color_scheme="amber", variant="soft", size="1",
            style={"flexShrink": "0", "whiteSpace": "nowrap"},
        ),
        rx.fragment(),
    )
    return rx.box(
        rx.vstack(
            rx.link(
                rx.hstack(
                    deadline_badge,
                    rx.text(
                        rx.cond(title != "", title, g["proposal_id"][:24] + "…"),
                        size="2", weight="medium", color="var(--gray-12)",
                        style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                        flex="1", min_width="0",
                    ),
                    spacing="2", align="center", width="100%",
                ),
                href="/governance/" + g["proposal_id"],
                underline="hover",
                color="inherit",
                width="100%",
            ),
            _vote_progress_bar(
                "DRep",
                g["drep_yes_pct"],
                g["drep_threshold_pct"],
                g["drep_applicable"],
            ),
            spacing="2", align="stretch", width="100%",
        ),
        padding="10px 12px",
        border_radius="8px",
        background="var(--gray-2)",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )


def _ga_link_row_spo(g: rx.Var) -> rx.Component:
    """SPO 未投票 GA 1 件: 締切日付 + タイトル + SPO 投票率バー。"""
    title = rx.cond(
        AuthState.language == "ja",
        rx.cond(g["title_ja"] != "", g["title_ja"], g["title"]),
        g["title"],
    )
    deadline_badge = rx.cond(
        g["expiration_date"] != "",
        rx.badge(
            AuthState.t["dashboard_ga_deadline_label"],
            g["expiration_date"],
            color_scheme="amber", variant="soft", size="1",
            style={"flexShrink": "0", "whiteSpace": "nowrap"},
        ),
        rx.fragment(),
    )
    return rx.box(
        rx.vstack(
            rx.link(
                rx.hstack(
                    deadline_badge,
                    rx.text(
                        rx.cond(title != "", title, g["proposal_id"][:24] + "…"),
                        size="2", weight="medium", color="var(--gray-12)",
                        style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                        flex="1", min_width="0",
                    ),
                    spacing="2", align="center", width="100%",
                ),
                href="/governance/" + g["proposal_id"],
                underline="hover",
                color="inherit",
                width="100%",
            ),
            _vote_progress_bar(
                "SPO",
                g["pool_yes_pct"],
                g["pool_threshold_pct"],
                g["pool_applicable"],
            ),
            spacing="2", align="stretch", width="100%",
        ),
        padding="10px 12px",
        border_radius="8px",
        background="var(--gray-2)",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )


def _unvoted_gas_section() -> rx.Component:
    """「あなたの未投票 GA」セクション。DRep または SPO のときだけ表示する。"""
    self_block = rx.cond(
        DashboardState.unvoted_gas_self.length() > 0,
        rx.vstack(
            rx.text(
                AuthState.t["dashboard_unvoted_self_label"],
                size="1", color="var(--gray-10)", weight="medium",
            ),
            rx.foreach(
                DashboardState.unvoted_gas_self.to(list[dict[str, str]]),
                _ga_link_row,
            ),
            spacing="2", align="stretch", width="100%",
        ),
        rx.fragment(),
    )
    spo_block = rx.cond(
        DashboardState.unvoted_gas_spo.length() > 0,
        rx.vstack(
            rx.hstack(
                rx.icon("crown", size=12, color="var(--amber-11)"),
                rx.text(
                    AuthState.t["dashboard_unvoted_spo_label"],
                    size="1", color="var(--amber-11)", weight="medium",
                ),
                spacing="1", align="center",
            ),
            rx.foreach(
                DashboardState.unvoted_gas_spo.to(list[dict[str, str]]),
                _ga_link_row_spo,
            ),
            spacing="2", align="stretch", width="100%",
        ),
        rx.fragment(),
    )
    inner = rx.cond(
        (DashboardState.unvoted_gas_self.length() == 0)
        & (DashboardState.unvoted_gas_spo.length() == 0),
        rx.text(
            AuthState.t["dashboard_unvoted_empty"],
            size="2", color="var(--gray-10)",
        ),
        rx.vstack(
            self_block,
            spo_block,
            spacing="3", align="stretch", width="100%",
        ),
    )
    body = rx.cond(DashboardState.unvoted_gas_loading, _section_spinner(), inner)
    # DRep でも SPO でもないユーザーにはセクション自体を表示しない
    return rx.cond(
        DashboardState.is_drep_or_spo,
        _section_card(
            AuthState.t["dashboard_unvoted_title"],
            "circle-alert",
            body,
        ),
        rx.fragment(),
    )


# ── 締切が近い GA (Phase B) ────────────────────

def _vote_progress_bar(
    label,
    yes_pct: rx.Var,
    threshold_pct: rx.Var,
    applicable: rx.Var,
) -> rx.Component:
    """投票率の横バー (賛成率の塗りつぶし + 閾値マーカー)。

    - 閾値の数字はマーカー直近 (バー上方) に配置することで視線移動を減らす
    - applicable == "no" の場合はグレーアウト (該当しない voter group)
    - threshold_pct が空文字なら閾値マーカー / 数字とも非表示
    """
    not_applicable = applicable == "no"
    fill_color = rx.cond(not_applicable, "var(--gray-6)", "var(--blue-9)")
    return rx.vstack(
        # 上ラベル行: voter group 名 + 現在の賛成率
        rx.hstack(
            rx.text(
                label,
                size="1", weight="medium",
                color=rx.cond(not_applicable, "var(--gray-9)", "var(--gray-11)"),
                style={"minWidth": "40px"},
            ),
            rx.spacer(),
            rx.text(
                yes_pct, "%",
                size="1", weight="medium",
                color=rx.cond(not_applicable, "var(--gray-9)", "var(--gray-12)"),
            ),
            spacing="1", align="baseline", width="100%",
        ),
        # バー本体 (上に閾値の数字を absolute で重ねる)
        rx.box(
            # 閾値ラベル (マーカー位置の真上に中央揃えで配置)
            rx.cond(
                threshold_pct != "",
                rx.text(
                    threshold_pct, "%",
                    color="var(--gray-11)",
                    position="absolute",
                    top="-14px",
                    left=threshold_pct + "%",
                    style={
                        "transform": "translateX(-50%)",
                        "whiteSpace": "nowrap",
                        "fontSize": "10px",
                        "fontWeight": "500",
                        "lineHeight": "1",
                        "pointerEvents": "none",
                    },
                ),
                rx.fragment(),
            ),
            # 背景バー
            rx.box(
                width="100%", height="6px",
                background="var(--gray-3)",
                border_radius="3px",
            ),
            # 賛成率の塗りつぶし
            rx.box(
                width=yes_pct + "%",
                height="6px",
                background=fill_color,
                border_radius="3px",
                position="absolute",
                top="0", left="0",
                style={"transition": "width 0.3s ease"},
            ),
            # 閾値マーカー (縦線)
            rx.cond(
                threshold_pct != "",
                rx.box(
                    width="2px", height="10px",
                    background="var(--gray-12)",
                    position="absolute",
                    top="-2px",
                    left=threshold_pct + "%",
                    border_radius="1px",
                ),
                rx.fragment(),
            ),
            position="relative",
            width="100%",
            height="6px",
            # 上部の閾値数字の分の余白 (絶対配置のため通常 flow に乗らない)
            margin_top="14px",
        ),
        spacing="1", align="stretch", width="100%",
    )




# ── ダッシュボード本体 ──────────────────────────

def _filter_chip(c: rx.Var) -> rx.Component:
    """アドレスフィルタチップ 1 件 (active 切替対応)。"""
    is_active = c["active"] != ""
    return rx.el.button(
        rx.text(c["label"], size="1", weight="medium"),
        on_click=DashboardState.set_filter_address(c["value"]),
        style={
            "padding": "4px 12px",
            "borderRadius": "999px",
            "fontSize": "12px",
            "cursor": "pointer",
            "transition": "background 0.15s, color 0.15s, border-color 0.15s",
            "whiteSpace": "nowrap",
            "border": "1px solid transparent",
        },
        background=rx.cond(is_active, rx.color("amber", 9), rx.color("gray", 3)),
        color=rx.cond(is_active, "white", "var(--gray-11)"),
        border_color=rx.cond(is_active, rx.color("amber", 8), "transparent"),
        _hover=rx.cond(
            is_active,
            {},
            {"background": rx.color("gray", 4), "color": "var(--gray-12)"},
        ),
    )


def _address_filter_section() -> rx.Component:
    """アドレスフィルタチップ。登録 4 件以上のときだけ表示。"""
    return rx.cond(
        DashboardState.delegations.length() >= 4,
        rx.box(
            rx.hstack(
                rx.icon("filter", size=14, color="var(--gray-10)"),
                rx.foreach(DashboardState.filter_chips, _filter_chip),
                spacing="2", align="center", wrap="wrap", width="100%",
            ),
            padding="8px 4px",
            width="100%",
        ),
        rx.fragment(),
    )


def dashboard() -> rx.Component:
    """ログインユーザー向けトップダッシュボード本体（ヒーローを除く）。

    ヒーロー (welcome + username) は呼び出し側 (マイページ) が
    タブ外のヘッダーとして表示するため、ここでは含めない。

    レイアウト自体は即座に表示し、各セクションが個別に
    ロード中スピナー → データ表示 へ切り替わる UX にしている。
    """
    return rx.box(
        rx.vstack(
            _quick_actions_section(),
            _epoch_treasury_section(),
            _address_filter_section(),
            _delegations_section(),
            _pool_performances_section(),
            _drep_votes_section(),
            _unvoted_gas_section(),
            _favorites_section(),
            _notification_summary_section(),
            spacing="4",
            width="100%",
        ),
        width="100%",
    )
