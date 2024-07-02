import reflex as rx
from cardanoism.templates import template


def hero_section_text(mobile=False):
    return rx.vstack(
        rx.chakra.text(
            "Project Catalyst Japanese Potal",
            text_align="left" if not mobile else "center",
            color="#6C6C81",
            font_size=["24px", "30px", "40px", "54px", "54px", "54px"],
            font_weight="bold",
            line_height="1",
            #max_width=["200px", "300px", "400px", "650px", "650px", "650px"],
        ),
         rx.chakra.text(
            "カタリスト日本語ポータルサイト",
            text_align="left" if not mobile else "center",
            color="#6C6C81",
            font_size=["24px", "30px", "40px", "54px", "54px", "54px"],
            font_weight="bold",
            line_height="1",
            #max_width=["200px", "300px", "400px", "650px", "650px", "650px"],
        ),

        align_items="center" if mobile else "start",
        
    )

def hero_section_buttons(mobile=False):
    button_size={
        "padding_y": "1.5em",
        "padding_x": "2em",
        "border_radius": "8px",
        "color":"#FFFFFF",
        "align_items":"center",
        "justify_content":"center",
        "font_weight":"400",
        "font_size":"1em",
    }
    return rx.hstack(
        rx.link(
            rx.flex(
                rx.button(
                    "Fund12提案書一覧",
                    rx.icon(
                    tag="chevron-right",
                        size=18,
                        stroke_width="1px",
                        padding_left=".1em",
                    ),
                    background="linear-gradient(180deg, #6151F3 0%, #5646ED 100%)",
                    box_shadow="0px 2px 9px -4px rgba(64, 51, 192, 0.70), 0px 0px 6px 2px rgba(255, 255, 255, 0.12) inset, 0px 0px 0px 1px rgba(255, 255, 255, 0.09) inset",
                    display= "inline-flex;",   
                    border= "1px solid transparent;", 
                    style=button_size,
                ),
                _hover={
                    "border": "1px solid rgba(94, 78, 242, .15)",
                },
                border= "1px solid transparent;",
                padding="3px",
                border_radius="8px",
            ),
            href="/catalyst"        
        ),
        align_items="center",
        justify="start" if not mobile else "center",
        width="100%",
    )

@template(route="/", title="カルダノイズム | カルダノガバナンス日本語ポータルサイト")
def index() -> rx.Component:
    return rx.center(
        rx.vstack(
            hero_section_text(),
            hero_section_buttons(),
            rx.box(
                rx.section(
                    rx.heading("当サイトについて"),
                    rx.box(
                        rx.text("カルダノブロックチェーン資金調達プラットフォームの提案書を日本語で確認できるように開発されました。"),
                    ),
                    padding_left="12px",
                    padding_right="12px",
                    background_color="var(--gray-2)",
                ),
                rx.section(
                    rx.heading("投票のお願い"),
                    rx.box(
                        rx.text("当サイトは今後カルダノブロックチェーンの総合ガバナンス日本語ポータルに発展させるため、カタリストFund12に提案書を提出しております！"),
                        rx.link("当プロジェクトの提案書はこちらです", href="/catalyst/121284/"),
                        rx.text("ぜひ投票をお願いいたします。")
                        ),
                    padding_left="12px",
                    padding_right="12px",
                    background_color="var(--gray-2)",
                ),

                rx.section(
                    rx.heading("お知らせ"),
                    rx.text("2024/07/02 プレオープン"),
                    padding_left="12px",
                    padding_right="12px",
                    background_color="var(--gray-2)",
                ),
                width="100%",
                margin_top="50px"
            ),
        ),
    )
