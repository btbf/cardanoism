"""ウォレット接続関連の UI コンポーネント。

公開関数:
- wallet_connector_mount() : window.cardanoismWallet API をページに inject + bootstrap
- wallet_status()          : ナビバー右側の「接続中」ピル (未接続時は何も出さない)
- wallet_picker_menu(trig) : 任意のトリガから対応ウォレット一覧を開くドロップダウン
- wallet_connect_pill(addr): 指定 stake address に対する接続/検証状態
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.wallet_state import WalletState
from cardanoism_wallet import wallet_module_script


_WALLET_CSS = """
<style>
@keyframes cdn_wallet_pulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(34,197,94,0.22), 0 0 0 0 rgba(34,197,94,0); }
  50%      { box-shadow: 0 0 0 5px rgba(34,197,94,0.08), 0 0 0 9px rgba(34,197,94,0.0); }
}
.cdn-wallet-pill {
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.15s ease, box-shadow 0.18s ease;
}
.cdn-wallet-pill:hover {
  transform: translateY(-1px);
}
</style>
"""


# 対応ウォレットの一覧 (表示順)
# (key, label, platform_hint)
_WALLET_DEFS: list[tuple[str, str, str]] = [
    ("eternl",      "Eternl", "PC / Mobile"),
    ("lace",        "Lace",   "PC / Mobile"),
    ("yoroi",       "Yoroi",  "PC / Mobile"),
    ("typhoncip30", "Typhon", "PC"),
    ("tokeo",       "Tokeo",  "PC / Mobile"),
    ("vespr",       "VESPR",  "Mobile"),
]


# ── 内部ヘルパー ────────────────────────────────────────────


def _wallet_menu_item(
    wallet_key: str,
    label: str,
    platform_hint: str,
    target_address=""
) -> rx.Component:
    is_available = WalletState.available_wallets.contains(wallet_key)
    return rx.menu.item(
        rx.hstack(
            rx.icon("wallet", size=14),
            rx.vstack(
                rx.text(label, size="2", weight="medium"),
                rx.text(platform_hint, size="1", color="var(--gray-10)"),
                spacing="0",
                align_items="start",
            ),
            rx.spacer(),
            rx.cond(
                is_available,
                rx.box(
                    rx.text("検出済み", size="1", color="var(--green-11)", weight="medium"),
                    padding="2px 8px",
                    border_radius="999px",
                    background="var(--green-3)",
                ),
                rx.box(
                    rx.text("未インストール", size="1", color="var(--gray-10)"),
                    padding="2px 8px",
                    border_radius="999px",
                    background="var(--gray-3)",
                ),
            ),
            spacing="2", align="center", width="100%",
        ),
        on_click=WalletState.connect_wallet(wallet_key, target_address),
        disabled=~is_available,
        cursor=rx.cond(is_available, "pointer", "not-allowed"),
        opacity=rx.cond(is_available, "1", "0.55"),
    )


def _menu_content(target_address="") -> rx.Component:
    return rx.menu.content(
        *[
            _wallet_menu_item(key, label, hint, target_address)
            for key, label, hint in _WALLET_DEFS
        ],
        min_width="240px",
    )


def _wallet_register_menu_item(
    wallet_key: str, label: str, platform_hint: str
) -> rx.Component:
    """新規登録用のメニュー項目 (fetch_for_register を呼ぶ)。"""
    is_available = WalletState.available_wallets.contains(wallet_key)
    return rx.menu.item(
        rx.hstack(
            rx.icon("wallet", size=14),
            rx.vstack(
                rx.text(label, size="2", weight="medium"),
                rx.text(platform_hint, size="1", color="var(--gray-10)"),
                spacing="0",
                align_items="start",
            ),
            rx.spacer(),
            rx.cond(
                is_available,
                rx.box(
                    rx.text("検出済み", size="1", color="var(--green-11)", weight="medium"),
                    padding="2px 8px",
                    border_radius="999px",
                    background="var(--green-3)",
                ),
                rx.box(
                    rx.text("未インストール", size="1", color="var(--gray-10)"),
                    padding="2px 8px",
                    border_radius="999px",
                    background="var(--gray-3)",
                ),
            ),
            spacing="2", align="center", width="100%",
        ),
        on_click=WalletState.fetch_for_register(wallet_key),
        disabled=~is_available,
        cursor=rx.cond(is_available, "pointer", "not-allowed"),
        opacity=rx.cond(is_available, "1", "0.55"),
    )


def _menu_content_for_register() -> rx.Component:
    return rx.menu.content(
        *[
            _wallet_register_menu_item(key, label, hint)
            for key, label, hint in _WALLET_DEFS
        ],
        min_width="240px",
    )


def _connected_button() -> rx.Component:
    """接続中ウォレットを示す pill。glass morphism + ライブパルス。"""
    return rx.box(
        rx.hstack(
            # ライブパルスドット
            rx.box(
                width="8px",
                height="8px",
                border_radius="999px",
                background="#22c55e",
                style={"animation": "cdn_wallet_pulse 2.4s ease-in-out infinite"},
                flex_shrink="0",
            ),
            # ウォレット名 (太字) + 短縮 reward addr (monospace, faded)
            rx.vstack(
                rx.text(
                    WalletState.wallet_label,
                    color="var(--gray-12)",
                    style={
                        "fontSize": "12px",
                        "fontWeight": "700",
                        "lineHeight": "1.1",
                        "letterSpacing": "0.02em",
                    },
                ),
                rx.text(
                    WalletState.reward_address_short,
                    color="var(--gray-10)",
                    style={
                        "fontFamily": "ui-monospace, SFMono-Regular, monospace",
                        "fontSize": "10px",
                        "lineHeight": "1.1",
                    },
                ),
                spacing="0",
                align_items="start",
            ),
            rx.icon("chevron-down", size=14, color="var(--gray-10)"),
            spacing="3",
            align="center",
        ),
        class_name="cdn-wallet-pill",
        padding="6px 12px 6px 12px",
        border_radius="999px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond(
            "linear-gradient(135deg, rgba(255,255,255,0.85), rgba(255,255,255,0.55))",
            "linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02))",
        ),
        cursor="pointer",
        style={
            "backdropFilter": "blur(10px)",
            "WebkitBackdropFilter": "blur(10px)",
        },
        _hover={
            "border_color": rx.color("gray", 8),
            "box_shadow": rx.color_mode_cond(
                "0 6px 18px -8px rgba(0,0,0,0.18)",
                "0 6px 18px -8px rgba(0,0,0,0.6)",
            ),
        },
    )


def _connected_menu() -> rx.Component:
    return rx.menu.root(
        rx.menu.trigger(_connected_button()),
        rx.menu.content(
            rx.menu.item(
                rx.hstack(
                    rx.icon("badge-info", size=14),
                    rx.vstack(
                        rx.text("接続中", size="1", color="var(--gray-10)"),
                        rx.text(WalletState.wallet_label, size="2", weight="medium"),
                        spacing="0", align_items="start",
                    ),
                    spacing="2", align="center",
                ),
                disabled=True,
            ),
            rx.menu.separator(),
            rx.menu.item(
                rx.hstack(
                    rx.icon("log-out", size=14),
                    rx.text("切断", size="2"),
                    spacing="2", align="center",
                ),
                on_click=WalletState.disconnect_wallet,
                cursor="pointer",
                color="var(--red-11)",
            ),
        ),
    )


# ── 公開関数 ────────────────────────────────────────────────


def wallet_picker_menu(trigger: rx.Component, target_address="") -> rx.Component:
    """任意のトリガからウォレット選択ドロップダウンを開く汎用 picker。

    target_address を指定すると、ウォレットが返してきた reward と一致しない場合に
    接続を拒否してユーザにアカウント切替を促す (per-card の接続ボタンで使用)。
    """
    return rx.menu.root(
        rx.menu.trigger(trigger),
        _menu_content(target_address),
    )


def wallet_register_picker_menu(trigger: rx.Component) -> rx.Component:
    """新規ステークアドレス登録フォーム用 picker。

    ウォレットを選択するとアドレスを取得して登録フォームを自動入力する。
    現状の WalletState の接続状態 (`connected` 等) は変更しない。
    """
    return rx.menu.root(
        rx.menu.trigger(trigger),
        _menu_content_for_register(),
    )


def wallet_connector_mount() -> rx.Component:
    """window.cardanoismWallet API をページに inject。

    `navbar_icons()` の最上位に置いて全ページで常時生存させる。
    マウント時に検出 + 自動再接続を試みる。

    LucidProvider が `@lucid-evolution/lucid` を npm から import し
    `window.__cardanoismLucid` に publish する。Vite の optimizeDeps.exclude
    で pre-bundling が回避されるので WASM 依存も runtime で正しくロードされる。
    """
    return rx.fragment(
        # CSS (pulse keyframes 等) を inject
        rx.html(_WALLET_CSS),
        # ウォレット制御 JS モジュールを <script> として注入
        rx.script(wallet_module_script()),
        # 検出 + auto reconnect トリガ用の不可視ボックス
        rx.box(
            on_mount=WalletState.bootstrap,
            display="none",
        ),
    )


def wallet_status() -> rx.Component:
    """ナビバー右側の接続中ピル。未接続時は何も出さない。"""
    return rx.cond(
        WalletState.connected,
        _connected_menu(),
        rx.fragment(),
    )


def wallet_connect_pill(addr) -> rx.Component:
    """登録 stake address カードに対する接続/検証状態表示。

    検証済みバッジ (左) と 接続状態の操作 (右) を並列に表示する。
    検証済みでも未接続なら再接続ボタンを出す。
    """
    stake_address = addr["address"]
    is_verified = addr["verified"].to(bool)
    is_this_connected = (
        WalletState.connected & (WalletState.reward_address == stake_address)
    )
    is_busy = WalletState.verifying_address == stake_address

    verified_badge = rx.hstack(
        rx.icon("shield-check", size=12, color="var(--green-11)"),
        rx.text("検証済み", size="1", color="var(--green-11)", weight="medium"),
        spacing="2",
        align="center",
        padding="4px 10px",
        border_radius="999px",
        background="var(--green-3)",
        border="1px solid var(--green-5)",
    )

    # 接続中ウォレット名バッジ (例: "● Eternl")
    wallet_badge = rx.hstack(
        rx.box(
            width="6px", height="6px",
            border_radius="999px",
            background="var(--green-9)",
        ),
        rx.icon("wallet", size=11, color="var(--gray-11)"),
        rx.text(
            WalletState.wallet_label,
            size="1", color="var(--gray-12)", weight="medium",
        ),
        spacing="2",
        align="center",
        padding="4px 10px",
        border_radius="999px",
        background="var(--gray-3)",
        border="1px solid var(--gray-5)",
    )

    verify_button = rx.button(
        rx.cond(is_busy, rx.spinner(size="1"), rx.icon("shield-check", size=12)),
        rx.text(
            rx.cond(is_busy, "署名待ち…", "ウォレットで検証"),
            size="1",
        ),
        size="1",
        variant="soft",
        color_scheme="green",
        cursor="pointer",
        disabled=is_busy,
        on_click=WalletState.request_verify(stake_address),
    )

    connect_button = rx.button(
        rx.icon("wallet", size=12),
        rx.text("ウォレット接続", size="1"),
        size="1",
        variant="soft",
        color_scheme="amber",
        cursor="pointer",
    )

    # 接続状態に応じた表示
    # - 接続中: ウォレット名バッジ + (未検証なら検証ボタン / 検証済みなら省略)
    # - 未接続: ウォレット接続ボタン (picker)
    connection_part = rx.cond(
        is_this_connected,
        rx.hstack(
            wallet_badge,
            rx.cond(is_verified, rx.fragment(), verify_button),
            spacing="2",
            align="center",
            wrap="wrap",
        ),
        wallet_picker_menu(connect_button, target_address=stake_address),
    )

    return rx.hstack(
        rx.cond(is_verified, verified_badge, rx.fragment()),
        connection_part,
        spacing="2",
        align="center",
        wrap="wrap",
    )
