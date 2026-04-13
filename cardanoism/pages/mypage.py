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
    "pool_retire": "プールリタイア",
    "pool_fee_change": "手数料変更",
    "pool_saturation": "飽和ライン超過",
    "pool_pledge_shortage": "誓約不足",
    "pool_reward_received": "報酬受取",
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
                    rx.text("お気に入りはありません", size="4", color="var(--gray-8)"),
                    spacing="3",
                    align="center",
                ),
                padding_y="40px",
            ),
            rx.vstack(
                rx.foreach(AuthState.filtered_favorites, favorite_card),
                # ページネーション
                rx.hstack(
                    rx.icon_button(
                        rx.icon("chevron-left", size=16),
                        variant="soft",
                        disabled=AuthState.favorites_page <= 1,
                        on_click=AuthState.favorites_prev_page,
                        cursor="pointer",
                    ),
                    rx.text(
                        AuthState.favorites_page.to(str),
                        " / ",
                        AuthState.favorites_total_pages.to(str),
                        size="3",
                        color="var(--gray-10)",
                    ),
                    rx.icon_button(
                        rx.icon("chevron-right", size=16),
                        variant="soft",
                        disabled=AuthState.favorites_page >= AuthState.favorites_total_pages,
                        on_click=AuthState.favorites_next_page,
                        cursor="pointer",
                    ),
                    justify="center",
                    align="center",
                    spacing="3",
                    width="100%",
                    padding_top="8px",
                ),
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
            rx.text("表示名", size="3", weight="medium"),
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
            rx.text("メールアドレス", size="3", weight="medium"),
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
                    rx.text("保存しました", size="3", color="var(--green-9)"),
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
                rx.text(addr["nickname"], size="4", weight="medium"),
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
            "登録したアドレスのイベントを通知します。最大3件まで登録できます。",
            size="3",
            color="var(--gray-9)",
        ),
        # 登録済みアドレス一覧
        rx.cond(
            AuthState.is_stake_addresses_empty,
            rx.center(
                rx.text("登録されたステークアドレスはありません", size="3", color="var(--gray-8)"),
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
                rx.text("委任先情報を確認中...", size="2", color="var(--gray-8)"),
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
                    rx.text("新規登録", size="4", weight="medium"),
                    rx.vstack(
                        rx.text("ニックネーム", size="3"),
                        rx.input(
                            value=AuthState.new_stake_nickname,
                            on_change=AuthState.set_new_stake_nickname,
                            placeholder="メインウォレット",
                            size="3",
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                        align_items="start",
                    ),
                    rx.vstack(
                        rx.text("受信アドレス", size="3"),
                        rx.input(
                            value=AuthState.new_stake_address,
                            on_change=AuthState.set_new_stake_address,
                            placeholder="addr1...",
                            size="3",
                            width="100%",
                            font_family="monospace",
                        ),
                        rx.text(
                            "ウォレットの受信アドレスを入力するとステークアドレスを自動取得します",
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
                        "追加",
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
                "ステークアドレスの登録上限（3件）に達しています。",
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

def general_notification_toggle_row(event_type: str, label: str) -> rx.Component:
    """ユーザー全体の通知設定トグル行。"""
    return rx.hstack(
        rx.text(label, size="4"),
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
            rx.text(NOTIFICATION_LABELS[et], size="3"),
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
                        rx.text("委任プール", size="2", color="var(--gray-9)"),
                        rx.badge(addr["delegated_pool_name"], variant="soft", color_scheme="blue", size="1"),
                        spacing="1",
                        align="center",
                    ),
                    rx.cond(
                        addr["delegated_pool_id"],
                        rx.hstack(
                            rx.text("委任プール", size="2", color="var(--gray-9)"),
                            rx.badge(addr["delegated_pool_id"], variant="outline", color_scheme="blue", size="1", font_family="monospace"),
                            spacing="1",
                            align="center",
                        ),
                        rx.fragment(),
                    ),
                ),
                rx.cond(
                    (addr["role"] == "delegator") & addr["delegated_drep_name"],
                    rx.hstack(
                        rx.text("委任DRep", size="2", color="var(--gray-9)"),
                        rx.badge(addr["delegated_drep_name"], variant="soft", color_scheme="amber", size="1"),
                        spacing="1",
                        align="center",
                    ),
                    rx.cond(
                        (addr["role"] == "delegator") & addr["delegated_drep_id"],
                        rx.hstack(
                            rx.text("委任DRep", size="2", color="var(--gray-9)"),
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
                    rx.text("委任プール", size="2", color="var(--gray-9)"),
                    rx.badge(addr["delegated_pool_name"], variant="soft", color_scheme="blue", size="1"),
                    spacing="1",
                    align="center",
                ),
                rx.cond(
                    addr["delegated_pool_id"],
                    rx.hstack(
                        rx.text("委任プール", size="2", color="var(--gray-9)"),
                        rx.badge(addr["delegated_pool_id"], variant="outline", color_scheme="blue", size="1", font_family="monospace"),
                        spacing="1",
                        align="center",
                    ),
                    rx.fragment(),
                ),
            ),
            # プール通知
            rx.text("ステークプール通知", size="3", weight="bold", color="var(--gray-10)"),
            rx.cond(
                addr["delegated_pool_id"],
                rx.vstack(
                    *_toggle_rows(addr_id_str, POOL_NOTIFICATION_EVENT_TYPES),
                    spacing="1",
                    width="100%",
                    align_items="start",
                ),
                rx.text(
                    "ステークプールに委任していないため、プール関連の通知はありません",
                    size="3",
                    color="var(--gray-8)",
                ),
            ),
            rx.divider(margin_y="8px"),
            # ガバナンス通知（ロール別）
            rx.hstack(
                rx.text("ガバナンス通知", size="3", weight="bold", color="var(--gray-10)"),
                rx.cond(
                    addr["role"] == "drep",
                    rx.badge("DRep", color_scheme="amber", size="1"),
                    rx.cond(
                        addr["role"] == "abstain",
                        rx.badge("棄権", color_scheme="red", size="1"),
                        rx.badge("委任者", color_scheme="gray", size="1"),
                    ),
                ),
                spacing="2",
                align="center",
            ),
            # 委任先情報（アコーディオン内）
            rx.cond(
                (addr["role"] == "delegator") & addr["delegated_drep_name"],
                rx.hstack(
                    rx.text("委任DRep", size="2", color="var(--gray-9)"),
                    rx.badge(addr["delegated_drep_name"], variant="soft", color_scheme="amber", size="1"),
                    spacing="1",
                    align="center",
                ),
                rx.cond(
                    (addr["role"] == "delegator") & addr["delegated_drep_id"],
                    rx.hstack(
                        rx.text("委任DRep", size="2", color="var(--gray-9)"),
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
                            "ガバナンス投票を棄権中のため、DRep関連の通知はありません",
                            size="3",
                            color="var(--gray-8)",
                        ),
                        rx.text(
                            "Cardanoは分散型ガバナンスへ移行しており、トレジャリーの使途や各種提案はDRepの投票によって決まります。あなたのADAも、1ADA＝1票としてその意思決定に活かすことができます。まだ委任していない方は、ぜひDRepへの委任をご検討ください。",
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
                                "DRepに委任していないため、DRep関連の通知はありません",
                                size="3",
                                color="var(--gray-8)",
                            ),
                            rx.text(
                                "Cardanoは分散型ガバナンスへ移行しており、トレジャリーの使途や各種提案はDRepの投票によって決まります。あなたのADAも、1ADA＝1票としてその意思決定に活かすことができます。まだ委任していない方は、ぜひDRepへの委任をご検討ください。",
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


def notification_tab() -> rx.Component:
    return rx.vstack(
        # LINE連携セクション
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("message-circle", size=18, color="#06C755"),
                    rx.text("LINE通知連携", size="4", weight="bold"),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    AuthState.is_logged_in,
                    rx.text("LINEログインで連携済みです。通知を受け取るには、Cardanoism公式LINEアカウントを友だち追加してください。", size="3", color="var(--gray-9)"),
                    rx.link(
                        rx.button("LINEと連携する", size="3", cursor="pointer"),
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
                    size="3",
                    color="var(--gray-8)",
                ),
                padding="16px",
                border_radius="10px",
                border=f"1px solid {rx.color('gray', 4)}",
                width="100%",
            ),
            rx.box(
                rx.vstack(
                    rx.text("アドレスごとの通知設定", size="4", weight="bold"),
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
                rx.text("一般通知", size="4", weight="bold"),
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
                        rx.text(AuthState.email, size="3", color="var(--gray-9)"),
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
                            rx.hstack(rx.icon("wallet", size=14), rx.text("アドレス"), spacing="1"),
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
                    value=AuthState.active_tab,
                    on_change=AuthState.set_active_tab,
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
                    rx.text("マイページを利用するにはログインが必要です", size="4", color="var(--gray-8)"),
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
