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
            rx.icon("vote", size=13, color="var(--gray-10)"),
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
                rx.icon("vote", size=13, color="var(--gray-10)"),
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
                rx.icon("vote", size=13, color="var(--gray-9)"),
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
        rx.vstack(
            rx.hstack(
                rx.icon("wallet", size=14, color="var(--amber-11)"),
                rx.text(d["nickname"], size="2", weight="bold", color="var(--gray-12)"),
                verified_badge,
                spacing="2", align="center", wrap="wrap", width="100%",
            ),
            rx.hstack(
                pool_label,
                rx.box(width="1px", height="14px", background="var(--gray-5)", margin_x="6px", flex_shrink="0"),
                drep_label,
                spacing="2", align="center", wrap="wrap", width="100%",
            ),
            spacing="2", align="stretch", width="100%",
        ),
        padding="12px 14px",
        border_radius="8px",
        background="var(--gray-2)",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )


def _delegations_section() -> rx.Component:
    body = rx.cond(
        DashboardState.delegations.length() > 0,
        rx.vstack(
            rx.foreach(
                DashboardState.delegations.to(list[dict[str, str]]),
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

def _drep_vote_row(v: rx.Var) -> rx.Component:
    vote_color = rx.match(
        v["vote"],
        ("Yes", "var(--blue-11)"),
        ("No", "var(--orange-11)"),
        ("Abstain", "var(--gray-11)"),
        "var(--gray-11)",
    )
    return rx.link(
        rx.hstack(
            rx.badge(v["vote"], variant="soft", color_scheme="gray", size="1", style={"color": vote_color}),
            rx.text(
                rx.cond(v["proposal_title"] != "", v["proposal_title"], v["proposal_id"][:24] + "…"),
                size="2", color="var(--gray-12)",
                style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                flex="1", min_width="0",
            ),
            spacing="2", align="center", width="100%",
        ),
        href="/governance/" + v["proposal_id"],
        underline="hover",
        color="inherit",
        width="100%",
    )


def _drep_votes_section() -> rx.Component:
    body = rx.cond(
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
    return _section_card(
        AuthState.t["dashboard_drep_votes_title"],
        "vote",
        body,
    )


def _drep_votes_for_delegation(d: rx.Var) -> rx.Component:
    """この stake_address の DRep の直近投票を表示する。"""
    votes = DashboardState.drep_recent_votes[d["drep_id"]]
    return rx.cond(
        (d["drep_id"] != "") & (d["drep_id"] != "always_abstain"),
        rx.vstack(
            rx.hstack(
                rx.text(d["nickname"], size="1", color="var(--gray-10)", weight="medium"),
                rx.text("→", size="1", color="var(--gray-9)"),
                rx.text(
                    rx.cond(d["drep_name"] != "", d["drep_name"], d["drep_id"][:14] + "…"),
                    size="2", weight="medium", color="var(--gray-12)",
                ),
                spacing="1", align="center", wrap="wrap",
            ),
            rx.cond(
                votes.length() > 0,
                rx.vstack(
                    rx.foreach(votes.to(list[dict[str, str]]), _drep_vote_row),
                    spacing="1", align="stretch", width="100%",
                ),
                rx.text(
                    AuthState.t["dashboard_drep_no_votes"],
                    size="1", color="var(--gray-9)", style={"fontStyle": "italic"},
                ),
            ),
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

    return _section_card(
        AuthState.t["dashboard_favorites_title"],
        "star",
        rx.grid(
            catalyst_block,
            governance_block,
            columns={"base": "1", "md": "2"},
            spacing="4",
            width="100%",
        ),
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

    return _section_card(
        AuthState.t["dashboard_notifications_title"],
        "bell",
        rx.hstack(
            _channel_chip("LINE", "line", "message-square"),
            _channel_chip("Email", "email", "mail"),
            _channel_chip("Telegram", "telegram", "send"),
            spacing="2", align="center", wrap="wrap",
        ),
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
            rx.text(DashboardState.current_epoch_str, size="6", weight="bold", color="var(--gray-12)"),
            rx.text("ep", size="2", color="var(--gray-10)"),
            spacing="1", align="baseline",
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
    return rx.box(
        rx.grid(
            epoch_box,
            treasury_box,
            columns={"base": "1", "sm": "2"},
            spacing="4",
            width="100%",
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

def _pool_perf_row(p: rx.Var) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.icon("server", size=14, color="var(--amber-11)", flex_shrink="0"),
            rx.vstack(
                rx.text(p["nickname"], size="1", color="var(--gray-10)"),
                rx.text(
                    rx.cond(p["pool_ticker"] != "", p["pool_ticker"], p["pool_name"]),
                    size="2", weight="bold", color="var(--gray-12)",
                ),
                spacing="0", align_items="start",
            ),
            rx.spacer(),
            rx.vstack(
                rx.text(AuthState.t["dashboard_pool_blocks_5ep"], size="1", color="var(--gray-10)"),
                rx.text(p["blocks_5ep_total"], size="3", weight="bold", color="var(--gray-12)"),
                spacing="0", align_items="end",
            ),
            rx.vstack(
                rx.text(AuthState.t["dashboard_pool_apy_avg"], size="1", color="var(--gray-10)"),
                rx.text(p["apy_avg_pct"], "%", size="3", weight="bold", color="var(--blue-11)"),
                spacing="0", align_items="end",
            ),
            spacing="4", align="center", width="100%", wrap="wrap",
        ),
        padding="12px 14px",
        border_radius="8px",
        background="var(--gray-2)",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )


def _pool_performances_section() -> rx.Component:
    body = rx.cond(
        DashboardState.pool_performances.length() > 0,
        rx.vstack(
            rx.foreach(
                DashboardState.pool_performances.to(list[dict[str, str]]),
                _pool_perf_row,
            ),
            spacing="2", align="stretch", width="100%",
        ),
        rx.text(
            AuthState.t["dashboard_pool_perf_empty"],
            size="2", color="var(--gray-10)",
        ),
    )
    return _section_card(
        AuthState.t["dashboard_pool_perf_title"],
        "trending-up",
        body,
    )


# ── 報酬 (Phase B) ─────────────────────────────

def _reward_total_row(t: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("wallet", size=12, color="var(--amber-11)"),
        rx.text(t["nickname"], size="1", color="var(--gray-10)"),
        rx.spacer(),
        rx.text(t["total_ada"], size="2", weight="bold", color="var(--gray-12)"),
        rx.text("ADA", size="1", color="var(--gray-10)"),
        spacing="2", align="baseline", width="100%",
        padding="6px 10px",
        border_radius="6px",
        background="var(--gray-2)",
    )


def _reward_recent_row(r: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.text("ep", size="1", color="var(--gray-10)"),
        rx.text(r["epoch_no"], size="1", weight="medium", color="var(--gray-12)"),
        rx.text(r["nickname"], size="1", color="var(--gray-10)"),
        rx.spacer(),
        rx.text(r["amount_ada"], size="2", weight="bold", color="var(--green-11)"),
        rx.text("ADA", size="1", color="var(--gray-10)"),
        spacing="2", align="baseline", width="100%",
        padding="6px 10px",
        border_radius="6px",
        background="var(--gray-2)",
    )


def _rewards_section() -> rx.Component:
    totals_block = rx.cond(
        DashboardState.total_rewards.length() > 0,
        rx.vstack(
            rx.text(AuthState.t["dashboard_rewards_total"], size="1", color="var(--gray-10)", weight="medium"),
            rx.foreach(
                DashboardState.total_rewards.to(list[dict[str, str]]),
                _reward_total_row,
            ),
            spacing="1", align="stretch", width="100%",
        ),
        rx.fragment(),
    )

    recent_block = rx.cond(
        DashboardState.recent_rewards.length() > 0,
        rx.vstack(
            rx.text(AuthState.t["dashboard_rewards_recent"], size="1", color="var(--gray-10)", weight="medium"),
            rx.foreach(
                DashboardState.recent_rewards.to(list[dict[str, str]]),
                _reward_recent_row,
            ),
            spacing="1", align="stretch", width="100%",
        ),
        rx.fragment(),
    )

    missing_cta = rx.cond(
        DashboardState.rewards_missing_addresses.length() > 0,
        rx.hstack(
            rx.icon("info", size=14, color="var(--amber-11)"),
            rx.text(
                AuthState.t["dashboard_rewards_missing_note"],
                size="1", color="var(--gray-10)", line_height="1.5",
            ),
            rx.spacer(),
            rx.link(
                rx.button(
                    rx.icon("bell", size=12),
                    rx.text(AuthState.t["dashboard_rewards_enable_notify"], size="1"),
                    variant="soft", color_scheme="amber", size="1", cursor="pointer",
                ),
                href="/mypage?tab=notification", underline="none",
            ),
            spacing="2", align="center", width="100%",
            padding="10px 12px",
            border_radius="8px",
            background=rx.color("amber", 2),
            border=f"1px solid {rx.color('amber', 5)}",
        ),
        rx.fragment(),
    )

    body = rx.vstack(
        rx.cond(
            (DashboardState.total_rewards.length() == 0)
            & (DashboardState.recent_rewards.length() == 0),
            rx.text(
                AuthState.t["dashboard_rewards_empty"],
                size="2", color="var(--gray-10)",
            ),
            rx.grid(
                totals_block,
                recent_block,
                columns={"base": "1", "md": "2"},
                spacing="4",
                width="100%",
            ),
        ),
        missing_cta,
        spacing="3", align="stretch", width="100%",
    )
    return _section_card(
        AuthState.t["dashboard_rewards_title"],
        "coins",
        body,
    )


# ── 未投票 GA (Phase B) ────────────────────────

def _ga_link_row(g: rx.Var) -> rx.Component:
    title = rx.cond(
        AuthState.language == "ja",
        rx.cond(g["title_ja"] != "", g["title_ja"], g["title"]),
        g["title"],
    )
    epochs_left_label = rx.cond(
        g["epochs_left"] != "",
        rx.badge(
            AuthState.t["dashboard_ga_left_prefix"], " ", g["epochs_left"], " ep",
            color_scheme="amber", variant="soft", size="1",
        ),
        rx.fragment(),
    )
    return rx.link(
        rx.hstack(
            rx.icon("file-text", size=12, color="var(--gray-10)", flex_shrink="0"),
            rx.text(
                rx.cond(title != "", title, g["proposal_id"][:24] + "…"),
                size="2", color="var(--gray-12)",
                style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                flex="1", min_width="0",
            ),
            epochs_left_label,
            spacing="2", align="center", width="100%",
        ),
        href="/governance/" + g["proposal_id"],
        underline="hover",
        color="inherit",
        width="100%",
    )


def _unvoted_gas_section() -> rx.Component:
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
            spacing="1", align="stretch", width="100%",
        ),
        rx.fragment(),
    )
    delegated_block = rx.cond(
        DashboardState.unvoted_gas_delegated.length() > 0,
        rx.vstack(
            rx.text(
                AuthState.t["dashboard_unvoted_delegated_label"],
                size="1", color="var(--gray-10)", weight="medium",
            ),
            rx.foreach(
                DashboardState.unvoted_gas_delegated.to(list[dict[str, str]]),
                _ga_link_row,
            ),
            spacing="1", align="stretch", width="100%",
        ),
        rx.fragment(),
    )
    body = rx.cond(
        (DashboardState.unvoted_gas_self.length() == 0)
        & (DashboardState.unvoted_gas_delegated.length() == 0),
        rx.text(
            AuthState.t["dashboard_unvoted_empty"],
            size="2", color="var(--gray-10)",
        ),
        rx.vstack(
            self_block,
            delegated_block,
            spacing="3", align="stretch", width="100%",
        ),
    )
    return _section_card(
        AuthState.t["dashboard_unvoted_title"],
        "circle-alert",
        body,
    )


# ── 締切が近い GA (Phase B) ────────────────────

def _expiring_gas_section() -> rx.Component:
    body = rx.cond(
        DashboardState.expiring_gas.length() > 0,
        rx.vstack(
            rx.foreach(
                DashboardState.expiring_gas.to(list[dict[str, str]]),
                _ga_link_row,
            ),
            spacing="1", align="stretch", width="100%",
        ),
        rx.text(
            AuthState.t["dashboard_expiring_empty"],
            size="2", color="var(--gray-10)",
        ),
    )
    return _section_card(
        AuthState.t["dashboard_expiring_title"],
        "hourglass",
        body,
    )


# ── ダッシュボード本体 ──────────────────────────

def dashboard() -> rx.Component:
    """ログインユーザー向けトップダッシュボード本体（ヒーローを除く）。

    ヒーロー (welcome + username) は呼び出し側 (マイページ) が
    タブ外のヘッダーとして表示するため、ここでは含めない。
    """
    return rx.cond(
        DashboardState.load,
        rx.box(
            rx.vstack(
                _quick_actions_section(),
                _epoch_treasury_section(),
                _delegations_section(),
                _pool_performances_section(),
                _rewards_section(),
                _unvoted_gas_section(),
                _expiring_gas_section(),
                _drep_votes_section(),
                _favorites_section(),
                _notification_summary_section(),
                spacing="4",
                width="100%",
            ),
            width="100%",
        ),
        rx.flex(
            rx.spinner(size="3"),
            justify="center", align="center",
            width="100%", padding_y="40px",
        ),
    )
