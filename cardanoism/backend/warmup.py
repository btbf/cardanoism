import reflex as rx
from cardanoism.backend.db_connect import ensure_warm


class WarmupState(rx.State):
    """Minimal state to expose a warm-up event for on_load."""

    def warm_up_only(self):
        ensure_warm()
