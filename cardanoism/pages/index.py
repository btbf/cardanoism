import reflex as rx
from cardanoism.templates import template
from cardanoism.backend.warmup import WarmupState



def hero_section_text(mobile=False):
    return rx.vstack(
        rx.text(
            "Cardano Governance Japanese Potal",
            text_align="left" if not mobile else "center",
            color="#6C6C81",
            font_size=["24px", "30px", "40px", "24px", "54px", "54px"],
            font_weight="bold",
            line_height="1",
            #max_width=["200px", "300px", "400px", "650px", "650px", "650px"],
        ),
         rx.text(
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
                    "カタリスト提案書をチェック！",
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

@template(route="/", title="カルダノイズム | カルダノガバナンス日本語ポータルサイト", on_load=WarmupState.warm_up_only)
def index() -> rx.Component:
    return rx.center(
        rx.vstack(
            hero_section_text(),
            hero_section_buttons(),
            rx.box(
                # rx.link(
                #     rx.callout(
                #         "利用者アンケートの回答にご協力お願いします🙇‍♂️",
                #         icon="info",
                #         color_scheme="green",
                #         size="3"
                #     ),
                #     href="https://forms.gle/NLnvYodwQky4L4BZ6",
                #     is_external=True
                # ),
                rx.section(
                    rx.heading("更新情報"),
                    rx.text("2025/10/03　Fund14提案データ反映"),
                    rx.text("2025/02/10　フィルター追加&レイアウト微調整"),
                    rx.text("2024/11/01　Fund13提案データ反映"),
                    rx.text("2024/10/28　採択プロジェクト進捗状況追加"),
                    rx.text("2024/07/18　Fund12投票結果反映"),
                    rx.text("2024/07/04　カタリスト日本語ポータル　プレオープン"),
                    rx.text("2024/07/17　カタリストFund12 提案採択"),
                    padding_left="12px",
                    padding_right="12px",
                ),
                width="100%",
                margin_top="50px"
            ),
        ),
    )
