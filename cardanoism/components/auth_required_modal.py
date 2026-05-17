"""auth_required_modal.py

委任前のウォレット認証が必要なユーザーに表示する誘導モーダル。

表示トリガー: 各ページの「委任する」ボタンクリック時 (未認証時のみ)
  - 開く: AuthState.open_auth_required_modal
  - 閉じる: AuthState.close_auth_required_modal (X / Escape / overlay クリック)

CTA: 「アドレス管理を開く」→ /mypage?tab=stake へ遷移
template.py で全ページに mount する。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState


def _step_row(num: str, label) -> rx.Component:
    """ステップ表示: [番号バッジ] テキスト の横並び 1 行。"""
    return rx.hstack(
        rx.box(
            rx.text(num, size="2", weight="bold", color="var(--amber-11)"),
            style={
                "minWidth": "26px",
                "height": "26px",
                "borderRadius": "999px",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "background": rx.color_mode_cond("var(--amber-3)", "rgba(245,158,11,0.14)"),
                "border": "1px solid",
                "borderColor": rx.color_mode_cond("var(--amber-6)", "rgba(245,158,11,0.30)"),
            },
        ),
        rx.text(label, size="3", color="var(--gray-12)", style={"lineHeight": "1.6"}),
        spacing="3", align="center", width="100%",
    )


def auth_required_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            # 右上の X 閉じる (absolute で常に最前面に固定)
            rx.box(
                rx.dialog.close(
                    rx.icon_button(
                        rx.icon("x", size=16),
                        variant="ghost",
                        color_scheme="gray",
                        size="2",
                        cursor="pointer",
                        on_click=AuthState.close_auth_required_modal,
                    ),
                ),
                style={
                    "position": "absolute",
                    "top": "12px",
                    "right": "12px",
                    "zIndex": 10,
                },
            ),
            rx.vstack(
                # ヒーロー: アイコン + タイトル + 説明 (中央寄せ)
                rx.vstack(
                    rx.box(
                        rx.icon("shield-check", size=26, color="var(--amber-11)"),
                        style={
                            "width": "56px",
                            "height": "56px",
                            "borderRadius": "16px",
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "background": rx.color_mode_cond(
                                "linear-gradient(135deg, var(--amber-2), var(--amber-3))",
                                "linear-gradient(135deg, rgba(245,158,11,0.12), rgba(245,158,11,0.04))",
                            ),
                            "border": "1px solid",
                            "borderColor": rx.color_mode_cond("var(--amber-5)", "rgba(245,158,11,0.20)"),
                        },
                    ),
                    rx.dialog.title(
                        rx.text(
                            AuthState.t["auth_required_modal_title"],
                            size="6", weight="bold", color="var(--gray-12)",
                            text_align="center",
                            style={"letterSpacing": "0.005em"},
                        ),
                        style={"margin": "0", "textAlign": "center"},
                    ),
                    rx.dialog.description(
                        rx.text(
                            AuthState.t["auth_required_modal_desc"],
                            size="3", color="var(--gray-11)",
                            text_align="center",
                            style={"lineHeight": "1.75", "maxWidth": "400px"},
                        ),
                        style={"margin": "0"},
                    ),
                    spacing="3", align="center", width="100%",
                ),
                # 3 ステップガイド (薄カード)
                rx.vstack(
                    _step_row("1", AuthState.t["auth_required_step_1"]),
                    _step_row("2", AuthState.t["auth_required_step_2"]),
                    _step_row("3", AuthState.t["auth_required_step_3"]),
                    spacing="3",
                    width="100%",
                    padding="16px 18px",
                    border_radius="12px",
                    background=rx.color_mode_cond("var(--gray-2)", "rgba(255,255,255,0.03)"),
                    border="1px solid",
                    border_color=rx.color_mode_cond("var(--gray-4)", "rgba(255,255,255,0.06)"),
                ),
                # アクション: キャンセル (ghost) + 主 CTA (gradient)
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            AuthState.t["auth_required_modal_close"],
                            variant="ghost", size="3",
                            color="var(--gray-10)",
                            cursor="pointer",
                            on_click=AuthState.close_auth_required_modal,
                        ),
                    ),
                    rx.spacer(),
                    rx.link(
                        rx.button(
                            rx.text(
                                AuthState.t["auth_required_modal_button"],
                                weight="bold", size="3",
                            ),
                            rx.icon("arrow-right", size=16),
                            size="3",
                            color_scheme="amber",
                            variant="solid",
                            cursor="pointer",
                            style={"borderRadius": "8px", "padding": "0 20px"},
                            on_click=AuthState.close_auth_required_modal,
                        ),
                        href="/mypage?tab=stake",
                        underline="none",
                    ),
                    width="100%",
                    align="center",
                ),
                spacing="5",
                align="stretch",
                width="100%",
                # 上は X 用のスペース、左右と下は通常パディング
                padding="20px 4px 4px",
            ),
            max_width="500px",
            # X を absolute 配置するため relative にする
            style={"position": "relative"},
        ),
        open=AuthState.show_auth_required_modal,
        on_open_change=AuthState.close_auth_required_modal,
    )
