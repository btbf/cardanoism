import reflex as rx
from cardanoism.templates import template


def hero_section_text(mobile=False):
    return rx.vstack(
        rx.chakra.text(
            "Cardano Governance Japanese Potal",
            text_align="left" if not mobile else "center",
            color="#6C6C81",
            font_size=["24px", "30px", "40px", "54px", "54px", "54px"],
            font_weight="bold",
            line_height="1",
            #max_width=["200px", "300px", "400px", "650px", "650px", "650px"],
        ),
         rx.chakra.text(
            "カルダノガバナンス日本語ポータルサイト",
            text_align="left" if not mobile else "center",
            color="#6C6C81",
            font_size=["24px", "30px", "40px", "54px", "54px", "54px"],
            font_weight="bold",
            line_height="1",
            #max_width=["200px", "300px", "400px", "650px", "650px", "650px"],
        ),

        align_items="center" if mobile else "start",
        margin="20px"
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
                    "カタリストFund12提案書をチェック！",
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
                    _hover={"cursor": "pointer"},
                ),
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
                rx.chakra.alert(
                        rx.chakra.alert_icon(),
                        rx.chakra.alert_title(
                            rx.link(
                            rx.text("当プロジェクトの提案書が採択されました🎉"),
                            href="https://projectcatalyst.io/funds/12/f12-cardano-open-ecosystem",
                            is_external=True
                        ),),

                        status="info",
                        variant="top-accent",
                    ),

                rx.section(
                    rx.heading("お知らせ"),
                    rx.text("2024/07/04 カタリスト日本語ポータル　プレオープン"),
                    rx.text("2024/07/17 カタリストFund12 提案採択"),
                    padding_left="12px",
                    padding_right="12px",
                    background_color="var(--gray-2)",
                ),
                width="100%",
                margin_top="50px"
            ),
        ),
    )
