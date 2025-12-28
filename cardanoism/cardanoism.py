"""Welcome to Reflex!."""

import reflex as rx

from cardanoism.backend.db_connect import AppState
from cardanoism.pages import *
from cardanoism.pages.proposals import _proposal_description, _proposal_title, proposal_detail_page


class State(rx.State):
    """Define empty state to allow access to rx.State.router."""


# Create the app.
app = rx.App(head_components=[
    rx.script(src="https://www.googletagmanager.com/gtag/js?id=G-EEG3K7D578"),
    rx.script("window.dataLayer = window.dataLayer || [];function gtag(){dataLayer.push(arguments);}gtag('js', new Date());gtag('config', 'G-EEG3K7D578');"),
])

app.add_page(
    proposal_detail_page,
    route="/catalyst/proposals/[proposal_id]",
    title=_proposal_title(),
    on_load=[
        AppState.load_detail_page,
        rx.call_script(
            "setTimeout(() => {"
            "  const url = window.location.href;"
            "  const image = `${window.location.origin}/cardanoism-ogp.jpg`;"
            "  const ogUrl = document.querySelector('meta[property=\"og:url\"]');"
            "  if (ogUrl) { ogUrl.setAttribute('content', url); }"
            "  const twUrl = document.querySelector('meta[name=\"twitter:url\"]');"
            "  if (twUrl) { twUrl.setAttribute('content', url); }"
            "  const ogImg = document.querySelector('meta[property=\"og:image\"]');"
            "  if (ogImg) { ogImg.setAttribute('content', image); }"
            "  const twImg = document.querySelector('meta[name=\"twitter:image\"]');"
            "  if (twImg) { twImg.setAttribute('content', image); }"
            "}, 0);"
        ),
    ],
)
