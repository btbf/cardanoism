"""
auth_state.py
LINE OAuthフロー・セッション管理・マイページデータを一元管理するReflex State

セッショントークンは rx.LocalStorage で永続化する。
（FastAPIルート不要・Reflexページだけで完結）
"""
import os
import re
import secrets
import logging
from urllib.parse import urlparse, parse_qs

import reflex as rx

from cardanoism.backend.koios import detect_stake_role, get_stake_address_from_addr
from cardanoism.backend.auth_db import (
    get_user_by_session,
    get_or_create_user_by_line,
    create_session,
    delete_session,
    update_user_profile,
    get_stake_addresses,
    add_stake_address,
    update_stake_address_role,
    delete_stake_address,
    get_favorite_ids,
    get_favorites,
    add_favorite,
    remove_favorite,
    get_notification_settings,
    update_notification_setting,
    update_notification_frequency,
    get_stake_notification_settings,
    update_stake_notification_setting,
    update_language,
    update_line_id,
    get_user_by_line_id,
)

logger = logging.getLogger(__name__)

LINE_CLIENT_ID = os.getenv("LINE_CLIENT_ID", "")
LINE_CLIENT_SECRET = os.getenv("LINE_CLIENT_SECRET", "")
LINE_REDIRECT_URI = os.getenv("LINE_REDIRECT_URI", "")


class AuthState(rx.State):
    """ログイン状態・ユーザー情報・OAuthフローを管理するグローバルState。"""

    # セッショントークン（LocalStorageで永続化）
    session_token: str = rx.LocalStorage("")

    # ユーザー基本情報
    user_id: int = 0
    username: str = ""
    avatar_url: str = ""
    email: str = ""
    line_id: str = ""
    is_logged_in: bool = False

    # LINE OAuth CSRF用 state
    oauth_state: str = ""
    oauth_mode: str = "login"  # "login" | "connect"

    # プロフィール編集用
    edit_username: str = ""
    edit_email: str = ""
    edit_avatar_url: str = ""
    profile_saved: bool = False

    # ステークアドレス
    stake_addresses: list[dict] = []
    new_stake_address: str = ""
    new_stake_nickname: str = ""
    stake_error: str = ""
    stake_adding: bool = False
    stake_role_loading: bool = False
    active_tab: str = "favorites"

    # お気に入り（catalyst）
    favorites: list[dict] = []
    favorite_ids: list[str] = []  # カード表示用のUUIDリスト
    favorites_fund_filter: str = "all"
    favorites_status_filter: str = "all"
    favorites_sort: str = "amount_desc"
    favorites_page: int = 1

    # ユーザー全体の通知設定（epoch_start など）
    notification_settings: dict[str, bool] = {}
    notification_frequency: str = "instant"

    # ステークアドレスごとの通知設定
    # key: "{stake_address_id}:{event_type}", value: bool
    stake_notification_settings: dict[str, bool] = {}

    # 言語設定
    language: str = "ja"
    _lang_manually_set: bool = False  # ユーザーが手動切替したか（自動検出を上書きしない）

    # ログインモーダル表示フラグ
    show_login_modal: bool = False

    # コールバック処理中のエラー
    auth_error: str = ""

    # ============================================================
    # 認証チェック
    # ============================================================

    # ============================================================
    # 多言語対応
    # ============================================================

    @rx.var
    def t(self) -> dict[str, str]:
        """UI テキスト辞書（言語に応じて切り替わる）。"""
        from cardanoism.backend.i18n import UI_EN, UI_JA
        return UI_EN if self.language == "en" else UI_JA

    @rx.var
    def notification_labels(self) -> dict[str, str]:
        """通知イベントラベル辞書（言語に応じて切り替わる）。"""
        from cardanoism.backend.i18n import NOTIFICATION_LABELS_EN, NOTIFICATION_LABELS_JA
        return NOTIFICATION_LABELS_EN if self.language == "en" else NOTIFICATION_LABELS_JA

    def set_language(self, lang: str):
        """ユーザーが手動で言語を切り替える（自動検出より優先）。"""
        if lang not in ("ja", "en"):
            return
        self.language = lang
        self._lang_manually_set = True
        if self.is_logged_in:
            update_language(self.user_id, lang)

    def on_browser_language_detected(self, browser_lang: str):
        """rx.call_script のコールバック。手動切替済みなら無視。"""
        if self._lang_manually_set or self.is_logged_in:
            return
        detected = "ja" if (browser_lang or "").lower().startswith("ja") else "en"
        self.language = detected

    def detect_browser_language(self):
        """ブラウザの優先言語を取得して言語設定に反映する。"""
        if self._lang_manually_set or self.is_logged_in:
            return
        return rx.call_script(
            "navigator.language || navigator.languages?.[0] || 'ja'",
            callback=AuthState.on_browser_language_detected,
        )

    # ============================================================
    # 認証チェック
    # ============================================================

    def check_auth(self):
        """session_token（LocalStorage）からユーザー情報をStateに反映する。"""
        if not self.session_token:
            self.is_logged_in = False
            return

        user = get_user_by_session(self.session_token)
        if user:
            self.user_id = user["id"]
            self.username = user["username"]
            self.avatar_url = user.get("avatar_url") or ""
            self.email = user.get("email") or ""
            self.line_id = user.get("line_id") or ""
            self.notification_frequency = user.get("notification_frequency") or "instant"
            self.language = user.get("language") or "ja"
            self.is_logged_in = True
            self.favorite_ids = [s for s in get_favorite_ids(self.user_id) if isinstance(s, str) and s]
        else:
            # 期限切れ or 無効
            self.session_token = ""
            self.is_logged_in = False

    def open_login_modal(self):
        self.show_login_modal = True

    def close_login_modal(self):
        self.show_login_modal = False

    # ============================================================
    # LINE OAuth フロー
    # ============================================================

    def start_line_login(self):
        """LINE認証ページへリダイレクトする。"""
        state = secrets.token_urlsafe(16)
        self.oauth_state = state
        self.oauth_mode = "login"

        auth_url = (
            "https://access.line.me/oauth2/v2.1/authorize"
            f"?response_type=code"
            f"&client_id={LINE_CLIENT_ID}"
            f"&redirect_uri={LINE_REDIRECT_URI}"
            f"&state={state}"
            f"&scope=profile%20openid%20email"
        )
        return rx.redirect(auth_url)

    def start_line_connect(self):
        """LINE通知連携用OAuth（ログイン済みユーザー専用）。"""
        if not self.is_logged_in:
            self.show_login_modal = True
            return
        state = secrets.token_urlsafe(16)
        self.oauth_state = state
        self.oauth_mode = "connect"

        auth_url = (
            "https://access.line.me/oauth2/v2.1/authorize"
            f"?response_type=code"
            f"&client_id={LINE_CLIENT_ID}"
            f"&redirect_uri={LINE_REDIRECT_URI}"
            f"&state={state}"
            f"&scope=profile"
        )
        return rx.redirect(auth_url)

    def handle_line_callback(self):
        """
        /auth/line/callback の on_load で呼ばれる。
        URLのクエリパラメータからcode・stateを取得してOAuth処理を行う。
        """
        import requests as http_requests

        # クエリパラメータを解析
        raw_path = self.router.page.raw_path
        parsed = urlparse(raw_path)
        params = parse_qs(parsed.query)

        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        error = params.get("error", [""])[0]

        if error:
            self.auth_error = "LINEログインがキャンセルされました"
            return rx.redirect("/login?error=line_denied")

        # state検証（CSRF対策）
        if not state or state != self.oauth_state:
            logger.warning("OAuth state mismatch: got=%s expected=%s", state, self.oauth_state)
            self.auth_error = "セキュリティエラーが発生しました"
            return rx.redirect("/login?error=state_mismatch")

        if not code:
            self.auth_error = "認証コードが取得できませんでした"
            return rx.redirect("/login?error=no_code")

        # アクセストークン取得
        try:
            token_resp = http_requests.post(
                "https://api.line.me/oauth2/v2.1/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": LINE_REDIRECT_URI,
                    "client_id": LINE_CLIENT_ID,
                    "client_secret": LINE_CLIENT_SECRET,
                },
                timeout=10,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
        except Exception as e:
            logger.error("Token exchange failed: %s", e)
            self.auth_error = "LINEとの認証に失敗しました"
            return rx.redirect("/login?error=token_error")

        access_token = token_data.get("access_token")
        if not access_token:
            self.auth_error = "アクセストークンが取得できませんでした"
            return rx.redirect("/login?error=token_error")

        # プロフィール取得
        try:
            profile_resp = http_requests.get(
                "https://api.line.me/v2/profile",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            profile_resp.raise_for_status()
            profile = profile_resp.json()
        except Exception as e:
            logger.error("Profile fetch failed: %s", e)
            self.auth_error = "LINEプロフィールの取得に失敗しました"
            return rx.redirect("/login?error=profile_error")

        line_id = profile.get("userId", "")
        display_name = profile.get("displayName", "LINEユーザー")
        picture_url = profile.get("pictureUrl", "")

        if not line_id:
            dest = "/mypage?tab=notification&error=no_user_id" if self.oauth_mode == "connect" else "/login?error=no_user_id"
            self.oauth_state = ""
            return rx.redirect(dest)

        # ── connect モード: 現在のユーザーに line_id を紐付ける ──
        if self.oauth_mode == "connect":
            self.oauth_state = ""
            self.oauth_mode = "login"
            if not self.is_logged_in:
                return rx.redirect("/login")
            existing = get_user_by_line_id(line_id)
            if existing and existing["id"] != self.user_id:
                return rx.redirect("/mypage?tab=notification&error=line_already_linked")
            try:
                update_line_id(self.user_id, line_id)
                self.line_id = line_id
            except Exception as e:
                logger.error("update_line_id failed: %s", e)
                return rx.redirect("/mypage?tab=notification&error=db_error")
            return rx.redirect("/mypage?tab=notification&connected=line")

        # ── login モード: ユーザー取得 or 作成 ──
        try:
            user = get_or_create_user_by_line(line_id, display_name, picture_url)
        except Exception as e:
            logger.error("DB error: %s", e)
            return rx.redirect("/login?error=db_error")

        try:
            token = create_session(user["id"])
        except Exception as e:
            logger.error("Session creation failed: %s", e)
            return rx.redirect("/login?error=session_error")

        self.session_token = token
        self.user_id = user["id"]
        self.username = user["username"]
        self.avatar_url = user.get("avatar_url") or ""
        self.email = user.get("email") or ""
        self.line_id = user.get("line_id") or line_id
        self.language = user.get("language") or "ja"
        self.is_logged_in = True
        self.oauth_state = ""
        self.oauth_mode = "login"

        return rx.redirect("/mypage")

    def logout(self):
        """ログアウト処理。"""
        if self.session_token:
            try:
                delete_session(self.session_token)
            except Exception as e:
                logger.warning("Failed to delete session: %s", e)

        self.session_token = ""
        self.is_logged_in = False
        self.user_id = 0
        self.username = ""
        self.avatar_url = ""
        self.email = ""
        self.line_id = ""
        return rx.redirect("/")

    # ============================================================
    # プロフィール編集
    # ============================================================

    def load_profile(self):
        self.edit_username = self.username
        self.edit_email = self.email
        self.edit_avatar_url = self.avatar_url
        self.profile_saved = False

    def set_edit_username(self, value: str):
        self.edit_username = value

    def set_edit_email(self, value: str):
        self.edit_email = value

    def set_edit_avatar_url(self, value: str):
        self.edit_avatar_url = value

    def save_profile(self):
        if not self.is_logged_in:
            return
        update_user_profile(
            self.user_id,
            self.edit_username,
            self.edit_email or None,
            self.edit_avatar_url or None,
        )
        self.username = self.edit_username
        self.email = self.edit_email
        self.avatar_url = self.edit_avatar_url
        self.profile_saved = True

    # ============================================================
    # ステークアドレス
    # ============================================================

    def load_stake_addresses(self):
        if self.is_logged_in:
            self.stake_addresses = get_stake_addresses(self.user_id)
            self.stake_error = ""

    def set_new_stake_address(self, value: str):
        self.new_stake_address = value
        self.stake_error = ""

    def set_new_stake_nickname(self, value: str):
        self.new_stake_nickname = value

    async def add_stake_address_handler(self):
        if not self.is_logged_in:
            return
        input_addr = self.new_stake_address.strip()
        nickname = self.new_stake_nickname.strip()
        # フォーマットのみ即時バリデーション（API不要）
        from cardanoism.backend.i18n import get_ui as _get_ui
        _t = _get_ui(self.language)
        if not input_addr or not nickname:
            self.stake_error = _t["err_addr_required"]
            return
        if not input_addr.startswith("addr") and not _is_valid_stake_address(input_addr):
            self.stake_error = _t["err_invalid_addr"]
            return
        # ここで即時 yield → ボタンがローディング状態になる
        self.stake_error = ""
        self.stake_adding = True
        yield
        # --- 以降は UI 更新後に実行 ---
        wallet_address = None
        if input_addr.startswith("addr"):
            address = get_stake_address_from_addr(input_addr)
            if not address:
                self.stake_error = _t["err_stake_not_found"]
                self.stake_adding = False
                return
            wallet_address = input_addr
        else:
            address = input_addr
        result = add_stake_address(self.user_id, address, nickname, wallet_address)
        self.stake_adding = False
        if result == "ok":
            self.new_stake_address = ""
            self.new_stake_nickname = ""
            self.stake_addresses = get_stake_addresses(self.user_id)
            self._load_stake_notification_settings()
            self.stake_role_loading = True
            yield  # アドレスを即時表示
            # Koios API でロール・プール・DRep情報を取得
            new_entry = next((a for a in self.stake_addresses if a["address"] == address), None)
            if new_entry:
                info = detect_stake_role(address)
                update_stake_address_role(
                    new_entry["id"],
                    info["role"],
                    info.get("drep_id"),
                    info.get("drep_name"),
                    info.get("pool_id"),
                    info.get("pool_name"),
                )
                self.stake_addresses = get_stake_addresses(self.user_id)
            self.stake_role_loading = False
        elif result == "duplicate":
            self.stake_error = _t["err_duplicate"]
        else:
            self.stake_error = _t["err_limit"]

    def delete_stake_address_handler(self, address_id: int):
        if not self.is_logged_in:
            return
        delete_stake_address(address_id, self.user_id)
        self.stake_addresses = get_stake_addresses(self.user_id)
        self._load_stake_notification_settings()

    def _load_stake_notification_settings(self):
        """全ステークアドレスの通知設定をフラットなdictに展開する。"""
        flat: dict[str, bool] = {}
        for addr in self.stake_addresses:
            addr_id = addr["id"]
            settings = get_stake_notification_settings(addr_id)
            for event_type, enabled in settings.items():
                flat[f"{addr_id}:{event_type}"] = enabled
        self.stake_notification_settings = flat

    def toggle_stake_notification(self, key: str):
        """key = "{stake_address_id}:{event_type}" でON/OFFを切り替える。"""
        if not self.is_logged_in:
            return
        parts = key.split(":", 1)
        if len(parts) != 2:
            return
        stake_address_id = int(parts[0])
        event_type = parts[1]
        current = self.stake_notification_settings.get(key, True)
        new_value = not current
        update_stake_notification_setting(stake_address_id, event_type, new_value)
        self.stake_notification_settings = {**self.stake_notification_settings, key: new_value}

    # ============================================================
    # お気に入り
    # ============================================================

    def toggle_favorite(self, proposal_uuid: str):
        """カード上のハートボタンからお気に入りをトグルする。"""
        if not self.is_logged_in:
            self.show_login_modal = True
            return
        if not proposal_uuid:
            return
        if proposal_uuid in self.favorite_ids:
            # UIを先に更新してからDB操作
            self.favorite_ids = [uid for uid in self.favorite_ids if uid != proposal_uuid]
            yield
            remove_favorite(self.user_id, proposal_uuid, "catalyst")
        else:
            self.favorite_ids = self.favorite_ids + [proposal_uuid]
            yield
            add_favorite(self.user_id, proposal_uuid, "catalyst")
        # マイページ表示中のみ同期
        if self.favorites:
            self.favorites = get_favorites(self.user_id, "catalyst")

    def load_favorites(self):
        if self.is_logged_in:
            self.favorites = get_favorites(self.user_id, "catalyst")

    def set_favorites_fund_filter(self, value: str):
        self.favorites_fund_filter = value
        self.favorites_page = 1

    def set_favorites_status_filter(self, value: str):
        self.favorites_status_filter = value
        self.favorites_page = 1

    def set_favorites_sort(self, value: str):
        self.favorites_sort = value
        self.favorites_page = 1

    def favorites_prev_page(self):
        if self.favorites_page > 1:
            self.favorites_page -= 1

    def favorites_next_page(self):
        if self.favorites_page < self.favorites_total_pages:
            self.favorites_page += 1

    def remove_favorite_handler(self, proposal_uuid: str):
        if not self.is_logged_in:
            return
        remove_favorite(self.user_id, proposal_uuid, "catalyst")
        self.favorite_ids = [uid for uid in self.favorite_ids if uid != proposal_uuid]
        self.load_favorites()

    @rx.var
    def filtered_favorites_all(self) -> list[dict]:
        """フィルター・ソート済みの全件リスト（ページネーション前）。"""
        items = list(self.favorites)
        if self.favorites_fund_filter and self.favorites_fund_filter != "all":
            items = [f for f in items if str(f.get("fund_label", "")) == self.favorites_fund_filter]
        if self.favorites_status_filter and self.favorites_status_filter != "all":
            items = [f for f in items if str(f.get("funding_status", "")) == self.favorites_status_filter]
        if self.favorites_sort == "amount_desc":
            items.sort(key=lambda f: f.get("amount_requested") or 0, reverse=True)
        elif self.favorites_sort == "amount_asc":
            items.sort(key=lambda f: f.get("amount_requested") or 0)
        return items

    @rx.var
    def filtered_favorites(self) -> list[dict]:
        """現在ページ分のみ返す。"""
        start = (self.favorites_page - 1) * 10
        return self.filtered_favorites_all[start:start + 10]

    @rx.var
    def favorites_total_pages(self) -> int:
        return max(1, (len(self.filtered_favorites_all) + 9) // 10)

    @rx.var
    def is_favorites_empty(self) -> bool:
        return len(self.filtered_favorites_all) == 0

    @rx.var
    def is_stake_addresses_empty(self) -> bool:
        return len(self.stake_addresses) == 0

    @rx.var
    def stake_addresses_count(self) -> int:
        return len(self.stake_addresses)

    # ============================================================
    # 通知設定
    # ============================================================

    def disconnect_line(self):
        """LINE通知連携を解除する。"""
        if not self.is_logged_in:
            return
        update_line_id(self.user_id, None)
        self.line_id = ""

    def load_notification_settings(self):
        if self.is_logged_in:
            self.notification_settings = get_notification_settings(self.user_id)

    def toggle_notification(self, event_type: str):
        if not self.is_logged_in:
            return
        current = self.notification_settings.get(event_type, True)
        new_value = not current
        update_notification_setting(self.user_id, event_type, new_value)
        self.notification_settings = {**self.notification_settings, event_type: new_value}

    def set_notification_frequency(self, frequency: str):
        if not self.is_logged_in:
            return
        update_notification_frequency(self.user_id, frequency)
        self.notification_frequency = frequency

    # ============================================================
    # マイページ初期ロード
    # ============================================================

    def load_mypage(self):
        """マイページ on_load: 認証確認 + 全データ読み込み。"""
        self.check_auth()
        if not self.is_logged_in:
            self.show_login_modal = True
            return
        self.load_profile()
        self.stake_addresses = get_stake_addresses(self.user_id)
        self.favorites = get_favorites(self.user_id, "catalyst")
        self.notification_settings = get_notification_settings(self.user_id)
        self._load_stake_notification_settings()
        # ?tab= クエリパラメータでタブを指定できる
        valid_tabs = {"favorites", "profile", "stake", "notification"}
        tab = self.router.page.params.get("tab", "favorites")
        self.active_tab = tab if tab in valid_tabs else "favorites"


# bech32のデータ部で使用できる文字（小文字のみ）
_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
# stake1  + 53文字 = 59文字（メインネット）
# stake_test1 + 53文字 = 64文字（テストネット）
_STAKE_ADDR_RE = re.compile(
    r"^stake(?:_test)?1[" + _BECH32_CHARSET + r"]{6,}$"
)


def _is_valid_stake_address(address: str) -> bool:
    """Cardano ステークアドレスの簡易バリデーション（bech32形式チェック）。"""
    addr = address.strip().lower()
    if not _STAKE_ADDR_RE.match(addr):
        return False
    # メインネット: 59文字、テストネット: 64文字
    if addr.startswith("stake_test1"):
        return len(addr) == 64
    return len(addr) == 59
