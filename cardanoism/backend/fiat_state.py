"""
fiat_state.py
ナビバー / その他で参照する ADA 法定通貨レート用の Reflex State。

データソースは fiat_rate テーブル (id=1 固定、notify_worker.py --event fiat_sync で更新)。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import reflex as rx

from cardanoism.backend.fiat_db import get_fiat_rate

logger = logging.getLogger(__name__)

# 表示用 TZ: 日本語版は JST (UTC+9)、英語版は UTC をそのまま表示する。
_JST = timezone(timedelta(hours=9), name="JST")


class FiatRateState(rx.State):
    ada_jpy: str = "—"
    ada_usd: str = "—"
    updated_label_jst: str = ""  # 例: "14:30 JST"
    updated_label_utc: str = ""  # 例: "05:30 UTC"

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
                # MariaDB の DATETIME はサーバ TZ (UTC 前提)。
                dt_utc = updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc)
                self.updated_label_utc = dt_utc.astimezone(timezone.utc).strftime("%H:%M UTC")
                self.updated_label_jst = dt_utc.astimezone(_JST).strftime("%H:%M JST")
            else:
                # 文字列で来た場合は HH:MM 部分だけ抜き出して UTC タグ
                hhmm = str(updated)[11:16]
                self.updated_label_utc = f"{hhmm} UTC"
                self.updated_label_jst = ""
        except Exception:
            self.updated_label_jst = ""
            self.updated_label_utc = ""
