"""Welcome to Reflex!."""

import reflex as rx
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from cardanoism.backend.telegram_bot import telegram_webhook, telegram_setup

# Import all the pages.
from cardanoism.pages import *


class State(rx.State):
    """Define empty state to allow access to rx.State.router."""


def _add_telegram_routes(reflex_asgi):
    """Telegram エンドポイントを Reflex の前段に配置する ASGI ラッパー。"""
    return Starlette(routes=[
        Route("/telegram/webhook", telegram_webhook, methods=["POST"]),
        Route("/telegram/setup", telegram_setup, methods=["GET"]),
        Mount("", app=reflex_asgi),
    ])


# Create the app.
app = rx.App(
    head_components=[
        rx.script(
            src="https://www.googletagmanager.com/gtag/js?id=G-EEG3K7D578",
            async_=True,
        ),
        rx.script(
            "window.dataLayer = window.dataLayer || [];"
            "function gtag(){dataLayer.push(arguments);}"
            "gtag('js', new Date());"
            "gtag('config', 'G-EEG3K7D578');"
        ),
    ],
    api_transformer=_add_telegram_routes,
)
