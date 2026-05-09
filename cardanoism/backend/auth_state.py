"""
auth_state.py
ログイン状態・ユーザー情報・OAuthフロー・マイページデータを管理するReflex State
"""
import os
import re
import secrets
import logging
import hmac
import hashlib
import base64
import time as _time
from urllib.parse import urlparse, parse_qs

import reflex as rx

from cardanoism.backend.koios import detect_stake_role, get_stake_address_from_addr
from cardanoism.backend.auth_db import (
    get_user_by_session,
    get_or_create_user_by_provider,
    get_user_providers,
    create_session,
    delete_session,
    update_user_profile,
    get_stake_addresses,
    add_stake_address,
    update_stake_address_role,
    delete_stake_address,
    update_stake_address_nickname,
    detect_spo_pool_id,
    update_stake_address_spo,
    get_favorite_ids,
    get_favorites,
    add_favorite,
    remove_favorite,
    get_ga_favorites,
    get_notification_settings,
    update_notification_setting,
    update_notification_frequency,
    get_stake_notification_settings,
    update_stake_notification_setting,
    update_language,
    get_notification_channels,
    upsert_notification_channel,
    set_channel_enabled,
    remove_notification_channel,
)

logger = logging.getLogger(__name__)

LINE_CLIENT_ID = os.getenv("LINE_CLIENT_ID", "")
LINE_CLIENT_SECRET = os.getenv("LINE_CLIENT_SECRET", "")
LINE_REDIRECT_URI = os.getenv("LINE_REDIRECT_URI", "")


def _env(key: str) -> str:
    """環境変数を呼び出し時に取得する。"""
    return os.getenv(key, "")


# ── OAuth state 署名 ──────────────────────────────────────────────
# Reflex State (server-side session) に依存しない HMAC 署名で CSRF を検証する。
# モバイルで LINE Universal Link 等により WebView を跨ぐと session が切れて
# self.oauth_state が失われ state_mismatch になる問題を回避する。
_OAUTH_STATE_SECRET = (
    os.getenv("OAUTH_STATE_SECRET")
    or os.getenv("LINE_CLIENT_SECRET")
    or os.getenv("GOOGLE_CLIENT_SECRET")
    or "_dev-fallback-do-not-use_"
)
_OAUTH_STATE_TTL_SECONDS = 600  # 10 分以内のコールバックのみ受け付ける


def _make_signed_state(provider: str, mode: str = "login") -> str:
    """形式: provider.mode.timestamp.nonce.signature

    HMAC-SHA256 で署名するためサーバ State を持たずに検証可能。
    """
    timestamp = int(_time.time())
    nonce = secrets.token_urlsafe(8)
    payload = f"{provider}.{mode}.{timestamp}.{nonce}"
    sig = hmac.new(
        _OAUTH_STATE_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"{payload}.{sig}"


def _verify_signed_state(state: str, expected_provider: str) -> tuple[bool, str]:
    """state を検証。戻り値: (valid, mode)。失敗時は (False, "")。"""
    if not state:
        return False, ""
    parts = state.split(".")
    if len(parts) != 5:
        return False, ""
    provider, mode, ts_str, nonce, sig = parts
    if provider != expected_provider:
        return False, ""
    try:
        ts = int(ts_str)
    except ValueError:
        return False, ""
    if int(_time.time()) - ts > _OAUTH_STATE_TTL_SECONDS:
        return False, ""
    payload = f"{provider}.{mode}.{ts}.{nonce}"
    expected_sig = hmac.new(
        _OAUTH_STATE_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected_sig):
        return False, ""
    return True, mode


def _derive_twitter_verifier_from_nonce(nonce: str) -> str:
    """Twitter PKCE の code_verifier を nonce から決定的に導出する。

    同じ nonce + 同じ secret → 同じ verifier なので、コールバック時に
    state からだけで verifier を再現できる (Reflex State 不要)。
    """
    seed = hmac.new(
        _OAUTH_STATE_SECRET.encode(),
        f"twitter-verifier.{nonce}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(seed).rstrip(b"=").decode()  # 43 chars (RFC 7636)


def _make_twitter_state_and_verifier() -> tuple[str, str]:
    """Twitter login 開始時の (state, code_verifier) を生成。

    state は signed state (provider=twitter)、verifier は nonce から派生。
    """
    timestamp = int(_time.time())
    nonce = secrets.token_urlsafe(16)
    payload = f"twitter.login.{timestamp}.{nonce}"
    sig = hmac.new(
        _OAUTH_STATE_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:16]
    state = f"{payload}.{sig}"
    verifier = _derive_twitter_verifier_from_nonce(nonce)
    return state, verifier


def _verify_twitter_state(state: str) -> tuple[bool, str]:
    """state を検証し、対応する code_verifier を返す。

    戻り値: (valid, code_verifier)。失敗時は (False, "")。
    """
    valid, _mode = _verify_signed_state(state, "twitter")
    if not valid:
        return False, ""
    parts = state.split(".")
    if len(parts) != 5:
        return False, ""
    nonce = parts[3]
    return True, _derive_twitter_verifier_from_nonce(nonce)


class AuthState(rx.State):
    """ログイン状態・ユーザー情報・OAuthフローを管理するグローバルState。"""

    # セッショントークン（LocalStorageで永続化）
    session_token: str = rx.LocalStorage("")

    # ユーザー基本情報
    user_id: int = 0
    username: str = ""
    avatar_url: str = ""
    email: str = ""
    is_logged_in: bool = False

    # 認証プロバイダ（どのSNSでログインしているか）
    auth_providers: list[str] = []  # ["line", "google", "twitter"]

    # 通知チャンネル
    line_notify_channel: str = ""    # LINE通知送信先 (LINE user ID)
    email_notify_channel: str = ""   # メール通知送信先
    telegram_chat_id: str = ""       # Telegram chat ID
    telegram_reload_msg: str = ""    # リロード結果メッセージ
    line_notify_enabled: bool = True
    email_notify_enabled: bool = True
    telegram_notify_enabled: bool = True

    # OAuth CSRF用 state（全プロバイダ共通）
    oauth_state: str = ""
    _twitter_code_verifier: str = ""  # Twitter PKCE用（バックエンド専用）

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
    # ニックネーム編集中の stake_address.id (0 = 編集中なし)
    editing_stake_id: int = 0
    editing_stake_nickname: str = ""
    # ダッシュボード「報酬実績」用: バックグラウンドで報酬履歴を取得中か
    rewards_backfilling: bool = False
    active_tab: str = "dashboard"

    # サブスクリプション表示用 (Phase 0 - 表示のみ、変更操作は将来)
    subscription_tier:           str = ""
    subscription_status:         str = ""
    subscription_billing_cycle:  str = ""
    subscription_started_at:     str = ""
    subscription_period_end:     str = ""


    # お気に入り（catalyst）
    favorites: list[dict] = []
    favorite_ids: list[str] = []
    favorites_fund_filter: str = "all"
    favorites_status_filter: str = "all"
    favorites_sort: str = "amount_desc"
    favorites_page: int = 1
    favorites_category: str = "catalyst"  # "catalyst" | "governance"

    # お気に入り（governance）
    ga_favorites: list[dict] = []
    ga_favorite_ids: list[str] = []
    ga_favorites_page: int = 1

    # 通知設定（イベントON/OFF）
    notification_settings: dict[str, bool] = {}
    notification_frequency: str = "instant"

    # ステークアドレスごとの通知設定
    stake_notification_settings: dict[str, bool] = {}

    # 言語設定
    language: str = "ja"
    _lang_manually_set: bool = False

    # ログインモーダル
    show_login_modal: bool = False

    # コールバックエラー
    auth_error: str = ""

    # ============================================================
    # 多言語対応
    # ============================================================

    @rx.var
    def t(self) -> dict[str, str]:
        from cardanoism.backend.i18n import UI_EN, UI_JA
        return UI_EN if self.language == "en" else UI_JA

    @rx.var
    def notification_labels(self) -> dict[str, str]:
        from cardanoism.backend.i18n import NOTIFICATION_LABELS_EN, NOTIFICATION_LABELS_JA
        return NOTIFICATION_LABELS_EN if self.language == "en" else NOTIFICATION_LABELS_JA

    @rx.var
    def funding_status_options(self) -> list[dict]:
        if self.language == "en":
            return [
                {"value": "funded", "label": "Funded"},
                {"value": "not_approved", "label": "Not Approved"},
                {"value": "over_budget", "label": "Over Budget"},
                {"value": "pending", "label": "Pending Vote"},
            ]
        return [
            {"value": "funded", "label": "採択"},
            {"value": "not_approved", "label": "不採択"},
            {"value": "over_budget", "label": "申請不備"},
            {"value": "pending", "label": "投票期間中"},
        ]

    @rx.var
    def project_status_options(self) -> list[dict]:
        if self.language == "en":
            return [
                {"value": "in_progress", "label": "In Progress"},
                {"value": "complete", "label": "Complete"},
            ]
        return [
            {"value": "in_progress", "label": "進行中"},
            {"value": "complete", "label": "完了"},
        ]

    @rx.var
    def gov_type_options(self) -> list[dict]:
        if self.language == "en":
            return [
                {"value": "ParameterChange",     "label": "Protocol Change"},
                {"value": "TreasuryWithdrawals",  "label": "Treasury Withdrawals"},
                {"value": "HardForkInitiation",   "label": "Hard Fork"},
                {"value": "InfoAction",           "label": "Info Action"},
                {"value": "NewCommittee",         "label": "Committee Change"},
                {"value": "NewConstitution",      "label": "New Constitution"},
                {"value": "NoConfidence",         "label": "No Confidence"},
            ]
        return [
            {"value": "ParameterChange",     "label": "プロトコル変更"},
            {"value": "TreasuryWithdrawals",  "label": "国庫引き出し"},
            {"value": "HardForkInitiation",   "label": "ハードフォーク"},
            {"value": "InfoAction",           "label": "情報提案"},
            {"value": "NewCommittee",         "label": "委員会変更"},
            {"value": "NewConstitution",      "label": "新憲法"},
            {"value": "NoConfidence",         "label": "不信任"},
        ]

    @rx.var
    def gov_status_options(self) -> list[dict]:
        if self.language == "en":
            return [
                {"value": "active",   "label": "Active"},
                {"value": "ratified", "label": "Ratified"},
                {"value": "enacted",  "label": "Enacted"},
                {"value": "expired",  "label": "Expired"},
                {"value": "dropped",  "label": "Dropped"},
            ]
        return [
            {"value": "active",   "label": "アクティブ"},
            {"value": "ratified", "label": "批准済み"},
            {"value": "enacted",  "label": "施行済み"},
            {"value": "expired",  "label": "失効"},
            {"value": "dropped",  "label": "廃止"},
        ]

    def set_language(self, lang: str):
        if lang not in ("ja", "en"):
            return
        self.language = lang
        self._lang_manually_set = True
        if self.is_logged_in:
            update_language(self.user_id, lang)

    def on_browser_language_detected(self, browser_lang: str):
        if self._lang_manually_set or self.is_logged_in:
            return
        detected = "ja" if (browser_lang or "").lower().startswith("ja") else "en"
        # 同値ならスキップ — 代入すると t (@rx.var) が無効化されて全 i18n 依存
        # コンポーネントが再レンダーされる (= 2 秒遅れの flicker の原因)
        if self.language != detected:
            self.language = detected

    def detect_browser_language(self):
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
        """session_token からユーザー情報を復元する。"""
        if not self.session_token:
            self.is_logged_in = False
            return

        user = get_user_by_session(self.session_token)
        if user:
            self.user_id = user["id"]
            self.username = user["username"]
            self.avatar_url = user.get("avatar_url") or ""
            self.email = user.get("email") or ""
            self.notification_frequency = user.get("notification_frequency") or "instant"
            self.language = user.get("language") or "ja"
            self.is_logged_in = True
            self.favorite_ids = [s for s in get_favorite_ids(self.user_id) if isinstance(s, str) and s]
            self.ga_favorite_ids = [s for s in get_favorite_ids(self.user_id, "governance") if isinstance(s, str) and s]
            self._load_providers_and_channels()
        else:
            self.session_token = ""
            self.is_logged_in = False

    def _load_providers_and_channels(self):
        """プロバイダ一覧と通知チャンネルを state に反映する。"""
        providers = get_user_providers(self.user_id)
        self.auth_providers = [p["provider"] for p in providers]

        self.line_notify_channel = ""
        self.email_notify_channel = ""
        self.telegram_chat_id = ""
        self.line_notify_enabled = True
        self.email_notify_enabled = True
        self.telegram_notify_enabled = True

        for ch in get_notification_channels(self.user_id):
            if ch["channel_type"] == "line":
                self.line_notify_channel = ch["channel_value"]
                self.line_notify_enabled = bool(ch["enabled"])
            elif ch["channel_type"] == "email":
                self.email_notify_channel = ch["channel_value"]
                self.email_notify_enabled = bool(ch["enabled"])
            elif ch["channel_type"] == "telegram":
                self.telegram_chat_id = ch["channel_value"]
                self.telegram_notify_enabled = bool(ch["enabled"])

        # メールアドレスが登録済みなのにチャンネルがない場合は自動作成
        if self.email and not self.email_notify_channel:
            upsert_notification_channel(self.user_id, "email", self.email)
            self.email_notify_channel = self.email
            self.email_notify_enabled = True

    def _apply_login(self, user: dict, session_token: str):
        """ログイン後の state をまとめてセットする。"""
        self.session_token = session_token
        self.user_id = user["id"]
        self.username = user["username"]
        self.avatar_url = user.get("avatar_url") or ""
        self.email = user.get("email") or ""
        self.notification_frequency = user.get("notification_frequency") or "instant"
        self.language = user.get("language") or "ja"
        self.is_logged_in = True
        self.oauth_state = ""
        self._load_providers_and_channels()

    def open_login_modal(self):
        self.show_login_modal = True

    def close_login_modal(self):
        self.show_login_modal = False

    # ============================================================
    # LINE OAuth フロー
    # ============================================================

    def start_line_login(self):
        """LINE認証ページへリダイレクトする。"""
        state_param = _make_signed_state("line", "login")

        auth_url = (
            "https://access.line.me/oauth2/v2.1/authorize"
            f"?response_type=code"
            f"&client_id={LINE_CLIENT_ID}"
            f"&redirect_uri={LINE_REDIRECT_URI}"
            f"&state={state_param}"
            f"&scope=profile%20openid%20email"
        )
        return rx.redirect(auth_url)

    def start_line_connect(self):
        """LINE通知連携用OAuth（ログイン済みユーザー専用）。"""
        if not self.is_logged_in and self.session_token:
            self.check_auth()
        if not self.is_logged_in:
            self.show_login_modal = True
            return
        state_param = _make_signed_state("line", "connect")

        auth_url = (
            "https://access.line.me/oauth2/v2.1/authorize"
            f"?response_type=code"
            f"&client_id={LINE_CLIENT_ID}"
            f"&redirect_uri={LINE_REDIRECT_URI}"
            f"&state={state_param}"
            f"&scope=profile"
        )
        return rx.redirect(auth_url)

    def handle_line_callback(self):
        """LINE OAuth コールバック処理。state パラメータに mode を埋め込む。"""
        import requests as http_requests

        raw_path = self.router.page.raw_path
        parsed = urlparse(raw_path)
        params = parse_qs(parsed.query)

        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        error = params.get("error", [""])[0]

        if error:
            self.auth_error = "LINEログインがキャンセルされました"
            return rx.redirect("/login?error=line_denied")

        # HMAC 署名 state を検証 (Reflex State 不要なので WebView 切替でも壊れない)
        valid, oauth_mode = _verify_signed_state(state, "line")
        if not valid:
            logger.warning("LINE OAuth state invalid (HMAC mismatch or expired): %s", state[:24])
            # mode 不明なので login 側にリダイレクト（connect 失敗もほぼここ）
            return rx.redirect("/login?error=state_mismatch")

        if not code:
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
            logger.error("LINE token exchange failed: %s", e)
            return rx.redirect("/login?error=token_error")

        access_token = token_data.get("access_token")
        if not access_token:
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
            logger.error("LINE profile fetch failed: %s", e)
            return rx.redirect("/login?error=profile_error")

        line_id = profile.get("userId", "")
        display_name = profile.get("displayName", "LINEユーザー")
        picture_url = profile.get("pictureUrl", "")

        if not line_id:
            dest = "/mypage?tab=notification&error=no_user_id" if oauth_mode == "connect" else "/login?error=no_user_id"
            self.oauth_state = ""
            return rx.redirect(dest)

        # ── connect モード: 通知チャンネルのみ更新 ──
        if oauth_mode == "connect":
            self.oauth_state = ""
            user_id = self.user_id
            if not user_id and self.session_token:
                db_user = get_user_by_session(self.session_token)
                if db_user:
                    user_id = db_user["id"]
                    self.user_id = user_id
                    self.is_logged_in = True
            if not user_id:
                return rx.redirect("/login?error=session_expired")
            try:
                upsert_notification_channel(user_id, "line", line_id)
                self.line_notify_channel = line_id
                self.line_notify_enabled = True
            except Exception as e:
                logger.error("upsert_notification_channel failed: %s", e)
                return rx.redirect("/mypage?tab=notification&error=db_error")
            return rx.redirect("/mypage?tab=notification&connected=line")

        # ── login モード: ユーザー取得 or 作成 ──
        try:
            user = get_or_create_user_by_provider("line", line_id, display_name, picture_url)
        except Exception as e:
            logger.error("DB error: %s", e)
            return rx.redirect("/login?error=db_error")

        # 既存ユーザーでも LINE 通知チャンネルを確実に登録する
        try:
            upsert_notification_channel(user["id"], "line", line_id)
        except Exception as e:
            logger.warning("LINE notification channel upsert failed: %s", e)

        try:
            token = create_session(user["id"])
        except Exception as e:
            logger.error("Session creation failed: %s", e)
            return rx.redirect("/login?error=session_error")

        self._apply_login(user, token)
        return rx.redirect("/mypage")

    def disconnect_line(self):
        """LINE通知チャンネルを解除する。"""
        if not self.is_logged_in:
            return
        remove_notification_channel(self.user_id, "line")
        self.line_notify_channel = ""

    def start_telegram_connect(self):
        """Telegram 連携用の一時トークンを生成して Bot へのリンクにリダイレクトする。"""
        if not self.is_logged_in:
            self.show_login_modal = True
            return
        from cardanoism.backend.auth_db import create_telegram_token
        import os
        bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "")
        if not bot_username:
            logger.warning("TELEGRAM_BOT_USERNAME が未設定です")
            return
        token = create_telegram_token(self.user_id)
        return rx.redirect(f"https://t.me/{bot_username}?start={token}", is_external=True)

    def disconnect_telegram(self):
        """Telegram 通知チャンネルを解除する。"""
        if not self.is_logged_in:
            return
        remove_notification_channel(self.user_id, "telegram")
        self.telegram_chat_id = ""

    def reload_telegram_channel(self):
        """Telegram連携後にDBから最新チャンネル情報を再取得する。"""
        if not self.is_logged_in:
            return
        prev = self.telegram_chat_id
        self._load_providers_and_channels()
        if self.telegram_chat_id:
            self.telegram_reload_msg = ""
        else:
            self.telegram_reload_msg = "まだ連携が確認できません。BotでStartを送信してからお試しください。"

    # ============================================================
    # Google OAuth フロー
    # ============================================================

    def start_google_login(self):
        """Google認証ページへリダイレクトする。"""
        state_param = _make_signed_state("google", "login")

        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?response_type=code"
            f"&client_id={_env('GOOGLE_CLIENT_ID')}"
            f"&redirect_uri={_env('GOOGLE_REDIRECT_URI')}"
            f"&state={state_param}"
            f"&scope=openid%20email%20profile"
        )
        return rx.redirect(auth_url)

    def handle_google_callback(self):
        """Google OAuth コールバック処理。"""
        import requests as http_requests

        raw_path = self.router.page.raw_path
        parsed = urlparse(raw_path)
        params = parse_qs(parsed.query)

        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        error = params.get("error", [""])[0]

        if error:
            return rx.redirect("/login?error=google_denied")

        valid, _mode = _verify_signed_state(state, "google")
        if not valid:
            logger.warning("Google OAuth state invalid (HMAC mismatch or expired): %s", state[:24])
            return rx.redirect("/login?error=state_mismatch")

        if not code:
            return rx.redirect("/login?error=no_code")

        try:
            token_resp = http_requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _env("GOOGLE_REDIRECT_URI"),
                    "client_id": _env("GOOGLE_CLIENT_ID"),
                    "client_secret": _env("GOOGLE_CLIENT_SECRET"),
                },
                timeout=10,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
        except Exception as e:
            logger.error("Google token exchange failed: %s", e)
            return rx.redirect("/login?error=token_error")

        access_token = token_data.get("access_token")
        if not access_token:
            return rx.redirect("/login?error=token_error")

        try:
            profile_resp = http_requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            profile_resp.raise_for_status()
            profile = profile_resp.json()
        except Exception as e:
            logger.error("Google profile fetch failed: %s", e)
            return rx.redirect("/login?error=profile_error")

        google_id = profile.get("sub", "")
        display_name = profile.get("name", "Googleユーザー")
        picture_url = profile.get("picture", "")
        email = profile.get("email", "")

        if not google_id:
            return rx.redirect("/login?error=no_user_id")

        try:
            user = get_or_create_user_by_provider("google", google_id, display_name, picture_url, email)
        except Exception as e:
            logger.error("DB error: %s", e)
            return rx.redirect("/login?error=db_error")

        try:
            token = create_session(user["id"])
        except Exception as e:
            logger.error("Session creation failed: %s", e)
            return rx.redirect("/login?error=session_error")

        self._apply_login(user, token)
        return rx.redirect("/mypage")

    # ============================================================
    # X (Twitter) OAuth 2.0 + PKCE フロー
    # ============================================================

    def start_twitter_login(self):
        """X(Twitter)認証ページへリダイレクトする（PKCE）。

        state と code_verifier を HMAC で導出するため、Reflex State に
        頼らず (= モバイル WebView 切替に耐える) PKCE が成立する。
        """
        state, code_verifier = _make_twitter_state_and_verifier()
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()

        auth_url = (
            "https://twitter.com/i/oauth2/authorize"
            f"?response_type=code"
            f"&client_id={_env('TWITTER_CLIENT_ID')}"
            f"&redirect_uri={_env('TWITTER_REDIRECT_URI')}"
            f"&state={state}"
            f"&scope=tweet.read%20users.read"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )
        return rx.redirect(auth_url)

    def handle_twitter_callback(self):
        """X(Twitter) OAuth コールバック処理。"""
        import requests as http_requests

        raw_path = self.router.page.raw_path
        parsed = urlparse(raw_path)
        params = parse_qs(parsed.query)

        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        error = params.get("error", [""])[0]

        if error:
            return rx.redirect("/login?error=twitter_denied")

        valid, code_verifier = _verify_twitter_state(state)
        if not valid:
            logger.warning("Twitter OAuth state invalid (HMAC mismatch or expired): %s", state[:24])
            return rx.redirect("/login?error=state_mismatch")

        if not code:
            return rx.redirect("/login?error=no_code")

        try:
            credentials = base64.b64encode(
                f"{_env('TWITTER_CLIENT_ID')}:{_env('TWITTER_CLIENT_SECRET')}".encode()
            ).decode()
            token_resp = http_requests.post(
                "https://api.twitter.com/2/oauth2/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {credentials}",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _env("TWITTER_REDIRECT_URI"),
                    "code_verifier": code_verifier,
                },
                timeout=10,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
        except Exception as e:
            logger.error("Twitter token exchange failed: %s", e)
            return rx.redirect("/login?error=token_error")

        access_token = token_data.get("access_token")
        if not access_token:
            return rx.redirect("/login?error=token_error")

        try:
            profile_resp = http_requests.get(
                "https://api.twitter.com/2/users/me",
                params={"user.fields": "name,profile_image_url"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            profile_resp.raise_for_status()
            profile_data = profile_resp.json().get("data", {})
        except Exception as e:
            logger.error("Twitter profile fetch failed: %s", e)
            return rx.redirect("/login?error=profile_error")

        twitter_id = profile_data.get("id", "")
        display_name = profile_data.get("name", "Xユーザー")
        picture_url = (profile_data.get("profile_image_url") or "").replace("_normal", "")

        if not twitter_id:
            return rx.redirect("/login?error=no_user_id")

        try:
            user = get_or_create_user_by_provider("twitter", twitter_id, display_name, picture_url)
        except Exception as e:
            logger.error("DB error: %s", e)
            return rx.redirect("/login?error=db_error")

        try:
            token = create_session(user["id"])
        except Exception as e:
            logger.error("Session creation failed: %s", e)
            return rx.redirect("/login?error=session_error")

        self._apply_login(user, token)
        self._twitter_code_verifier = ""
        return rx.redirect("/mypage")

    # ============================================================
    # ログアウト
    # ============================================================

    @rx.event(background=True)
    async def delete_session_async(self, token: str):
        """セッション DB 削除をバックグラウンドで実行 (logout の体感速度向上)。"""
        try:
            delete_session(token)
        except Exception as e:
            logger.warning("Failed to delete session async: %s", e)

    def logout(self):
        # 1) State をまず即座にクリアして UI をログアウト状態に
        token = self.session_token
        self.session_token = ""
        self.is_logged_in = False
        self.user_id = 0
        self.username = ""
        self.avatar_url = ""
        self.email = ""
        self.auth_providers = []
        self.line_notify_channel = ""
        self.email_notify_channel = ""
        self.telegram_chat_id = ""
        self.favorite_ids = []
        self.favorites = []
        self.ga_favorite_ids = []
        self.ga_favorites = []

        # 2) DB 削除はバックグラウンド (ネットワーク往復で UI を待たせない)
        events: list = []
        if token:
            events.append(AuthState.delete_session_async(token))
        # 3) 即座にホームへリダイレクト
        events.append(rx.redirect("/"))
        return events

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
        # Googleログインユーザーはメール変更不可
        email_to_save = self.email if "google" in self.auth_providers else (self.edit_email or None)
        update_user_profile(
            self.user_id,
            self.edit_username,
            email_to_save,
            self.edit_avatar_url or None,
        )
        self.username = self.edit_username
        self.email = email_to_save or ""
        self.avatar_url = self.edit_avatar_url
        self.profile_saved = True

        # メールアドレスに応じて通知チャンネルを同期
        if self.email:
            upsert_notification_channel(self.user_id, "email", self.email)
        else:
            remove_notification_channel(self.user_id, "email")
        self._load_providers_and_channels()

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
        from cardanoism.backend.i18n import get_ui as _get_ui
        _t = _get_ui(self.language)
        if not input_addr or not nickname:
            self.stake_error = _t["err_addr_required"]
            return
        if not input_addr.startswith("addr") and not _is_valid_stake_address(input_addr):
            self.stake_error = _t["err_invalid_addr"]
            return
        self.stake_error = ""
        self.stake_adding = True
        yield
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
            yield
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
                # SPO 判定: pools.reward_addr / owners と突合
                try:
                    spo_pool_id = detect_spo_pool_id(address)
                    if spo_pool_id:
                        update_stake_address_spo(new_entry["id"], spo_pool_id)
                except Exception as e:  # noqa: BLE001
                    logger.warning("SPO 判定失敗 (addr=%s): %s", address, e)
                self.stake_addresses = get_stake_addresses(self.user_id)
            self.stake_role_loading = False
            # 登録した stake_address の過去報酬を裏で取得して stake_rewards にキャッシュする。
            # ダッシュボードの「報酬実績」popover が初見でも履歴を表示できるようにする目的。
            yield AuthState.backfill_stake_rewards(address)
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

    def _load_subscription(self) -> None:
        """サブスクリプション情報を State に反映する (Phase 0: 表示のみ)。"""
        try:
            from cardanoism.backend.subscription_db import get_user_subscription
            sub = get_user_subscription(self.user_id) or {}
        except Exception as e:
            logger.debug("_load_subscription failed: %s", e)
            sub = {}

        def _fmt(dt) -> str:
            if not dt:
                return ""
            try:
                return dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)
            except Exception:
                return ""

        self.subscription_tier          = str(sub.get("tier") or "")
        self.subscription_status        = str(sub.get("status") or "")
        self.subscription_billing_cycle = str(sub.get("billing_cycle") or "")
        self.subscription_started_at    = _fmt(sub.get("started_at"))
        self.subscription_period_end    = _fmt(sub.get("current_period_end"))

    def change_active_tab(self, tab: str):
        """タブ切替ハンドラ。ダッシュボードタブを「他タブから」開いた時にデータ再ロードする。

        Reflex の rx.tabs.root(on_change=...) から呼ばれる。
        load_mypage で active_tab を初期設定すると tabs.root の value 変化で
        onValueChange が発火するケースがあり、二重発火を避けるため
        実際にタブが変わった時のみ DashboardState.on_load を発火する。
        """
        if tab == self.active_tab:
            # 同タブクリック / 値同期による発火は無視
            return
        self.active_tab = tab
        if tab == "dashboard":
            from cardanoism.backend.dashboard_state import DashboardState
            return DashboardState.on_load

    @rx.event(background=True)
    async def backfill_stake_rewards(self, stake_address: str):
        """新規登録 stake_address の報酬履歴を直近 30 エポック分取得してキャッシュする。

        Koios `/account_reward_history` を `_epoch_no` 省略 + `limit` で叩き、
        type 別行を epoch ごとに集計して `stake_rewards` テーブルに upsert する。
        進行中は `rewards_backfilling` を True にして UI 側でスピナーを出させる。
        """
        addr = (stake_address or "").strip()
        if not addr:
            return
        async with self:
            self.rewards_backfilling = True
        try:
            from cardanoism.backend.koios import (
                fetch_reward_history_recent,
                aggregate_rewards_by_epoch,
            )
            from cardanoism.backend.stake_rewards_db import bulk_upsert_stake_rewards

            rows = fetch_reward_history_recent([addr], n_epochs=30)
            if rows:
                tuples = aggregate_rewards_by_epoch(rows)
                if tuples:
                    bulk_upsert_stake_rewards(tuples)
                    logger.info(
                        "backfill_stake_rewards: upserted %d epoch rows for %s",
                        len(tuples), addr,
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("backfill_stake_rewards failed (addr=%s): %s", addr, e)
        finally:
            async with self:
                self.rewards_backfilling = False

    # ── ステークアドレスのニックネーム編集 ──

    def start_edit_stake_nickname(self, address_id: int, current_nickname: str):
        """編集モード開始。address_id のカードに input を出す。"""
        try:
            self.editing_stake_id = int(address_id)
        except (TypeError, ValueError):
            self.editing_stake_id = 0
            return
        self.editing_stake_nickname = str(current_nickname or "")

    def cancel_edit_stake_nickname(self):
        self.editing_stake_id = 0
        self.editing_stake_nickname = ""

    def set_editing_stake_nickname(self, value: str):
        self.editing_stake_nickname = value

    def save_stake_nickname(self):
        """編集中のニックネームを保存。"""
        if not self.is_logged_in or self.editing_stake_id == 0:
            return
        _t = self.t
        name = (self.editing_stake_nickname or "").strip()
        if not name:
            return rx.toast.error(_t["stake_nickname_required"])
        if len(name) > 100:
            return rx.toast.error(_t["stake_nickname_too_long"])
        try:
            ok = update_stake_address_nickname(self.user_id, self.editing_stake_id, name)
        except Exception as e:  # noqa: BLE001
            logger.exception("update_stake_address_nickname failed: %s", e)
            return rx.toast.error(_t["stake_nickname_update_failed"])
        if not ok:
            return rx.toast.error(_t["stake_nickname_update_failed"])
        self.stake_addresses = get_stake_addresses(self.user_id)
        self.editing_stake_id = 0
        self.editing_stake_nickname = ""
        return rx.toast.success(_t["stake_nickname_updated"])

    def _load_stake_notification_settings(self):
        flat: dict[str, bool] = {}
        for addr in self.stake_addresses:
            addr_id = addr["id"]
            settings = get_stake_notification_settings(addr_id)
            for event_type, enabled in settings.items():
                flat[f"{addr_id}:{event_type}"] = enabled
        self.stake_notification_settings = flat

    def toggle_stake_notification(self, key: str):
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
        if not self.is_logged_in:
            self.show_login_modal = True
            return
        if not proposal_uuid:
            return
        if proposal_uuid in self.favorite_ids:
            self.favorite_ids = [uid for uid in self.favorite_ids if uid != proposal_uuid]
            yield
            remove_favorite(self.user_id, proposal_uuid, "catalyst")
        else:
            self.favorite_ids = self.favorite_ids + [proposal_uuid]
            yield
            add_favorite(self.user_id, proposal_uuid, "catalyst")
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
        start = (self.favorites_page - 1) * 10
        return self.filtered_favorites_all[start:start + 10]

    @rx.var
    def favorites_total_pages(self) -> int:
        return max(1, (len(self.filtered_favorites_all) + 9) // 10)

    @rx.var
    def is_favorites_empty(self) -> bool:
        return len(self.filtered_favorites_all) == 0

    # ============================================================
    # GAお気に入り
    # ============================================================

    def toggle_ga_favorite(self, proposal_id: str):
        if not self.is_logged_in:
            self.show_login_modal = True
            return
        if not proposal_id:
            return
        if proposal_id in self.ga_favorite_ids:
            self.ga_favorite_ids = [uid for uid in self.ga_favorite_ids if uid != proposal_id]
            yield
            remove_favorite(self.user_id, proposal_id, "governance")
        else:
            self.ga_favorite_ids = self.ga_favorite_ids + [proposal_id]
            yield
            add_favorite(self.user_id, proposal_id, "governance")
        if self.ga_favorites:
            self.ga_favorites = get_ga_favorites(self.user_id)

    def load_ga_favorites(self):
        if self.is_logged_in:
            self.ga_favorites = get_ga_favorites(self.user_id)

    def remove_ga_favorite_handler(self, proposal_id: str):
        if not self.is_logged_in:
            return
        remove_favorite(self.user_id, proposal_id, "governance")
        self.ga_favorite_ids = [uid for uid in self.ga_favorite_ids if uid != proposal_id]
        self.load_ga_favorites()

    def ga_favorites_prev_page(self):
        if self.ga_favorites_page > 1:
            self.ga_favorites_page -= 1

    def ga_favorites_next_page(self):
        if self.ga_favorites_page < self.ga_favorites_total_pages:
            self.ga_favorites_page += 1

    def set_favorites_category(self, category: str):
        self.favorites_category = category
        if category == "governance" and not self.ga_favorites:
            self.load_ga_favorites()

    @rx.var
    def filtered_ga_favorites(self) -> list[dict]:
        start = (self.ga_favorites_page - 1) * 10
        return self.ga_favorites[start:start + 10]

    @rx.var
    def ga_favorites_total_pages(self) -> int:
        return max(1, (len(self.ga_favorites) + 9) // 10)

    @rx.var
    def is_ga_favorites_empty(self) -> bool:
        return len(self.ga_favorites) == 0

    @rx.var
    def is_stake_addresses_empty(self) -> bool:
        return len(self.stake_addresses) == 0

    @rx.var
    def stake_addresses_count(self) -> int:
        return len(self.stake_addresses)

    # ============================================================
    # 通知チャンネル設定
    # ============================================================

    def set_line_notify_enabled(self, value: bool):
        if not self.is_logged_in or not self.line_notify_channel:
            return
        self.line_notify_enabled = value
        set_channel_enabled(self.user_id, "line", value)

    def set_email_notify_enabled(self, value: bool):
        if not self.is_logged_in or not self.email_notify_channel:
            return
        self.email_notify_enabled = value
        set_channel_enabled(self.user_id, "email", value)

    def set_telegram_notify_enabled(self, value: bool):
        if not self.is_logged_in or not self.telegram_chat_id:
            return
        self.telegram_notify_enabled = value
        set_channel_enabled(self.user_id, "telegram", value)

    # ============================================================
    # 通知設定（イベントON/OFF）
    # ============================================================

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
        self.check_auth()
        if not self.is_logged_in:
            self.show_login_modal = True
            return
        self.load_profile()
        self.stake_addresses = get_stake_addresses(self.user_id)
        self.favorites = get_favorites(self.user_id, "catalyst")
        self.ga_favorites = get_ga_favorites(self.user_id)
        self.notification_settings = get_notification_settings(self.user_id)
        self._load_stake_notification_settings()
        self._load_subscription()
        valid_tabs = {"dashboard", "favorites", "profile", "stake", "notification", "subscription"}
        tab = self.router.page.params.get("tab", "dashboard")
        self.active_tab = tab if tab in valid_tabs else "dashboard"
        # ダッシュボードタブで開いたなら DashboardState.on_load を 1 度だけ発火
        # (mypage の @template(on_load=...) では指定せず、ここから明示的に呼ぶ
        #  ことで、active_tab 設定 → tabs.root の onValueChange → change_active_tab
        #  経由の二重発火を回避する)
        if self.active_tab == "dashboard":
            from cardanoism.backend.dashboard_state import DashboardState
            return DashboardState.on_load


# ============================================================
# バリデーション
# ============================================================

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_STAKE_ADDR_RE = re.compile(
    r"^stake(?:_test)?1[" + _BECH32_CHARSET + r"]{6,}$"
)


def _is_valid_stake_address(address: str) -> bool:
    addr = address.strip().lower()
    if not _STAKE_ADDR_RE.match(addr):
        return False
    if addr.startswith("stake_test1"):
        return len(addr) == 64
    return len(addr) == 59
