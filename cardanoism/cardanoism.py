"""Welcome to Reflex!."""

import reflex as rx
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, Mount
from cardanoism.backend.telegram_bot import telegram_webhook, telegram_setup
from cardanoism.backend.tx_routes import get_routes as get_tx_routes

# Import all the pages.
from cardanoism.pages import *


class State(rx.State):
    """Define empty state to allow access to rx.State.router."""


def _add_custom_routes(reflex_asgi):
    """Telegram と Cardano tx 構築 API を Reflex の前段に配置する ASGI ラッパー。

    /wallet/tx/* (フロント :3000 ↔ バックエンド :8000 のクロスオリジンリクエスト
    が dev mode で発生するため CORS middleware を追加) を含む。
    """
    custom_routes = [
        Route("/telegram/webhook", telegram_webhook, methods=["POST"]),
        Route("/telegram/setup", telegram_setup, methods=["GET"]),
        # /wallet/tx/pool_delegation, /wallet/tx/drep_delegation
        *get_tx_routes(),
    ]
    middleware = [
        Middleware(
            CORSMiddleware,
            # dev mode は localhost:3000 / 同一マシン内 IP からアクセス。
            # prod は cardanoism.com (同オリジン配信想定) のみ許可。
            allow_origins=[
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "https://cardanoism.com",
            ],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        ),
    ]
    return Starlette(
        routes=[*custom_routes, Mount("", app=reflex_asgi)],
        middleware=middleware,
    )


# Google Analytics: SPA route 変更を手動追跡する
# Reflex は SPA なので、初回ロード以降の navigation では gtag の auto page_view が
# 発火しない。history.pushState / replaceState / popstate をフックして、URL が
# 変わるたびに手動で page_view イベントを送る。
_GA_TRACKING_ID = "G-EEG3K7D578"
_GA_INLINE_SCRIPT = (
    "window.dataLayer = window.dataLayer || [];"
    "function gtag(){dataLayer.push(arguments);}"
    "gtag('js', new Date());"
    # send_page_view: false で auto 発火を止め、自前で全 navigation 通知する
    f"gtag('config', '{_GA_TRACKING_ID}', {{ send_page_view: false }});"
    ""
    "function _cdnSendPageView(){"
    # title は React ルート遷移後にしか更新されないので 1 frame 遅延させる
    "  requestAnimationFrame(function(){"
    "    if (typeof gtag !== 'function') return;"
    "    gtag('event', 'page_view', {"
    "      page_path: location.pathname + location.search,"
    "      page_location: location.href,"
    "      page_title: document.title,"
    "    });"
    "  });"
    "}"
    ""
    # 初回ロード分
    "if (document.readyState === 'complete') { _cdnSendPageView(); }"
    "else { window.addEventListener('load', _cdnSendPageView); }"
    ""
    # SPA の navigation を全部捕捉
    "(function(){"
    "  const _origPush = history.pushState;"
    "  history.pushState = function(){"
    "    _origPush.apply(this, arguments);"
    "    _cdnSendPageView();"
    "  };"
    "  const _origReplace = history.replaceState;"
    "  history.replaceState = function(){"
    "    _origReplace.apply(this, arguments);"
    "    _cdnSendPageView();"
    "  };"
    "  window.addEventListener('popstate', _cdnSendPageView);"
    "})();"
)

# Create the app.
app = rx.App(
    head_components=[
        rx.script(
            src=f"https://www.googletagmanager.com/gtag/js?id={_GA_TRACKING_ID}",
            async_=True,
        ),
        rx.script(_GA_INLINE_SCRIPT),
    ],
    api_transformer=_add_custom_routes,
)
