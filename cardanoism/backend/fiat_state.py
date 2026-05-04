"""
fiat_state.py
ナビバー / その他で参照する ADA 法定通貨レート用の Reflex State。

データソースは fiat_rate テーブル (id=1 固定、notify_worker.py --event fiat_sync で更新)。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import reflex as rx

from cardanoism.backend.fiat_db import get_fiat_rate

logger = logging.getLogger(__name__)


class FiatRateState(rx.State):
    ada_jpy: str = "—"
    ada_usd: str = "—"
    updated_label: str = ""

    @rx.event
    def load_rates(self):
        try:
            row = get_fiat_rate()
        except Exception as exc:
            logger.warning("fiat_rate 取得失敗: %s", exc)
            return
        if not row:
            return

        jpy = row.get("ada_jpy")
        usd = row.get("ada_usd")
        if jpy is not None:
            try:
                self.ada_jpy = f"¥{float(jpy):,.2f}"
            except (TypeError, ValueError):
                self.ada_jpy = "—"
        if usd is not None:
            try:
                self.ada_usd = f"${float(usd):,.4f}"
            except (TypeError, ValueError):
                self.ada_usd = "—"

        updated = row.get("updated_at")
        if updated is None:
            return
        try:
            if isinstance(updated, datetime):
                # MariaDB の DATETIME はサーバ TZ。表示用に HH:MM だけ取り出す。
                self.updated_label = updated.strftime("%H:%M")
            else:
                self.updated_label = str(updated)[11:16]
        except Exception:
            self.updated_label = ""
