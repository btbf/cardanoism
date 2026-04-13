"""
line_auth.py
LINE OAuth2 認証フロー（FastAPI APIRouter）

環境変数:
  LINE_CLIENT_ID      - LINE Developers の Channel ID
  LINE_CLIENT_SECRET  - LINE Developers の Channel Secret
  LINE_REDIRECT_URI   - コールバックURL (例: https://cardanoism.com/auth/line/callback)
  SECRET_KEY          - Cookieの署名用シークレット（必ず本番用に変更すること）
"""
import os
import secrets
import logging

import requests as http_requests
import itsdangerous
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from cardanoism.backend.auth_db import (
    get_or_create_user_by_line,
    create_session,
    delete_session,
    get_user_by_session,
    update_line_id,
    get_user_by_line_id,
)

logger = logging.getLogger(__name__)

router = APIRouter()

LINE_CLIENT_ID = os.getenv("LINE_CLIENT_ID", "")
LINE_CLIENT_SECRET = os.getenv("LINE_CLIENT_SECRET", "")
LINE_REDIRECT_URI = os.getenv(
    "LINE_REDIRECT_URI", "https://cardanoism.com/auth/line/callback"
)
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

_signer = itsdangerous.URLSafeSerializer(SECRET_KEY, salt="line-oauth-state")

SESSION_COOKIE = "cardanoism_session"
STATE_COOKIE = "line_oauth_state"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30日


# ============================================================
# /auth/line/login
# ============================================================
@router.get("/auth/line/login")
async def line_login(request: Request):
    """LINE認証ページへリダイレクトする。"""
    csrf = secrets.token_urlsafe(16)
    signed_state = _signer.dumps({"csrf": csrf, "mode": "login"})

    auth_url = (
        "https://access.line.me/oauth2/v2.1/authorize"
        f"?response_type=code"
        f"&client_id={LINE_CLIENT_ID}"
        f"&redirect_uri={LINE_REDIRECT_URI}"
        f"&state={csrf}"
        f"&scope=profile%20openid%20email"
    )

    response = RedirectResponse(auth_url)
    response.set_cookie(
        STATE_COOKIE,
        signed_state,
        httponly=True,
        max_age=600,
        samesite="lax",
    )
    return response


# ============================================================
# /auth/line/callback
# ============================================================
@router.get("/auth/line/callback")
async def line_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """LINEからのコールバックを処理する。
    mode=connect: line_id を現在のユーザーに紐付ける。
    mode=login:   ユーザーを取得/作成してセッションを発行する。
    """
    # state 検証 & mode 判定
    signed_state = request.cookies.get(STATE_COOKIE, "")
    mode = "login"
    try:
        state_data = _signer.loads(signed_state)
        if isinstance(state_data, dict):
            # 新形式: {"csrf": ..., "mode": ...}
            expected_csrf = state_data["csrf"]
            mode = state_data.get("mode", "login")
        else:
            # 旧形式: 文字列のまま（後方互換）
            expected_csrf = state_data
    except Exception:
        logger.warning("Invalid state cookie")
        error_dest = "/mypage?tab=notification&error=invalid_state" if mode == "connect" else "/login?error=invalid_state"
        return RedirectResponse(error_dest)

    if error:
        logger.warning("LINE OAuth error: %s", error)
        dest = "/mypage?tab=notification&error=line_denied" if mode == "connect" else "/login?error=line_denied"
        return RedirectResponse(dest)

    if state != expected_csrf:
        logger.warning("State mismatch: got=%s expected=%s", state, expected_csrf)
        dest = "/mypage?tab=notification&error=state_mismatch" if mode == "connect" else "/login?error=state_mismatch"
        return RedirectResponse(dest)

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
        return RedirectResponse("/login?error=token_error")

    access_token = token_data.get("access_token")
    if not access_token:
        logger.error("No access_token in response: %s", token_data)
        return RedirectResponse("/login?error=token_error")

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
        return RedirectResponse("/login?error=profile_error")

    line_id = profile.get("userId", "")
    username = profile.get("displayName", "LINEユーザー")
    avatar_url = profile.get("pictureUrl", "")

    if not line_id:
        dest = "/mypage?tab=notification&error=no_user_id" if mode == "connect" else "/login?error=no_user_id"
        return RedirectResponse(dest)

    # ── connect モード: 現在のセッションユーザーに line_id を紐付ける ──
    if mode == "connect":
        session_token = request.cookies.get(SESSION_COOKIE, "")
        user = get_user_by_session(session_token) if session_token else None
        if not user:
            return RedirectResponse("/mypage?tab=notification&error=session_expired")

        existing = get_user_by_line_id(line_id)
        if existing and existing["id"] != user["id"]:
            logger.warning("line_id %s already linked to user %d", line_id, existing["id"])
            return RedirectResponse("/mypage?tab=notification&error=line_already_linked")

        try:
            update_line_id(user["id"], line_id)
        except Exception as e:
            logger.error("update_line_id failed: %s", e)
            return RedirectResponse("/mypage?tab=notification&error=db_error")

        response = RedirectResponse("/mypage?tab=notification&connected=line")
        response.delete_cookie(STATE_COOKIE)
        return response

    # ── login モード: ユーザー取得 or 作成してセッション発行 ──
    try:
        user = get_or_create_user_by_line(line_id, username, avatar_url)
    except Exception as e:
        logger.error("DB error in get_or_create_user_by_line: %s", e)
        return RedirectResponse("/login?error=db_error")

    try:
        session_token = create_session(user["id"])
    except Exception as e:
        logger.error("Session creation failed: %s", e)
        return RedirectResponse("/login?error=session_error")

    response = RedirectResponse("/mypage")
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        max_age=COOKIE_MAX_AGE,
        samesite="lax",
    )
    response.delete_cookie(STATE_COOKIE)
    return response


# ============================================================
# /auth/line/connect  （通知用LINE連携：ログイン済みユーザー専用）
# ============================================================

@router.get("/auth/line/connect")
async def line_connect(request: Request):
    """ログイン済みユーザーのLINE通知連携を開始する。
    既存の /auth/line/callback を流用し、state に mode=connect を埋め込む。
    """
    session_token = request.cookies.get(SESSION_COOKIE, "")
    if not session_token:
        return RedirectResponse("/mypage?tab=notification&error=not_logged_in")

    csrf = secrets.token_urlsafe(16)
    # state に mode を埋め込んでサイン
    signed_state = _signer.dumps({"csrf": csrf, "mode": "connect"})

    auth_url = (
        "https://access.line.me/oauth2/v2.1/authorize"
        f"?response_type=code"
        f"&client_id={LINE_CLIENT_ID}"
        f"&redirect_uri={LINE_REDIRECT_URI}"
        f"&state={csrf}"
        f"&scope=profile"
    )

    response = RedirectResponse(auth_url)
    response.set_cookie(STATE_COOKIE, signed_state, httponly=True, max_age=600, samesite="lax")
    return response


# ============================================================
# /auth/logout
# ============================================================
@router.get("/auth/logout")
async def logout(request: Request):
    """セッションを削除してトップページへリダイレクトする。"""
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        try:
            delete_session(session_token)
        except Exception as e:
            logger.warning("Failed to delete session: %s", e)

    response = RedirectResponse("/")
    response.delete_cookie(SESSION_COOKIE)
    return response
