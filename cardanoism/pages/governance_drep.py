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
    get_ga_titles as _get_ga_titles,
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
    """DRepマッチング診断 v2 (7 axis / 9 問 二者択一+迷う) の State。

    view: "list" / "intro" / "quiz" / "results"
    answers: { q_id: 1 (左) / 2 (迷う) / 3 (右) }
    importance: 重要マーク済み q_id のリスト (最大 3)
    results: quality filter を通った DRep からマッチ度上位 N 件
    """
    view: str = "list"
    current_question: int = 0
    answers: dict[str, int] = {}
    importance: list[str] = []
    results: list[dict[str, str]] = []

    # 透明性モーダル: axis chip クリックで「なぜこの axis 判定？」を見せる
    evidence_modal_open: bool = False
    modal_drep_name: str = ""
    modal_axis_label_key: str = ""
    modal_axis_side_label: str = ""        # 「攻め 22%」のような表示
    modal_axis_conf_pct: str = ""          # 「90%」(信頼度)
    modal_axis_vote_count: str = ""        # 「5 票分析」
    modal_evidence_items: list[dict[str, str]] = []

    @rx.var
    def current_question_i18n_key(self) -> str:
        idx = self.current_question
        if 0 <= idx < _COMPASS_QUESTION_TOTAL:
            return _COMPASS_QUESTIONS[idx].i18n_key
        return ""

    @rx.var
    def current_context_i18n_key(self) -> str:
        idx = self.current_question
        if 0 <= idx < _COMPASS_QUESTION_TOTAL:
            return _COMPASS_QUESTIONS[idx].context_i18n_key
        return ""

    @rx.var
    def current_pros_i18n_key(self) -> str:
        idx = self.current_question
        if 0 <= idx < _COMPASS_QUESTION_TOTAL:
            return _COMPASS_QUESTIONS[idx].pros_i18n_key
        return ""

    @rx.var
    def current_cons_i18n_key(self) -> str:
        idx = self.current_question
        if 0 <= idx < _COMPASS_QUESTION_TOTAL:
            return _COMPASS_QUESTIONS[idx].cons_i18n_key
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
        """5 段階 Likert で回答。最終問以外は次に進む。
        1=強く左 / 2=やや左 / 3=中立 / 4=やや右 / 5=強く右
        """
        try:
            v = int(level)
        except (TypeError, ValueError):
            return
        if v < 1 or v > 5:
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
        """回答から user_vector を計算し、quality filter を通った TOP N マッチを取得。

        amount (委任量) はソート / フィルタには使わない。
        投票実績 + 投票理由公開率 + 自己紹介の有無で母集団を絞り、純粋に
        マッチ度の高い順に並べる (liquid democracy 的)。
        """
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

        # 委任量 / fiat 表示 (カードへの参考表示用)
        rate = get_fiat_rate() or {}
        ada_jpy = float(rate.get("ada_jpy") or 0)
        ada_usd = float(rate.get("ada_usd") or 0)
        total_lovelace = sum_total_delegation(only_registered=True)

        def _to_label(axes: list[str]) -> str:
            # 7 axis を「drep_match_axis_<axis>」i18n キーに変換
            return ",".join(f"drep_match_axis_{a}" for a in (axes or []) if a)

        # 透明性モーダル用に GA タイトルを batch fetch
        all_pids: set[str] = set()
        for r in raw:
            evd = r.get("evidence_per_axis") or {}
            if isinstance(evd, dict):
                for items in evd.values():
                    for e in (items or []):
                        pid = str(e.get("proposal_id") or "")
                        if pid:
                            all_pids.add(pid)
        ga_titles: dict[str, str] = {}
        if all_pids:
            try:
                ga_titles = _get_ga_titles(list(all_pids))
            except Exception as e:  # noqa: BLE001
                logger.debug("get_ga_titles failed: %s", e)

        # axis_detail を {axis: {score, conf, user_value}} の flat dict にする
        # モーダルで axis ごとの情報表示用
        def _axis_info(r: dict, axis: str) -> dict[str, str]:
            details = r.get("axis_details") or []
            for d in details:
                if d.get("axis") == axis:
                    return {
                        "score":      f"{float(d.get('drep_value') or 0.5):.2f}",
                        "conf":       f"{float(d.get('confidence') or 0.0) * 100:.0f}",
                        "user_value": f"{float(d.get('user_value') or 0.5):.2f}",
                    }
            return {"score": "0.50", "conf": "0", "user_value": "0.50"}

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

            # axis ごとの evidence (GA タイトル付き) を flat field で持つ
            # Reflex の Var 操作で扱いやすいよう axis 名を suffix にした dict 文字列で
            evidence_dict = r.get("evidence_per_axis") or {}
            evidence_by_axis: dict[str, list[dict[str, str]]] = {}
            axis_info_by_axis: dict[str, dict[str, str]] = {}
            for axis in _COMPASS_AXES:
                items = evidence_dict.get(axis, []) if isinstance(evidence_dict, dict) else []
                enriched: list[dict[str, str]] = []
                for e in (items or []):
                    pid = str(e.get("proposal_id") or "")
                    enriched.append({
                        "proposal_id": pid,
                        "ga_title":    str(ga_titles.get(pid, pid[:24])),
                        "vote":        str(e.get("vote") or ""),
                        "direction":   f"{float(e.get('direction') or 0.5):.2f}",
                        "reason":      str(e.get("reason") or "")[:200],
                    })
                evidence_by_axis[axis] = enriched
                axis_info_by_axis[axis] = _axis_info(r, axis)

            out.append({
                "drep_id":              drep_id,
                "given_name":           str(d.get("given_name") or ""),
                "image_url":            str(d.get("image_url") or ""),
                "total_score":          f"{float(r.get('total_score') or 0):.1f}",
                "summary":              str(r.get("summary") or ""),
                "summary_en":           str(r.get("summary_en") or ""),
                "reasoning_pct":        f"{float(r.get('reasoning_disclosure_rate') or 0) * 100:.1f}",
                "analyzed_votes":       str(r.get("analyzed_vote_count") or 0),
                "matched_axes_csv":     _to_label(r.get("matched_axes")),
                "mismatched_axes_csv":  _to_label(r.get("mismatched_axes")),
                "low_conf_axes_csv":    _to_label(r.get("low_confidence_axes")),
                "amount_ada":           format_ada(amount, integer=True) if amount else "0",
                "amount_jpy":           jpy_d,
                "amount_usd":           usd_d,
                "share_pct":            share_display,
                "evidence_by_axis":     evidence_by_axis,
                "axis_info":            axis_info_by_axis,
            })
        self.results = out
        self.view = "results"

    # ─── 透明性モーダル: axis chip クリックで開く ─────────────

    def open_evidence_modal(self, drep_id: str, drep_name: str, label_key: str):
        """axis chip クリックハンドラ。drep_id + axis i18n key から evidence を抽出して
        モーダル state に反映 → モーダル表示 ON。"""
        # i18n key "drep_match_axis_<axis>" から axis 名を抽出
        # axis 名にアンダースコアが含まれる (large_treasury 等) ので split[-1] は不可。
        _PREFIX = "drep_match_axis_"
        axis = label_key[len(_PREFIX):] if (label_key or "").startswith(_PREFIX) else ""
        if not axis:
            return
        # 対象カードを探す
        card = next((r for r in (self.results or []) if r.get("drep_id") == drep_id), None)
        if not card:
            return
        evidence_by_axis = card.get("evidence_by_axis") or {}
        items = evidence_by_axis.get(axis, []) if isinstance(evidence_by_axis, dict) else []
        info = (card.get("axis_info") or {}).get(axis, {}) if isinstance(card.get("axis_info"), dict) else {}

        self.modal_drep_name = drep_name or drep_id[:24]
        self.modal_axis_label_key = label_key
        self.modal_axis_side_label = f"DRep スコア: {info.get('score', '?')} / あなた: {info.get('user_value', '?')}"
        self.modal_axis_conf_pct = f"{info.get('conf', '0')}%"
        self.modal_axis_vote_count = f"{len(items)} 票"
        self.modal_evidence_items = list(items)
        self.evidence_modal_open = True

    def close_evidence_modal(self):
        self.evidence_modal_open = False

    def on_evidence_modal_open_change(self, is_open: bool):
        """Radix Dialog の閉じる操作 (× / ESC / overlay クリック) で発火。"""
        if not is_open:
            self.evidence_modal_open = False


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


def _drep_match_hero_cta() -> rx.Component:
    """DRep 一覧ページの最上部に置く、マッチング診断への大型 CTA カード。
    クリックで /governance/drep/match に遷移。スマホでは文字 / アイコンを縮小。
    """
    return rx.link(
        rx.box(
            rx.hstack(
                # 左: アイコンバッジ (スマホで縮小)
                rx.center(
                    rx.icon("sparkles", size=24, color="var(--amber-12)"),
                    border_radius="999px",
                    background="var(--amber-3)",
                    border=f"1px solid {rx.color('amber', 7)}",
                    style={
                        "flexShrink": "0",
                        "width": "48px", "height": "48px",
                        "@media (min-width: 768px)": {
                            "width": "64px", "height": "64px",
                        },
                    },
                ),
                # 中: タイトル + 説明 (スマホでサイズ調整)
                rx.vstack(
                    rx.hstack(
                        rx.text(
                            AuthState.t["drep_match_hero_cta_title"],
                            size={"initial": "3", "sm": "5"},
                            weight="bold", color="var(--gray-12)",
                        ),
                        rx.badge(
                            AuthState.t["drep_match_beta_label"],
                            color_scheme="amber", variant="soft", size="1",
                        ),
                        spacing="2", align="center", wrap="wrap",
                    ),
                    rx.text(
                        AuthState.t["drep_match_hero_cta_desc"],
                        size={"initial": "1", "sm": "2"},
                        color="var(--gray-11)",
                    ),
                    spacing="1", align="start", flex="1", min_width="0",
                ),
                # 右: 矢印アイコン (CTA を強調、ダーク対応で amber-contrast)
                rx.center(
                    rx.icon("arrow-right", size=22, color="var(--amber-contrast)"),
                    width="42px", height="42px",
                    border_radius="999px",
                    background="var(--amber-9)",
                    style={"flexShrink": "0"},
                ),
                spacing="4", align="center", width="100%",
            ),
            padding="18px 22px",
            border_radius="14px",
            border=f"1px solid {rx.color('amber', 6)}",
            background=rx.color_mode_cond(
                "linear-gradient(135deg, var(--amber-2) 0%, white 100%)",
                "linear-gradient(135deg, rgba(245,158,11,0.10) 0%, rgba(255,255,255,0.02) 100%)",
            ),
            width="100%",
            style={
                "transition": "transform 0.15s, box-shadow 0.15s, border-color 0.15s",
                "boxShadow": "0 2px 8px -2px rgba(245,158,11,0.20)",
            },
            _hover={
                "transform": "translateY(-2px)",
                "border_color": rx.color("amber", 8),
                "box_shadow": "0 6px 20px -4px rgba(245,158,11,0.35)",
            },
        ),
        href="/governance/drep/match",
        style={"textDecoration": "none", "width": "100%"},
    )


# 旧 _quiz_explanation_panel / _quiz_context_panel / _quiz_pros_cons_grid は
# 新設計で不要になったため撤去 (i18n キー drep_match_q_*_context / _pros / _cons
# を参照していた)。


def _choice_button(
    level: int,
    label_key: str,
    scheme: str = "amber",
) -> rx.Component:
    """5 段階 Likert (agree/disagree) ボタン。

    level: 1 (強く反対) / 2 (やや反対) / 3 (中立) / 4 (やや賛成) / 5 (強く賛成)
    label_key: 「強く反対」「やや反対」など全質問共通の i18n キー
    scheme: "amber" (両端 = 強く) / "soft_amber" (やや) / "gray" (中立)

    v4 では全質問で同じ 5 ボタンを表示 (universal Likert)。
    質問ごとの左右ラベル変更は無し。
    """
    is_selected = DrepMatchState.current_answer == level
    if scheme == "gray":
        sel_bg, sel_border = "var(--gray-3)", "var(--gray-9)"
        sel_text = "var(--gray-12)"
        unsel_border = "1.5px solid var(--gray-6)"
    elif scheme == "soft_amber":
        sel_bg, sel_border = "var(--amber-2)", "var(--amber-7)"
        sel_text = "var(--amber-12)"
        unsel_border = "1.5px solid var(--gray-6)"
    else:  # amber (強)
        sel_bg, sel_border = "var(--amber-3)", "var(--amber-9)"
        sel_text = "var(--amber-12)"
        unsel_border = "1.5px solid var(--gray-6)"

    return rx.el.button(
        rx.text(
            AuthState.t[label_key],
            size={"initial": "2", "sm": "3"}, weight="bold",
            color=rx.cond(is_selected, sel_text, "var(--gray-12)"),
            style={"whiteSpace": "normal", "textAlign": "center",
                   "lineHeight": "1.3"},
        ),
        on_click=DrepMatchState.set_answer(level),
        cursor="pointer",
        style={
            "padding":      "12px 10px",
            "borderRadius": "12px",
            "background":   rx.cond(is_selected, sel_bg, "transparent"),
            "border":       rx.cond(is_selected, f"2px solid {sel_border}", unsel_border),
            "minHeight":    "60px",
            "flex":         "1 1 calc(50% - 6px)",
            "transition":   "background 0.15s, border-color 0.15s, transform 0.15s",
            "@media (min-width: 768px)": {
                "padding":   "16px 12px",
                "minHeight": "70px",
                "flex":      "1 1 calc(20% - 10px)",
            },
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
                size={"initial": "4", "sm": "6"},
                weight="bold", color="var(--gray-12)",
                style={"lineHeight": "1.5", "textAlign": "center"},
            ),
            # 質問の論点 (v4)
            rx.box(
                rx.hstack(
                    rx.text(
                        AuthState.t["drep_match_q_context_label"],
                        size="1", weight="bold", color="var(--amber-11)",
                        style={"whiteSpace": "nowrap"},
                    ),
                    rx.text(
                        AuthState.t[DrepMatchState.current_context_i18n_key],
                        size={"initial": "2", "sm": "3"},
                        color="var(--gray-11)",
                        style={"lineHeight": "1.7"},
                    ),
                    spacing="2", align="start", wrap="wrap",
                ),
                padding="12px 16px",
                border_radius="8px",
                background="var(--amber-2)",
                border="1px solid var(--amber-5)",
                width="100%",
            ),
            # 5 段階 Likert agree/disagree (universal labels)
            rx.hstack(
                _choice_button(1, "drep_match_answer_strongly_disagree", "amber"),
                _choice_button(2, "drep_match_answer_slightly_disagree", "soft_amber"),
                _choice_button(3, "drep_match_answer_neutral",           "gray"),
                _choice_button(4, "drep_match_answer_slightly_agree",    "soft_amber"),
                _choice_button(5, "drep_match_answer_strongly_agree",    "amber"),
                spacing="2", wrap="wrap", justify="center", width="100%", padding_y="6px",
            ),
            # 賛成派の主張 / 反対派の主張 (v4) - 横並びだがモバイルは縦に wrap
            rx.hstack(
                rx.box(
                    rx.vstack(
                        rx.text(
                            AuthState.t["drep_match_q_pros_label"],
                            size="1", weight="bold", color="var(--green-11)",
                        ),
                        rx.text(
                            AuthState.t[DrepMatchState.current_pros_i18n_key],
                            size={"initial": "1", "sm": "2"},
                            color="var(--gray-12)",
                            style={"lineHeight": "1.7", "whiteSpace": "pre-line"},
                        ),
                        spacing="1", align="start", width="100%",
                    ),
                    padding="10px 14px",
                    border_radius="8px",
                    background=rx.color_mode_cond("var(--green-2)", "rgba(34,197,94,0.06)"),
                    border="1px solid var(--green-5)",
                    style={"flex": "1 1 calc(50% - 6px)", "minWidth": "0"},
                ),
                rx.box(
                    rx.vstack(
                        rx.text(
                            AuthState.t["drep_match_q_cons_label"],
                            size="1", weight="bold", color="var(--tomato-11)",
                        ),
                        rx.text(
                            AuthState.t[DrepMatchState.current_cons_i18n_key],
                            size={"initial": "1", "sm": "2"},
                            color="var(--gray-12)",
                            style={"lineHeight": "1.7", "whiteSpace": "pre-line"},
                        ),
                        spacing="1", align="start", width="100%",
                    ),
                    padding="10px 14px",
                    border_radius="8px",
                    background=rx.color_mode_cond("var(--tomato-2)", "rgba(229,72,77,0.06)"),
                    border="1px solid var(--tomato-5)",
                    style={"flex": "1 1 calc(50% - 6px)", "minWidth": "0"},
                ),
                spacing="3", wrap="wrap", align="stretch", width="100%",
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
                            size={"initial": "4", "sm": "5"}, weight="bold",
                            color="var(--amber-contrast)",
                        ),
                        rx.icon("arrow-right", size=22, color="var(--amber-contrast)"),
                        on_click=DrepMatchState.submit_quiz,
                        cursor="pointer",
                        style={
                            "display":        "inline-flex",
                            "alignItems":     "center",
                            "justifyContent": "center",
                            "gap":            "10px",
                            "padding":        "14px 32px",
                            "borderRadius":   "999px",
                            "background":     "var(--amber-9)",
                            "border":         "none",
                            "minWidth":       "240px",
                            "maxWidth":       "100%",
                            "boxShadow":      "0 4px 16px -4px rgba(245,158,11,0.45)",
                            "transition":     "background 0.15s, transform 0.15s, box-shadow 0.15s",
                            "@media (min-width: 768px)": {
                                "padding":  "20px 64px",
                                "minWidth": "320px",
                                "gap":      "12px",
                            },
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
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.04)"),
        width="100%",
        style={
            "padding": "20px 14px",
            "@media (min-width: 768px)": {
                "padding": "32px 28px",
            },
        },
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


def _axis_chip(drep_id, drep_name, label_key, scheme: str) -> rx.Component:
    """軸スコアチップ (一致点 / 相違点 / 低信頼)。クリックで evidence モーダルを開く。

    drep_id / drep_name: クリックハンドラに渡すコンテキスト (どの DRep か)
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
    return rx.el.button(
        rx.text(label, size="2", weight="medium", color=color,
                style={"whiteSpace": "nowrap"}),
        on_click=DrepMatchState.open_evidence_modal(drep_id, drep_name, label_key),
        cursor="pointer",
        style={
            "display":      "inline-flex",
            "alignItems":   "center",
            "padding":      "4px 12px",
            "borderRadius": "999px",
            "background":   bg,
            "border":       border,
            "transition":   "transform 0.1s, filter 0.15s",
        },
        _hover={"transform": "translateY(-1px)", "filter": "brightness(1.05)"},
    )


def _evidence_modal_row(item) -> rx.Component:
    """evidence モーダル内の 1 行 (1 投票)。GA タイトルクリックで GA 詳細へ。"""
    vote_color = rx.match(
        item["vote"],
        ("Yes", "var(--green-11)"),
        ("No",  "var(--tomato-11)"),
        "var(--gray-10)",
    )
    return rx.hstack(
        # 投票結果 (Yes / No / Abstain)
        rx.text(
            item["vote"],
            size="1", weight="bold", color=vote_color,
            style={"width": "44px", "textAlign": "center", "flexShrink": "0"},
        ),
        # GA タイトル + リンク
        rx.link(
            rx.text(
                item["ga_title"],
                size="2", color="var(--gray-12)",
                style={
                    "overflow": "hidden", "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap",
                },
            ),
            href="/governance/" + item["proposal_id"],
            style={"textDecoration": "none", "flex": "1", "minWidth": "0"},
            _hover={"color": "var(--amber-11)"},
        ),
        # axis タグの reasoning (1 行)
        rx.text(
            item["reason"],
            size="1", color="var(--gray-10)",
            style={
                "overflow": "hidden", "textOverflow": "ellipsis",
                "whiteSpace": "nowrap", "flex": "1.5", "minWidth": "0",
            },
        ),
        spacing="3", align="center", width="100%",
        padding="6px 0",
        style={"borderBottom": "1px solid var(--gray-4)"},
    )


def _evidence_modal() -> rx.Component:
    """axis chip クリックで開く透明性モーダル。

    1 ページに 1 つだけマウントする (全カード共通で使い回す)。
    開いている axis と DRep は DrepMatchState に保持される。
    """
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                # ヘッダ: DRep 名 + axis 名
                rx.hstack(
                    rx.icon("sparkles", size=18, color="var(--amber-11)"),
                    rx.text(
                        DrepMatchState.modal_drep_name,
                        size="2", color="var(--gray-11)", weight="medium",
                    ),
                    rx.text("›", color="var(--gray-9)"),
                    rx.text(
                        AuthState.t[DrepMatchState.modal_axis_label_key],
                        size="3", weight="bold", color="var(--gray-12)",
                    ),
                    spacing="2", align="center", wrap="wrap",
                ),
                # サブヘッダ: score + 信頼度 + 票数
                rx.hstack(
                    rx.text(
                        DrepMatchState.modal_axis_side_label,
                        size="1", color="var(--gray-11)",
                    ),
                    rx.text("·", color="var(--gray-8)"),
                    rx.text(
                        "信頼度 ", DrepMatchState.modal_axis_conf_pct,
                        size="1", color="var(--gray-11)",
                    ),
                    rx.text("·", color="var(--gray-8)"),
                    rx.text(
                        "寄与 ", DrepMatchState.modal_axis_vote_count,
                        size="1", color="var(--gray-11)",
                    ),
                    spacing="2", align="center", wrap="wrap",
                ),
                # 投票リスト
                rx.cond(
                    DrepMatchState.modal_evidence_items,
                    rx.vstack(
                        rx.foreach(
                            DrepMatchState.modal_evidence_items.to(list[dict[str, str]]),
                            _evidence_modal_row,
                        ),
                        spacing="0", width="100%",
                        style={"maxHeight": "60vh", "overflowY": "auto"},
                    ),
                    rx.callout(
                        "この axis に寄与した投票はありません (判断材料不足)。",
                        icon="info", color_scheme="gray", size="1",
                    ),
                ),
                # 閉じるボタン
                rx.dialog.close(
                    rx.button(
                        "閉じる",
                        variant="soft", color_scheme="gray", cursor="pointer",
                        on_click=DrepMatchState.close_evidence_modal,
                    ),
                    style={"alignSelf": "flex-end"},
                ),
                spacing="3", align_items="stretch", width="100%",
            ),
            style={"maxWidth": "720px", "width": "92vw"},
        ),
        open=DrepMatchState.evidence_modal_open,
        on_open_change=DrepMatchState.on_evidence_modal_open_change,
    )


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
        rx.text(r["given_name"], size={"initial": "2", "sm": "3"},
                weight="bold", color="var(--gray-12)"),
        rx.text(AuthState.t["drep_no_name"], size={"initial": "2", "sm": "3"},
                color="var(--gray-10)"),
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
                            size={"initial": "4", "sm": "5"},
                            weight="bold", color="var(--amber-11)"),
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
    # 数値メトリクスはスマホで size 3、PC で size 4 に
    _val_size = {"initial": "3", "sm": "4"}
    delegation_row = rx.hstack(
        rx.vstack(
            rx.text(AuthState.t["drep_delegated_label"], size="1", color="var(--gray-10)"),
            rx.hstack(
                rx.text(r["amount_ada"], size=_val_size, weight="bold", color="var(--amber-11)"),
                rx.text("ADA", size="1", color="var(--gray-11)"),
                spacing="1", align="baseline",
            ),
            fiat_text,
            spacing="0", align="start",
        ),
        rx.vstack(
            rx.text(AuthState.t["drep_influence_label"], size="1", color="var(--gray-10)"),
            rx.hstack(
                rx.text(r["share_pct"], size=_val_size, weight="bold", color="var(--blue-11)"),
                rx.text("%", size="1", color="var(--blue-10)"),
                spacing="0", align="baseline",
            ),
            spacing="0", align="start",
        ),
        rx.vstack(
            rx.text(AuthState.t["drep_match_results_analyzed_votes"],
                    size="1", color="var(--gray-10)"),
            rx.hstack(
                rx.text(r["analyzed_votes"], size=_val_size, weight="bold", color="var(--gray-12)"),
                rx.text(AuthState.t["gov_results_unit"], size="1", color="var(--gray-11)"),
                spacing="1", align="baseline",
            ),
            spacing="0", align="start",
        ),
        rx.vstack(
            rx.text(AuthState.t["drep_match_results_reasoning_rate"],
                    size="1", color="var(--gray-10)"),
            rx.hstack(
                rx.text(r["reasoning_pct"], size=_val_size, weight="bold", color="var(--gray-12)"),
                rx.text("%", size="1", color="var(--gray-11)"),
                spacing="0", align="baseline",
            ),
            spacing="0", align="start",
        ),
        spacing={"initial": "3", "sm": "6"}, align="start", wrap="wrap",
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
            # 言語に応じて summary_en / summary を切替。summary_en 空ならフォールバックで summary。
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
                        rx.cond(
                            AuthState.language == "en",
                            rx.cond(r["summary_en"] != "", r["summary_en"], r["summary"]),
                            r["summary"],
                        ),
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
                    rx.foreach(
                        r["matched_axes_csv"].split(","),
                        lambda lk: _axis_chip(r["drep_id"], r["given_name"], lk, "match"),
                    ),
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
                    rx.foreach(
                        r["mismatched_axes_csv"].split(","),
                        lambda lk: _axis_chip(r["drep_id"], r["given_name"], lk, "mismatch"),
                    ),
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
                        rx.foreach(
                            r["low_conf_axes_csv"].split(","),
                            lambda lk: _axis_chip(r["drep_id"], r["given_name"], lk, "lowconf"),
                        ),
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
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.04)"),
        width="100%",
        _hover={
            "border_color": rx.color("amber", 8),
            "transform":    "translateY(-1px)",
        },
        style={
            "transition": "border-color 0.15s, transform 0.15s",
            "padding": "14px 14px",
            "@media (min-width: 768px)": {
                "padding": "18px 20px",
            },
        },
    )


def _restart_button(size: str = "3") -> rx.Component:
    """「もう一度診断」ボタン。size=\"3\" / \"4\" で大きさを切り替え。

    text/icon は amber-9 (黄〜オレンジ) 背景の上でも常に読める
    var(--amber-contrast) (= 濃色) を使う。
    """
    return rx.el.button(
        rx.icon("rotate-cw", size=18, color="var(--amber-contrast)"),
        rx.text(
            AuthState.t["drep_match_restart_button"],
            size=size, weight="bold", color="var(--amber-contrast)",
        ),
        on_click=DrepMatchState.start_quiz,
        cursor="pointer",
        style={
            "display":        "inline-flex",
            "alignItems":     "center",
            "justifyContent": "center",
            "gap":            "10px",
            "padding":        "12px 32px",
            "borderRadius":   "999px",
            "background":     "var(--amber-9)",
            "border":         "none",
            "boxShadow":      "0 2px 10px -2px rgba(245,158,11,0.35)",
            "transition":     "background 0.15s, transform 0.15s",
        },
        _hover={
            "background": "var(--amber-10)",
            "transform":  "translateY(-1px)",
        },
    )


def _results_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading(AuthState.t["drep_match_results_heading"], size="5"),
            rx.spacer(),
            _restart_button(size="3"),
            width="100%", align="center", wrap="wrap",
        ),
        # 母集団の選び方を明示 (委任量に依存しないことをユーザーに伝える)
        rx.callout(
            AuthState.t["drep_match_results_quality_note"],
            icon="info", color_scheme="gray", size="1",
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
        # 結果リスト末尾にも目立つ「もう一度診断」ボタンを置いて
        # 一覧を最後まで読んだ後でも再診断しやすくする
        rx.center(_restart_button(size="4"), width="100%", padding_y="16px"),
        spacing="4", width="100%",
    )


def _intro_feature_card(icon: str, title_key: str, desc_key: str) -> rx.Component:
    """スタートカード内の特徴 1 行 (アイコン + タイトル + 説明、横並び)。

    スマホでは文字 / アイコンを縮小して表示。
    """
    return rx.hstack(
        rx.center(
            rx.icon(icon, size=22, color="var(--amber-11)"),
            border_radius="999px",
            background="var(--amber-3)",
            border="1px solid var(--amber-6)",
            style={
                "flexShrink": "0",
                "width": "44px", "height": "44px",
                "@media (min-width: 768px)": {
                    "width": "56px", "height": "56px",
                },
            },
        ),
        rx.vstack(
            rx.text(
                AuthState.t[title_key],
                size={"initial": "3", "sm": "4"},
                weight="bold", color="var(--gray-12)",
            ),
            rx.text(
                AuthState.t[desc_key],
                size={"initial": "2", "sm": "3"},
                color="var(--gray-11)",
                style={"lineHeight": "1.6"},
            ),
            spacing="1", align="start", width="100%",
        ),
        spacing="3", align="center", width="100%",
        padding="12px 14px",
    )


def _intro_view() -> rx.Component:
    """マッチング診断タブを押した直後に表示するスタート画面。

    カード内に「DRep マッチング診断 Beta」見出しを大きく表示し、
    特徴は 3 行の縦並び (アイコン + タイトル + 説明)。
    親 _match_view 側の小さい見出しはこの view では非表示にする。
    """
    # カード内の大見出し + Beta バッジ + リード文 (スマホで縮小)
    hero = rx.vstack(
        rx.center(
            rx.icon("handshake", size=28, color="var(--amber-11)"),
            border_radius="999px",
            background=rx.color_mode_cond("var(--amber-2)", "var(--amber-3)"),
            border=f"1px solid {rx.color('amber', 6)}",
            style={
                "width": "56px", "height": "56px",
                "@media (min-width: 768px)": {
                    "width": "72px", "height": "72px",
                },
            },
        ),
        rx.hstack(
            rx.heading(
                AuthState.t["drep_match_heading"],
                size={"initial": "6", "sm": "8"},
                weight="bold", color="var(--gray-12)",
                style={"letterSpacing": "-0.01em", "textAlign": "center"},
            ),
            rx.badge(
                AuthState.t["drep_match_beta_label"],
                color_scheme="amber", variant="soft",
                size={"initial": "2", "sm": "3"},
                style={"alignSelf": "center"},
            ),
            spacing="2", align="center", wrap="wrap", justify="center",
        ),
        rx.text(
            AuthState.t["drep_match_intro"],
            size={"initial": "3", "sm": "4"},
            color="var(--gray-12)",
            style={
                "lineHeight": "1.7",
                "textAlign": "center",
                "maxWidth": "720px",
                "margin": "0 auto",
                "whiteSpace": "pre-line",
            },
        ),
        spacing="3", align="center", width="100%",
    )

    # 特徴 3 つを縦並び (各行: アイコン + タイトル + 説明)
    features = rx.vstack(
        _intro_feature_card("list-checks", "drep_match_feature1_title", "drep_match_feature1_desc"),
        _intro_feature_card("radar",       "drep_match_feature2_title", "drep_match_feature2_desc"),
        _intro_feature_card("users-round", "drep_match_feature3_title", "drep_match_feature3_desc"),
        spacing="2", align="stretch", width="100%",
    )

    # 大型開始ボタン (text/icon は amber-9 上でも読める var(--amber-contrast) を使用)
    start_button = rx.center(
        rx.el.button(
            rx.icon("play", size=20, color="var(--amber-contrast)"),
            rx.text(
                AuthState.t["drep_match_start_button"],
                size={"initial": "3", "sm": "4"}, weight="bold",
                color="var(--amber-contrast)",
            ),
            on_click=DrepMatchState.start_quiz,
            cursor="pointer",
            style={
                "display":        "inline-flex",
                "alignItems":     "center",
                "justifyContent": "center",
                "gap":            "10px",
                "padding":        "12px 32px",
                "borderRadius":   "999px",
                "background":     "var(--amber-9)",
                "border":         "none",
                "minWidth":       "220px",
                "maxWidth":       "100%",
                "boxShadow":      "0 4px 16px -4px rgba(245,158,11,0.45)",
                "transition":     "background 0.15s, transform 0.15s, box-shadow 0.15s",
                "@media (min-width: 768px)": {
                    "padding":  "14px 48px",
                    "minWidth": "260px",
                },
            },
            _hover={
                "background": "var(--amber-10)",
                "transform":  "translateY(-1px)",
                "box_shadow": "0 6px 20px -4px rgba(245,158,11,0.55)",
            },
        ),
        width="100%",
    )

    # 注意書き (footnote 風に小さく)
    disclaimer = rx.callout(
        AuthState.t["drep_match_ai_disclaimer"],
        icon="triangle-alert",
        color_scheme="amber",
        size="1",
    )

    card = rx.box(
        rx.vstack(
            hero,
            features,
            start_button,
            disclaimer,
            spacing="5", align_items="stretch", width="100%",
        ),
        border_radius="14px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond(
            "linear-gradient(180deg, var(--amber-1) 0%, white 60%)",
            "linear-gradient(180deg, rgba(245,158,11,0.08) 0%, rgba(255,255,255,0.02) 60%)",
        ),
        width="100%",
        style={
            "padding": "20px 16px",
            "@media (min-width: 768px)": {
                "padding": "28px 24px",
            },
        },
    )
    return rx.box(card, width="100%", padding_y="8px")


def _match_view() -> rx.Component:
    """intro / quiz / results を view に応じて切り替える親コンテナ。

    intro の時はカード内に大きく見出しを出すので、この外側の見出しは隠す。
    """
    return rx.box(
        rx.vstack(
            rx.cond(
                DrepMatchState.view != "intro",
                rx.hstack(
                    rx.heading(AuthState.t["drep_match_heading"], size="6", weight="bold"),
                    rx.badge(
                        AuthState.t["drep_match_beta_label"],
                        color_scheme="amber", variant="soft", size="2",
                        style={"alignSelf": "center"},
                    ),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.fragment(),
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
                # マッチング診断への大型 CTA カード (常時表示)
                _drep_match_hero_cta(),
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
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )


# ─── マッチング診断 専用ページ (/governance/drep/match) ───────────────────────


@template(
    route="/governance/drep/match",
    title="DRepマッチング診断 | ガバナンス | Cardanoism",
    on_load=DrepMatchState.enter_match_tab,
)
def governance_drep_match_page() -> rx.Component:
    """マッチング診断の専用ページ。intro / quiz / results を view に応じて切替。

    on_load の enter_match_tab で「結果があれば results / なければ intro」に振り分ける。
    list view への遷移は明示的に「DRep 一覧に戻る」リンクで /governance/drep へ。
    """
    return rx.box(
        login_modal(),
        drep_delegation_dialog(),
        # 透明性モーダル (axis chip クリックで展開、1 ページに 1 度だけマウント)
        _evidence_modal(),
        rx.vstack(
            # パンくず: ガバナンス > DRep 一覧 > マッチング診断
            breadcrumb(
                [
                    ("nav_governance", "/governance"),
                    ("gov_subnav_drep", "/governance/drep"),
                ],
                "drep_match_heading",
            ),
            governance_subnav("drep"),
            # 「DRep 一覧に戻る」リンク (タブ撤廃の代替ナビ)
            rx.link(
                rx.hstack(
                    rx.icon("arrow-left", size=14, color="var(--gray-11)"),
                    rx.text(
                        AuthState.t["drep_match_back_to_list"],
                        size="2", color="var(--gray-11)",
                    ),
                    spacing="2", align="center",
                ),
                href="/governance/drep",
                style={"textDecoration": "none", "alignSelf": "start"},
            ),
            _match_view(),
            spacing="4",
            width="100%",
        ),
        width="100%",
        max_width="1130px",
    )
