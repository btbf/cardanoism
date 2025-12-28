"""Common templates used between pages in the app."""

from __future__ import annotations

from cardanoism import styles
#from cardanoism.components.sidebar import sidebar
from cardanoism.components.navbar import navbar_icons
from cardanoism.components.footer import footer_three_columns
from typing import Callable

import reflex as rx

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
        ),
    )


def render_page(content: rx.Component) -> rx.Component:
    return rx.theme(
        rx.vstack(
            # sidebar(),
            navbar_icons(),
            rx.box(
                rx.box(
                    content,
                    **styles.template_content_style,
                    width="100%",
                ),
                **styles.template_page_style,
            ),
            footer_three_columns(),
            align="start",
            position="relative",
            style={
                "scrollbar_gutter": "stable",
                "min-height": "100vh",
                "display": "flex",
                "flex_direction": "column",
            },
            background_color="var(--gray-1)",
        ),
        appearance="inherit",
        has_background=True,
        accent_color="amber",
        gray_color="slate",
    )


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
            return render_page(page_content())

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
                accent_color="amber",
                gray_color="slate",
            )

        return theme_wrap

    return decorator
