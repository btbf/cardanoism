"""Welcome to Reflex!."""

# Import all the pages.
from cardanoism.pages import *

import reflex as rx


class State(rx.State):
    """Define empty state to allow access to rx.State.router."""


# Create the app.
app = rx.App(head_components=[
    rx.el.script(src="https://www.googletagmanager.com/gtag/js?id=G-EEG3K7D578"),
    rx.el.script("window.dataLayer = window.dataLayer || [];function gtag(){dataLayer.push(arguments);}gtag('js', new Date());gtag('config', 'G-EEG3K7D578');"),
])
