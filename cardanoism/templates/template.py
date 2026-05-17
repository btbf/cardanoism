"""Common templates used between pages in the app."""

from __future__ import annotations

from cardanoism import styles
#from cardanoism.components.sidebar import sidebar
from cardanoism.components.navbar import navbar_icons
from cardanoism.components.footer import footer_three_columns
from cardanoism.components.cookie_banner import cookie_banner
from cardanoism.components.mobile_page_subnav import mobile_page_subnav
from cardanoism.components.auth_required_modal import auth_required_modal
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.fiat_state import FiatRateState
from cardanoism.backend.cookie_consent_state import CookieConsentState
from typing import Callable

import reflex as rx

# Meta tags for the app.
default_meta = [
    {"name": "viewport", "content": "width=device-width, shrink-to-fit=no, initial-scale=1"},
    {"property": "og:url", "content": "https://cardanoism.com"},
    {"property": "og:type", "content": "website"},
    {"property": "og:title", "content": "カルダノガバナンスを日本語でナビゲート | Cardanoism "},
    {"property": "og:description", "content": "Catalyst提案検索からCardanoの意思決定を日本語でキャッチアップし、ガバナンス・ステーキングの管理をワンストップで扱えるプラットフォームへ進化させます。"},
    {"property": "og:site_name", "content": "Cardanoism カルダノイズム"},
    {"property": "og:image", "content": "https://cardanoism.com/cardanoism-ogp.jpg"},
    {"property": "twitter:card", "content": "summary_large_image"},
]


def menu_item_link(text, href):
    return rx.menu.item(
        rx.link(
            text,
            href=href,
            width="100%",
        ),
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

        # on_load にAuthState.check_auth・言語検出・法定通貨レート読込・Cookie 同意状態を必ず含める
        _base_load = [
            AuthState.check_auth,
            AuthState.detect_browser_language,
            FiatRateState.load_rates,
            CookieConsentState.initialize_on_load,
        ]
        if on_load is None:
            combined_on_load = _base_load
        elif isinstance(on_load, list):
            combined_on_load = [*_base_load, *on_load]
        else:
            combined_on_load = [*_base_load, on_load]
        
        def templated_page():
            return rx.vstack(
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
                # スマホ専用: 各セクションのサブナビを全幅リンクで表示 (デスクトップは非表示)
                mobile_page_subnav(),
                footer_three_columns(),
                cookie_banner(),
                auth_required_modal(),
                align="start",
                position="relative",
                style={"scrollbar_gutter": "stable", "min-height": "100vh", "display": "flex", "flex_direction": "column"},
                background_color="var(--gray-1)",
            )

        @rx.page(
            route=route,
            title=title,
            description=description,
            meta=all_meta,
            on_load=combined_on_load,
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
