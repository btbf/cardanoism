"""
governance_drep.py
ガバナンス > DRep 一覧ページ（/governance/drep）

データソースは dreps テーブル（notify_worker.py --event drep_sync で同期）。
ページ側は DB を読むだけで Koios を叩かない。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.wallet_state import WalletState
from cardanoism.backend.drep_db import get_dreps, count_dreps, sum_total_delegation
from cardanoism.backend.fiat_db import get_fiat_rate
from cardanoism.backend.price import format_ada, format_jpy_short, format_usd_short
from cardanoism.components.governance_nav import governance_subnav
from cardanoism.components.breadcrumb import breadcrumb
from cardanoism.components.login_modal import login_modal
from cardanoism.components.drep_delegation_dialog import drep_delegation_dialog, drep_delegate_button

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 30


# ─── State ────────────────────────────────────────────────────────────────────


class DrepState(rx.State):
    load: bool = False
    error: str = ""

    inputed_value: str = ""
    search_query: str = ""
    sort: str = "amount_desc"
    only_registered: bool = True

    current_page: int = 1
    total_pages: int = 0
    total_items: int = 0
    start_page: int = 1
    end_page: int = 1
    middle_page: list[int] = []

    dreps: List[Dict[str, Any]] = []
    total_delegation_ada_display: str = "-"
    total_delegation_lovelace: int = 0

    def _fetch(self):
        offset = (self.current_page - 1) * ITEMS_PER_PAGE
        try:
            rate = get_fiat_rate() or {}
            ada_jpy = float(rate.get("ada_jpy") or 0)
            ada_usd = float(rate.get("ada_usd") or 0)

            # 総委任量を取得して、各 DRep のシェアを計算する
            total_lovelace = sum_total_delegation(only_registered=self.only_registered)
            self.total_delegation_lovelace = total_lovelace
            self.total_delegation_ada_display = format_ada(total_lovelace, integer=True) if total_lovelace else "0"

            rows = get_dreps(
                search=self.search_query,
                only_registered=self.only_registered,
                sort=self.sort,
                limit=ITEMS_PER_PAGE,
                offset=offset,
            )
            total = count_dreps(search=self.search_query, only_registered=self.only_registered)

            out: list[dict] = []
            for idx, r in enumerate(rows):
                amount = int(r.get("amount") or 0)
                ada = amount / 1_000_000
                jpy_d = format_jpy_short(ada * ada_jpy) if ada_jpy else ""
                usd_d = format_usd_short(ada * ada_usd) if ada_usd else ""
                share_pct = (amount / total_lovelace * 100.0) if total_lovelace > 0 else 0.0
                if share_pct >= 1.0:
                    share_display = f"{share_pct:.2f}"
                elif share_pct > 0:
                    share_display = f"{share_pct:.3f}"
                else:
                    share_display = "0"
                drep_id = str(r.get("drep_id") or "")
                # スマホ用の短縮表示（先頭 14 + ... + 末尾 8）
                if len(drep_id) > 24:
                    drep_id_short = f"{drep_id[:14]}...{drep_id[-8:]}"
                else:
                    drep_id_short = drep_id
                out.append({
                    "rank":          str(offset + idx + 1),
                    "drep_id":       drep_id,
                    "drep_id_short": drep_id_short,
                    "given_name":    str(r.get("given_name") or ""),
                    "image_url":     str(r.get("image_url") or ""),
                    "drep_status":   str(r.get("drep_status") or ""),
                    "is_active":     "1" if r.get("active") else "",
                    "amount_ada":    format_ada(amount, integer=True) if amount else "0",
                    "amount_jpy":    jpy_d,
                    "amount_usd":    usd_d,
                    "share_pct":     share_display,
                })
            self.dreps = out
            self.total_items = total
            self.total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            self.start_page = max(1, self.current_page - 3)
            self.end_page   = min(self.total_pages, self.current_page + 3)
            self.middle_page = list(range(self.start_page, self.end_page + 1))
        except Exception as e:
            logger.exception("DrepState._fetch: %s", e)
            self.error = str(e)

    def on_load(self):
        self.load = False
        self.error = ""
        self.inputed_value = ""
        self.search_query = ""
        self.sort = "amount_desc"
        self.only_registered = True
        self.current_page = 1
        self._fetch()
        self.load = True

    def set_input(self, v: str):
        self.inputed_value = v
        self.search_query = v
        self.current_page = 1
        self._fetch()

    def set_sort(self, v: str):
        self.sort = v
        self.current_page = 1
        self._fetch()

    def set_page(self, p):
        try:
            self.current_page = int(p)
            self._fetch()
        except (TypeError, ValueError):
            pass
        return rx.call_script("window.scrollTo(0, 0)")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._fetch()
        return rx.call_script("window.scrollTo(0, 0)")

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._fetch()
        return rx.call_script("window.scrollTo(0, 0)")


# ─── DRep マッチング診断 (委任コンパス MVP) State ──────────────────────────────

from cardanoism.backend.drep_compass.api import (
    list_drep_matches_for_vector as _list_matches_for_vector,
    save_drep_match_answers as _save_compass_answers,
)
from cardanoism.backend.drep_compass.questionnaire import (
    QUESTIONS as _COMPASS_QUESTIONS,
    QUESTION_TOTAL as _COMPASS_QUESTION_TOTAL,
    build_user_vector as _build_user_vector,
)
from cardanoism.backend.drep_compass import config as _COMPASS_CONFIG
from cardanoism.backend.drep_compass.taxonomy import AXES as _COMPASS_AXES
from cardanoism.backend.drep_db import get_drep as _get_drep


class DrepMatchState(rx.State):
    """DRepマッチング診断 v2 (7 axis / 10 問 二者択一+迷う) の State。

    view: "list" / "intro" / "quiz" / "results"
    answers: { q_id: 1 (左) / 2 (迷う) / 3 (右) }
    importance: 重要マーク済み q_id のリスト (最大 3)
    results: 結果カード描画用 dict のリスト
    """
    view: str = "list"
    current_question: int = 0
    answers: dict[str, int] = {}
    importance: list[str] = []
    results: list[dict[str, str]] = []

    @rx.var
    def current_question_i18n_key(self) -> str:
        idx = self.current_question
        if 0 <= idx < _COMPASS_QUESTION_TOTAL:
            return _COMPASS_QUESTIONS[idx].i18n_key
        return ""

    @rx.var
    def current_left_i18n_key(self) -> str:
        idx = self.current_question
        if 0 <= idx < _COMPASS_QUESTION_TOTAL:
            return _COMPASS_QUESTIONS[idx].left_i18n_key
        return ""

    @rx.var
    def current_right_i18n_key(self) -> str:
        idx = self.current_question
        if 0 <= idx < _COMPASS_QUESTION_TOTAL:
            return _COMPASS_QUESTIONS[idx].right_i18n_key
        return ""

    @rx.var
    def current_question_id(self) -> str:
        idx = self.current_question
        if 0 <= idx < _COMPASS_QUESTION_TOTAL:
            return _COMPASS_QUESTIONS[idx].q_id
        return ""

    @rx.var
    def current_question_is_important(self) -> bool:
        return self.current_question_id in self.importance

    @rx.var
    def importance_full(self) -> bool:
        return len(self.importance) >= _COMPASS_CONFIG.MAX_IMPORTANT_AXES

    @rx.var
    def progress_current(self) -> str:
        return str(self.current_question + 1)

    @rx.var
    def progress_total(self) -> str:
        return str(_COMPASS_QUESTION_TOTAL)

    @rx.var
    def is_first_question(self) -> bool:
        return self.current_question == 0

    @rx.var
    def is_last_question(self) -> bool:
        return self.current_question == _COMPASS_QUESTION_TOTAL - 1

    @rx.var
    def current_answer(self) -> int:
        return int(self.answers.get(self.current_question_id, 0))

    @rx.var
    def can_submit(self) -> bool:
        if not self.is_last_question:
            return False
        return self.current_answer >= 1

    @rx.var
    def progress_pct(self) -> str:
        if _COMPASS_QUESTION_TOTAL <= 0:
            return "0"
        pct = (self.current_question + 1) / _COMPASS_QUESTION_TOTAL * 100
        return f"{pct:.1f}"

    def set_view(self, view: str):
        if view in ("list", "intro", "quiz", "results"):
            self.view = view

    def enter_match_tab(self):
        if self.results:
            self.view = "results"
        else:
            self.view = "intro"

    def start_quiz(self):
        self.view = "quiz"
        self.current_question = 0
        self.answers = {}
        self.importance = []
        self.results = []

    def set_answer(self, level: int):
        """1 (左) / 2 (迷う) / 3 (右) で回答。最終問以外は次に進む。"""
        try:
            v = int(level)
        except (TypeError, ValueError):
            return
        if v < 1 or v > 3:
            return
        qid = self.current_question_id
        if not qid:
            return
        new_answers = dict(self.answers)
        new_answers[qid] = v
        self.answers = new_answers
        if not self.is_last_question:
            self.current_question += 1

    def toggle_importance(self):
        qid = self.current_question_id
        if not qid:
            return
        if qid in self.importance:
            self.importance = [q for q in self.importance if q != qid]
            return
        if len(self.importance) >= _COMPASS_CONFIG.MAX_IMPORTANT_AXES:
            return
        self.importance = list(self.importance) + [qid]

    def prev_question(self):
        if self.current_question > 0:
            self.current_question -= 1

    def submit_quiz(self):
        """回答から user_vector を計算し、TOP N マッチを取得。"""
        try:
            user_vector, weights = _build_user_vector(
                dict(self.answers), list(self.importance),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("build_user_vector failed: %s", e)
            user_vector, weights = {}, {}
        try:
            raw = _list_matches_for_vector(
                user_vector, weights,
                limit=_COMPASS_CONFIG.DEFAULT_MATCH_LIMIT,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("list_drep_matches_for_vector failed: %s", e)
            raw = []
        logger.info("submit_quiz: user_vector=%d axes, results=%d",
                    len(user_vector), len(raw))

        # アンケート回答を best-effort で保存
        try:
            sid = None
            try:
                sid = getattr(self.router.session, "client_token", None)
            except Exception:  # noqa: BLE001
                sid = None
            _save_compass_answers(
                user_id=None,
                session_id=str(sid) if sid else None,
                answers=dict(self.answers),
                importance=list(self.importance),
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("save_drep_match_answers (best-effort) failed: %s", e)

        # 委任量 / fiat 表示
        rate = get_fiat_rate() or {}
        ada_jpy = float(rate.get("ada_jpy") or 0)
        ada_usd = float(rate.get("ada_usd") or 0)
        total_lovelace = sum_total_delegation(only_registered=True)

        out: list[dict[str, str]] = []
        for r in raw:
            drep_id = str(r.get("drep_id") or "")
            d = _get_drep(drep_id) or {}
            amount = int(d.get("amount") or 0)
            ada = amount / 1_000_000
            jpy_d = format_jpy_short(ada * ada_jpy) if ada_jpy else ""
            usd_d = format_usd_short(ada * ada_usd) if ada_usd else ""
            share_pct = (amount / total_lovelace * 100.0) if total_lovelace > 0 else 0.0
            if share_pct >= 1.0:
                share_display = f"{share_pct:.2f}"
            elif share_pct > 0:
                share_display = f"{share_pct:.3f}"
            else:
                share_display = "0"

            # 7 axis の matched/mismatched を「drep_match_axis_<axis>」i18n キーに変換
            def _to_label(axes: list[str]) -> str:
                return ",".join(f"drep_match_axis_{a}" for a in (axes or []) if a)

            out.append({
                "drep_id":              drep_id,
                "given_name":           str(d.get("given_name") or ""),
                "image_url":            str(d.get("image_url") or ""),
                "total_score":          f"{float(r.get('total_score') or 0):.1f}",
                "summary":              str(r.get("summary") or ""),
                "reasoning_pct":        f"{float(r.get('reasoning_disclosure_rate') or 0) * 100:.1f}",
                "analyzed_votes":       str(r.get("analyzed_vote_count") or 0),
                "matched_axes_csv":     _to_label(r.get("matched_axes")),
                "mismatched_axes_csv":  _to_label(r.get("mismatched_axes")),
                "low_conf_axes_csv":    _to_label(r.get("low_confidence_axes")),
                "amount_ada":           format_ada(amount, integer=True) if amount else "0",
                "amount_jpy":           jpy_d,
                "amount_usd":           usd_d,
                "share_pct":            share_display,
            })
        self.results = out
        self.view = "results"


# ─── UI パーツ ────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return breadcrumb([("nav_governance", "/governance")], "gov_subnav_drep")


def _drep_card(d) -> rx.Component:
    """1 件の DRep カード。PC ではランク・プロフィール・ID・委任量を横一列に展開。"""
    rank_badge = rx.center(
        rx.text(
            "#", d["rank"],
            size="4", weight="bold", color="var(--gray-11)",
            style={"letterSpacing": "-0.02em"},
        ),
        min_width="56px",
        padding_x="8px",
        height="56px",
        border_radius="10px",
        background="var(--gray-4)",
        flex_shrink="0",
    )
    avatar = rx.link(
        rx.cond(
            d["image_url"] != "",
            rx.image(
                src=d["image_url"],
                width="56px",
                height="56px",
                border_radius="50%",
                style={"objectFit": "cover"},
                flex_shrink="0",
            ),
            rx.center(
                rx.icon("user-round", size=28, color="var(--gray-9)"),
                width="56px",
                height="56px",
                border_radius="50%",
                background="var(--gray-4)",
                flex_shrink="0",
            ),
        ),
        href="/drep/" + d["drep_id"],
        underline="none",
        style={"display": "inline-block", "lineHeight": 0},
    )
    status_badge = rx.cond(
        d["is_active"] != "",
        rx.badge(AuthState.t["drep_status_active"], color_scheme="green", variant="soft"),
        rx.badge(AuthState.t["drep_status_inactive"], color_scheme="gray", variant="soft"),
    )
    name_text = rx.link(
        rx.cond(
            d["given_name"] != "",
            rx.text(d["given_name"], size="4", weight="bold", color="var(--gray-12)",
                    style={"wordBreak": "break-word"}),
            rx.text(AuthState.t["drep_no_name"], size="4", weight="bold", color="var(--gray-10)"),
        ),
        href="/drep/" + d["drep_id"],
        underline="hover",
        color="inherit",
    )
    fiat = rx.cond(
        AuthState.language == "en",
        rx.cond(
            d["amount_usd"] != "",
            rx.text("(≈ ", d["amount_usd"], ")", size="1", color="var(--gray-10)"),
            rx.fragment(),
        ),
        rx.cond(
            d["amount_jpy"] != "",
            rx.text("(≈ ", d["amount_jpy"], ")", size="1", color="var(--gray-10)"),
            rx.fragment(),
        ),
    )
    # DRep ID（コピー用。末尾にコピーアイコンをインライン配置）
    # スマホでは短縮表示、PCではフル表示。コピー時は常にフル ID がコピーされる。
    _id_text_style = {
        "fontFamily": "var(--code-font-family, ui-monospace, monospace)",
        "fontSize": "11px",
        "color": "var(--gray-10)",
        "wordBreak": "break-all",
    }
    _copy_btn = rx.el.button(
        rx.icon("copy", size=12),
        on_click=[
            rx.set_clipboard(d["drep_id"]),
            rx.toast(
                AuthState.t["drep_id_copied"],
                position="top-center",
                style={
                    "background-color": "var(--indigo-11)",
                    "color": "white",
                    "border-radius": "0.5rem",
                },
            ),
        ],
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "verticalAlign": "middle",
            "marginLeft": "4px",
            "padding": "2px",
            "border": "none",
            "background": "transparent",
            "color": "var(--gray-10)",
            "cursor": "pointer",
        },
        _hover={"color": "var(--gray-12)"},
    )
    drep_id_block = rx.fragment(
        rx.mobile_only(
            rx.box(
                rx.el.span(d["drep_id_short"], style=_id_text_style),
                _copy_btn,
                style={"lineHeight": "1.5"},
                width="100%",
            ),
        ),
        rx.tablet_and_desktop(
            rx.box(
                rx.el.span(d["drep_id"], style=_id_text_style),
                _copy_btn,
                style={"lineHeight": "1.5"},
                width="100%",
            ),
        ),
    )
    # プロフィール（名前 + ステータス + DRep ID） — 左、広めに確保して DRep ID が 1 行に収まるように
    profile_col = rx.vstack(
        rx.hstack(name_text, status_badge, spacing="2", align="center", wrap="wrap"),
        drep_id_block,
        spacing="2",
        align_items="start",
        flex="2",
        min_width="420px",
    )
    # 委任量 — 中央（縮めて配置）
    delegation_col = rx.vstack(
        rx.text(AuthState.t["drep_delegated_label"], size="1", color="var(--gray-10)"),
        rx.hstack(
            rx.text(d["amount_ada"], size="5", weight="bold", color="var(--amber-11)"),
            rx.text("ADA", size="2", color="var(--gray-11)"),
            spacing="1", align="baseline",
        ),
        fiat,
        spacing="1",
        align_items="center",
        flex="1",
        min_width="160px",
    )
    # 影響力（シェア％）— 右端、大きく
    percentage_col = rx.vstack(
        rx.text(AuthState.t["drep_influence_label"], size="1", color="var(--gray-10)"),
        rx.hstack(
            rx.text(
                d["share_pct"],
                size="8", weight="bold", color="var(--blue-11)",
                style={"letterSpacing": "-0.02em"},
            ),
            rx.text("%", size="4", color="var(--blue-10)"),
            spacing="0", align="baseline",
        ),
        spacing="1",
        align_items="center",
        min_width="110px",
        flex_shrink="0",
    )

    # 委任状態の判定 (SPO と同パターン):
    #   - 接続中ウォレットの現在委任先 == このカードの DRep: 「委任中」 (amber バッジ、クリック不可)
    #   - 接続中: 「委任する」 (amber アクティブボタン)
    #   - 未接続: 「委任する」 (gray, disabled)
    is_currently_delegated = (
        WalletState.connected
        & (WalletState.current_delegated_drep_id == d["drep_id"])
    )
    delegated_badge = rx.hstack(
        rx.icon("circle-check", size=11, color="var(--amber-11)"),
        rx.text(
            AuthState.t["delegate_btn_currently"],
            size="1", weight="bold", color="var(--amber-12)",
            style={"whiteSpace": "nowrap"},
        ),
        spacing="2",
        align="center",
        padding="4px 12px 4px 10px",
        border_radius="999px",
        background="var(--amber-3)",
        border="1px solid var(--amber-8)",
        cursor="default",
        style={
            "boxShadow": "0 1px 3px rgba(245,158,11,0.18)",
            "display": "inline-flex",
            "flexShrink": "0",
        },
    )
    delegate_active = rx.el.button(
        rx.icon("zap", size=14, color="var(--amber-11)"),
        rx.text(
            AuthState.t["delegate_btn"],
            color="var(--amber-12)",
            style={
                "fontSize": "13px",
                "fontWeight": "700",
                "lineHeight": "1.0",
                "whiteSpace": "nowrap",
            },
        ),
        on_click=WalletState.request_delegate_to_drep(d["drep_id"]),
        cursor="pointer",
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "gap": "6px",
            "padding": "8px 16px",
            "borderRadius": "999px",
            "background": "transparent",
            "border": "1.5px solid var(--amber-8)",
            "transition": "background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease",
            "flexShrink": "0",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
        },
        _hover={
            "background": "var(--amber-3)",
            "border_color": "var(--amber-10)",
            "transform": "translateY(-1px)",
            "box_shadow": "0 4px 10px -2px rgba(245,158,11,0.25)",
        },
    )
    # 未認証用ボタン: 見た目は active と同じ amber スタイル。クリックで委任ではなく
    # 認証誘導モーダル (AuthState.show_auth_required_modal) を開く。
    delegate_prompt_auth = rx.el.button(
        rx.icon("zap", size=14, color="var(--amber-11)"),
        rx.text(
            AuthState.t["delegate_btn"],
            color="var(--amber-12)",
            style={
                "fontSize": "13px",
                "fontWeight": "700",
                "lineHeight": "1.0",
                "whiteSpace": "nowrap",
            },
        ),
        on_click=AuthState.open_auth_required_modal,
        cursor="pointer",
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "gap": "6px",
            "padding": "8px 16px",
            "borderRadius": "999px",
            "background": "transparent",
            "border": "1.5px solid var(--amber-8)",
            "transition": "background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease",
            "flexShrink": "0",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
        },
        _hover={
            "background": "var(--amber-3)",
            "border_color": "var(--amber-10)",
            "transform": "translateY(-1px)",
            "box_shadow": "0 4px 10px -2px rgba(245,158,11,0.25)",
        },
    )
    delegate_button = rx.box(
        rx.cond(
            is_currently_delegated,
            delegated_badge,
            rx.cond(
                WalletState.connected,
                delegate_active,
                # 未接続: active と同じ amber スタイル。クリックで認証誘導モーダル
                delegate_prompt_auth,
            ),
        ),
        flex_shrink="0",
    )

    # お気に入りトグル (heart アイコン、catalyst / GA と同パターン)
    fav_button = rx.box(
        rx.cond(
            AuthState.drep_favorite_ids.contains(d["drep_id"]),
            rx.icon("heart", size=22, color="var(--red-9)", style={"fill": "var(--red-9)"}),
            rx.icon("heart", size=22, color="var(--gray-8)"),
        ),
        on_click=AuthState.toggle_drep_favorite(d["drep_id"]),
        cursor="pointer",
        padding="6px",
        flex_shrink="0",
    )

    # ── スマホ専用レイアウト ───────────────────────────────────────────
    # 上から: 番号+アイコン(小) / 名前+ステータス / ID / 委任量 / 影響力+委任+♥
    mobile_rank = rx.center(
        rx.text(
            "#", d["rank"],
            size="2", weight="bold", color="var(--gray-11)",
            style={"letterSpacing": "-0.02em"},
        ),
        min_width="40px",
        padding_x="6px",
        height="40px",
        border_radius="8px",
        background="var(--gray-4)",
        flex_shrink="0",
    )
    mobile_avatar = rx.link(
        rx.cond(
            d["image_url"] != "",
            rx.image(
                src=d["image_url"],
                width="40px",
                height="40px",
                border_radius="50%",
                style={"objectFit": "cover"},
                flex_shrink="0",
            ),
            rx.center(
                rx.icon("user-round", size=20, color="var(--gray-9)"),
                width="40px",
                height="40px",
                border_radius="50%",
                background="var(--gray-4)",
                flex_shrink="0",
            ),
        ),
        href="/drep/" + d["drep_id"],
        underline="none",
        style={"display": "inline-block", "lineHeight": 0},
    )
    mobile_amount_row = rx.hstack(
        rx.text(AuthState.t["drep_delegated_label"], size="1", color="var(--gray-10)"),
        rx.text(d["amount_ada"], size="3", weight="bold", color="var(--amber-11)"),
        rx.text("ADA", size="1", color="var(--gray-11)"),
        fiat,
        spacing="2", align="baseline", wrap="wrap",
    )
    mobile_layout = rx.vstack(
        rx.hstack(mobile_rank, mobile_avatar, spacing="2", align="center"),
        rx.hstack(name_text, status_badge, spacing="2", align="center", wrap="wrap"),
        drep_id_block,
        mobile_amount_row,
        rx.hstack(
            rx.hstack(
                rx.text(AuthState.t["drep_influence_label"], size="1", color="var(--gray-10)"),
                rx.text(
                    d["share_pct"],
                    size="5", weight="bold", color="var(--blue-11)",
                    style={"letterSpacing": "-0.02em"},
                ),
                rx.text("%", size="2", color="var(--blue-10)"),
                spacing="1", align="baseline",
            ),
            rx.spacer(),
            delegate_button,
            fav_button,
            spacing="2", align="center", width="100%",
        ),
        spacing="3",
        align_items="stretch",
        width="100%",
    )

    return rx.box(
        rx.mobile_only(mobile_layout),
        rx.tablet_and_desktop(
            rx.hstack(
                rank_badge,
                avatar,
                profile_col,
                delegation_col,
                percentage_col,
                delegate_button,
                fav_button,
                align="center",
                spacing="3",
                wrap="wrap",
                width="100%",
            ),
        ),
        padding="14px 16px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="10px",
        background="var(--gray-2)",
        width="100%",
        _hover={"background": "var(--gray-3)"},
        transition="background 0.15s",
    )


def _filter_bar() -> rx.Component:
    return rx.hstack(
        rx.input(
            rx.cond(
                DrepState.inputed_value != "",
                rx.input.slot(
                    rx.icon(
                        "x",
                        size=16,
                        cursor="pointer",
                        on_click=DrepState.set_input(""),
                        style={"_hover": {"color": "var(--gray-12)"}},
                    ),
                    side="right",
                    color="var(--gray-9)",
                ),
                rx.fragment(),
            ),
            placeholder=AuthState.t["drep_search_placeholder"],
            size="3",
            max_length=100,
            value=DrepState.inputed_value,
            on_change=lambda v: DrepState.set_input(v).debounce(400),
            flex="1",
            min_width="0",
        ),
        rx.select.root(
            rx.select.trigger(),
            rx.select.content(
                rx.select.item(AuthState.t["drep_sort_amount_desc"], value="amount_desc"),
                rx.select.item(AuthState.t["drep_sort_amount_asc"],  value="amount_asc"),
                rx.select.item(AuthState.t["drep_sort_name_asc"],    value="name_asc"),
                rx.select.item(AuthState.t["drep_sort_active"],      value="active"),
            ),
            value=DrepState.sort,
            on_change=DrepState.set_sort,
            size="3",
        ),
        spacing="2", wrap="wrap", width="100%",
    )


def _pagination() -> rx.Component:
    def btn(page):
        is_active = page == DrepState.current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: DrepState.set_page(page),
            variant=rx.cond(is_active, "solid", "soft"),
            radius="full",
            size="2",
            padding_x="10px",
            class_name="md:inline-flex hidden",
            _hover={"cursor": "pointer"},
        )
    return rx.flex(
        rx.button(
            rx.icon(tag="chevron-left"),
            on_click=DrepState.prev_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=DrepState.current_page == 1,
            _hover={"cursor": "pointer"},
        ),
        rx.foreach(DrepState.middle_page, btn),
        rx.button(
            rx.icon(tag="chevron-right"),
            on_click=DrepState.next_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=DrepState.current_page == DrepState.total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="pagination gap-2",
        padding_top="1.5em",
        justify="end",
        align="center",
    )


# ─── マッチング診断 UI ────────────────────────────────────────────────────────


def _tab_button(view_key: str, label, on_click) -> rx.Component:
    """list / match タブ切り替えボタン。"""
    # "list" タブ: view == "list" の時 active
    # "match" タブ: view が "intro" / "quiz" / "results" の時 active
    is_active = rx.cond(
        view_key == "list",
        DrepMatchState.view == "list",
        (DrepMatchState.view == "intro")
        | (DrepMatchState.view == "quiz")
        | (DrepMatchState.view == "results"),
    )
    return rx.el.button(
        rx.text(
            label,
            size="2",
            weight="bold",
            color=rx.cond(is_active, "var(--amber-12)", "var(--gray-11)"),
        ),
        on_click=on_click,
        cursor="pointer",
        style={
            "padding":      "7px 18px",
            "borderRadius": "9999px",
            "border":       rx.cond(is_active, "1px solid var(--amber-8)", "1px solid var(--gray-6)"),
            "background":   rx.cond(is_active, "var(--amber-3)", "transparent"),
            "whiteSpace":   "nowrap",
            "transition":   "background 0.15s, border-color 0.15s, color 0.15s",
        },
        _hover=rx.cond(
            is_active,
            {"background": "var(--amber-4)"},
            {"background": "var(--gray-3)", "border_color": "var(--gray-8)"},
        ),
    )


def _drep_match_tabs() -> rx.Component:
    return rx.hstack(
        _tab_button("list",  AuthState.t["drep_tab_list"],  DrepMatchState.set_view("list")),
        # マッチング診断タブ: クリックすると intro (注意書き + スタートボタン) を表示
        # 既に診断結果があればそれを温存して results に戻る
        _tab_button("match", AuthState.t["drep_tab_match"], DrepMatchState.enter_match_tab),
        spacing="2", wrap="wrap", padding_y="4px",
    )


# 旧 _quiz_explanation_panel / _quiz_context_panel / _quiz_pros_cons_grid は
# 新設計で不要になったため撤去 (i18n キー drep_match_q_*_context / _pros / _cons
# を参照していた)。


def _choice_button(level: int, label, scheme: str = "amber") -> rx.Component:
    """3 択 (左 / 迷う / 右) の大型回答ボタン。"""
    is_selected = DrepMatchState.current_answer == level
    if scheme == "gray":
        sel_bg, sel_border = "var(--gray-3)", "var(--gray-9)"
        sel_text = "var(--gray-12)"
    else:
        sel_bg, sel_border = "var(--amber-3)", "var(--amber-9)"
        sel_text = "var(--amber-12)"
    return rx.el.button(
        rx.text(label, size="4", weight="bold",
                color=rx.cond(is_selected, sel_text, "var(--gray-12)"),
                style={"whiteSpace": "normal", "textAlign": "center",
                       "lineHeight": "1.4"}),
        on_click=DrepMatchState.set_answer(level),
        cursor="pointer",
        style={
            "padding":      "24px 18px",
            "borderRadius": "14px",
            "background":   rx.cond(is_selected, sel_bg, "transparent"),
            "border":       rx.cond(is_selected, f"2px solid {sel_border}",
                                    "1.5px solid var(--gray-6)"),
            "minWidth":     "200px",
            "minHeight":    "100px",
            "flex":         "1 1 220px",
            "transition":   "background 0.15s, border-color 0.15s, transform 0.15s",
        },
        _hover={"background": "var(--amber-2)", "border_color": "var(--amber-8)",
                "transform": "translateY(-1px)"},
    )


def _quiz_view() -> rx.Component:
    """質問カード (二者択一+迷う + 重要マーク toggle)。"""
    importance_btn_disabled = (
        DrepMatchState.importance_full
        & ~DrepMatchState.current_question_is_important
    )
    importance_btn = rx.button(
        rx.cond(
            DrepMatchState.current_question_is_important,
            rx.hstack(
                rx.icon("star", size=16, color="var(--amber-11)"),
                rx.text(AuthState.t["drep_match_importance_selected"], size="2"),
                spacing="2", align="center",
            ),
            rx.hstack(
                rx.icon("star", size=16),
                rx.text(AuthState.t["drep_match_importance_select"], size="2"),
                spacing="2", align="center",
            ),
        ),
        on_click=DrepMatchState.toggle_importance,
        variant=rx.cond(DrepMatchState.current_question_is_important, "solid", "soft"),
        color_scheme="amber",
        size="2",
        disabled=importance_btn_disabled,
        cursor=rx.cond(importance_btn_disabled, "not-allowed", "pointer"),
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(
                    AuthState.t["drep_match_progress"], " ",
                    DrepMatchState.progress_current,
                    " ", AuthState.t["drep_match_progress_of"], " ",
                    DrepMatchState.progress_total,
                    size="3", color="var(--gray-11)", weight="medium",
                ),
                rx.spacer(),
                rx.box(
                    rx.box(
                        width=DrepMatchState.progress_pct + "%",
                        height="100%",
                        background="var(--amber-9)",
                        border_radius="999px",
                        transition="width 0.3s",
                    ),
                    width="120px", height="6px",
                    background="var(--gray-4)",
                    border_radius="999px",
                    overflow="hidden",
                ),
                width="100%", align="center",
            ),
            rx.heading(
                AuthState.t[DrepMatchState.current_question_i18n_key],
                size="6", weight="bold", color="var(--gray-12)",
                style={"lineHeight": "1.5", "textAlign": "center"},
            ),
            # 二者択一 + 迷う (大きな 3 ボタン)
            rx.hstack(
                _choice_button(1, AuthState.t[DrepMatchState.current_left_i18n_key], "amber"),
                _choice_button(2, AuthState.t["drep_match_answer_unsure"], "gray"),
                _choice_button(3, AuthState.t[DrepMatchState.current_right_i18n_key], "amber"),
                spacing="3", wrap="wrap", justify="center", width="100%", padding_y="6px",
            ),
            # 重要視 toggle
            rx.hstack(
                importance_btn,
                rx.text(
                    AuthState.t["drep_match_importance_hint"],
                    size="2", color="var(--gray-10)",
                ),
                spacing="3", align="center", wrap="wrap",
            ),
            # 戻るボタン (左寄せ、控えめ)
            rx.hstack(
                rx.cond(
                    DrepMatchState.is_first_question,
                    rx.fragment(),
                    rx.button(
                        rx.icon("chevron-left", size=16),
                        rx.text(AuthState.t["drep_match_back_button"], size="2"),
                        on_click=DrepMatchState.prev_question,
                        variant="soft", color_scheme="gray", cursor="pointer",
                    ),
                ),
                rx.spacer(),
                width="100%", align="center", padding_top="8px",
            ),
            # 診断する (最終問のみ表示。下部中央に大型で出す)
            rx.cond(
                DrepMatchState.can_submit,
                rx.center(
                    rx.el.button(
                        rx.text(
                            AuthState.t["drep_match_submit_button"],
                            size="5", weight="bold", color="var(--amber-12)",
                        ),
                        rx.icon("arrow-right", size=24, color="var(--amber-12)"),
                        on_click=DrepMatchState.submit_quiz,
                        cursor="pointer",
                        style={
                            "display":        "inline-flex",
                            "alignItems":     "center",
                            "justifyContent": "center",
                            "gap":            "12px",
                            "padding":        "20px 64px",
                            "borderRadius":   "999px",
                            "background":     "var(--amber-9)",
                            "border":         "none",
                            "minWidth":       "320px",
                            "boxShadow":      "0 4px 16px -4px rgba(245,158,11,0.45)",
                            "transition":     "background 0.15s, transform 0.15s, box-shadow 0.15s",
                        },
                        _hover={
                            "background": "var(--amber-10)",
                            "transform":  "translateY(-1px)",
                            "box_shadow": "0 6px 20px -4px rgba(245,158,11,0.55)",
                        },
                    ),
                    width="100%", padding_y="20px",
                ),
                rx.fragment(),
            ),
            spacing="5", align_items="stretch", width="100%",
        ),
        padding="32px 28px",
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.04)"),
        width="100%",
    )


def _social_link_icon(item) -> rx.Component:
    """item は 'icon|url' 形式の Var[str] (CIP-119 references_json)。"""
    parts = item.split("|")
    icon_name = parts[0]
    url = parts[1]
    icon_comp = rx.match(
        icon_name,
        ("twitter",        rx.icon("twitter",        size=14, color="#1DA1F2")),
        ("github",         rx.icon("github",         size=14, color="var(--gray-12)")),
        ("send",           rx.icon("send",           size=14, color="#2AABEE")),
        ("youtube",        rx.icon("youtube",        size=14, color="#FF0000")),
        ("message-circle", rx.icon("message-circle", size=14, color="#5865F2")),
        ("linkedin",       rx.icon("linkedin",       size=14, color="#0A66C2")),
        rx.icon("globe", size=14, color="var(--gray-11)"),
    )
    return rx.link(
        rx.box(
            icon_comp,
            width="26px", height="26px",
            display="flex", align_items="center", justify_content="center",
            border_radius="999px",
            background="var(--gray-3)",
            style={"transition": "background 0.15s"},
            _hover={"background": "var(--amber-4)"},
        ),
        href=url, is_external=True, underline="none",
        custom_attrs={"title": url},
    )


def _axis_chip(label_key, scheme: str) -> rx.Component:
    """軸スコアチップ (一致点 / 相違点 / 低信頼)。

    label_key: 7 axis i18n キー ("drep_match_axis_<axis>")

    scheme:
      "match"    → green
      "mismatch" → tomato
      "lowconf"  → gray
    """
    label = AuthState.t[label_key]
    if scheme == "match":
        bg = "var(--green-3)"; border = "1px solid var(--green-7)"; color = "var(--green-12)"
    elif scheme == "mismatch":
        bg = "var(--tomato-3)"; border = "1px solid var(--tomato-7)"; color = "var(--tomato-12)"
    else:
        bg = "var(--gray-3)"; border = "1px solid var(--gray-7)"; color = "var(--gray-12)"
    return rx.box(
        rx.text(label, size="2", weight="medium", color=color,
                style={"whiteSpace": "nowrap"}),
        padding="4px 12px",
        border_radius="999px",
        background=bg,
        border=border,
        style={"display": "inline-flex"},
    )


def _match_axis_chip(label_key) -> rx.Component:
    return _axis_chip(label_key, "match")


def _mismatch_axis_chip(label_key) -> rx.Component:
    return _axis_chip(label_key, "mismatch")


def _lowconf_axis_chip(label_key) -> rx.Component:
    return _axis_chip(label_key, "lowconf")


def _match_result_card(r) -> rx.Component:
    """マッチ結果 1 件の DRep カード (委任コンパス用)。"""
    avatar = rx.cond(
        r["image_url"] != "",
        rx.image(
            src=r["image_url"],
            width="56px", height="56px",
            border_radius="50%",
            style={"objectFit": "cover", "flexShrink": "0"},
            custom_attrs={"referrerpolicy": "no-referrer"},
        ),
        rx.center(
            rx.icon("user-round", size=28, color="var(--gray-9)"),
            width="56px", height="56px",
            border_radius="50%",
            background="var(--gray-4)",
            style={"flexShrink": "0"},
        ),
    )
    name_text = rx.cond(
        r["given_name"] != "",
        rx.text(r["given_name"], size="3", weight="bold", color="var(--gray-12)"),
        rx.text(AuthState.t["drep_no_name"], size="3", color="var(--gray-10)"),
    )
    header_link = rx.link(
        rx.hstack(
            avatar,
            rx.vstack(
                name_text,
                rx.hstack(
                    rx.text(AuthState.t["drep_match_results_match_label"], " ",
                            size="1", color="var(--gray-10)"),
                    rx.text(r["total_score"], "%",
                            size="5", weight="bold", color="var(--amber-11)"),
                    spacing="1", align="baseline", wrap="wrap",
                ),
                spacing="1", align_items="start", flex="1", min_width="0",
            ),
            spacing="3", align="center", width="100%",
        ),
        href="/drep/" + r["drep_id"],
        color="inherit", underline="none",
        style={"display": "block", "width": "100%"},
        _hover={"color": "var(--amber-11)"},
    )
    fiat_text = rx.cond(
        AuthState.language == "en",
        rx.cond(
            r["amount_usd"] != "",
            rx.text("(≈ ", r["amount_usd"], ")", size="1", color="var(--gray-10)"),
            rx.fragment(),
        ),
        rx.cond(
            r["amount_jpy"] != "",
            rx.text("(≈ ", r["amount_jpy"], ")", size="1", color="var(--gray-10)"),
            rx.fragment(),
        ),
    )
    delegation_row = rx.hstack(
        rx.vstack(
            rx.text(AuthState.t["drep_delegated_label"], size="1", color="var(--gray-10)"),
            rx.hstack(
                rx.text(r["amount_ada"], size="4", weight="bold", color="var(--amber-11)"),
                rx.text("ADA", size="1", color="var(--gray-11)"),
                spacing="1", align="baseline",
            ),
            fiat_text,
            spacing="0", align="start",
        ),
        rx.vstack(
            rx.text(AuthState.t["drep_influence_label"], size="1", color="var(--gray-10)"),
            rx.hstack(
                rx.text(r["share_pct"], size="4", weight="bold", color="var(--blue-11)"),
                rx.text("%", size="1", color="var(--blue-10)"),
                spacing="0", align="baseline",
            ),
            spacing="0", align="start",
        ),
        rx.vstack(
            rx.text(AuthState.t["drep_match_results_analyzed_votes"],
                    size="1", color="var(--gray-10)"),
            rx.hstack(
                rx.text(r["analyzed_votes"], size="4", weight="bold", color="var(--gray-12)"),
                rx.text(AuthState.t["gov_results_unit"], size="1", color="var(--gray-11)"),
                spacing="1", align="baseline",
            ),
            spacing="0", align="start",
        ),
        rx.vstack(
            rx.text(AuthState.t["drep_match_results_reasoning_rate"],
                    size="1", color="var(--gray-10)"),
            rx.hstack(
                rx.text(r["reasoning_pct"], size="4", weight="bold", color="var(--gray-12)"),
                rx.text("%", size="1", color="var(--gray-11)"),
                spacing="0", align="baseline",
            ),
            spacing="0", align="start",
        ),
        spacing="6", align="start", wrap="wrap",
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(header_link, flex="1", min_width="0"),
                drep_delegate_button(r["drep_id"]),
                spacing="3", align="center", width="100%", wrap="wrap",
            ),
            delegation_row,
            # AI が見たこの DRep のサマリ (1 行、なければ非表示)
            rx.cond(
                r["summary"] != "",
                rx.box(
                    rx.hstack(
                        rx.icon("sparkles", size=14, color="var(--amber-11)"),
                        rx.text(
                            AuthState.t["drep_match_summary_label"],
                            size="1", weight="bold", color="var(--amber-11)",
                            style={"whiteSpace": "nowrap"},
                        ),
                        spacing="2", align="center",
                    ),
                    rx.text(
                        r["summary"],
                        size="2", color="var(--gray-12)",
                        style={"lineHeight": "1.6", "marginTop": "4px"},
                    ),
                    padding="12px 14px",
                    border_radius="8px",
                    background="var(--amber-2)",
                    border="1px solid var(--amber-5)",
                    width="100%",
                ),
                rx.fragment(),
            ),
            # 一致点
            rx.cond(
                r["matched_axes_csv"] != "",
                rx.hstack(
                    rx.text(
                        AuthState.t["drep_match_results_matched_label"],
                        size="2", color="var(--green-11)", weight="medium",
                        style={"flexShrink": "0"},
                    ),
                    rx.foreach(r["matched_axes_csv"].split(","), _match_axis_chip),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.fragment(),
            ),
            # 相違点
            rx.cond(
                r["mismatched_axes_csv"] != "",
                rx.hstack(
                    rx.text(
                        AuthState.t["drep_match_results_mismatched_label"],
                        size="2", color="var(--tomato-11)", weight="medium",
                        style={"flexShrink": "0"},
                    ),
                    rx.foreach(r["mismatched_axes_csv"].split(","), _mismatch_axis_chip),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.fragment(),
            ),
            # 低信頼軸
            rx.cond(
                r["low_conf_axes_csv"] != "",
                rx.vstack(
                    rx.hstack(
                        rx.text(
                            AuthState.t["drep_match_results_low_conf_label"],
                            size="2", color="var(--gray-11)", weight="medium",
                            style={"flexShrink": "0"},
                        ),
                        rx.foreach(r["low_conf_axes_csv"].split(","), _lowconf_axis_chip),
                        spacing="2", align="center", wrap="wrap",
                    ),
                    rx.text(
                        AuthState.t["drep_match_results_low_conf_note"],
                        size="1", color="var(--gray-10)",
                    ),
                    spacing="1", align="start", width="100%",
                ),
                rx.fragment(),
            ),
            # 独自分類の注記
            rx.text(
                AuthState.t["drep_match_results_classification_note"],
                size="1", color="var(--gray-10)",
                style={"fontStyle": "italic"},
            ),
            spacing="3", align_items="stretch", width="100%",
        ),
        padding="18px 20px",
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.04)"),
        width="100%",
        _hover={
            "border_color": rx.color("amber", 8),
            "transform":    "translateY(-1px)",
        },
        style={"transition": "border-color 0.15s, transform 0.15s"},
    )


def _results_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading(AuthState.t["drep_match_results_heading"], size="5"),
            rx.spacer(),
            rx.button(
                rx.icon("rotate-cw", size=14),
                rx.text(AuthState.t["drep_match_restart_button"], size="2"),
                on_click=DrepMatchState.start_quiz,
                variant="soft", color_scheme="gray", cursor="pointer",
            ),
            width="100%", align="center", wrap="wrap",
        ),
        rx.cond(
            DrepMatchState.results,
            rx.vstack(
                rx.foreach(
                    DrepMatchState.results.to(list[dict[str, str]]),
                    _match_result_card,
                ),
                spacing="3", width="100%",
            ),
            rx.callout(
                AuthState.t["drep_match_results_no_match"],
                icon="info", color_scheme="gray",
            ),
        ),
        spacing="4", width="100%",
    )


def _intro_feature_card(icon: str, title_key: str, desc_key: str) -> rx.Component:
    """スタートカード内の特徴 1 枚 (アイコン + タイトル + 説明)。"""
    return rx.vstack(
        rx.center(
            rx.icon(icon, size=32, color="var(--amber-11)"),
            width="64px", height="64px",
            border_radius="999px",
            background="var(--amber-3)",
            border="1px solid var(--amber-6)",
        ),
        rx.text(
            AuthState.t[title_key],
            size="3", weight="bold", color="var(--gray-12)",
            style={"textAlign": "center"},
        ),
        rx.text(
            AuthState.t[desc_key],
            size="2", color="var(--gray-11)",
            style={"textAlign": "center", "lineHeight": "1.7"},
        ),
        spacing="3", align="center", width="100%",
        padding="20px 18px",
    )


def _intro_view() -> rx.Component:
    """マッチング診断タブを押した直後に表示するスタート画面 (ヒーロー型)。"""
    # ヒーロー (大型 握手アイコン + 見出し + リード文)
    hero = rx.vstack(
        rx.center(
            rx.icon("handshake", size=56, color="var(--amber-11)"),
            width="120px", height="120px",
            border_radius="999px",
            background=rx.color_mode_cond("var(--amber-2)", "var(--amber-3)"),
            border=f"2px solid {rx.color('amber', 7)}",
            style={"boxShadow": "0 6px 24px -8px rgba(245,158,11,0.35)"},
        ),
        rx.hstack(
            rx.heading(
                AuthState.t["drep_match_heading"],
                size="8", weight="bold", color="var(--gray-12)",
                style={"letterSpacing": "-0.01em", "textAlign": "center"},
            ),
            rx.badge(
                AuthState.t["drep_match_beta_label"],
                color_scheme="amber", variant="soft", size="2",
                style={"alignSelf": "center"},
            ),
            spacing="3", align="center", wrap="wrap", justify="center",
        ),
        rx.text(
            AuthState.t["drep_match_intro"],
            size="4", color="var(--gray-11)",
            style={
                "lineHeight": "1.8",
                "textAlign": "center",
                "maxWidth": "720px",
                "margin": "0 auto",
            },
        ),
        spacing="5", align="center", width="100%",
    )

    # 特徴 3 カード (グリッド配置、レスポンシブ)
    features = rx.box(
        _intro_feature_card("list-checks", "drep_match_feature1_title", "drep_match_feature1_desc"),
        _intro_feature_card("radar",       "drep_match_feature2_title", "drep_match_feature2_desc"),
        _intro_feature_card("users-round", "drep_match_feature3_title", "drep_match_feature3_desc"),
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(240px, 1fr))",
            "gridAutoRows": "1fr",
            "gap": "16px",
        },
        width="100%",
    )

    # 注意書きと AI 免責
    notes = rx.vstack(
        rx.text(
            AuthState.t["drep_match_intro_note"],
            size="2", color="var(--gray-10)",
            style={"lineHeight": "1.7", "textAlign": "center"},
        ),
        rx.callout(
            AuthState.t["drep_match_ai_disclaimer"],
            icon="triangle-alert",
            color_scheme="amber",
            size="2",
        ),
        spacing="3", align="stretch", width="100%",
    )

    # 大型開始ボタン (クイズの「診断する」ボタンと同じスタイルで統一)
    start_button = rx.center(
        rx.el.button(
            rx.icon("play", size=24, color="var(--amber-12)"),
            rx.text(
                AuthState.t["drep_match_start_button"],
                size="5", weight="bold", color="var(--amber-12)",
            ),
            on_click=DrepMatchState.start_quiz,
            cursor="pointer",
            style={
                "display":        "inline-flex",
                "alignItems":     "center",
                "justifyContent": "center",
                "gap":            "12px",
                "padding":        "20px 64px",
                "borderRadius":   "999px",
                "background":     "var(--amber-9)",
                "border":         "none",
                "minWidth":       "320px",
                "boxShadow":      "0 4px 16px -4px rgba(245,158,11,0.45)",
                "transition":     "background 0.15s, transform 0.15s, box-shadow 0.15s",
            },
            _hover={
                "background": "var(--amber-10)",
                "transform":  "translateY(-1px)",
                "box_shadow": "0 6px 20px -4px rgba(245,158,11,0.55)",
            },
        ),
        width="100%", padding_y="12px",
    )

    card = rx.box(
        rx.vstack(
            hero,
            features,
            notes,
            start_button,
            spacing="7", align_items="stretch", width="100%",
        ),
        padding="48px 36px",
        border_radius="16px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond(
            "linear-gradient(180deg, var(--amber-1) 0%, white 60%)",
            "linear-gradient(180deg, rgba(245,158,11,0.08) 0%, rgba(255,255,255,0.02) 60%)",
        ),
        width="100%",
    )
    return rx.box(card, width="100%", padding_y="12px")


def _match_view() -> rx.Component:
    """intro / quiz / results を view に応じて切り替える親コンテナ。"""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading(AuthState.t["drep_match_heading"], size="6", weight="bold"),
                rx.badge(
                    AuthState.t["drep_match_beta_label"],
                    color_scheme="amber", variant="soft", size="2",
                    style={"alignSelf": "center"},
                ),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.match(
                DrepMatchState.view,
                ("intro",   _intro_view()),
                ("results", _results_view()),
                rx.box(_quiz_view(), width="100%", padding_y="12px"),
            ),
            spacing="4", align_items="stretch", width="100%",
        ),
        width="100%",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/governance/drep",
    title="DRep一覧 | ガバナンス | Cardanoism",
    on_load=DrepState.on_load,
)
def governance_drep_page() -> rx.Component:
    return rx.cond(
        DrepState.load,
        rx.box(
            login_modal(),
            # DRep 委任確認モーダル (1 ページに 1 度だけマウント)
            drep_delegation_dialog(),
            rx.vstack(
                _breadcrumb(),
                governance_subnav("drep"),
                _drep_match_tabs(),
                rx.match(
                    DrepMatchState.view,
                    ("intro",   _match_view()),
                    ("quiz",    _match_view()),
                    ("results", _match_view()),
                    # default: "list" — 既存の DRep 一覧
                    rx.vstack(
                        _filter_bar(),
                        rx.hstack(
                            rx.text(AuthState.t["gov_search_results"], size="3"),
                            rx.text(DrepState.total_items, size="5", weight="bold", color="var(--amber-11)"),
                            rx.text(AuthState.t["gov_results_unit"], size="3"),
                            rx.spacer(),
                            rx.hstack(
                                rx.text(AuthState.t["drep_total_delegation_label"], size="2", color="var(--gray-10)"),
                                rx.text(DrepState.total_delegation_ada_display, size="3", weight="bold", color="var(--amber-11)"),
                                rx.text("ADA", size="1", color="var(--gray-10)"),
                                spacing="2", align="baseline",
                            ),
                            spacing="2", align="baseline", width="100%", wrap="wrap",
                        ),
                        rx.cond(
                            DrepState.dreps,
                            rx.vstack(
                                rx.foreach(DrepState.dreps.to(list[dict[str, str]]), _drep_card),
                                spacing="2", width="100%",
                            ),
                            rx.callout(AuthState.t["drep_empty"], icon="info", color_scheme="gray"),
                        ),
                        rx.cond(DrepState.dreps, _pagination(), rx.fragment()),
                        spacing="4", width="100%",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
