"""cookie_consent_state.py
Cookie 同意管理ステート。

GDPR / 日本版 Cookie 同意ガイドライン対応:
- localStorage で同意状態を永続化
- 13 ヶ月で同意失効 → 再表示
- ポリシー version を上げると強制再同意
- Google Consent Mode v2 (analytics_storage の granted/denied) を切替
"""
from __future__ import annotations

import json
import logging
import time

import reflex as rx

logger = logging.getLogger(__name__)


# 同意ポリシーのバージョン。値を上げると次回ロード時に再同意を要求する。
CONSENT_VERSION = 1
# 同意の有効期間 (秒)。GDPR 推奨に倣い約 13 ヶ月。
CONSENT_VALIDITY_SECONDS = 13 * 30 * 24 * 60 * 60


class CookieConsentState(rx.State):
    """Cookie 同意のセッション/ローカルストレージ管理。"""

    # localStorage に JSON 文字列で保存される同意レコード
    # 形式: {"v": 1, "ts": 1714867200, "essential": true, "functional": true, "analytics": false}
    consent_raw: str = rx.LocalStorage("", name="cardanoism_cookie_consent")

    # UI 状態
    show_banner: bool = False
    show_settings: bool = False

    # 設定モーダル内の保留中トグル状態 (保存ボタンで consent_raw に反映)
    pending_analytics: bool = False

    # ── 内部ヘルパ ──────────────────────────────────────────

    def _parse_consent(self) -> dict:
        if not self.consent_raw:
            return {}
        try:
            return json.loads(self.consent_raw)
        except Exception:  # noqa: BLE001
            return {}

    def _is_valid(self, data: dict) -> bool:
        if data.get("v") != CONSENT_VERSION:
            return False
        ts = data.get("ts", 0)
        try:
            return (time.time() - int(ts)) < CONSENT_VALIDITY_SECONDS
        except (TypeError, ValueError):
            return False

    def _save(self, *, analytics: bool) -> None:
        data = {
            "v": CONSENT_VERSION,
            "ts": int(time.time()),
            "essential": True,
            "functional": True,
            "analytics": bool(analytics),
        }
        self.consent_raw = json.dumps(data)

    def _gtag_update(self, granted: bool) -> rx.event.EventSpec:
        """gtag に同意状態を反映する JavaScript を実行する。

        承認時 (granted=True) は、`send_page_view: false` で自動 page_view が
        無効化されているため、現在ページの page_view を手動で 1 回発火する。
        これがないと、ユーザーが画面遷移するまで GA に何も送信されない。
        """
        value = "granted" if granted else "denied"
        if granted:
            return rx.call_script(
                "if (typeof gtag === 'function') {"
                f"  gtag('consent', 'update', {{ analytics_storage: '{value}', "
                f"      ad_storage: '{value}', ad_user_data: '{value}', ad_personalization: '{value}' }});"
                "  gtag('event', 'page_view', {"
                "    page_path: location.pathname + location.search,"
                "    page_location: location.href,"
                "    page_title: document.title,"
                "  });"
                "}"
            )
        return rx.call_script(
            "if (typeof gtag === 'function') {"
            f"  gtag('consent', 'update', {{ analytics_storage: '{value}', "
            f"      ad_storage: '{value}', ad_user_data: '{value}', ad_personalization: '{value}' }});"
            "}"
        )

    # ── イベントハンドラ ──────────────────────────────────────

    @rx.event
    def initialize_on_load(self):
        """ページロード時に呼び出される。同意が無効ならバナーを表示し、有効なら gtag を更新。"""
        data = self._parse_consent()
        if not self._is_valid(data):
            self.show_banner = True
            self.show_settings = False
            self.pending_analytics = False
            return None
        self.show_banner = False
        self.show_settings = False
        self.pending_analytics = bool(data.get("analytics", False))
        return self._gtag_update(self.pending_analytics)

    @rx.event
    def accept_all(self):
        self._save(analytics=True)
        self.show_banner = False
        self.show_settings = False
        self.pending_analytics = True
        return self._gtag_update(True)

    @rx.event
    def reject_non_essential(self):
        self._save(analytics=False)
        self.show_banner = False
        self.show_settings = False
        self.pending_analytics = False
        return self._gtag_update(False)

    @rx.event
    def open_settings(self):
        data = self._parse_consent()
        # 有効な同意があれば現在値、無ければ未承認 (False)
        self.pending_analytics = bool(data.get("analytics", False)) if self._is_valid(data) else False
        self.show_banner = False  # バナーは隠す
        self.show_settings = True

    @rx.event
    def close_settings(self):
        self.show_settings = False
        # 同意がまだ無ければバナーに戻る
        data = self._parse_consent()
        if not self._is_valid(data):
            self.show_banner = True

    @rx.event
    def on_settings_open_change(self, is_open: bool):
        """rx.dialog.root の on_open_change ハンドラ。is_open=False のときに閉じる処理。"""
        if not is_open:
            self.show_settings = False
            data = self._parse_consent()
            if not self._is_valid(data):
                self.show_banner = True

    @rx.event
    def set_pending_analytics(self, value: bool):
        self.pending_analytics = bool(value)

    @rx.event
    def save_settings(self):
        self._save(analytics=self.pending_analytics)
        self.show_settings = False
        self.show_banner = False
        return self._gtag_update(self.pending_analytics)
