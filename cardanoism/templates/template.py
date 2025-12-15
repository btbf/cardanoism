"""Common templates used between pages in the app."""

from __future__ import annotations

from cardanoism import styles
#from cardanoism.components.sidebar import sidebar
from cardanoism.components.navbar import navbar_icons
from cardanoism.components.footer import footer_three_columns
from typing import Callable

import reflex as rx

# Palette tuned to new logo colors
CUSTOM_COLORS = """
:root {
  /* Light mode */
  --color-primary-100: #073ff4;  /* ロゴ濃紺 */ バッジ文字色
  --color-primary-200: #0071C9;  /* ロゴライトブルー */
  --color-primary-300: #f5f4f1;  /* ホバー/アクセント用の少し明るいブルー */
  --color-text-100:    #444444;  /* メインテキストカラー */
  --color-text-200:    #4c4c4c;  /* サブテキストカラー */
  --color-text-300:    #707070;  /* サブテキストカラー2 */
  --color-accent-text: #ffcf00;  /* ロゴカラー色 */
  --color-bg-100:      #fcfcfc;
  --color-bg-200:      #F6F8FB;
  --color-bg-300:      #D8DDE5;
  --color-bg-accent:   #808080;  /* 見出し背景グレー */
  --color-border:      #D8DDE5;
}
[data-theme="dark"] {
  /* Dark mode */
  --color-primary-100: #0071C9;  /* ロゴブルーを軸に */
  --color-primary-200: #4FA9FF;  /* 明るめブルー（ホバー） */
  --color-primary-300: #1A2635;  /* 低彩度の濃紺 */
  --color-text-100:    #444444;  /* メインテキストカラー */
  --color-text-200:    #999999;  /* サブテキストカラー */
  --color-text-300:    #CCCCCC;  /* サブテキストカラー2 */
  --color-bg-100:      #000000;
  --color-bg-200:      #0B121C;
  --color-bg-300:      #1A2630;
  --color-border:      #1F2A38;
}
body {
  background-color: var(--color-bg-100);
  color: var(--color-text-100);
}
"""
# Meta tags for the app.
default_meta = [
    {
        "name": "viewport",
        "content": "width=device-width, shrink-to-fit=no, initial-scale=1",
    },
]

google_tags =[rx.script("""
<script async src="https://www.googletagmanager.com/gtag/js?id=G-EEG3K7D578"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());

gtag('config', 'G-EEG3K7D578');
</script>
""")]


def menu_item_link(text, href):
    return rx.menu.item(
        rx.link(
            text,
            href=href,
            width="100%",
            color="inherit",
        ),
        _hover={
            "color": styles.accent_color,
            "background_color": styles.accent_text_color,
        },
    )


def menu_button() -> rx.Component:
    """The menu button on the top right of the page.

    Returns:
        The menu button component.
    """
    from reflex.page import get_decorated_pages

    return rx.box(
        rx.menu.root(
            rx.menu.trigger(
                rx.button(
                    rx.icon("menu"),
                    variant="soft",
                )
            ),
            rx.menu.content(
                *[
                    menu_item_link(page["title"], page["route"])
                    for page in get_decorated_pages()
                ],
                rx.menu.separator(),
                menu_item_link("About", "https://github.com/reflex-dev"),
                menu_item_link("Contact", "mailto:founders@=reflex.dev"),
            ),
        ),
        position="fixed",
        right="2em",
        top="2em",
        z_index="500",
    )


class ThemeState(rx.State):
    """The state for the theme of the app."""

    accent_color: str = "indigo"

    gray_color: str = "gray"


def template(
    route: str | None = None,
    title: str | None = None,
    description: str | None = None,
    meta: str | None = None,
    script_tags: list[rx.Component] | None = None,
    on_load: rx.event.EventHandler | list[rx.event.EventHandler] | None = None,
) -> Callable[[Callable[[], rx.Component]], rx.Component]:
    """The template for each page of the app.

    Args:
        route: The route to reach the page.
        title: The title of the page.
        description: The description of the page.
        meta: Additionnal meta to add to the page.
        head_components: googleAnalytics.
        on_load: The event handler(s) called when the page load.
        script_tags: Scripts to attach to the page.


    Returns:
        The template with the page content.
    """
    
    def decorator(page_content: Callable[[], rx.Component]) -> rx.Component:
        """The template for each page of the app.

        Args:
            page_content: The content of the page.

        Returns:
            The template with the page content.
        """
        # Get the meta tags for the page.
        all_meta = [*default_meta, *(meta or [])]
        
        def templated_page():
            return rx.vstack(
                rx.html(f"<style>{CUSTOM_COLORS}</style>") if CUSTOM_COLORS else rx.fragment(),
                # sidebar(),
                navbar_icons(),
                rx.box(
                    rx.box(
                        page_content(),
                        **styles.template_content_style,
                        width="100%",
                    ),
                    **styles.template_page_style,
                ),
                footer_three_columns(),
                #menu_button(),
                align="start",
                background=rx.color_mode_cond(
                    "var(--color-bg-100)",
                    "var(--color-bg-100)",
                ),
                position="relative",
                style={"scrollbar_gutter": "stable"},
            )

        @rx.page(
            route=route,
            title=title,
            description=description,
            meta=all_meta,
            script_tags=script_tags,
            on_load=on_load,
            
        )
        def theme_wrap():
            return rx.theme(
                templated_page(),
                appearance="inherit",
                has_background=True,
                accent_color=ThemeState.accent_color,
                gray_color=ThemeState.gray_color,
            )

        return theme_wrap

    return decorator
