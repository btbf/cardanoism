"""
mypage.py
マイページ (/mypage) - 5タブ構成
  1. ダッシュボード（自分の Cardano 参加状況）
  2. お気に入り（カタリスト提案）
  3. プロフィール編集
  4. ステークアドレス管理
  5. 通知管理
"""
import reflex as rx
from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.login_modal import login_modal
from cardanoism.components.dashboard import dashboard
from cardanoism.components.wallet_button import (
    wallet_connect_pill,
    wallet_register_picker_menu,
)
from cardanoism.backend.wallet_state import WalletState
from cardanoism.backend.auth_db import (
    POOL_NOTIFICATION_EVENT_TYPES,
    DELEGATOR_NOTIFICATION_EVENT_TYPES,
    DREP_ONLY_NOTIFICATION_EVENT_TYPES,
)

ACCENT = "#ffcf00"
ACCENT_DARK = "#c7a300"

GENERAL_EVENTS = [
    "epoch_start",
    "treasury_withdrawal_enacted",
]


# ============================================================
# タブ1: お気に入り
# ============================================================

_GA_TYPE_LABELS = {
    "ParameterChange":    "プロトコル変更",
    "TreasuryWithdrawals": "国庫引き出し",
    "HardForkInitiation": "ハードフォーク",
    "InfoAction":         "情報提案",
    "NewCommittee":       "委員会変更",
    "NewConstitution":    "新憲法",
    "NoConfidence":       "不信任",
}


def ga_favorite_card(fav: rx.Var[dict]) -> rx.Component:
    """ガバナンスお気に入りカード。"""
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.link(
                    rx.text(
                        rx.cond(fav["title_ja"], fav["title_ja"], rx.cond(fav["title"], fav["title"], "（タイトルなし）")),
                        size="4",
                        weight="medium",
                        line_height="1.4",
                    ),
                    href="/governance/" + fav["proposal_uuid"].to(str),
                    underline="hover",
                ),
                rx.hstack(
                    rx.badge(fav["proposal_type"], variant="soft", color_scheme="amber", size="1"),
                    rx.text("Epoch ", fav["proposed_epoch"].to(str), size="2", color="var(--gray-9)"),
                    spacing="2",
                    wrap="wrap",
                ),
                spacing="1",
                align_items="start",
                width="100%",
            ),
            rx.icon_button(
                rx.icon("trash-2", size=14),
                variant="ghost",
                color_scheme="red",
                size="1",
                cursor="pointer",
                on_click=AuthState.remove_ga_favorite_handler(fav["proposal_uuid"].to(str)),
            ),
            align="start",
            width="100%",
        ),
        padding="14px 16px",
        border_radius="10px",
        border=f"1px solid {rx.color('gray', 4)}",
        background=rx.color_mode_cond("white", "rgba(15,15,25,0.85)"),
        width="100%",
    )


def favorite_card(fav: rx.Var[dict]) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.link(
                    rx.text(
                        rx.cond(fav["title_ja"], fav["title_ja"], fav["title"]),
                        size="4",
                        weight="medium",
                        line_height="1.4",
                    ),
                    href="/catalyst/proposals/" + fav["proposal_uuid"].to(str),
                    underline="hover",
                ),
                rx.hstack(
                    rx.badge(fav["fund_label"], variant="soft", color_scheme="amber", size="1"),
                    rx.badge(fav["funding_status"], variant="soft", size="1"),
                    rx.text(
                        fav["currency_symbol"],
                        fav["amount_requested"].to(str),
                        size="2",
                        color="var(--gray-9)",
                    ),
                    spacing="2",
                    wrap="wrap",
                ),
                spacing="1",
                align_items="start",
                width="100%",
            ),
            rx.icon_button(
                rx.icon("trash-2", size=14),
                variant="ghost",
                color_scheme="red",
                size="1",
                cursor="pointer",
                on_click=AuthState.remove_favorite_handler(fav["proposal_uuid"].to(str)),
            ),
            align="start",
            width="100%",
        ),
        padding="14px 16px",
        border_radius="10px",
        border=f"1px solid {rx.color('gray', 4)}",
        background=rx.color_mode_cond("white", "rgba(15,15,25,0.85)"),
        width="100%",
    )


def _fav_pagination(page_var, total_var, prev_handler, next_handler) -> rx.Component:
    return rx.hstack(
        rx.icon_button(
            rx.icon("chevron-left", size=16),
            variant="soft",
            disabled=page_var <= 1,
            on_click=prev_handler,
            cursor="pointer",
        ),
        rx.text(page_var.to(str), " / ", total_var.to(str), size="3", color="var(--gray-10)"),
        rx.icon_button(
            rx.icon("chevron-right", size=16),
            variant="soft",
            disabled=page_var >= total_var,
            on_click=next_handler,
            cursor="pointer",
        ),
        justify="center",
        align="center",
        spacing="3",
        width="100%",
        padding_top="8px",
    )


def _catalyst_list() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.select.root(
                rx.select.trigger(placeholder=AuthState.t["filter_fund_placeholder"]),
                rx.select.content(
                    rx.select.item(AuthState.t["filter_all"], value="all"),
                    rx.select.item("Fund 12", value="Fund 12"),
                    rx.select.item("Fund 13", value="Fund 13"),
                    rx.select.item("Fund 14", value="Fund 14"),
                ),
                size="2",
                value=AuthState.favorites_fund_filter,
                on_change=AuthState.set_favorites_fund_filter,
            ),
            rx.select.root(
                rx.select.trigger(placeholder=AuthState.t["filter_status_placeholder"]),
                rx.select.content(
                    rx.select.item(AuthState.t["filter_all"], value="all"),
                    rx.select.item(AuthState.t["status_funded"], value="funded"),
                    rx.select.item(AuthState.t["status_not_funded"], value="not_funded"),
                    rx.select.item(AuthState.t["status_over_budget"], value="over_budget"),
                ),
                size="2",
                value=AuthState.favorites_status_filter,
                on_change=AuthState.set_favorites_status_filter,
            ),
            rx.select.root(
                rx.select.trigger(),
                rx.select.content(
                    rx.select.item(AuthState.t["sort_amount_desc"], value="amount_desc"),
                    rx.select.item(AuthState.t["sort_amount_asc"], value="amount_asc"),
                ),
                size="2",
                value=AuthState.favorites_sort,
                on_change=AuthState.set_favorites_sort,
            ),
            wrap="wrap",
            spacing="2",
        ),
        rx.cond(
            AuthState.is_favorites_empty,
            rx.center(
                rx.vstack(
                    rx.icon("bookmark", size=36, color="var(--gray-6)"),
                    rx.text(AuthState.t["favorites_empty"], size="4", color="var(--gray-8)"),
                    spacing="3",
                    align="center",
                ),
                padding_y="40px",
            ),
            rx.vstack(
                rx.foreach(AuthState.filtered_favorites, favorite_card),
                _fav_pagination(
                    AuthState.favorites_page,
                    AuthState.favorites_total_pages,
                    AuthState.favorites_prev_page,
                    AuthState.favorites_next_page,
                ),
                spacing="2",
                width="100%",
            ),
        ),
        spacing="3",
        width="100%",
    )


def _governance_list() -> rx.Component:
    return rx.cond(
        AuthState.is_ga_favorites_empty,
        rx.center(
            rx.vstack(
                rx.icon("bookmark", size=36, color="var(--gray-6)"),
                rx.text("ガバナンスのお気に入りはまだありません", size="4", color="var(--gray-8)"),
                spacing="3",
                align="center",
            ),
            padding_y="40px",
        ),
        rx.vstack(
            rx.foreach(AuthState.filtered_ga_favorites, ga_favorite_card),
            _fav_pagination(
                AuthState.ga_favorites_page,
                AuthState.ga_favorites_total_pages,
                AuthState.ga_favorites_prev_page,
                AuthState.ga_favorites_next_page,
            ),
            spacing="2",
            width="100%",
        ),
    )


def drep_favorite_card(fav: rx.Var[dict]) -> rx.Component:
    """DRep お気に入りカード。"""
    drep_id = fav["drep_id"].to(str)
    avatar = rx.cond(
        fav["image_url"] != "",
        rx.image(
            src=fav["image_url"],
            width="40px", height="40px", border_radius="50%",
            style={"objectFit": "cover"},
            flex_shrink="0",
        ),
        rx.center(
            rx.icon("user-round", size=20, color="var(--gray-9)"),
            width="40px", height="40px",
            border_radius="50%",
            background="var(--gray-4)",
            flex_shrink="0",
        ),
    )
    status = rx.cond(
        fav["active"] != "",
        rx.badge(AuthState.t["drep_status_active"], color_scheme="green", variant="soft", size="1"),
        rx.badge(AuthState.t["drep_status_inactive"], color_scheme="gray", variant="soft", size="1"),
    )
    name = rx.cond(
        fav["given_name"] != "",
        rx.text(fav["given_name"], size="4", weight="medium"),
        rx.text(AuthState.t["drep_no_name"], size="4", weight="medium", color="var(--gray-10)"),
    )
    return rx.box(
        rx.hstack(
            avatar,
            rx.vstack(
                rx.link(name, href="/drep/" + drep_id, underline="hover", color="inherit"),
                rx.hstack(status, spacing="2"),
                spacing="1", align_items="start", flex="1", min_width="0",
            ),
            rx.icon_button(
                rx.icon("trash-2", size=14),
                variant="ghost",
                color_scheme="red",
                size="1",
                cursor="pointer",
                on_click=AuthState.remove_drep_favorite_handler(drep_id),
            ),
            align="center", width="100%",
        ),
        padding="14px 16px",
        border_radius="10px",
        border=f"1px solid {rx.color('gray', 4)}",
        background=rx.color_mode_cond("white", "rgba(15,15,25,0.85)"),
        width="100%",
    )


def pool_favorite_card(fav: rx.Var[dict]) -> rx.Component:
    """ステークプールお気に入りカード。"""
    pool_id = fav["pool_id"].to(str)
    icon_src = rx.cond(fav["pool_icon_url"] != "", fav["pool_icon_url"], fav["pool_logo_url"])
    icon = rx.cond(
        icon_src != "",
        rx.image(
            src=icon_src,
            width="40px", height="40px", border_radius="8px",
            style={"objectFit": "cover"},
            flex_shrink="0",
            custom_attrs={"referrerpolicy": "no-referrer", "loading": "lazy"},
        ),
        rx.center(
            rx.icon("server", size=20, color="var(--gray-9)"),
            width="40px", height="40px",
            border_radius="8px",
            background="var(--gray-4)",
            flex_shrink="0",
        ),
    )
    title = rx.hstack(
        rx.cond(
            fav["ticker"] != "",
            rx.badge(fav["ticker"], variant="solid", color_scheme="amber", radius="full", size="1"),
            rx.fragment(),
        ),
        rx.cond(
            fav["pool_name"] != "",
            rx.text(fav["pool_name"], size="4", weight="medium"),
            rx.text(AuthState.t["staking_no_name"], size="4", weight="medium", color="var(--gray-10)"),
        ),
        rx.cond(
            fav["retiring_epoch"] != "",
            rx.badge(AuthState.t["staking_badge_retiring"], color_scheme="red", variant="soft", size="1"),
            rx.fragment(),
        ),
        spacing="2", align="center", wrap="wrap",
    )
    return rx.box(
        rx.hstack(
            icon,
            rx.vstack(
                title,
                rx.text(pool_id, size="1", color="var(--gray-9)",
                        style={"fontFamily": "ui-monospace, monospace", "wordBreak": "break-all"}),
                spacing="1", align_items="start", flex="1", min_width="0",
            ),
            rx.icon_button(
                rx.icon("trash-2", size=14),
                variant="ghost",
                color_scheme="red",
                size="1",
                cursor="pointer",
                on_click=AuthState.remove_pool_favorite_handler(pool_id),
            ),
            align="center", width="100%",
        ),
        padding="14px 16px",
        border_radius="10px",
        border=f"1px solid {rx.color('gray', 4)}",
        background=rx.color_mode_cond("white", "rgba(15,15,25,0.85)"),
        width="100%",
    )


def _drep_list() -> rx.Component:
    return rx.cond(
        AuthState.is_drep_favorites_empty,
        rx.center(
            rx.vstack(
                rx.icon("bookmark", size=36, color="var(--gray-6)"),
                rx.text(AuthState.t["favorites_drep_empty"], size="4", color="var(--gray-8)"),
                spacing="3",
                align="center",
            ),
            padding_y="40px",
        ),
        rx.vstack(
            rx.foreach(AuthState.filtered_drep_favorites, drep_favorite_card),
            _fav_pagination(
                AuthState.drep_favorites_page,
                AuthState.drep_favorites_total_pages,
                AuthState.drep_favorites_prev_page,
                AuthState.drep_favorites_next_page,
            ),
            spacing="2",
            width="100%",
        ),
    )


def _pool_list() -> rx.Component:
    return rx.cond(
        AuthState.is_pool_favorites_empty,
        rx.center(
            rx.vstack(
                rx.icon("bookmark", size=36, color="var(--gray-6)"),
                rx.text(AuthState.t["favorites_pool_empty"], size="4", color="var(--gray-8)"),
                spacing="3",
                align="center",
            ),
            padding_y="40px",
        ),
        rx.vstack(
            rx.foreach(AuthState.filtered_pool_favorites, pool_favorite_card),
            _fav_pagination(
                AuthState.pool_favorites_page,
                AuthState.pool_favorites_total_pages,
                AuthState.pool_favorites_prev_page,
                AuthState.pool_favorites_next_page,
            ),
            spacing="2",
            width="100%",
        ),
    )


def favorites_tab() -> rx.Component:
    # カテゴリ切り替えボタン
    def _cat_btn(label: str, value: str, icon_name: str) -> rx.Component:
        is_active = AuthState.favorites_category == value
        return rx.button(
            rx.hstack(rx.icon(icon_name, size=14), rx.text(label, size="2"), spacing="1", align="center"),
            variant=rx.cond(is_active, "solid", "soft"),
            color_scheme=rx.cond(is_active, "amber", "gray"),
            size="2",
            cursor="pointer",
            on_click=AuthState.set_favorites_category(value),
        )

    return rx.vstack(
        rx.hstack(
            _cat_btn("ガバナンス", "governance", "landmark"),
            _cat_btn("DRep", "drep", "user-round"),
            _cat_btn("ステークプール", "pool", "server"),
            _cat_btn("Catalyst", "catalyst", "flask-conical"),
            spacing="2",
            wrap="wrap",
        ),
        rx.match(
            AuthState.favorites_category,
            ("catalyst",   _catalyst_list()),
            ("drep",       _drep_list()),
            ("pool",       _pool_list()),
            _governance_list(),
        ),
        spacing="4",
        width="100%",
    )


# ============================================================
# タブ2: プロフィール編集
# ============================================================

def profile_tab() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.text(AuthState.t["display_name"], size="3", weight="medium"),
            rx.input(
                value=AuthState.edit_username,
                on_change=AuthState.set_edit_username,
                placeholder=AuthState.t["display_name"],
                size="3",
                width="100%",
            ),
            spacing="1",
            width="100%",
            align_items="start",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(AuthState.t["email_address"], size="3", weight="medium"),
                rx.cond(
                    AuthState.auth_providers.contains("google"),
                    rx.badge("Google連携", color_scheme="blue", size="1", variant="soft"),
                    rx.box(),
                ),
                spacing="2",
                align="center",
            ),
            rx.input(
                value=AuthState.edit_email,
                on_change=AuthState.set_edit_email,
                placeholder="email@example.com",
                type="email",
                size="3",
                width="100%",
                disabled=AuthState.auth_providers.contains("google"),
                style=rx.cond(
                    AuthState.auth_providers.contains("google"),
                    {"opacity": "0.6", "cursor": "not-allowed"},
                    {},
                ),
            ),
            rx.cond(
                AuthState.auth_providers.contains("google"),
                rx.text(
                    "Googleアカウントのメールアドレスは変更できません。",
                    size="1",
                    color="var(--gray-8)",
                ),
                rx.box(),
            ),
            spacing="1",
            width="100%",
            align_items="start",
        ),
        rx.hstack(
            rx.button(
                AuthState.t["save"],
                on_click=AuthState.save_profile,
                size="3",
                style={
                    "background": f"linear-gradient(135deg, {ACCENT}, {ACCENT_DARK})",
                    "color": "#111",
                    "cursor": "pointer",
                },
            ),
            rx.cond(
                AuthState.profile_saved,
                rx.hstack(
                    rx.icon("check", size=16, color="var(--green-9)"),
                    rx.text(AuthState.t["saved"], size="3", color="var(--green-9)"),
                    spacing="1",
                    align="center",
                ),
                rx.box(),
            ),
            spacing="3",
            align="center",
        ),
        spacing="5",
        width="100%",
        max_width="480px",
    )


# ============================================================
# タブ3: ステークアドレス管理
# ============================================================

def stake_address_card(addr: rx.Var[dict]) -> rx.Component:
    is_active_wallet = (
        WalletState.connected & (WalletState.reward_address == addr["address"])
    )
    is_editing = AuthState.editing_stake_id == addr["id"].to(int)
    nickname_block = rx.cond(
        is_editing,
        rx.hstack(
            rx.input(
                value=AuthState.editing_stake_nickname,
                on_change=AuthState.set_editing_stake_nickname,
                size="2",
                max_length=100,
                width="220px",
            ),
            rx.icon_button(
                rx.icon("check", size=14),
                on_click=AuthState.save_stake_nickname,
                color_scheme="green",
                size="1",
                cursor="pointer",
            ),
            rx.icon_button(
                rx.icon("x", size=14),
                on_click=AuthState.cancel_edit_stake_nickname,
                variant="ghost",
                color_scheme="gray",
                size="1",
                cursor="pointer",
            ),
            spacing="1", align="center",
        ),
        rx.hstack(
            rx.text(addr["nickname"], size="4", weight="medium"),
            rx.icon_button(
                rx.icon("pencil", size=12),
                variant="ghost",
                color_scheme="gray",
                size="1",
                cursor="pointer",
                on_click=AuthState.start_edit_stake_nickname(
                    addr["id"].to(int), addr["nickname"].to(str),
                ),
            ),
            spacing="2", align="center",
        ),
    )
    # 編集中はゴミ箱ボタンを隠して押し間違いを防ぐ
    delete_button = rx.cond(
        is_editing,
        rx.fragment(),
        rx.icon_button(
            rx.icon("trash-2", size=14),
            variant="ghost",
            color_scheme="red",
            size="1",
            cursor="pointer",
            on_click=AuthState.delete_stake_address_handler(addr["id"]),
        ),
    )
    spo_badge = rx.cond(
        addr["spo_pool_id"],
        rx.tooltip(
            rx.badge(
                rx.icon("crown", size=12),
                rx.text("SPO", weight="bold", size="1"),
                variant="solid",
                color_scheme="amber",
                size="1",
            ),
            content=addr["spo_pool_id"],
        ),
        rx.fragment(),
    )
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    nickname_block,
                    spo_badge,
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                # 受信アドレス（メイン表示）
                rx.cond(
                    addr["wallet_address"],
                    rx.text(
                        addr["wallet_address"],
                        size="2",
                        color="var(--gray-9)",
                        font_family="monospace",
                        word_break="break-all",
                    ),
                    rx.fragment(),
                ),
                # ステークアドレス（サブ表示）
                rx.hstack(
                    rx.text("stake", size="2", color="var(--gray-7)"),
                    rx.text(
                        addr["address"],
                        size="2",
                        color="var(--gray-7)",
                        font_family="monospace",
                        word_break="break-all",
                    ),
                    spacing="1",
                    align="start",
                    wrap="wrap",
                ),
                # ウォレット接続/検証状態 (このカードのアドレスに対して)
                wallet_connect_pill(addr),
                spacing="2",
                align_items="start",
                width="100%",
            ),
            delete_button,
            align="start",
            width="100%",
        ),
        padding="14px 16px",
        border_radius="10px",
        border=rx.cond(
            is_active_wallet,
            "1px solid var(--green-7)",
            f"1px solid {rx.color('gray', 4)}",
        ),
        background=rx.cond(
            is_active_wallet,
            rx.color_mode_cond(
                "linear-gradient(135deg, var(--green-2), var(--green-3))",
                "linear-gradient(135deg, rgba(34,197,94,0.14), rgba(34,197,94,0.05))",
            ),
            rx.color_mode_cond("white", "rgba(15,15,25,0.85)"),
        ),
        box_shadow=rx.cond(
            is_active_wallet,
            "0 0 0 3px rgba(34,197,94,0.10)",
            "none",
        ),
        width="100%",
        style={"transition": "background 0.18s, border-color 0.18s, box-shadow 0.18s"},
    )


def stake_tab() -> rx.Component:
    return rx.vstack(
        rx.text(
            AuthState.t["stake_tab_desc"],
            size="3",
            color="var(--gray-9)",
        ),
        # 登録済みアドレス一覧
        rx.cond(
            AuthState.is_stake_addresses_empty,
            rx.center(
                rx.text(AuthState.t["stake_empty"], size="3", color="var(--gray-8)"),
                padding_y="20px",
            ),
            rx.vstack(
                rx.foreach(AuthState.stake_addresses, stake_address_card),
                spacing="2",
                width="100%",
            ),
        ),
        rx.cond(
            AuthState.stake_role_loading,
            rx.hstack(
                rx.spinner(size="1"),
                rx.text(AuthState.t["stake_role_loading"], size="2", color="var(--gray-8)"),
                spacing="2",
                align="center",
            ),
            rx.fragment(),
        ),
        # 新規登録フォーム
        rx.cond(
            AuthState.stake_addresses_count < 3,
            rx.box(
                rx.vstack(
                    rx.text(AuthState.t["stake_new_title"], size="4", weight="medium"),
                    # ── ウォレットで自動取得 ──────────────
                    rx.box(
                        rx.vstack(
                            rx.flex(
                                rx.icon("wallet", size=16, color="var(--amber-11)",
                                        style={"flexShrink": "0"}),
                                rx.vstack(
                                    rx.text(
                                        AuthState.t["stake_wallet_auto_title"],
                                        size="2", weight="medium",
                                    ),
                                    rx.text(
                                        AuthState.t["stake_wallet_auto_desc"],
                                        size="1", color="var(--gray-10)",
                                        style={"wordBreak": "break-word"},
                                    ),
                                    spacing="0", align_items="start",
                                    style={"minWidth": "0", "flex": "1 1 auto"},
                                ),
                                rx.spacer(),
                                wallet_register_picker_menu(
                                    rx.button(
                                        rx.icon("wallet", size=12),
                                        rx.text(
                                            AuthState.t["stake_wallet_pick_button"],
                                            size="1",
                                        ),
                                        rx.icon("chevron-down", size=12),
                                        size="2",
                                        variant="soft",
                                        color_scheme="amber",
                                        cursor="pointer",
                                    ),
                                ),
                                spacing="3",
                                align="center",
                                width="100%",
                                wrap="wrap",
                            ),
                            # モバイルユーザー向け注意書き
                            rx.text(
                                AuthState.t["stake_wallet_mobile_note"],
                                size="1",
                                color="var(--amber-11)",
                                style={
                                    "wordBreak": "break-word",
                                    "lineHeight": "1.6",
                                },
                            ),
                            spacing="2",
                            align_items="start",
                            width="100%",
                        ),
                        padding="12px 14px",
                        border_radius="8px",
                        border="1px dashed var(--amber-7)",
                        background="var(--amber-2)",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.divider(flex="1"),
                        rx.text(
                            AuthState.t["stake_wallet_or_manual"],
                            size="1", color="var(--gray-9)",
                        ),
                        rx.divider(flex="1"),
                        spacing="3", align="center", width="100%",
                    ),
                    rx.vstack(
                        rx.text(AuthState.t["stake_nickname_label"], size="3"),
                        rx.input(
                            value=AuthState.new_stake_nickname,
                            on_change=AuthState.set_new_stake_nickname,
                            placeholder=AuthState.t["stake_nickname_placeholder"],
                            size="3",
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                        align_items="start",
                    ),
                    rx.vstack(
                        rx.text(AuthState.t["stake_address_label"], size="3"),
                        rx.input(
                            value=AuthState.new_stake_address,
                            on_change=AuthState.set_new_stake_address,
                            placeholder="addr1...",
                            size="3",
                            width="100%",
                            font_family="monospace",
                        ),
                        rx.text(
                            AuthState.t["stake_address_hint"],
                            size="2",
                            color="var(--gray-8)",
                        ),
                        spacing="1",
                        width="100%",
                        align_items="start",
                    ),
                    rx.cond(
                        AuthState.stake_error != "",
                        rx.text(AuthState.stake_error, size="3", color="var(--red-9)"),
                        rx.box(),
                    ),
                    rx.button(
                        rx.icon("plus", size=14),
                        AuthState.t["stake_add_button"],
                        on_click=AuthState.add_stake_address_handler,
                        size="2",
                        cursor="pointer",
                        loading=AuthState.stake_adding | AuthState.stake_role_loading,
                        disabled=AuthState.stake_adding | AuthState.stake_role_loading,
                    ),
                    spacing="3",
                    width="100%",
                    align_items="start",
                ),
                padding="16px",
                border_radius="10px",
                border=f"1px solid {rx.color('gray', 4)}",
                background=rx.color_mode_cond("var(--gray-2)", "rgba(15,15,25,0.5)"),
                width="100%",
            ),
            rx.text(
                AuthState.t["stake_limit_message"],
                size="3",
                color="var(--gray-8)",
            ),
        ),
        spacing="4",
        width="100%",
    )


# ============================================================
# タブ4: 通知管理
# ============================================================

def _disabled_toggle_rows(event_types: list) -> list:
    """グレーアウト表示用の無効トグル行（ステークアドレス未登録時）。"""
    return [
        rx.hstack(
            rx.text(AuthState.notification_labels[et], size="3", color="var(--gray-8)"),
            rx.switch(checked=False, disabled=True, color_scheme="gray", size="1"),
            justify="between",
            width="100%",
            padding_y="3px",
        )
        for et in event_types
    ]


def stake_notification_empty_preview() -> rx.Component:
    """ステークアドレス未登録時のグレーアウトプレビュー表示。"""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("info", size=16, color="var(--amber-9)"),
                rx.text(
                    AuthState.t["notification_tab_no_stake"],
                    size="2",
                    color="var(--amber-11)",
                ),
                spacing="2",
                align="center",
                padding="10px 12px",
                border_radius="8px",
                background="var(--amber-2)",
                border=f"1px solid var(--amber-6)",
                width="100%",
            ),
            # グレーアウトコンテンツ
            rx.box(
                rx.vstack(
                    rx.text(AuthState.t["notification_tab_per_addr_title"], size="4", weight="bold", color="var(--gray-7)"),
                    rx.box(
                        rx.vstack(
                            rx.text(AuthState.t["notification_pool_section"], size="3", weight="bold", color="var(--gray-7)"),
                            *_disabled_toggle_rows(POOL_NOTIFICATION_EVENT_TYPES),
                            rx.divider(margin_y="6px"),
                            rx.text(AuthState.t["notification_governance_section"], size="3", weight="bold", color="var(--gray-7)"),
                            *_disabled_toggle_rows(DELEGATOR_NOTIFICATION_EVENT_TYPES),
                            spacing="1",
                            width="100%",
                            align_items="start",
                        ),
                        padding="12px",
                        border_radius="8px",
                        border=f"1px solid {rx.color('gray', 4)}",
                        background=rx.color_mode_cond("var(--gray-2)", "rgba(15,15,25,0.4)"),
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                    align_items="start",
                ),
                opacity="0.6",
                pointer_events="none",
                width="100%",
            ),
            spacing="3",
            width="100%",
            align_items="start",
        ),
        padding="16px",
        border_radius="10px",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )


def general_notification_toggle_row(event_type: str) -> rx.Component:
    """ユーザー全体の通知設定トグル行。"""
    return rx.hstack(
        rx.text(AuthState.notification_labels[event_type], size="4"),
        rx.switch(
            checked=AuthState.notification_settings[event_type],
            on_change=lambda _: AuthState.toggle_notification(event_type),
            color_scheme="amber",
        ),
        justify="between",
        width="100%",
        padding_y="4px",
    )


def _toggle_rows(addr_id_str: rx.Var, event_types: list) -> list:
    return [
        rx.hstack(
            rx.text(AuthState.notification_labels[et], size="3"),
            rx.switch(
                checked=AuthState.stake_notification_settings[addr_id_str + ":" + et],
                on_change=AuthState.toggle_stake_notification(addr_id_str + ":" + et),
                color_scheme="amber",
                size="1",
            ),
            justify="between",
            width="100%",
            padding_y="3px",
        )
        for et in event_types
    ]


def stake_notification_section(addr: rx.Var) -> rx.Component:
    """ステークアドレス1件ぶんの通知設定アコーディオン（ロール別）。"""
    addr_id_str = addr["id"].to(str)
    item = rx.accordion.item(
        value=addr_id_str,
        header=rx.vstack(
            rx.text(addr["nickname"], size="4", weight="medium"),
            rx.text(
                addr["address"],
                size="2",
                color="var(--gray-8)",
                font_family="monospace",
                word_break="break-all",
            ),
            rx.hstack(
                rx.cond(
                    addr["delegated_pool_name"],
                    rx.hstack(
                        rx.text(AuthState.t["notification_pool_label"], size="2", color="var(--gray-9)"),
                        rx.badge(addr["delegated_pool_name"], variant="soft", color_scheme="blue", size="1"),
                        rx.cond(
                            addr["pool_pending_effective_epoch"],
                            rx.badge(AuthState.t["staking_badge_pending_fee"], variant="soft", color_scheme="amber", size="1"),
                            rx.fragment(),
                        ),
                        spacing="1",
                        align="center",
                    ),
                    rx.cond(
                        addr["delegated_pool_id"],
                        rx.hstack(
                            rx.text(AuthState.t["notification_pool_label"], size="2", color="var(--gray-9)"),
                            rx.badge(addr["delegated_pool_id"], variant="outline", color_scheme="blue", size="1", font_family="monospace"),
                            rx.cond(
                                addr["pool_pending_effective_epoch"],
                                rx.badge(AuthState.t["staking_badge_pending_fee"], variant="soft", color_scheme="amber", size="1"),
                                rx.fragment(),
                            ),
                            spacing="1",
                            align="center",
                        ),
                        rx.fragment(),
                    ),
                ),
                rx.cond(
                    (addr["role"] == "delegator") & addr["delegated_drep_name"],
                    rx.hstack(
                        rx.text(AuthState.t["notification_drep_label"], size="2", color="var(--gray-9)"),
                        rx.badge(addr["delegated_drep_name"], variant="soft", color_scheme="amber", size="1"),
                        spacing="1",
                        align="center",
                    ),
                    rx.cond(
                        (addr["role"] == "delegator") & addr["delegated_drep_id"],
                        rx.hstack(
                            rx.text(AuthState.t["notification_drep_label"], size="2", color="var(--gray-9)"),
                            rx.badge(addr["delegated_drep_id"], variant="outline", color_scheme="amber", size="1", font_family="monospace"),
                            spacing="1",
                            align="center",
                        ),
                        rx.fragment(),
                    ),
                ),
                spacing="3",
                wrap="wrap",
            ),
            spacing="1",
            align_items="start",
            width="100%",
        ),
        content=rx.vstack(
            # プール委任先情報
            rx.cond(
                addr["delegated_pool_name"],
                rx.hstack(
                    rx.text(AuthState.t["notification_pool_label"], size="2", color="var(--gray-9)"),
                    rx.badge(addr["delegated_pool_name"], variant="soft", color_scheme="blue", size="1"),
                    rx.cond(
                        addr["pool_pending_effective_epoch"],
                        rx.badge(AuthState.t["staking_badge_pending_fee"], variant="soft", color_scheme="amber", size="1"),
                        rx.fragment(),
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.cond(
                    addr["delegated_pool_id"],
                    rx.hstack(
                        rx.text(AuthState.t["notification_pool_label"], size="2", color="var(--gray-9)"),
                        rx.badge(addr["delegated_pool_id"], variant="outline", color_scheme="blue", size="1", font_family="monospace"),
                        rx.cond(
                            addr["pool_pending_effective_epoch"],
                            rx.badge(AuthState.t["staking_badge_pending_fee"], variant="soft", color_scheme="amber", size="1"),
                            rx.fragment(),
                        ),
                        spacing="1",
                        align="center",
                    ),
                    rx.fragment(),
                ),
            ),
            # プール通知
            rx.text(AuthState.t["notification_pool_section"], size="3", weight="bold", color="var(--gray-10)"),
            rx.cond(
                addr["delegated_pool_id"],
                rx.vstack(
                    *_toggle_rows(addr_id_str, POOL_NOTIFICATION_EVENT_TYPES),
                    spacing="1",
                    width="100%",
                    align_items="start",
                ),
                rx.text(
                    AuthState.t["notification_pool_undelegated"],
                    size="3",
                    color="var(--gray-8)",
                ),
            ),
            rx.divider(margin_y="8px"),
            # ガバナンス通知（ロール別）
            rx.hstack(
                rx.text(AuthState.t["notification_governance_section"], size="3", weight="bold", color="var(--gray-10)"),
                rx.cond(
                    addr["role"] == "drep",
                    rx.badge(AuthState.t["badge_drep"], color_scheme="amber", size="1"),
                    rx.cond(
                        addr["role"] == "abstain",
                        rx.badge(AuthState.t["badge_abstain"], color_scheme="red", size="1"),
                        rx.badge(AuthState.t["badge_delegator"], color_scheme="gray", size="1"),
                    ),
                ),
                spacing="2",
                align="center",
            ),
            # 委任先情報（アコーディオン内）
            rx.cond(
                (addr["role"] == "delegator") & addr["delegated_drep_name"],
                rx.hstack(
                    rx.text(AuthState.t["notification_drep_label"], size="2", color="var(--gray-9)"),
                    rx.badge(addr["delegated_drep_name"], variant="soft", color_scheme="amber", size="1"),
                    spacing="1",
                    align="center",
                ),
                rx.cond(
                    (addr["role"] == "delegator") & addr["delegated_drep_id"],
                    rx.hstack(
                        rx.text(AuthState.t["notification_drep_label"], size="2", color="var(--gray-9)"),
                        rx.badge(addr["delegated_drep_id"], variant="outline", color_scheme="amber", size="1", font_family="monospace"),
                        spacing="1",
                        align="center",
                    ),
                    rx.fragment(),
                ),
            ),
            rx.cond(
                addr["role"] == "drep",
                # DRep本人
                rx.vstack(
                    *_toggle_rows(addr_id_str, DREP_ONLY_NOTIFICATION_EVENT_TYPES),
                    spacing="1",
                    width="100%",
                    align_items="start",
                ),
                rx.cond(
                    addr["role"] == "abstain",
                    # 棄権（ガバナンス通知なし）
                    rx.vstack(
                        rx.text(
                            AuthState.t["drep_abstain_notice"],
                            size="3",
                            color="var(--gray-8)",
                        ),
                        rx.text(
                            AuthState.t["drep_abstain_explanation"],
                            size="3",
                            color="var(--gray-9)",
                        ),
                        spacing="2",
                        width="100%",
                        align_items="start",
                    ),
                    # DRep委任者 or 未委任
                    rx.cond(
                        addr["delegated_drep_id"],
                        # 委任済み → 通知設定を表示
                        rx.vstack(
                            *_toggle_rows(addr_id_str, DELEGATOR_NOTIFICATION_EVENT_TYPES),
                            spacing="1",
                            width="100%",
                            align_items="start",
                        ),
                        # 未委任 → 案内メッセージ
                        rx.vstack(
                            rx.text(
                                AuthState.t["drep_undelegated_notice"],
                                size="3",
                                color="var(--gray-8)",
                            ),
                            rx.text(
                                AuthState.t["drep_abstain_explanation"],
                                size="3",
                                color="var(--gray-9)",
                            ),
                            spacing="2",
                            width="100%",
                            align_items="start",
                        ),
                    ),
                ),
            ),
            spacing="1",
            width="100%",
            align_items="start",
            padding="4px 0",
        ),
    )
    return rx.accordion.root(
        item,
        collapsible=True,
        width="100%",
        variant="surface",
        style={
            "& .rt-AccordionContent": {
                "background": rx.color_mode_cond("var(--gray-2)", "var(--gray-3)"),
                "border-radius": "0 0 6px 6px",
            },
        },
    )


def notification_channel_section() -> rx.Component:
    """通知チャンネル選択セクション（メール・LINE・Telegram いずれか連携済みの場合に表示）。"""
    has_email = AuthState.email_notify_channel != ""
    has_line = AuthState.line_notify_channel != ""
    has_telegram = AuthState.telegram_chat_id != ""
    return rx.cond(
        has_email | has_line | has_telegram,
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("send", size=18, color="var(--gray-10)"),
                    rx.text(AuthState.t["notification_channel_title"], size="4", weight="bold"),
                    spacing="2",
                    align="center",
                ),
                rx.text(
                    AuthState.t["notification_channel_desc"],
                    size="2",
                    color="var(--gray-9)",
                ),
                rx.vstack(
                    # メール通知チャンネル
                    rx.cond(
                        has_email,
                        rx.hstack(
                            rx.hstack(
                                rx.icon("mail", size=16, color="var(--gray-9)"),
                                rx.vstack(
                                    rx.text(AuthState.t["notification_channel_email"], size="3", weight="medium"),
                                    rx.text(AuthState.email, size="2", color="var(--gray-8)"),
                                    spacing="0",
                                    align_items="start",
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.switch(
                                checked=AuthState.email_notify_enabled,
                                on_change=AuthState.set_email_notify_enabled,
                                color_scheme="amber",
                            ),
                            justify="between",
                            align="center",
                            width="100%",
                        ),
                        rx.box(),
                    ),
                    # email + line の区切り線
                    rx.cond(
                        has_email & has_line,
                        rx.divider(),
                        rx.box(),
                    ),
                    # LINE通知チャンネル
                    rx.cond(
                        has_line,
                        rx.hstack(
                            rx.hstack(
                                rx.icon("message-circle", size=16, color="#06C755"),
                                rx.text(AuthState.t["notification_channel_line"], size="3", weight="medium"),
                                spacing="2",
                                align="center",
                            ),
                            rx.switch(
                                checked=AuthState.line_notify_enabled,
                                on_change=AuthState.set_line_notify_enabled,
                                color_scheme="amber",
                            ),
                            justify="between",
                            align="center",
                            width="100%",
                        ),
                        rx.box(),
                    ),
                    # (line | email) + telegram の区切り線
                    rx.cond(
                        (has_email | has_line) & has_telegram,
                        rx.divider(),
                        rx.box(),
                    ),
                    # Telegram通知チャンネル
                    rx.cond(
                        has_telegram,
                        rx.hstack(
                            rx.hstack(
                                rx.icon("send", size=16, color="#229ED9"),
                                rx.text(AuthState.t["notification_channel_telegram"], size="3", weight="medium"),
                                spacing="2",
                                align="center",
                            ),
                            rx.switch(
                                checked=AuthState.telegram_notify_enabled,
                                on_change=AuthState.set_telegram_notify_enabled,
                                color_scheme="amber",
                            ),
                            justify="between",
                            align="center",
                            width="100%",
                        ),
                        rx.box(),
                    ),
                    spacing="3",
                    width="100%",
                ),
                spacing="3",
                align_items="start",
                width="100%",
            ),
            padding="16px",
            border_radius="10px",
            border=f"1px solid {rx.color('gray', 4)}",
            width="100%",
        ),
        rx.box(),
    )


def subscription_tab() -> rx.Component:
    """サブスクリプション管理タブ (Phase 0: 表示のみ、決済は近日対応)。"""
    # tier 名 → i18n key (plan_config の name_key と揃える)
    tier_name = rx.match(
        AuthState.subscription_tier,
        ("free",     AuthState.t["plan_free_name"]),
        ("light",    AuthState.t["plan_light_name"]),
        ("standard", AuthState.t["plan_standard_name"]),
        ("plus",     AuthState.t["plan_plus_name"]),
        ("pro",      AuthState.t["plan_pro_name"]),
        AuthState.t["plan_free_name"],
    )
    status_label = rx.match(
        AuthState.subscription_status,
        ("active",   AuthState.t["subscription_status_active"]),
        ("canceled", AuthState.t["subscription_status_canceled"]),
        ("expired",  AuthState.t["subscription_status_expired"]),
        ("past_due", AuthState.t["subscription_status_past_due"]),
        AuthState.t["subscription_status_active"],
    )
    status_color = rx.match(
        AuthState.subscription_status,
        ("active",   "var(--green-9)"),
        ("canceled", "var(--gray-9)"),
        ("expired",  "var(--gray-9)"),
        ("past_due", "var(--red-9)"),
        "var(--gray-9)",
    )
    billing_label = rx.match(
        AuthState.subscription_billing_cycle,
        ("monthly", AuthState.t["subscription_billing_monthly"]),
        ("yearly",  AuthState.t["subscription_billing_yearly"]),
        "",
    )

    info_row = lambda label, value: rx.hstack(
        rx.text(label, size="2", color="var(--gray-10)", style={"flexShrink": "0"}),
        rx.spacer(),
        rx.text(value, size="2", weight="medium", color="var(--gray-12)"),
        spacing="3", align="center", width="100%", wrap="wrap",
    )

    return rx.vstack(
        # ベータ通知
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("info", size=16, color="var(--amber-11)"),
                    rx.text(
                        AuthState.t["subscription_beta_note"],
                        size="2", color="var(--amber-12)", line_height="1.6",
                        style={"wordBreak": "break-word"},
                    ),
                    spacing="2", align="start",
                ),
                spacing="0", width="100%",
            ),
            padding="14px 16px",
            border=f"1px solid var(--amber-7)",
            border_radius="12px",
            background=rx.color_mode_cond("rgba(255,243,199,0.55)", "rgba(120,80,0,0.18)"),
            width="100%",
        ),

        # 現在のプラン
        rx.box(
            rx.vstack(
                rx.text(AuthState.t["subscription_current_plan"], size="2",
                        weight="medium", color="var(--gray-10)"),
                rx.hstack(
                    rx.icon("crown", size=20, color="var(--amber-10)"),
                    rx.text(tier_name, size="6", weight="bold", color="var(--gray-12)",
                            style={"letterSpacing": "-0.02em"}),
                    spacing="2", align="center",
                ),
                rx.divider(),
                info_row(AuthState.t["subscription_status"],
                         rx.text(status_label, size="2", weight="bold", color=status_color)),
                rx.cond(
                    AuthState.subscription_billing_cycle != "",
                    info_row(AuthState.t["subscription_billing_monthly"].split("プラン")[0]
                             if False else "Billing", billing_label),
                    rx.fragment(),
                ),
                rx.cond(
                    AuthState.subscription_started_at != "",
                    info_row(AuthState.t["subscription_started_at"],
                             AuthState.subscription_started_at),
                    rx.fragment(),
                ),
                rx.cond(
                    AuthState.subscription_period_end != "",
                    info_row(AuthState.t["subscription_period_end"],
                             AuthState.subscription_period_end),
                    rx.fragment(),
                ),
                spacing="3", align_items="start", width="100%",
            ),
            padding="20px 22px",
            border=f"1px solid {rx.color('gray', 5)}",
            border_radius="14px",
            background=rx.color_mode_cond("rgba(255,255,255,0.7)", "rgba(255,255,255,0.025)"),
            width="100%",
        ),

        # アクション
        rx.flex(
            rx.link(
                rx.button(
                    rx.icon("layers", size=14),
                    AuthState.t["subscription_view_plans"],
                    rx.icon("arrow-right", size=14),
                    size="3",
                    cursor="pointer",
                    color_scheme="amber",
                ),
                href="/pricing",
                underline="none",
            ),
            rx.button(
                rx.icon("x", size=14),
                AuthState.t["subscription_cancel"],
                size="3",
                variant="soft",
                color_scheme="gray",
                cursor="not-allowed",
                disabled=True,
            ),
            spacing="3", wrap="wrap",
        ),

        spacing="4",
        align_items="start",
        width="100%",
    )


def notification_tab() -> rx.Component:
    return rx.vstack(
        # 通知チャンネル選択
        notification_channel_section(),
        # LINE連携セクション
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("message-circle", size=18, color="#06C755"),
                    rx.text(AuthState.t["notification_tab_line_title"], size="4", weight="bold"),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    # 連携状態に応じた表示（line_notify_channel で判定）
                    rx.cond(
                        AuthState.line_notify_channel != "",
                        # 連携済み
                        rx.vstack(
                            rx.hstack(
                                rx.icon("check-circle", size=16, color="var(--green-9)"),
                                rx.text(AuthState.t["notification_tab_line_connected"], size="3", color="var(--green-9)", weight="medium"),
                                spacing="1",
                                align="center",
                            ),
                            rx.text(AuthState.t["notification_tab_line_friend_hint"], size="2", color="var(--gray-9)"),
                            rx.button(
                                AuthState.t["notification_tab_line_disconnect_button"],
                                on_click=AuthState.disconnect_line,
                                size="2",
                                variant="soft",
                                color_scheme="red",
                                cursor="pointer",
                            ),
                            spacing="2",
                            align_items="start",
                        ),
                        # 未連携
                        rx.vstack(
                            rx.text(AuthState.t["notification_tab_line_not_connected"], size="3", color="var(--gray-9)"),
                            rx.el.a(
                                rx.el.span(
                                    rx.el.img(src="/line-icon.png", alt="LINE", style={"width": "28px", "height": "28px", "object-fit": "contain"}),
                                    style={
                                        "display": "flex",
                                        "align-items": "center",
                                        "justify-content": "center",
                                        "padding": "0 10px",
                                        "border-right": "1px solid rgba(255,255,255,0.3)",
                                        "height": "100%",
                                        "flex-shrink": "0",
                                    },
                                ),
                                rx.el.span(
                                    AuthState.t["notification_tab_line_connect_button"],
                                    style={
                                        "flex": "1",
                                        "text-align": "center",
                                        "font-size": "14px",
                                        "font-weight": "700",
                                        "color": "white",
                                        "padding": "0 12px",
                                    },
                                ),
                                href="/auth/line/connect",
                                style={
                                    "display": "flex",
                                    "align-items": "center",
                                    "height": "38px",
                                    "background": "#06C755",
                                    "border-radius": "5px",
                                    "text-decoration": "none",
                                    "overflow": "hidden",
                                    "cursor": "pointer",
                                    "transition": "filter 0.15s ease",
                                    "_hover": {"filter": "brightness(0.9)"},
                                    "_active": {"filter": "brightness(0.7)"},
                                },
                            ),
                            spacing="2",
                            align_items="start",
                        ),
                    ),
                    # QRコード（常に表示）
                    rx.link(
                        rx.image(
                            src="/line-qr.png",
                            width="90px",
                            height="90px",
                            alt="Cardanoism LINE公式QRコード",
                            border_radius="8px",
                        ),
                        href="https://line.me/R/ti/p/@022cmuds",
                        is_external=True,
                    ),
                    justify="between",
                    align="center",
                    width="100%",
                ),
                spacing="3",
                align_items="start",
            ),
            padding="16px",
            border_radius="10px",
            border=f"1px solid {rx.color('gray', 4)}",
            width="100%",
        ),
        # Telegram連携セクション
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("send", size=18, color="#2AABEE"),
                    rx.text(AuthState.t["notification_tab_telegram_title"], size="4", weight="bold"),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    AuthState.telegram_chat_id != "",
                    rx.vstack(
                        rx.hstack(
                            rx.icon("check-circle", size=16, color="var(--green-9)"),
                            rx.text(AuthState.t["notification_tab_telegram_connected"], size="3", color="var(--green-9)", weight="medium"),
                            spacing="1",
                            align="center",
                        ),
                        rx.button(
                            AuthState.t["notification_tab_telegram_disconnect_button"],
                            on_click=AuthState.disconnect_telegram,
                            size="2",
                            variant="soft",
                            color_scheme="red",
                            cursor="pointer",
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    rx.vstack(
                        rx.text(AuthState.t["notification_tab_telegram_not_connected"], size="3", color="var(--gray-9)"),
                        rx.hstack(
                            rx.button(
                                rx.hstack(
                                    rx.icon("send", size=16),
                                    rx.text(AuthState.t["notification_tab_telegram_connect_button"], size="3", weight="bold"),
                                    spacing="2",
                                    align="center",
                                ),
                                on_click=AuthState.start_telegram_connect,
                                size="2",
                                style={
                                    "background": "#2AABEE",
                                    "color": "white",
                                    "border": "none",
                                    "cursor": "pointer",
                                },
                            ),
                            rx.button(
                                rx.hstack(
                                    rx.icon("refresh-cw", size=16),
                                    rx.text(AuthState.t["notification_tab_telegram_reload_button"], size="3"),
                                    spacing="2",
                                    align="center",
                                ),
                                on_click=AuthState.reload_telegram_channel,
                                size="2",
                                variant="soft",
                            ),
                            spacing="2",
                            wrap="wrap",
                        ),
                        rx.cond(
                            AuthState.telegram_reload_msg != "",
                            rx.text(AuthState.telegram_reload_msg, size="2", color="var(--orange-9)"),
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                ),
                spacing="3",
                align_items="start",
            ),
            padding="16px",
            border_radius="10px",
            border=f"1px solid {rx.color('gray', 4)}",
            width="100%",
        ),
        # ステークアドレスごとの通知設定
        rx.cond(
            AuthState.is_stake_addresses_empty,
            stake_notification_empty_preview(),
            rx.box(
                rx.vstack(
                    rx.text(AuthState.t["notification_tab_per_addr_title"], size="4", weight="bold"),
                    rx.vstack(
                        rx.foreach(AuthState.stake_addresses, stake_notification_section),
                        spacing="3",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                    align_items="start",
                ),
                padding="16px",
                border_radius="10px",
                border=f"1px solid {rx.color('gray', 4)}",
                width="100%",
            ),
        ),
        # 一般通知
        rx.box(
            rx.vstack(
                rx.text(AuthState.t["notification_general_title"], size="4", weight="bold"),
                *[general_notification_toggle_row(et) for et in GENERAL_EVENTS],
                spacing="2",
                width="100%",
                align_items="start",
            ),
            padding="16px",
            border_radius="10px",
            border=f"1px solid {rx.color('gray', 4)}",
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


# ============================================================
# マイページ本体
# ============================================================

@template(
    route="/mypage",
    title="マイページ | Cardanoism",
    on_load=AuthState.load_mypage,
)
def mypage() -> rx.Component:
    # 現在のプランをサブスクタブと同じ tier 名で表示するバッジ
    plan_badge_only = rx.match(
        AuthState.subscription_tier,
        ("free",
         rx.badge(rx.icon("crown", size=14), AuthState.t["plan_free_name"],
                  color_scheme="gray",   variant="solid", size="2", radius="full")),
        ("light",
         rx.badge(rx.icon("crown", size=14), AuthState.t["plan_light_name"],
                  color_scheme="amber",  variant="solid", size="2", radius="full")),
        ("standard",
         rx.badge(rx.icon("crown", size=14), AuthState.t["plan_standard_name"],
                  color_scheme="blue",   variant="solid", size="2", radius="full")),
        ("plus",
         rx.badge(rx.icon("crown", size=14), AuthState.t["plan_plus_name"],
                  color_scheme="violet", variant="solid", size="2", radius="full")),
        ("pro",
         rx.badge(rx.icon("crown", size=14), AuthState.t["plan_pro_name"],
                  color_scheme="sky",    variant="solid", size="2", radius="full")),
        rx.fragment(),
    )
    plan_badge = rx.cond(
        AuthState.subscription_tier != "",
        rx.hstack(
            rx.text(
                AuthState.t["subscription_membership_label"], "：",
                size="2", color="var(--gray-10)",
            ),
            plan_badge_only,
            spacing="1", align="center",
        ),
        rx.fragment(),
    )

    # ダッシュボードヒーロー意匠 (welcome + username + plan badge + email + サブテキスト)
    hero = rx.box(
        rx.hstack(
            rx.cond(
                AuthState.avatar_url != "",
                rx.avatar(src=AuthState.avatar_url, size="5", radius="full"),
                rx.avatar(fallback=AuthState.username[:1], size="5", radius="full"),
            ),
            rx.vstack(
                rx.hstack(
                    rx.text(
                        AuthState.t["dashboard_welcome"],
                        size="3", color="var(--gray-10)",
                    ),
                    rx.heading(AuthState.username, size="6", weight="bold"),
                    plan_badge,
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.text(AuthState.email, size="2", color="var(--gray-9)"),
                rx.text(
                    AuthState.t["dashboard_welcome_sub"],
                    size="2", color="var(--gray-10)",
                ),
                spacing="1", align_items="start",
            ),
            spacing="4", align="center",
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

    return rx.box(
        login_modal(),
        rx.cond(
            AuthState.is_logged_in,
            rx.vstack(
                hero,
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("layout-dashboard", size=14), rx.text(AuthState.t["tab_dashboard"]), spacing="1"),
                            value="dashboard",
                            cursor="pointer",
                        ),
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("bookmark", size=14), rx.text(AuthState.t["tab_favorites"]), spacing="1"),
                            value="favorites",
                            cursor="pointer",
                        ),
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("user", size=14), rx.text(AuthState.t["tab_profile"]), spacing="1"),
                            value="profile",
                            cursor="pointer",
                        ),
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("wallet", size=14), rx.text(AuthState.t["tab_stake"]), spacing="1"),
                            value="stake",
                            cursor="pointer",
                        ),
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("bell", size=14), rx.text(AuthState.t["tab_notification"]), spacing="1"),
                            value="notification",
                            cursor="pointer",
                        ),
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("crown", size=14), rx.text(AuthState.t["tab_subscription"]), spacing="1"),
                            value="subscription",
                            cursor="pointer",
                        ),
                        wrap="wrap",
                    ),
                    rx.tabs.content(dashboard(), value="dashboard", padding_top="20px"),
                    rx.tabs.content(favorites_tab(), value="favorites", padding_top="20px"),
                    rx.tabs.content(profile_tab(), value="profile", padding_top="20px"),
                    rx.tabs.content(stake_tab(), value="stake", padding_top="20px"),
                    rx.tabs.content(notification_tab(), value="notification", padding_top="20px"),
                    rx.tabs.content(subscription_tab(), value="subscription", padding_top="20px"),
                    value=AuthState.active_tab,
                    on_change=AuthState.change_active_tab,
                    width="100%",
                ),
                spacing="4",
                width="100%",
                align_items="start",
            ),
            # 未ログイン時（モーダルが開くまでのプレースホルダー）
            rx.center(
                rx.vstack(
                    rx.icon("lock", size=40, color="var(--gray-6)"),
                    rx.text(AuthState.t["login_required"], size="4", color="var(--gray-8)"),
                    rx.link(
                        rx.button(AuthState.t["login_button"], size="3", cursor="pointer"),
                        href="/login",
                        underline="none",
                    ),
                    spacing="4",
                    align="center",
                ),
                min_height="50vh",
            ),
        ),
        width="100%",
    )
