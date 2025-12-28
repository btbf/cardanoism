import reflex as rx

from cardanoism.templates import template
from cardanoism import styles
from cardanoism.backend.warmup import WarmupState


ACCENT = "#ffcf00"
ACCENT_DARK = "#c7a300"
TEXT_MUTED = "var(--gray-9)"
HEADINGS_FONT_CSS = f"""
<style>
h1, h2, h3, h4, h5, h6 {{
  font-family: {styles.font_family};
}}
</style>
"""


def hero_section() -> rx.Component:
    stats = rx.hstack(
        rx.hstack(rx.icon("activity", size=16, color=ACCENT_DARK), rx.text("提案データを毎日更新", size="2"), spacing="2"),
        rx.hstack(rx.icon("layers", size=16, color=ACCENT_DARK), rx.text("ガバナンス管理", size="2"), spacing="2"),
        rx.hstack(rx.icon("sparkles", size=16, color=ACCENT_DARK), rx.text("ステーキング管理", size="2"), spacing="2"),
        spacing="4",
        wrap="wrap",
        align="start",
    )

    content = rx.vstack(
        rx.text("Project Catalyst / Governance / Staking", size="2", letter_spacing="0.08em", color="var(--gray-9)"),
        rx.heading("カルダノガバナンスを日本語でナビゲート", size="7", weight="bold", line_height="1.05", as_="h1"),
        rx.text(
            "Catalyst提案検索からCardanoの意思決定を日本語でキャッチアップし、ガバナンス・ステーキングの管理をワンストップで扱えるプラットフォームへ進化させます。",
            size="4",
            color=rx.color_mode_cond("rgba(30,30,30,0.82)", "rgba(230,230,245,0.9)"),
            line_height="1.6",
            max_width="820px",
        ),
        stats,
        rx.hstack(
            rx.link(
                rx.button(
                    "Catalyst提案を探す",
                    right_icon="arrow-right",
                    size="3",
                    background=f"linear-gradient(135deg, {ACCENT}, {ACCENT_DARK})",
                    color="#111",
                    border=f"1px solid {ACCENT_DARK}",
                    cursor="pointer",
                ),
                href="/catalyst",
            ),
            rx.link(
                rx.button(
                    "Fundの動きを見る",
                    variant="soft",
                    size="3",
                    border=rx.color_mode_cond("1px solid rgba(0,0,0,0.08)", f"1px solid {ACCENT}33"),
                    cursor="pointer",
                ),
                href="/catalyst/funds",
            ),
            spacing="3",
            wrap="wrap",
        ),
        spacing="5",
        align_items="start",
        width="100%",
    )

    return rx.box(
        rx.box(
            content,
            width="100%",
            margin_x="auto",
            max_width="1280px",
            padding_x=["16px", "5vw", "8vw"],
            padding_y="25px",
        ),
        background=rx.color_mode_cond(
            "linear-gradient(135deg, #fdfcf6 0%, #f8f6ff 45%, #eef2ff 100%)",
            "linear-gradient(135deg, #111322 0%, #0d0f1c 45%, #0c0d18 100%)",
        ),
        width="100vw",
        style={
            "position": "relative",
            "left": "50%",
            "right": "50%",
            "marginLeft": "-50vw",
            "marginRight": "-50vw",
            "width": "100vw",
            "maxWidth": "100vw",
        },
    )


def feature_card(title: str, desc: str, icon: str, note: str | None = None) -> rx.Component:
    title_row = (
        rx.vstack(
            rx.heading(title, size="5", as_="h3"),
            rx.text(note, size="1", color=TEXT_MUTED),
            spacing="1",
            align_items="start",
        )
        if note
        else rx.heading(title, size="5")
    )
    return rx.box(
        rx.hstack(
            rx.box(
                rx.icon(icon, size=18, color=ACCENT_DARK),
                padding="12px",
                background_color=f"{ACCENT}2b",
                border_radius="14px",
            ),
            rx.vstack(
                title_row,
                rx.text(desc, size="3", color=TEXT_MUTED, line_height="1.6"),
                spacing="2",
                align_items="start",
                width="100%",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        padding="18px",
        border_radius="18px",
        background=rx.color_mode_cond("rgba(255,255,255,0.95)", "rgba(15,15,25,0.92)"),
        border=f"1px solid {rx.color('gray', 5)}",
        box_shadow="0 18px 40px -28px rgba(0,0,0,0.15)",
        width="100%",
    )


def feature_section() -> rx.Component:
    items = [
        ("カタリスト管理", "投票に必要なデータを集め、気になる提案をまとめて管理。", "search", "開発中"),
        ("ガバナンス管理", "カルダノガバナンスを日本語で見える化し、委任先DRepの投票状況も通知。", "layers", "2026年実装"),
        ("ステーキング管理", "委任先ステークプールの運用状況をモニタし、異変をすぐ把握。", "sparkles", "2026年実装"),
    ]
    return rx.container(
        rx.vstack(
            rx.heading("Cardanoismのコア機能", size="6", as_="h2", weight="bold"),
            rx.text("プロダクトの進化軸を3つの視点で整理しました", size="3", color=TEXT_MUTED),
            rx.hstack(
                *[feature_card(title, desc, icon, note) for title, desc, icon, note in items],
                flex_direction=["column", "column", "row"],
                spacing="4",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
        max_width="1280px",
        width="100%",
        padding_x="6",
        padding_y="32px",
    )


def roadmap_card(quarter: str, items: list[str]) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.badge(quarter, variant="solid", color_scheme="yellow", radius="full", size="2", color="#111"),
                rx.text("リリース予定", size="2", color=TEXT_MUTED),
                spacing="2",
                align="center",
            ),
            rx.vstack(
                *[
                    rx.hstack(rx.icon("check", size=14, color=ACCENT_DARK), rx.text(item, size="3"), spacing="2")
                    for item in items
                ],
                spacing="2",
                align_items="start",
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="18px",
        border_radius="16px",
        width="100%",
        background=rx.color_mode_cond("rgba(255,255,255,0.96)", "rgba(15,15,25,0.92)"),
        border=f"1px solid {rx.color('gray', 5)}",
        box_shadow="0 18px 40px -28px rgba(0,0,0,0.18)",
        align_items="start",
    )


def roadmap_entry(quarter: str, items: list[str], align_left: bool) -> rx.Component:
    card = roadmap_card(quarter, items)
    marker = rx.box(
        width="14px",
        height="14px",
        background_color=ACCENT,
        border_radius="9999px",
        border=f"2px solid {ACCENT_DARK}",
        box_shadow="0 0 0 10px rgba(255, 207, 0, 0.12)",
        margin_top="15px",
    )

    return rx.vstack(
        card,
        marker,
        spacing="2",
        align_items="center",
        width="100%",
    )


def roadmap_section() -> rx.Component:
    roadmap = {
        "2026 Q1": ["ウォレットログイン", "マイページ", "お気に入り", "英語対応"],
        "2026 Q2": ["ガバナンスアクション閲覧", "DRepリスト", "DRep委任管理"],
        "2026 Q3": ["ステーキング管理", "プールモニタリング"],
        "2026 Q4": ["シークレット"],
    }
    roadmap_items = list(roadmap.items())
    return rx.container(
        rx.vstack(
            rx.text("ロードマップ", size="6", weight="bold"),
            rx.text("クォーターごとの主要マイルストーン", size="3", color=TEXT_MUTED),
            rx.box(
                rx.vstack(
                    *[
                        roadmap_entry(quarter, items, align_left=idx % 2 == 0)
                        for idx, (quarter, items) in enumerate(roadmap_items)
                    ],
                    spacing="5",
                    width="100%",
                ),
                width="100%",
                position="relative",
                padding_y="10",
                padding_x={"base": "2", "md": "0"},
                _before={
                    "content": "''",
                    "position": "absolute",
                    "left": "50%",
                    "top": "0",
                    "bottom": "0",
                    "width": "2px",
                    "background": rx.color_mode_cond(
                        "linear-gradient(180deg, rgba(20,20,20,0), rgba(20,20,20,0.28), rgba(20,20,20,0))",
                        "linear-gradient(180deg, rgba(255,255,255,0), rgba(255,255,255,0.32), rgba(255,255,255,0))",
                    ),
                    "transform": "translateX(-1px)",
                    "opacity": "0.9",
                },
            ),
            spacing="5",
            width="100%",
        ),
        max_width="1280px",
        width="100%",
        padding_x="6",
        padding_y="32px",
    )


def updates_section() -> rx.Component:
    updates = [
        "2025/10/03　Fund14 提案データ反映",
        "2025/02/10　フィルター追加とレイアウト微調整",
        "2024/11/01　Fund13 提案データ反映",
        "2024/10/28　採択・ロジスティクス進捗追跡",
        "2024/07/18　Fund12 投票結果反映",
    ]
    return rx.container(
        rx.accordion.root(
            rx.accordion.item(
                header=rx.accordion.trigger(
                    rx.hstack(
                        rx.icon("history", size=16, color=ACCENT_DARK),
                        rx.text("最新アップデート", size="3"),
                        spacing="2",
                        align="center",
                    )
                ),
                content=rx.accordion.content(
                    rx.vstack(
                        *[
                            rx.hstack(
                                rx.box(width="6px", height="6px", border_radius="999px", background_color=ACCENT_DARK),
                                rx.text(item, size="3", color=TEXT_MUTED),
                                spacing="2",
                                align="center",
                            )
                            for item in updates
                        ],
                        spacing="2",
                        align_items="start",
                        padding_top="6px",
                    )
                ),
                value="updates",
            ),
            type="single",
            collapsible=True,
            width="100%",
            variant="soft",
        ),
        max_width="1280px",
        width="100%",
        padding_x="6",
        padding_y="12px",
    )


@template(route="/", title="カルダノガバナンス日本語ポータル | Cardanoism ", on_load=WarmupState.warm_up_only)
def index() -> rx.Component:
    return rx.box(
        rx.html(HEADINGS_FONT_CSS),
        hero_section(),
        feature_section(),
        roadmap_section(),
        updates_section(),
        spacing="6",
        width="100vw",
        max_width="100%",
    )
