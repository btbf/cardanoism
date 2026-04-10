"""
mypage.py
マイページ (/mypage) - 4タブ構成
  1. お気に入り（カタリスト提案）
  2. プロフィール編集
  3. ステークアドレス管理
  4. 通知管理
"""
import reflex as rx
from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.login_modal import login_modal
from cardanoism.backend.auth_db import (
    NOTIFICATION_EVENT_TYPES,
    POOL_NOTIFICATION_EVENT_TYPES,
    DELEGATOR_NOTIFICATION_EVENT_TYPES,
    DREP_ONLY_NOTIFICATION_EVENT_TYPES,
)

ACCENT = "#ffcf00"
ACCENT_DARK = "#c7a300"

# 通知イベントの日本語ラベル
NOTIFICATION_LABELS = {
    # プール共通
    "pool_retire": "プールの引退",
    "pool_fee_change": "手数料変更",
    "pool_saturation": "飽和状態超過",
    "pool_pledge_shortage": "誓約不足",
    "pool_reward_estimate": "次エポック報酬予測",
    "pool_reward_received": "報酬受け取り",
    "pool_delegation_reminder": "長期委任リマインダー（90/120/365日）",
    # DRep委任者
    "drep_vote": "委任先DRepの投票通知",
    "drep_status_change": "委任先DRepのステータス変化",
    "drep_delegation_reminder": "長期委任リマインダー（90/120/365日）",
    # DRep本人
    "drep_new_governance_action": "新しいガバナンスアクション",
    "drep_unvoted_1week": "未投票リマインダー（1週間経過）",
    "drep_unvoted_2weeks": "未投票リマインダー（2週間経過）",
    # ユーザー全体
    "epoch_start": "エポックスタート",
}

GENERAL_EVENTS = [
    "epoch_start",
]


# ============================================================
# タブ1: お気に入り
# ============================================================

def favorite_card(fav: rx.Var[dict]) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.link(
                    rx.text(fav["title"], size="3", weight="medium", line_height="1.4"),
                    href="/catalyst/proposals/" + fav["proposal_id"].to(str),
                    underline="hover",
                ),
                rx.hstack(
                    rx.badge(fav["fund_label"], variant="soft", color_scheme="amber", size="1"),
                    rx.badge(fav["funding_status"], variant="soft", size="1"),
                    rx.text(
                        fav["currency_symbol"],
                        fav["amount_requested"].to(str),
                        size="1",
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
                on_click=AuthState.remove_favorite_handler(fav["proposal_id"].to(int)),
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


def favorites_tab() -> rx.Component:
    return rx.vstack(
        # フィルター・並び替え
        rx.hstack(
            rx.select.root(
                rx.select.trigger(placeholder="Fund で絞り込み"),
                rx.select.content(
                    rx.select.item("すべて", value="all"),
                    rx.select.item("Fund 12", value="Fund 12"),
                    rx.select.item("Fund 13", value="Fund 13"),
                    rx.select.item("Fund 14", value="Fund 14"),
                    rx.select.item("Fund 15", value="Fund 15"),
                ),
                size="2",
                value=AuthState.favorites_fund_filter,
                on_change=AuthState.set_favorites_fund_filter,
            ),
            rx.select.root(
                rx.select.trigger(placeholder="ステータスで絞り込み"),
                rx.select.content(
                    rx.select.item("すべて", value="all"),
                    rx.select.item("採択", value="funded"),
                    rx.select.item("未採択", value="not_funded"),
                    rx.select.item("予算超過", value="over_budget"),
                ),
                size="2",
                value=AuthState.favorites_status_filter,
                on_change=AuthState.set_favorites_status_filter,
            ),
            rx.select.root(
                rx.select.trigger(),
                rx.select.content(
                    rx.select.item("要求金額（高い順）", value="amount_desc"),
                    rx.select.item("要求金額（低い順）", value="amount_asc"),
                ),
                size="2",
                value=AuthState.favorites_sort,
                on_change=AuthState.set_favorites_sort,
            ),
            wrap="wrap",
            spacing="2",
        ),
        # お気に入りリスト
        rx.cond(
            AuthState.is_favorites_empty,
            rx.center(
                rx.vstack(
                    rx.icon("bookmark", size=36, color="var(--gray-6)"),
                    rx.text("お気に入りはありません", size="3", color="var(--gray-8)"),
                    spacing="3",
                    align="center",
                ),
                padding_y="40px",
            ),
            rx.vstack(
                rx.foreach(AuthState.filtered_favorites, favorite_card),
                spacing="2",
                width="100%",
            ),
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
            rx.text("表示名", size="2", weight="medium"),
            rx.input(
                value=AuthState.edit_username,
                on_change=AuthState.set_edit_username,
                placeholder="表示名",
                size="3",
                width="100%",
            ),
            spacing="1",
            width="100%",
            align_items="start",
        ),
        rx.vstack(
            rx.text("メールアドレス", size="2", weight="medium"),
            rx.input(
                value=AuthState.edit_email,
                on_change=AuthState.set_edit_email,
                placeholder="email@example.com",
                type="email",
                size="3",
                width="100%",
            ),
            spacing="1",
            width="100%",
            align_items="start",
        ),
        rx.hstack(
            rx.button(
                "保存",
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
                    rx.text("保存しました", size="2", color="var(--green-9)"),
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
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(addr["nickname"], size="3", weight="medium"),
                rx.text(
                    addr["address"],
                    size="1",
                    color="var(--gray-9)",
                    font_family="monospace",
                    word_break="break-all",
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
                on_click=AuthState.delete_stake_address_handler(addr["id"]),
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


def stake_tab() -> rx.Component:
    return rx.vstack(
        rx.text(
            "登録したステークアドレスのイベントを通知します。最大3件まで登録できます。",
            size="2",
            color="var(--gray-9)",
        ),
        # 登録済みアドレス一覧
        rx.cond(
            AuthState.is_stake_addresses_empty,
            rx.center(
                rx.text("登録されたステークアドレスはありません", size="2", color="var(--gray-8)"),
                padding_y="20px",
            ),
            rx.vstack(
                rx.foreach(AuthState.stake_addresses, stake_address_card),
                spacing="2",
                width="100%",
            ),
        ),
        # 新規登録フォーム
        rx.cond(
            AuthState.stake_addresses_count < 3,
            rx.box(
                rx.vstack(
                    rx.text("新規登録", size="3", weight="medium"),
                    rx.vstack(
                        rx.text("ニックネーム", size="2"),
                        rx.input(
                            value=AuthState.new_stake_nickname,
                            on_change=AuthState.set_new_stake_nickname,
                            placeholder="メインウォレット",
                            size="2",
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                        align_items="start",
                    ),
                    rx.vstack(
                        rx.text("ステークアドレス", size="2"),
                        rx.input(
                            value=AuthState.new_stake_address,
                            on_change=AuthState.set_new_stake_address,
                            placeholder="stake1u...",
                            size="2",
                            width="100%",
                            font_family="monospace",
                        ),
                        spacing="1",
                        width="100%",
                        align_items="start",
                    ),
                    rx.cond(
                        AuthState.stake_error != "",
                        rx.text(AuthState.stake_error, size="2", color="var(--red-9)"),
                        rx.box(),
                    ),
                    rx.button(
                        rx.icon("plus", size=14),
                        "追加",
                        on_click=AuthState.add_stake_address_handler,
                        size="2",
                        cursor="pointer",
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
                "ステークアドレスの登録上限（3件）に達しています。",
                size="2",
                color="var(--gray-8)",
            ),
        ),
        spacing="4",
        width="100%",
    )


# ============================================================
# タブ4: 通知管理
# ============================================================

def general_notification_toggle_row(event_type: str, label: str) -> rx.Component:
    """ユーザー全体の通知設定トグル行。"""
    return rx.hstack(
        rx.text(label, size="3"),
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
            rx.text(NOTIFICATION_LABELS[et], size="2"),
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
    return rx.accordion.item(
        value=addr_id_str,
        header=rx.hstack(
            rx.cond(
                addr["role"] == "drep",
                rx.badge("DRep", color_scheme="amber", size="1"),
                rx.badge("委任者", color_scheme="gray", size="1"),
            ),
            rx.text(addr["nickname"], size="3", weight="medium"),
            rx.text(
                addr["address"],
                size="1",
                color="var(--gray-8)",
                font_family="monospace",
                overflow="hidden",
                text_overflow="ellipsis",
                white_space="nowrap",
                max_width="180px",
            ),
            spacing="2",
            align="center",
        ),
        content=rx.vstack(
            # プール通知（全ロール共通）
            rx.text("ステークプール通知", size="2", weight="bold", color="var(--gray-10)"),
            *_toggle_rows(addr_id_str, POOL_NOTIFICATION_EVENT_TYPES),
            rx.divider(margin_y="8px"),
            # ロール別通知
            rx.cond(
                addr["role"] == "drep",
                # DRep本人
                rx.vstack(
                    rx.text("DRep通知", size="2", weight="bold", color="var(--gray-10)"),
                    *_toggle_rows(addr_id_str, DREP_ONLY_NOTIFICATION_EVENT_TYPES),
                    spacing="1",
                    width="100%",
                    align_items="start",
                ),
                # DRep委任者
                rx.vstack(
                    rx.text("DRep委任者通知", size="2", weight="bold", color="var(--gray-10)"),
                    *_toggle_rows(addr_id_str, DELEGATOR_NOTIFICATION_EVENT_TYPES),
                    spacing="1",
                    width="100%",
                    align_items="start",
                ),
            ),
            spacing="1",
            width="100%",
            align_items="start",
            padding="4px 0",
        ),
    )


def notification_tab() -> rx.Component:
    return rx.vstack(
        # LINE連携セクション
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("message-circle", size=18, color="#06C755"),
                    rx.text("LINE通知連携", size="3", weight="bold"),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    AuthState.is_logged_in,
                    rx.text("LINEログインで連携済みです。通知を受け取るには、Cardanoism公式LINEアカウントを友だち追加してください。", size="2", color="var(--gray-9)"),
                    rx.link(
                        rx.button("LINEと連携する", size="2", cursor="pointer"),
                        href="/auth/line/login",
                        underline="none",
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
            rx.box(
                rx.text(
                    "ステークアドレスを登録すると、アドレスごとに通知を設定できます。",
                    size="2",
                    color="var(--gray-8)",
                ),
                padding="16px",
                border_radius="10px",
                border=f"1px solid {rx.color('gray', 4)}",
                width="100%",
            ),
            rx.box(
                rx.vstack(
                    rx.text("アドレスごとの通知設定", size="3", weight="bold"),
                    rx.accordion.root(
                        rx.foreach(AuthState.stake_addresses, stake_notification_section),
                        collapsible=True,
                        width="100%",
                        variant="ghost",
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
                rx.text("一般通知", size="3", weight="bold"),
                *[
                    general_notification_toggle_row(event_type, NOTIFICATION_LABELS[event_type])
                    for event_type in GENERAL_EVENTS
                ],
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

@template(route="/mypage", title="マイページ | Cardanoism", on_load=AuthState.load_mypage)
def mypage() -> rx.Component:
    return rx.box(
        login_modal(),
        rx.cond(
            AuthState.is_logged_in,
            rx.vstack(
                # ヘッダー
                rx.hstack(
                    rx.cond(
                        AuthState.avatar_url != "",
                        rx.avatar(src=AuthState.avatar_url, size="5", radius="full"),
                        rx.avatar(fallback=AuthState.username[:1], size="5", radius="full"),
                    ),
                    rx.vstack(
                        rx.heading(AuthState.username, size="5", weight="bold"),
                        rx.text(AuthState.email, size="2", color="var(--gray-9)"),
                        spacing="1",
                        align_items="start",
                    ),
                    spacing="4",
                    align="center",
                    padding_bottom="8px",
                ),
                rx.divider(),
                # タブ
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("bookmark", size=14), rx.text("お気に入り"), spacing="1"),
                            value="favorites",
                        ),
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("user", size=14), rx.text("プロフィール"), spacing="1"),
                            value="profile",
                        ),
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("wallet", size=14), rx.text("ステークアドレス"), spacing="1"),
                            value="stake",
                        ),
                        rx.tabs.trigger(
                            rx.hstack(rx.icon("bell", size=14), rx.text("通知管理"), spacing="1"),
                            value="notification",
                        ),
                        wrap="wrap",
                    ),
                    rx.tabs.content(favorites_tab(), value="favorites", padding_top="20px"),
                    rx.tabs.content(profile_tab(), value="profile", padding_top="20px"),
                    rx.tabs.content(stake_tab(), value="stake", padding_top="20px"),
                    rx.tabs.content(notification_tab(), value="notification", padding_top="20px"),
                    default_value="favorites",
                    width="100%",
                ),
                spacing="5",
                width="100%",
                align_items="start",
            ),
            # 未ログイン時（モーダルが開くまでのプレースホルダー）
            rx.center(
                rx.vstack(
                    rx.icon("lock", size=40, color="var(--gray-6)"),
                    rx.text("マイページを利用するにはログインが必要です", size="3", color="var(--gray-8)"),
                    rx.link(
                        rx.button("ログインする", size="3", cursor="pointer"),
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
