"""governance_matrix.py
DRep × GA 投票マトリクスページ (/governance/matrix)

横軸: Active な GA、縦軸: 登録済み DRep。
セルに ✅ / ❌ / ⚪ / — の投票結果と、投票理由をマウスオーバーで表示。
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

import reflex as rx


class GA(TypedDict):
    proposal_id: str
    title: str
    title_ja: str
    proposal_type: str


class Cell(TypedDict):
    vote: str
    icon: str
    color: str
    rationale: str
    rationale_ja: str
    proposal_id: str


class Row(TypedDict):
    drep_id: str
    drep_id_short: str
    given_name: str
    image_url: str
    active: str
    cells: list[Cell]

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.vote_matrix_db import (
    get_gas_for_matrix,
    count_gas_for_matrix,
    count_dreps_for_matrix,
    get_dreps_for_matrix,
    get_votes_for_matrix,
)
from cardanoism.components.breadcrumb import breadcrumb
from cardanoism.components.governance_nav import governance_subnav

logger = logging.getLogger(__name__)


_PER_PAGE_OPTIONS = ["20", "50", "100"]
DEFAULT_PER_PAGE = 50

# GA 列のページサイズ。20/30/50 から選択（パフォーマンス上の上限）
_GA_PER_PAGE_OPTIONS = ["20", "30", "50"]
DEFAULT_GA_PER_PAGE = 30

# 投票理由ツールチップの最大文字数（長すぎるとブラウザが切る）
_RATIONALE_MAX_CHARS = 600


def _trim(s: str, n: int = _RATIONALE_MAX_CHARS) -> str:
    if not s:
        return ""
    s = s.strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


# ─── State ────────────────────────────────────────────────────────────────────


class VoteMatrixState(rx.State):
    load: bool = False
    error: str = ""

    inputed_value: str = ""
    search_query: str = ""

    # GA 列のステータスフィルタ ("active" / "ratified" / "enacted" / "dropped" / "expired")
    ga_status: str = "active"
    # GA 並び順: "asc" = 左→右 = 古い→新しい (デフォルト)、"desc" = 左→右 = 新しい→古い
    ga_order: str = "asc"

    # DRep 行のページネーション
    items_per_page: int = DEFAULT_PER_PAGE
    current_page: int = 1
    total_pages: int = 1
    total_items: int = 0

    start_page: int = 1
    end_page: int = 1
    middle_page: list[int] = []

    # GA 列のページネーション
    gas_per_page: int = DEFAULT_GA_PER_PAGE
    gas_current_page: int = 1
    gas_total_pages: int = 1
    gas_total_items: int = 0

    gas_start_page: int = 1
    gas_end_page: int = 1
    gas_middle_page: list[int] = []

    # マトリクスデータ
    # gas: 横軸（GA 列）
    gas: list[GA] = []
    # matrix_rows: 縦軸（DRep 行）。各 row に cells (GA 順に並んだ投票セル) を持たせる
    matrix_rows: list[Row] = []

    def _fetch(self):
        try:
            # GA 列のページング
            gas_total = count_gas_for_matrix(status=self.ga_status)
            self.gas_total_items = gas_total
            self.gas_total_pages = max(1, (gas_total + self.gas_per_page - 1) // self.gas_per_page)
            # 現在のページが範囲外なら 1 に戻す
            if self.gas_current_page > self.gas_total_pages:
                self.gas_current_page = 1
            gas_offset = (self.gas_current_page - 1) * self.gas_per_page
            self.gas_start_page = max(1, self.gas_current_page - 3)
            self.gas_end_page   = min(self.gas_total_pages, self.gas_current_page + 3)
            self.gas_middle_page = list(range(self.gas_start_page, self.gas_end_page + 1))

            gas_raw = get_gas_for_matrix(
                status=self.ga_status,
                limit=self.gas_per_page,
                offset=gas_offset,
                order=self.ga_order,
            )
            self.gas = [
                {
                    "proposal_id":   g["proposal_id"],
                    "title":         g.get("title") or "",
                    "title_ja":      g.get("title_ja") or "",
                    "proposal_type": g.get("proposal_type") or "",
                }
                for g in gas_raw
            ]
            proposal_ids = [g["proposal_id"] for g in self.gas]

            # DRep 行のページング
            offset = (self.current_page - 1) * self.items_per_page
            dreps = get_dreps_for_matrix(
                search=self.search_query,
                limit=self.items_per_page,
                offset=offset,
            )
            total = count_dreps_for_matrix(search=self.search_query)
            self.total_items = total
            self.total_pages = max(1, (total + self.items_per_page - 1) // self.items_per_page)
            self.start_page = max(1, self.current_page - 3)
            self.end_page   = min(self.total_pages, self.current_page + 3)
            self.middle_page = list(range(self.start_page, self.end_page + 1))

            drep_ids = [d["drep_id"] for d in dreps]
            votes = get_votes_for_matrix(drep_ids, proposal_ids)

            rows: list[dict[str, Any]] = []
            for d in dreps:
                drep_id = d["drep_id"]
                cells: list[dict[str, str]] = []
                for g in self.gas:
                    vk = votes.get((drep_id, g["proposal_id"]))
                    if vk is None:
                        cells.append({
                            "vote":         "",
                            "icon":         "—",
                            "color":        "var(--gray-9)",
                            "rationale":    "",
                            "rationale_ja": "",
                            "proposal_id":  g["proposal_id"],
                        })
                    else:
                        v = (vk.get("vote") or "").lower()
                        if v == "yes":
                            icon, color = "Y", "var(--green-10)"
                        elif v == "no":
                            icon, color = "N", "var(--red-10)"
                        elif v == "abstain":
                            icon, color = "−", "var(--gray-10)"
                        else:
                            icon, color = "·", "var(--gray-7)"
                        cells.append({
                            "vote":         v,
                            "icon":         icon,
                            "color":        color,
                            "rationale":    _trim(vk.get("rationale") or ""),
                            "rationale_ja": _trim(vk.get("rationale_ja") or ""),
                            "proposal_id":  g["proposal_id"],
                        })
                drep_id_short = (
                    drep_id[:10] + "…" + drep_id[-6:] if len(drep_id) > 24 else drep_id
                )
                rows.append({
                    "drep_id":       drep_id,
                    "drep_id_short": drep_id_short,
                    "given_name":    d.get("given_name") or "",
                    "image_url":     d.get("image_url") or "",
                    "active":        "1" if d.get("active") else "",
                    "cells":         cells,
                })
            self.matrix_rows = rows
        except Exception as e:  # noqa: BLE001
            logger.exception("VoteMatrixState._fetch: %s", e)
            self.error = str(e)

    def on_load(self):
        self.load = False
        self.error = ""
        self.inputed_value = ""
        self.search_query = ""
        self.ga_status = "active"
        self.items_per_page = DEFAULT_PER_PAGE
        self.current_page = 1
        self.gas_per_page = DEFAULT_GA_PER_PAGE
        self.gas_current_page = 1
        self._fetch()
        self.load = True

    def set_ga_status(self, status: str):
        # 不正値はガード
        if status not in ("active", "ratified", "enacted", "dropped", "expired"):
            return
        self.ga_status = status
        self.current_page = 1
        self.gas_current_page = 1
        self._fetch()

    def toggle_ga_order(self):
        """GA 並び順を asc / desc でトグルする。
        asc: 左 → 右 = 古い → 新しい (時系列順) / desc: 新しい → 古い (新着順)。
        """
        self.ga_order = "desc" if self.ga_order == "asc" else "asc"
        self.gas_current_page = 1
        self._fetch()

    def set_gas_per_page(self, v: str):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return
        if n in (20, 30, 50):
            self.gas_per_page = n
            self.gas_current_page = 1
            self._fetch()

    def set_gas_page(self, p):
        try:
            self.gas_current_page = int(p)
            self._fetch()
        except (TypeError, ValueError):
            pass

    def prev_gas_page(self):
        if self.gas_current_page > 1:
            self.gas_current_page -= 1
            self._fetch()

    def next_gas_page(self):
        if self.gas_current_page < self.gas_total_pages:
            self.gas_current_page += 1
            self._fetch()

    def set_search(self, v: str):
        self.inputed_value = v
        self.search_query = v
        self.current_page = 1
        self._fetch()

    def set_per_page(self, v: str):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return
        if n in (20, 50, 100):
            self.items_per_page = n
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


# ─── UI ───────────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return breadcrumb([("nav_governance", "/governance")], "gov_subnav_matrix")


def _filter_bar() -> rx.Component:
    return rx.flex(
        rx.input(
            placeholder=AuthState.t["matrix_search_placeholder"],
            value=VoteMatrixState.inputed_value,
            on_change=VoteMatrixState.set_search.debounce(300),
            size="2",
            style={"flex": "1 1 auto", "minWidth": "200px", "maxWidth": "320px"},
        ),
        rx.hstack(
            rx.text(AuthState.t["matrix_status_label"], size="2", color="var(--gray-11)"),
            rx.select.root(
                rx.select.trigger(),
                rx.select.content(
                    rx.select.item(AuthState.t["gov_status_active"],   value="active"),
                    rx.select.item(AuthState.t["gov_status_ratified"], value="ratified"),
                    rx.select.item(AuthState.t["gov_status_enacted"],  value="enacted"),
                    rx.select.item(AuthState.t["gov_status_dropped"],  value="dropped"),
                    rx.select.item(AuthState.t["gov_status_expired"],  value="expired"),
                ),
                value=VoteMatrixState.ga_status,
                on_change=VoteMatrixState.set_ga_status,
                size="2",
            ),
            spacing="2",
            align="center",
        ),
        rx.spacer(),
        # GA 並び順トグル: 左 → 右 = 古い → 新しい (asc) / 新しい → 古い (desc)
        rx.hstack(
            rx.text(AuthState.t["matrix_order_label"], size="2", color="var(--gray-11)"),
            rx.el.button(
                rx.text(
                    rx.cond(
                        VoteMatrixState.ga_order == "asc",
                        AuthState.t["matrix_order_asc"],
                        AuthState.t["matrix_order_desc"],
                    ),
                    size="2",
                    weight="medium",
                ),
                on_click=VoteMatrixState.toggle_ga_order,
                style={
                    "display":      "inline-flex",
                    "alignItems":   "center",
                    "padding":      "5px 12px",
                    "border":       "1px solid var(--gray-6)",
                    "borderRadius": "9999px",
                    "background":   "transparent",
                    "cursor":       "pointer",
                    "color":        "var(--gray-11)",
                    "whiteSpace":   "nowrap",
                    "transition":   "background 0.15s, border-color 0.15s",
                },
                _hover={
                    "background":  "var(--gray-3)",
                    "borderColor": "var(--gray-8)",
                },
            ),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.text(AuthState.t["matrix_gas_per_page"], size="2", color="var(--gray-11)"),
            rx.select(
                _GA_PER_PAGE_OPTIONS,
                value=VoteMatrixState.gas_per_page.to_string(),
                on_change=VoteMatrixState.set_gas_per_page,
                size="2",
            ),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.text(AuthState.t["matrix_per_page"], size="2", color="var(--gray-11)"),
            rx.select(
                _PER_PAGE_OPTIONS,
                value=VoteMatrixState.items_per_page.to_string(),
                on_change=VoteMatrixState.set_per_page,
                size="2",
            ),
            spacing="2",
            align="center",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding_y="8px",
        wrap="wrap",
    )


def _ga_header_cell(ga) -> rx.Component:
    """1 GA の header (上 1 行に sticky 配置)。タイトル truncate + クリックで詳細へ。"""
    title_text = rx.cond(
        AuthState.language == "ja",
        rx.cond(ga["title_ja"] != "", ga["title_ja"], ga["title"]),
        ga["title"],
    )
    fallback = rx.cond(ga["title"] != "", ga["title"], ga["proposal_id"])
    display = rx.cond(title_text != "", title_text, fallback)
    return rx.el.th(
        rx.link(
            rx.text(
                display,
                size="1",
                weight="medium",
                style={
                    "display":          "-webkit-box",
                    "WebkitLineClamp":  "2",
                    "WebkitBoxOrient":  "vertical",
                    "overflow":         "hidden",
                    "lineHeight":       "1.3",
                    "color":            "var(--gray-12)",
                },
            ),
            rx.text(
                ga["proposal_type"],
                size="1",
                style={"fontSize": "10px", "color": "var(--gray-9)"},
            ),
            href="/governance/" + ga["proposal_id"],
            color="inherit",
            underline="none",
            style={"display": "block"},
            title=display,
        ),
        style={
            "position":     "sticky",
            "top":          0,
            "zIndex":       2,
            "background":   "var(--gray-2)",
            "padding":      "8px 10px",
            "minWidth":     "140px",
            "maxWidth":     "180px",
            "borderBottom": "1px solid var(--gray-6)",
            "borderRight":  "1px solid var(--gray-5)",
            "verticalAlign": "top",
            "textAlign":    "left",
        },
    )


def _drep_name_cell(row) -> rx.Component:
    """先頭列 (DRep 名 + アバター)、左 sticky。クリックで /drep/<drep_id> へ。"""
    name_text = rx.cond(
        row["given_name"] != "",
        rx.text(
            row["given_name"],
            size="2",
            weight="medium",
            color="var(--gray-12)",
            style={
                "whiteSpace":    "nowrap",
                "overflow":      "hidden",
                "textOverflow":  "ellipsis",
                "maxWidth":      "180px",
                "@media (max-width: 768px)": {
                    "maxWidth": "100px",
                    "fontSize": "12px",
                },
            },
        ),
        rx.text(
            AuthState.t["drep_no_name"],
            size="2",
            color="var(--gray-10)",
            style={
                "@media (max-width: 768px)": {
                    "fontSize": "12px",
                },
            },
        ),
    )
    avatar = rx.cond(
        row["image_url"] != "",
        rx.image(
            src=row["image_url"],
            width="24px", height="24px",
            border_radius="50%",
            style={"objectFit": "cover", "flexShrink": "0"},
        ),
        rx.center(
            rx.icon("user-round", size=14, color="var(--gray-9)"),
            width="24px", height="24px",
            border_radius="50%",
            background="var(--gray-4)",
            style={"flexShrink": "0"},
        ),
    )
    return rx.el.td(
        rx.link(
            rx.hstack(
                avatar,
                rx.vstack(
                    name_text,
                    rx.text(
                        row["drep_id_short"],
                        size="1",
                        style={
                            "fontFamily": "ui-monospace, monospace",
                            "fontSize":   "10px",
                            "color":      "var(--gray-10)",
                            # モバイルでは ID を非表示にして DRep 列を狭くする
                            "@media (max-width: 768px)": {
                                "display": "none",
                            },
                        },
                    ),
                    spacing="0",
                    align_items="start",
                    style={"minWidth": "0"},
                ),
                spacing="2",
                align="center",
            ),
            href="/drep/" + row["drep_id"],
            color="inherit",
            underline="none",
            style={"display": "block"},
            _hover={"color": "var(--amber-11)"},
        ),
        style={
            "position":     "sticky",
            "left":         0,
            "background":   "var(--gray-1)",
            "zIndex":       1,
            "padding":      "8px 12px",
            "borderRight":  "1px solid var(--gray-6)",
            "borderBottom": "1px solid var(--gray-5)",
            "minWidth":     "220px",
            "maxWidth":     "240px",
            "@media (max-width: 768px)": {
                "minWidth": "140px",
                "maxWidth": "150px",
                "padding":  "6px 8px",
            },
        },
    )


def _vote_cell(c) -> rx.Component:
    rationale_text = rx.cond(
        AuthState.language == "ja",
        rx.cond(c["rationale_ja"] != "", c["rationale_ja"], c["rationale"]),
        c["rationale"],
    )
    has_rationale = (c["rationale_ja"] != "") | (c["rationale"] != "")

    badge = rx.match(
        c["vote"],
        ("yes",     rx.badge(AuthState.t["vote_label_yes"],     color_scheme="green", variant="solid", size="1", radius="small")),
        ("no",      rx.badge(AuthState.t["vote_label_no"],      color_scheme="red",   variant="solid", size="1", radius="small")),
        ("abstain", rx.badge(AuthState.t["vote_label_abstain"], color_scheme="gray",  variant="solid", size="1", radius="small")),
        # 未投票: 「ー」をシンプルに表示
        rx.text(AuthState.t["vote_label_none"], style={
            "color":      "var(--gray-9)",
            "fontSize":   "14px",
            "fontWeight": "600",
        }),
    )

    # 投票理由がある場合のみクリップアイコンを出す。クリックでダイアログを開く。
    # ダイアログは GA 詳細ページの投票一覧と同じフォーマット (投票結果バッジ +
    # 日本語訳ラベル + 原文ラベル) で表示する。
    clip = rx.cond(
        has_rationale,
        rx.dialog.root(
            rx.dialog.trigger(
                rx.el.button(
                    rx.icon("paperclip", size=12, color="var(--gray-10)"),
                    rx.text(
                        AuthState.t["dashboard_vote_rationale"],
                        size="1",
                        color="var(--gray-11)",
                    ),
                    style={
                        "display":        "inline-flex",
                        "alignItems":     "center",
                        "gap":            "3px",
                        "padding":        "2px 6px",
                        "background":     "transparent",
                        "border":         "1px solid var(--gray-5)",
                        "borderRadius":   "999px",
                        "cursor":         "pointer",
                    },
                    _hover={
                        "background": "var(--gray-3)",
                        "color":      "var(--gray-12)",
                    },
                ),
            ),
            rx.dialog.content(
                rx.dialog.title(AuthState.t["gov_vote_rationale_title"]),
                rx.vstack(
                    # 投票結果バッジ (matrix の vote 値 = "yes"/"no"/"abstain")
                    rx.match(
                        c["vote"],
                        ("yes",     rx.badge(AuthState.t["vote_label_yes"],     color_scheme="green", variant="solid", size="2", radius="full")),
                        ("no",      rx.badge(AuthState.t["vote_label_no"],      color_scheme="red",   variant="solid", size="2", radius="full")),
                        ("abstain", rx.badge(AuthState.t["vote_label_abstain"], color_scheme="gray",  variant="solid", size="2", radius="full")),
                        rx.fragment(),
                    ),
                    rx.divider(),
                    # 日本語訳 (あれば)
                    rx.cond(
                        c["rationale_ja"] != "",
                        rx.vstack(
                            rx.text(AuthState.t["gov_vote_rationale_ja_label"], size="2", weight="bold", color="var(--gray-12)"),
                            rx.text(
                                c["rationale_ja"],
                                size="2", color="var(--gray-12)",
                                style={"whiteSpace": "pre-wrap", "lineHeight": "1.6"},
                            ),
                            spacing="1", align="start", width="100%",
                        ),
                        rx.fragment(),
                    ),
                    # 原文 (あれば)
                    rx.cond(
                        c["rationale"] != "",
                        rx.vstack(
                            rx.text(AuthState.t["gov_vote_rationale_en_label"], size="2", weight="bold", color="var(--gray-12)"),
                            rx.text(
                                c["rationale"],
                                size="2", color="var(--gray-11)",
                                style={"whiteSpace": "pre-wrap", "lineHeight": "1.6"},
                            ),
                            spacing="1", align="start", width="100%",
                        ),
                        rx.fragment(),
                    ),
                    rx.dialog.close(
                        rx.button(
                            AuthState.t["gov_vote_rationale_close"],
                            variant="soft", size="2", cursor="pointer",
                        ),
                    ),
                    spacing="3", align="start", width="100%",
                ),
                max_width=["95vw", "95vw", "680px"],
                style={"boxSizing": "border-box"},
            ),
        ),
        rx.fragment(),
    )

    return rx.el.td(
        rx.flex(
            badge,
            clip,
            direction="row",
            align="center",
            justify="center",
            gap="4px",
        ),
        style={
            "padding":       "8px",
            "textAlign":     "center",
            "verticalAlign": "middle",
            "borderBottom":  "1px solid var(--gray-5)",
            "borderRight":   "1px solid var(--gray-5)",
            "minWidth":      "70px",
            "background":    "var(--gray-1)",
        },
    )


def _matrix_row(row) -> rx.Component:
    return rx.el.tr(
        _drep_name_cell(row),
        rx.foreach(row["cells"], _vote_cell),
        style={
            "transition": "background 0.15s",
            # 行 hover で sticky な DRep セル含めセル背景を上書き
            "&:hover td": {
                "background": "var(--amber-3)",
            },
        },
    )


def _matrix_table() -> rx.Component:
    """投票マトリクス本体。左 1 列 / 上 1 行 sticky でスクロール対応。"""
    return rx.cond(
        VoteMatrixState.matrix_rows.length() == 0,
        rx.center(
            rx.text(AuthState.t["matrix_empty"], size="3", color="var(--gray-10)"),
            padding_y="40px",
            width="100%",
            border="1px solid var(--gray-6)",
            border_radius="10px",
        ),
        rx.box(
            rx.el.table(
                rx.el.thead(
                    rx.el.tr(
                        rx.el.th(
                            rx.text(
                                AuthState.t["matrix_col_drep"],
                                size="2",
                                weight="bold",
                                color="var(--gray-12)",
                            ),
                            style={
                                "position":     "sticky",
                                "top":          0,
                                "left":         0,
                                "zIndex":       3,
                                "background":   "var(--gray-2)",
                                "padding":      "8px 12px",
                                "borderBottom": "1px solid var(--gray-6)",
                                "borderRight":  "1px solid var(--gray-6)",
                                "minWidth":     "220px",
                                "textAlign":    "left",
                                "@media (max-width: 768px)": {
                                    "minWidth": "140px",
                                    "maxWidth": "150px",
                                    "padding":  "6px 8px",
                                },
                            },
                        ),
                        rx.foreach(VoteMatrixState.gas, _ga_header_cell),
                    ),
                ),
                rx.el.tbody(
                    rx.foreach(VoteMatrixState.matrix_rows, _matrix_row),
                ),
                style={
                    "borderCollapse": "separate",
                    "borderSpacing":  0,
                    "width":          "max-content",
                },
            ),
            style={
                "overflow":      "auto",
                "maxHeight":     "calc(100vh - 280px)",
                "border":        "1px solid var(--gray-6)",
                "borderRadius":  "10px",
                "background":    "var(--gray-1)",
                "width":         "100%",
                "maxWidth":      "100%",
                "minWidth":      "0",
                "alignSelf":     "stretch",
            },
        ),
    )


def _legend() -> rx.Component:
    """凡例: 投票結果のバッジ説明。"""
    def _item(badge: rx.Component, label_key: str):
        return rx.hstack(
            badge,
            rx.text(AuthState.t[label_key], size="1", color="var(--gray-11)"),
            spacing="1",
            align="center",
        )

    return rx.flex(
        _item(rx.badge(AuthState.t["vote_label_yes"],     color_scheme="green", variant="solid", size="1", radius="small"),
              "matrix_legend_yes"),
        _item(rx.badge(AuthState.t["vote_label_no"],      color_scheme="red",   variant="solid", size="1", radius="small"),
              "matrix_legend_no"),
        _item(rx.badge(AuthState.t["vote_label_abstain"], color_scheme="gray",  variant="solid", size="1", radius="small"),
              "matrix_legend_abstain"),
        _item(rx.text(AuthState.t["vote_label_none"], style={
                  "color": "var(--gray-9)",
                  "fontSize": "14px",
                  "fontWeight": "600",
              }),
              "matrix_legend_no_vote"),
        spacing="4",
        wrap="wrap",
        align="center",
        padding_y="4px",
    )


def _pagination() -> rx.Component:
    """DRep 行のページネーション。"""
    def btn(page):
        is_active = page == VoteMatrixState.current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: VoteMatrixState.set_page(page),
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
            on_click=VoteMatrixState.prev_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=VoteMatrixState.current_page == 1,
            _hover={"cursor": "pointer"},
        ),
        rx.foreach(VoteMatrixState.middle_page, btn),
        rx.button(
            rx.icon(tag="chevron-right"),
            on_click=VoteMatrixState.next_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=VoteMatrixState.current_page == VoteMatrixState.total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="pagination gap-2",
        padding_top="1.5em",
        justify="end",
        align="center",
    )


def _gas_pagination() -> rx.Component:
    """GA 列のページネーション (マトリクス上部に表示)。"""
    def btn(page):
        is_active = page == VoteMatrixState.gas_current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: VoteMatrixState.set_gas_page(page),
            variant=rx.cond(is_active, "solid", "soft"),
            radius="full",
            size="1",
            padding_x="8px",
            class_name="md:inline-flex hidden",
            _hover={"cursor": "pointer"},
        )
    return rx.flex(
        rx.text(
            AuthState.t["matrix_gas_total"], " ",
            VoteMatrixState.gas_total_items.to_string(),
            size="1", color="var(--gray-10)",
        ),
        rx.spacer(),
        rx.button(
            rx.icon(tag="chevron-left", size=14),
            on_click=VoteMatrixState.prev_gas_page,
            radius="full",
            size="1",
            variant="soft",
            disabled=VoteMatrixState.gas_current_page == 1,
            _hover={"cursor": "pointer"},
        ),
        rx.foreach(VoteMatrixState.gas_middle_page, btn),
        rx.button(
            rx.icon(tag="chevron-right", size=14),
            on_click=VoteMatrixState.next_gas_page,
            radius="full",
            size="1",
            variant="soft",
            disabled=VoteMatrixState.gas_current_page == VoteMatrixState.gas_total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="gas-pagination gap-1",
        padding_y="6px",
        align="center",
        width="100%",
    )


# ─── Page ─────────────────────────────────────────────────────────────────────


@template(
    route="/governance/matrix",
    title="投票マトリクス | ガバナンス | Cardanoism",
    on_load=VoteMatrixState.on_load,
)
def governance_matrix_page() -> rx.Component:
    return rx.cond(
        VoteMatrixState.load,
        rx.box(
            rx.vstack(
                _breadcrumb(),
                governance_subnav("matrix"),
                rx.heading(
                    AuthState.t["matrix_title"],
                    size="6",
                    weight="bold",
                    style={"marginTop": "8px"},
                ),
                rx.text(
                    AuthState.t["matrix_desc"],
                    size="2",
                    color="var(--gray-10)",
                ),
                _filter_bar(),
                rx.cond(
                    VoteMatrixState.error != "",
                    rx.callout(
                        VoteMatrixState.error,
                        icon="triangle-alert",
                        color_scheme="red",
                        size="1",
                    ),
                    rx.fragment(),
                ),
                _gas_pagination(),
                _matrix_table(),
                rx.hstack(
                    rx.text(
                        AuthState.t["matrix_total"], " ",
                        VoteMatrixState.total_items.to_string(),
                        size="2",
                        color="var(--gray-10)",
                    ),
                    rx.spacer(),
                    _pagination(),
                    align="center",
                    width="100%",
                ),
                spacing="3",
                max_width="1480px",
                margin_x="auto",
                width="100%",
                padding_x=["0px", "20px", "20px"],
                padding_bottom="40px",
            ),
        ),
        rx.flex(
            rx.spinner(size="3"),
            justify="center",
            align="center",
            width="100%",
            padding_y="40px",
        ),
    )
