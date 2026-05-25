"""
governance_drep_detail.py
DRep 個別ページ（/governance/drep/[drep_id]）

そのDRepのプロフィール + 投票実績一覧を表示する。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.drep_db import get_drep, sum_total_delegation
from cardanoism.backend.drep_meta import format_links as _format_links
from cardanoism.backend.drep_compass.api import get_drep_profile as _get_compass_profile
from cardanoism.backend.drep_compass.taxonomy import (
    BALANCE_AXES as _COMPASS_BALANCE_AXES,
    SINGLE_AXES as _COMPASS_SINGLE_AXES,
)
from cardanoism.backend.vote_db import get_votes_by_drep, count_votes_by_drep
from cardanoism.backend.fiat_db import get_fiat_rate
from cardanoism.backend.price import format_ada, format_jpy_short, format_usd_short
from cardanoism.components.breadcrumb import breadcrumb
from cardanoism.components.governance_nav import governance_subnav
from cardanoism.components.login_modal import login_modal
from cardanoism.components.governance_card import _vote_badge
from cardanoism.components.drep_delegation_dialog import (
    drep_delegation_dialog,
    drep_delegate_button,
)

logger = logging.getLogger(__name__)

VOTES_PER_PAGE = 20


# ─── State ────────────────────────────────────────────────────────────────────


class DrepDetailState(rx.State):
    load: bool = False
    error: str = ""
    not_found: bool = False

    # プロフィール（※ URL 動的引数 drep_id と名前が衝突するため別名）
    display_drep_id: str = ""
    given_name: str = ""
    image_url: str = ""
    is_active: str = ""
    amount_ada: str = "-"
    amount_jpy: str = ""
    amount_usd: str = ""
    share_pct: str = "0"

    # CIP-119 プロフィール (全文)
    objectives: str = ""
    motivations: str = ""
    qualifications: str = ""
    links_csv: str = ""  # "icon|url,icon|url" CSV (_social_link_icon が分解)

    # 投票集計
    vote_total: int = 0
    vote_yes: int = 0
    vote_no: int = 0
    vote_abstain: int = 0

    # DRep委任コンパス プロファイル
    compass_has_profile: bool = False
    compass_analyzed_votes: str = "0"
    compass_reasoning_pct: str = "0"
    # 対立軸 4 行 (中央バー左右振れ表示用)
    # {kind="balance", key, label_key, pos_label_key, neg_label_key,
    #   side ("pos"|"neg"|"center"), magnitude_pct, side_desc_key, conf_class}
    compass_balance_rows: list[dict[str, str]] = []
    # 独立軸 3 行 (0〜100% バー表示用)
    # {kind="single", label_key, desc_key, score_pct, conf_class}
    compass_single_rows: list[dict[str, str]] = []

    @rx.var
    def has_profile_metadata(self) -> bool:
        return bool(
            (self.objectives or "").strip()
            or (self.motivations or "").strip()
            or (self.qualifications or "").strip()
            or (self.links_csv or "").strip()
        )

    # 投票履歴
    votes: List[Dict[str, Any]] = []

    # ページネーション
    current_page: int = 1

    @rx.var
    def votes_total(self) -> int:
        return len(self.votes)

    @rx.var
    def votes_total_pages(self) -> int:
        return max(1, (len(self.votes) + VOTES_PER_PAGE - 1) // VOTES_PER_PAGE)

    @rx.var
    def votes_page(self) -> list[dict]:
        start = max(0, (self.current_page - 1) * VOTES_PER_PAGE)
        end = start + VOTES_PER_PAGE
        return self.votes[start:end]

    @rx.var
    def votes_middle_pages(self) -> list[int]:
        start = max(1, self.current_page - 3)
        end = min(self.votes_total_pages, self.current_page + 3)
        return list(range(start, end + 1))

    def set_votes_page(self, p):
        try:
            page = int(p)
            if page < 1:
                page = 1
            elif page > self.votes_total_pages:
                page = self.votes_total_pages
            self.current_page = page
        except (TypeError, ValueError):
            pass
        return rx.call_script("window.scrollTo(0, 0)")

    def votes_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
        return rx.call_script("window.scrollTo(0, 0)")

    def votes_next_page(self):
        if self.current_page < self.votes_total_pages:
            self.current_page += 1
        return rx.call_script("window.scrollTo(0, 0)")

    async def on_load(self):
        self.load = False
        self.error = ""
        self.not_found = False
        self.current_page = 1
        try:
            # URL 末尾から drep_id 取得
            path = self.router.url.path or ""
            parts = [p for p in path.split("/") if p]
            drep_id = parts[-1] if parts else ""
            self.display_drep_id = drep_id

            d = get_drep(drep_id)
            if not d:
                self.not_found = True
                return

            self.given_name = str(d.get("given_name") or "")
            self.image_url = str(d.get("image_url") or "")
            self.is_active = "1" if d.get("active") else ""

            # CIP-119 プロフィール (全文表示用)
            self.objectives = str(d.get("objectives") or "").strip()
            self.motivations = str(d.get("motivations") or "").strip()
            self.qualifications = str(d.get("qualifications") or "").strip()
            links = _format_links(d.get("references_json"))
            self.links_csv = ",".join(f"{icon}|{url}" for icon, url in links)

            # 委任量
            amount = int(d.get("amount") or 0)
            ada = amount / 1_000_000
            rate = get_fiat_rate() or {}
            ada_jpy = float(rate.get("ada_jpy") or 0)
            ada_usd = float(rate.get("ada_usd") or 0)
            self.amount_ada = format_ada(amount, integer=True) if amount else "0"
            self.amount_jpy = format_jpy_short(ada * ada_jpy) if ada_jpy else ""
            self.amount_usd = format_usd_short(ada * ada_usd) if ada_usd else ""

            # 影響力（全体比）
            total_lovelace = sum_total_delegation(only_registered=True)
            share_pct = (amount / total_lovelace * 100.0) if total_lovelace > 0 else 0.0
            if share_pct >= 1.0:
                self.share_pct = f"{share_pct:.2f}"
            elif share_pct > 0:
                self.share_pct = f"{share_pct:.3f}"
            else:
                self.share_pct = "0"

            # 投票集計
            counts = count_votes_by_drep(drep_id)
            self.vote_total = counts["total"]
            self.vote_yes = counts["yes"]
            self.vote_no = counts["no"]
            self.vote_abstain = counts["abstain"]

            # DRep委任コンパス プロファイル
            try:
                cp = _get_compass_profile(drep_id) or {}
            except Exception as e:  # noqa: BLE001
                logger.warning("get_drep_profile failed for %s: %s", drep_id, e)
                cp = {}
            profile = cp.get("profile_json") or {}
            confidence = cp.get("confidence_json") or {}
            self.compass_has_profile = bool(profile)
            analyzed = int(cp.get("analyzed_vote_count") or 0)
            disclosure = float(cp.get("reasoning_disclosure_rate") or 0)
            self.compass_analyzed_votes = str(analyzed)
            self.compass_reasoning_pct = f"{disclosure * 100:.0f}"

            def _score(key: str) -> float:
                try:
                    return float(profile.get(key, 0.5))
                except (TypeError, ValueError):
                    return 0.5

            def _conf(key: str) -> float:
                try:
                    return float(confidence.get(key, 0.0))
                except (TypeError, ValueError):
                    return 0.0

            def _conf_class(c: float) -> str:
                if c >= 0.6:
                    return "high"
                if c >= 0.3:
                    return "mid"
                return "low"

            # 対立軸 4 行: pos 側 score を採用 (0.5 中立、>0.5 = pos 寄り)
            balance_rows: list[dict[str, str]] = []
            for key, pos_axis, neg_axis in _COMPASS_BALANCE_AXES:
                pos_score = _score(pos_axis)
                # pos 側スコアから中央 50% を引いて振れ幅 (-50〜+50) → 0〜100% に
                offset = pos_score - 0.5     # -0.5〜+0.5
                magnitude = abs(offset) * 2  # 0〜1
                if offset > 0.02:
                    side = "pos"
                    side_desc_key = f"drep_match_balance_{key}_pos_desc"
                elif offset < -0.02:
                    side = "neg"
                    side_desc_key = f"drep_match_balance_{key}_neg_desc"
                else:
                    side = "center"
                    side_desc_key = ""  # 中立は説明文を出さない
                # confidence は pos/neg のうち高い方
                conf_val = max(_conf(pos_axis), _conf(neg_axis))
                balance_rows.append({
                    "kind":           "balance",
                    "key":            key,
                    "label_key":      f"drep_match_balance_{key}_label",
                    "pos_label_key":  f"drep_match_balance_{key}_pos",
                    "neg_label_key":  f"drep_match_balance_{key}_neg",
                    "side":           side,
                    "magnitude_pct":  f"{magnitude * 100:.0f}",
                    "side_desc_key":  side_desc_key,
                    "conf_class":     _conf_class(conf_val),
                })
            self.compass_balance_rows = balance_rows

            # 独立軸 3 行: そのまま 0〜100% バー
            single_rows: list[dict[str, str]] = []
            for axis in _COMPASS_SINGLE_AXES:
                score = _score(axis)
                conf_val = _conf(axis)
                single_rows.append({
                    "kind":       "single",
                    "label_key":  f"drep_match_axis_{axis}",
                    "desc_key":   f"drep_match_axis_{axis}_desc",
                    "score_pct":  f"{score * 100:.0f}",
                    "conf_class": _conf_class(conf_val),
                })
            self.compass_single_rows = single_rows

            # 投票履歴（未投票 GA も含む）
            raw = get_votes_by_drep(drep_id, limit=500)
            out: list[dict] = []
            for v in raw:
                # 投票があれば投票時刻、無ければ GA の block_time を表示
                bt = v.get("vote_time") or v.get("ga_block_time")
                bt_display = bt.strftime("%Y-%m-%d %H:%M") if bt else ""
                vote = str(v.get("vote") or "")
                out.append({
                    "vote_id":         str(v.get("vote_id") or ""),
                    "proposal_id":     str(v.get("proposal_id") or ""),
                    "proposal_type":   str(v.get("proposal_type") or ""),
                    "title":           str(v.get("title") or ""),
                    "title_ja":        str(v.get("title_ja") or ""),
                    "ga_status":       str(v.get("ga_status") or "active"),
                    "vote":            vote,
                    "has_voted":       "1" if vote else "",
                    "block_time":      bt_display,
                    "rationale":       str(v.get("rationale") or ""),
                    "rationale_ja":    str(v.get("rationale_ja") or ""),
                })
            self.votes = out
        except Exception as e:
            logger.exception("DrepDetailState.on_load: %s", e)
            self.error = str(e)
        finally:
            self.load = True


# ─── UI ──────────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return breadcrumb(
        [("nav_governance", "/governance"), ("gov_subnav_drep", "/governance/drep")],
        "drep_detail_breadcrumb",
    )


def _profile_card() -> rx.Component:
    avatar = rx.cond(
        DrepDetailState.image_url != "",
        rx.image(
            src=DrepDetailState.image_url,
            width="96px",
            height="96px",
            border_radius="50%",
            style={"objectFit": "cover"},
        ),
        rx.center(
            rx.icon("user-round", size=44, color="var(--gray-9)"),
            width="96px",
            height="96px",
            border_radius="50%",
            background="var(--gray-4)",
        ),
    )
    status_badge = rx.cond(
        DrepDetailState.is_active != "",
        rx.badge(AuthState.t["drep_status_active"], color_scheme="green", variant="soft"),
        rx.badge(AuthState.t["drep_status_inactive"], color_scheme="gray", variant="soft"),
    )
    name_text = rx.cond(
        DrepDetailState.given_name != "",
        rx.text(DrepDetailState.given_name, size="6", weight="bold", color="var(--gray-12)"),
        rx.text(AuthState.t["drep_no_name"], size="6", weight="bold", color="var(--gray-10)"),
    )
    fiat = rx.cond(
        AuthState.language == "en",
        rx.cond(
            DrepDetailState.amount_usd != "",
            rx.text("(≈ ", DrepDetailState.amount_usd, ")", size="2", color="var(--gray-10)"),
            rx.fragment(),
        ),
        rx.cond(
            DrepDetailState.amount_jpy != "",
            rx.text("(≈ ", DrepDetailState.amount_jpy, ")", size="2", color="var(--gray-10)"),
            rx.fragment(),
        ),
    )
    # DRep ID コピーボタン
    drep_id_block = rx.box(
        rx.el.span(
            DrepDetailState.display_drep_id,
            style={
                "fontFamily": "var(--code-font-family, ui-monospace, monospace)",
                "fontSize": "12px",
                "color": "var(--gray-10)",
                "wordBreak": "break-all",
            },
        ),
        rx.el.button(
            rx.icon("copy", size=14),
            on_click=[
                rx.set_clipboard(DrepDetailState.display_drep_id),
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
        ),
        style={"lineHeight": "1.6"},
        width="100%",
    )
    return rx.box(
        rx.hstack(
            avatar,
            rx.vstack(
                rx.hstack(
                    rx.hstack(name_text, status_badge, spacing="3", align="center", wrap="wrap"),
                    rx.spacer(),
                    drep_delegate_button(DrepDetailState.display_drep_id),
                    spacing="3", align="center", width="100%", wrap="wrap",
                ),
                drep_id_block,
                rx.hstack(
                    rx.vstack(
                        rx.text(AuthState.t["drep_delegated_label"], size="1", color="var(--gray-10)"),
                        rx.hstack(
                            rx.text(DrepDetailState.amount_ada, size="5", weight="bold", color="var(--amber-11)"),
                            rx.text("ADA", size="2", color="var(--gray-11)"),
                            spacing="1", align="baseline",
                        ),
                        fiat,
                        spacing="0", align="start",
                    ),
                    rx.vstack(
                        rx.text(AuthState.t["drep_influence_label"], size="1", color="var(--gray-10)"),
                        rx.hstack(
                            rx.text(DrepDetailState.share_pct, size="5", weight="bold", color="var(--blue-11)"),
                            rx.text("%", size="2", color="var(--gray-11)"),
                            spacing="0", align="baseline",
                        ),
                        spacing="0", align="start",
                    ),
                    spacing="6", wrap="wrap",
                ),
                spacing="3",
                align_items="start",
                flex="1",
                min_width="0",
            ),
            spacing="4",
            align="start",
            width="100%",
            wrap="wrap",
        ),
        padding="20px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


def _social_link_icon(item) -> rx.Component:
    """item は 'icon|url' 形式の Var[str]。CIP-119 references_json から作る外部リンク。

    Reflex の StringVar.split は maxsplit を受け付けないため単純 split を使用。
    """
    parts = item.split("|")
    icon_name = parts[0]
    url = parts[1]
    icon_comp = rx.match(
        icon_name,
        ("twitter",        rx.icon("twitter",        size=16, color="#1DA1F2")),
        ("github",         rx.icon("github",         size=16, color="var(--gray-12)")),
        ("send",           rx.icon("send",           size=16, color="#2AABEE")),
        ("youtube",        rx.icon("youtube",        size=16, color="#FF0000")),
        ("message-circle", rx.icon("message-circle", size=16, color="#5865F2")),
        ("linkedin",       rx.icon("linkedin",       size=16, color="#0A66C2")),
        rx.icon("globe", size=16, color="var(--gray-11)"),
    )
    return rx.link(
        rx.box(
            icon_comp,
            width="30px", height="30px",
            display="flex",
            align_items="center",
            justify_content="center",
            border_radius="999px",
            background="var(--gray-3)",
            style={"transition": "background 0.15s"},
            _hover={"background": "var(--amber-4)"},
        ),
        href=url,
        is_external=True,
        underline="none",
        custom_attrs={"title": url},
    )


def _profile_text_section(label_key: str, value) -> rx.Component:
    """objectives / motivations / qualifications の 1 セクション。

    値が空でない時のみブロックを描画する。
    """
    return rx.cond(
        value != "",
        rx.vstack(
            rx.text(
                AuthState.t[label_key],
                size="2", weight="bold", color="var(--gray-12)",
            ),
            rx.text(
                value,
                size="2", color="var(--gray-11)",
                style={
                    "whiteSpace": "pre-wrap",
                    "wordBreak": "break-word",
                    "lineHeight": "1.7",
                },
            ),
            spacing="1", align="start", width="100%",
        ),
        rx.fragment(),
    )


def _profile_metadata_card() -> rx.Component:
    """CIP-119 メタデータ (objectives / motivations / qualifications + links) の全文表示。"""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("user", size=18, color="var(--amber-11)"),
                rx.text(
                    AuthState.t["drep_profile_section_title"],
                    size="4", weight="bold", color="var(--gray-12)",
                ),
                spacing="2", align="center",
            ),
            rx.cond(
                DrepDetailState.has_profile_metadata,
                rx.vstack(
                    _profile_text_section("drep_profile_objectives",     DrepDetailState.objectives),
                    _profile_text_section("drep_profile_motivations",    DrepDetailState.motivations),
                    _profile_text_section("drep_profile_qualifications", DrepDetailState.qualifications),
                    rx.cond(
                        DrepDetailState.links_csv != "",
                        rx.vstack(
                            rx.text(
                                AuthState.t["drep_profile_links"],
                                size="2", weight="bold", color="var(--gray-12)",
                            ),
                            rx.hstack(
                                rx.foreach(
                                    DrepDetailState.links_csv.split(","),
                                    _social_link_icon,
                                ),
                                spacing="2", align="center", wrap="wrap",
                            ),
                            spacing="2", align="start", width="100%",
                        ),
                        rx.fragment(),
                    ),
                    spacing="4", align="start", width="100%",
                ),
                rx.text(
                    AuthState.t["drep_profile_no_metadata"],
                    size="2", color="var(--gray-10)",
                ),
            ),
            spacing="3", align="start", width="100%",
        ),
        padding="20px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


def _bar_color(conf_class) -> rx.Var:
    return rx.match(
        conf_class,
        ("high", "var(--amber-9)"),
        ("mid",  "var(--amber-7)"),
        "var(--gray-7)",
    )


def _compass_balance_row(item) -> rx.Component:
    """対立軸 1 行 (中央バーから左右に振れる)。

    レイアウト:
      [ 軸名 ] [ 左ラベル ━━━●━━━━ 右ラベル ] [ 立場 (pos/neg/center) + 強度% ]
    """
    # 左半分: side == "neg" のとき左から内側へ伸びる
    left_width = rx.cond(item["side"] == "neg", item["magnitude_pct"] + "%", "0%")
    # 右半分: side == "pos" のとき右から内側へ伸びる (実際は中央起点 → 右へ伸ばす)
    right_width = rx.cond(item["side"] == "pos", item["magnitude_pct"] + "%", "0%")

    color = _bar_color(item["conf_class"])

    side_label = rx.match(
        item["side"],
        ("pos", AuthState.t[item["pos_label_key"]]),
        ("neg", AuthState.t[item["neg_label_key"]]),
        AuthState.t["drep_match_results_low_conf_label"],
    )
    side_text_color = rx.cond(
        item["side"] == "center",
        "var(--gray-10)",
        rx.cond(item["conf_class"] == "low", "var(--gray-10)", "var(--gray-12)"),
    )

    return rx.vstack(
        rx.hstack(
            # 左: 軸名
            rx.text(
                AuthState.t[item["label_key"]],
                size="2", weight="bold", color="var(--gray-12)",
                style={"width": "140px", "flexShrink": "0"},
            ),
            # 中央: 左右に伸びる中央バー
            rx.box(
                # 左半分 (neg 側に伸びる)
                rx.box(
                    rx.box(
                        width=left_width,
                        height="100%",
                        background=color,
                        border_radius="999px 0 0 999px",
                        margin_left="auto",
                        transition="width 0.3s",
                    ),
                    flex="1", height="100%", overflow="hidden",
                ),
                # 中央仕切り
                rx.box(
                    width="2px", height="14px",
                    background="var(--gray-9)",
                    style={"flexShrink": "0"},
                ),
                # 右半分 (pos 側に伸びる)
                rx.box(
                    rx.box(
                        width=right_width,
                        height="100%",
                        background=color,
                        border_radius="0 999px 999px 0",
                        transition="width 0.3s",
                    ),
                    flex="1", height="100%", overflow="hidden",
                ),
                # 全体: 2 つの flex 内 box が中央仕切りを挟む形
                style={"display": "flex", "alignItems": "center"},
                flex="1",
                height="10px",
                background="var(--gray-3)",
                border_radius="999px",
                overflow="hidden",
                min_width="200px",
            ),
            # 右: 立場ラベル + 強度
            rx.hstack(
                rx.text(side_label, size="2", weight="bold", color=side_text_color,
                        style={"whiteSpace": "nowrap"}),
                rx.cond(
                    item["side"] != "center",
                    rx.text(item["magnitude_pct"], "%",
                            size="2", color="var(--gray-11)",
                            style={
                                "fontFamily": "var(--code-font-family, ui-monospace, monospace)",
                            }),
                    rx.fragment(),
                ),
                spacing="1", align="baseline",
                style={"width": "160px", "flexShrink": "0",
                       "justifyContent": "flex-end"},
            ),
            spacing="3", align="center", width="100%",
        ),
        # サブ説明文 (どちら寄りかの具体的中身)
        rx.cond(
            item["side"] != "center",
            rx.text(
                AuthState.t[item["side_desc_key"]],
                size="1", color="var(--gray-10)",
                style={"lineHeight": "1.5",
                       "paddingLeft": "152px"},
            ),
            rx.fragment(),
        ),
        spacing="1", align="stretch", width="100%",
    )


def _compass_single_row(item) -> rx.Component:
    """独立軸 1 行 (0〜100% バー)。"""
    color = _bar_color(item["conf_class"])
    score_color = rx.cond(
        item["conf_class"] == "low", "var(--gray-10)", "var(--gray-12)",
    )
    return rx.vstack(
        rx.hstack(
            rx.text(
                AuthState.t[item["label_key"]],
                size="2", weight="bold", color="var(--gray-12)",
                style={"width": "140px", "flexShrink": "0"},
            ),
            rx.box(
                rx.box(
                    width=item["score_pct"] + "%",
                    height="100%",
                    background=color,
                    border_radius="999px",
                    transition="width 0.3s",
                ),
                flex="1", height="10px",
                background="var(--gray-3)",
                border_radius="999px",
                overflow="hidden",
                min_width="200px",
            ),
            rx.text(
                item["score_pct"], "%",
                size="2", weight="bold", color=score_color,
                style={"width": "160px", "textAlign": "right", "flexShrink": "0",
                       "fontFamily": "var(--code-font-family, ui-monospace, monospace)"},
            ),
            spacing="3", align="center", width="100%",
        ),
        rx.text(
            AuthState.t[item["desc_key"]],
            size="1", color="var(--gray-10)",
            style={"lineHeight": "1.5", "paddingLeft": "152px"},
        ),
        spacing="1", align="stretch", width="100%",
    )


def _compass_profile_section() -> rx.Component:
    """DRep委任コンパス プロファイル (11 axis バー + 投票実績 + 理由公開率)。

    プロファイル未生成の場合は「未生成」案内を表示。
    """
    body = rx.cond(
        DrepDetailState.compass_has_profile,
        rx.vstack(
            # 投票実績 + 理由公開率
            rx.hstack(
                rx.vstack(
                    rx.text(
                        AuthState.t["drep_match_results_analyzed_votes"],
                        size="1", color="var(--gray-10)",
                    ),
                    rx.hstack(
                        rx.text(
                            DrepDetailState.compass_analyzed_votes,
                            size="5", weight="bold", color="var(--amber-11)",
                        ),
                        rx.text(AuthState.t["gov_results_unit"], size="2",
                                color="var(--gray-11)"),
                        spacing="1", align="baseline",
                    ),
                    spacing="0", align="start",
                ),
                rx.vstack(
                    rx.text(
                        AuthState.t["drep_match_results_reasoning_rate"],
                        size="1", color="var(--gray-10)",
                    ),
                    rx.hstack(
                        rx.text(
                            DrepDetailState.compass_reasoning_pct,
                            size="5", weight="bold", color="var(--gray-12)",
                        ),
                        rx.text("%", size="2", color="var(--gray-11)"),
                        spacing="0", align="baseline",
                    ),
                    spacing="0", align="start",
                ),
                spacing="7", wrap="wrap",
            ),
            # 対立軸 4 行
            rx.vstack(
                rx.foreach(
                    DrepDetailState.compass_balance_rows.to(list[dict[str, str]]),
                    _compass_balance_row,
                ),
                spacing="4", align="stretch", width="100%",
                padding_top="8px",
            ),
            rx.divider(margin_y="8px"),
            # 独立軸 3 行
            rx.vstack(
                rx.foreach(
                    DrepDetailState.compass_single_rows.to(list[dict[str, str]]),
                    _compass_single_row,
                ),
                spacing="4", align="stretch", width="100%",
            ),
            spacing="4", align="start", width="100%",
        ),
        rx.callout(
            AuthState.t["drep_match_section_no_profile"],
            icon="info", color_scheme="gray",
        ),
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("radar", size=18, color="var(--amber-11)"),
                rx.text(
                    AuthState.t["drep_match_section_profile_heading"],
                    size="4", weight="bold", color="var(--gray-12)",
                ),
                spacing="2", align="center",
            ),
            body,
            rx.text(
                AuthState.t["drep_match_results_classification_note"],
                size="1", color="var(--gray-10)",
                style={"fontStyle": "italic"},
            ),
            spacing="3", align="start", width="100%",
        ),
        padding="20px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


def _vote_stats() -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(AuthState.t["drep_vote_total_label"], size="1", color="var(--gray-10)"),
            rx.text(DrepDetailState.vote_total.to_string(), size="5", weight="bold", color="var(--gray-12)"),
            spacing="0", align="center", flex="1", min_width="100px",
        ),
        rx.vstack(
            rx.text("Yes", size="1", color="var(--gray-10)"),
            rx.text(DrepDetailState.vote_yes.to_string(), size="5", weight="bold", color="var(--green-11)"),
            spacing="0", align="center", flex="1", min_width="80px",
        ),
        rx.vstack(
            rx.text("No", size="1", color="var(--gray-10)"),
            rx.text(DrepDetailState.vote_no.to_string(), size="5", weight="bold", color="var(--red-11)"),
            spacing="0", align="center", flex="1", min_width="80px",
        ),
        rx.vstack(
            rx.text("Abstain", size="1", color="var(--gray-10)"),
            rx.text(DrepDetailState.vote_abstain.to_string(), size="5", weight="bold", color="var(--gray-11)"),
            spacing="0", align="center", flex="1", min_width="80px",
        ),
        spacing="3",
        padding="16px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
        wrap="wrap",
    )


_GA_TYPE_COLORS = {
    "ParameterChange": "blue",
    "TreasuryWithdrawals": "amber",
    "HardForkInitiation": "tomato",
    "InfoAction": "gray",
    "NewCommittee": "violet",
    "NewConstitution": "green",
    "NoConfidence": "crimson",
}


def _vote_history_row(v) -> rx.Component:
    status_badge = rx.match(
        v["ga_status"],
        ("active",   rx.badge(AuthState.t["gov_status_active"],   color_scheme="green",  variant="soft", size="1")),
        ("ratified", rx.badge(AuthState.t["gov_status_ratified"], color_scheme="blue",   variant="soft", size="1")),
        ("enacted",  rx.badge(AuthState.t["gov_status_enacted"],  color_scheme="violet", variant="soft", size="1")),
        ("dropped",  rx.badge(AuthState.t["gov_status_dropped"],  color_scheme="gray",   variant="soft", size="1")),
        ("expired",  rx.badge(AuthState.t["gov_status_expired"],  color_scheme="gray",   variant="soft", size="1")),
        rx.badge(v["ga_status"], variant="soft", size="1"),
    )
    type_badge = rx.match(
        v["proposal_type"],
        ("ParameterChange",    rx.badge(AuthState.t["gov_type_parameter_change"],    color_scheme="blue",   variant="surface", size="1")),
        ("TreasuryWithdrawals", rx.badge(AuthState.t["gov_type_treasury_withdrawals"], color_scheme="amber",  variant="surface", size="1")),
        ("HardForkInitiation", rx.badge(AuthState.t["gov_type_hard_fork"],          color_scheme="tomato", variant="surface", size="1")),
        ("InfoAction",         rx.badge(AuthState.t["gov_type_info_action"],        color_scheme="gray",   variant="surface", size="1")),
        ("NewCommittee",       rx.badge(AuthState.t["gov_type_new_committee"],     color_scheme="violet", variant="surface", size="1")),
        ("NewConstitution",    rx.badge(AuthState.t["gov_type_new_constitution"],  color_scheme="green",  variant="surface", size="1")),
        ("NoConfidence",       rx.badge(AuthState.t["gov_type_no_confidence"],    color_scheme="crimson", variant="surface", size="1")),
        rx.badge(v["proposal_type"], variant="surface", size="1"),
    )
    vote_badge = rx.cond(
        v["has_voted"] != "",
        _vote_badge(v["vote"]),
        rx.badge(AuthState.t["gov_vote_not_voted"], color_scheme="gray", variant="outline", size="2"),
    )
    title_display = rx.cond(
        AuthState.language == "en",
        rx.cond(v["title"] != "", v["title"], v["title_ja"]),
        rx.cond(v["title_ja"] != "", v["title_ja"], v["title"]),
    )
    has_rationale = rx.cond(
        v["rationale_ja"] != "",
        True,
        v["rationale"] != "",
    )
    rationale_button = rx.cond(
        has_rationale,
        rx.dialog.root(
            rx.dialog.trigger(
                rx.button(
                    AuthState.t["gov_vote_rationale_view"],
                    variant="soft", color_scheme="blue", size="1",
                    cursor="pointer",
                ),
            ),
            rx.dialog.content(
                rx.dialog.title(AuthState.t["gov_vote_rationale_title"]),
                rx.vstack(
                    rx.text(title_display, size="2", weight="medium", color="var(--gray-12)"),
                    rx.divider(),
                    rx.cond(
                        v["rationale_ja"] != "",
                        rx.vstack(
                            rx.text(AuthState.t["gov_vote_rationale_ja_label"], size="2", weight="bold"),
                            rx.text(v["rationale_ja"], size="2", style={"whiteSpace": "pre-wrap", "lineHeight": "1.6"}),
                            spacing="1", align="start", width="100%",
                        ),
                        rx.fragment(),
                    ),
                    rx.cond(
                        v["rationale"] != "",
                        rx.vstack(
                            rx.text(AuthState.t["gov_vote_rationale_en_label"], size="2", weight="bold"),
                            rx.text(v["rationale"], size="2", color="var(--gray-11)", style={"whiteSpace": "pre-wrap", "lineHeight": "1.6"}),
                            spacing="1", align="start", width="100%",
                        ),
                        rx.fragment(),
                    ),
                    rx.dialog.close(rx.button(AuthState.t["gov_vote_rationale_close"], variant="soft", size="2", cursor="pointer")),
                    spacing="3", align="start", width="100%",
                ),
                max_width=["95vw", "95vw", "680px"],
            ),
        ),
        rx.text("—", size="1", color="var(--gray-8)"),
    )
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(status_badge, type_badge, spacing="2", align="center", wrap="wrap"),
                rx.link(
                    rx.text(
                        rx.cond(title_display != "", title_display, AuthState.t["gov_title_none"]),
                        size="3", weight="medium", color="var(--gray-12)",
                        style={"wordBreak": "break-word"},
                    ),
                    href="/governance/" + v["proposal_id"],
                    underline="hover",
                ),
                rx.text(v["block_time"], size="1", color="var(--gray-10)"),
                spacing="1", align="start", flex="1", min_width="0",
            ),
            rx.vstack(
                vote_badge,
                rationale_button,
                spacing="2", align="end", flex_shrink="0",
            ),
            align="start",
            spacing="3",
            width="100%",
        ),
        padding="12px 14px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="8px",
        background="var(--gray-2)",
        width="100%",
        _hover={"background": "var(--gray-3)"},
        transition="background 0.15s",
    )


def _vote_history_pagination() -> rx.Component:
    def btn(page):
        is_active = page == DrepDetailState.current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: DrepDetailState.set_votes_page(page),
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
            on_click=DrepDetailState.votes_prev_page,
            radius="full", size="2", variant="soft",
            disabled=DrepDetailState.current_page == 1,
            _hover={"cursor": "pointer"},
        ),
        rx.foreach(DrepDetailState.votes_middle_pages, btn),
        rx.button(
            rx.icon(tag="chevron-right"),
            on_click=DrepDetailState.votes_next_page,
            radius="full", size="2", variant="soft",
            disabled=DrepDetailState.current_page == DrepDetailState.votes_total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="pagination gap-2",
        padding_top="1em",
        justify="end",
        align="center",
    )


def _vote_history() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(AuthState.t["drep_vote_history_title"], size="4", weight="bold"),
                rx.spacer(),
                rx.text(
                    DrepDetailState.votes_total.to_string()
                    + " " + AuthState.t["gov_results_unit"],
                    size="2", color="var(--gray-10)",
                ),
                width="100%",
                align="baseline",
            ),
            rx.cond(
                DrepDetailState.votes,
                rx.vstack(
                    rx.foreach(
                        DrepDetailState.votes_page.to(list[dict[str, str]]),
                        _vote_history_row,
                    ),
                    _vote_history_pagination(),
                    spacing="2", width="100%",
                ),
                rx.callout(
                    AuthState.t["drep_no_votes"],
                    icon="info", color_scheme="gray",
                ),
            ),
            spacing="3", align="start", width="100%",
        ),
        width="100%",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/drep/[drep_id]",
    title="DRep | ガバナンス | Cardanoism",
    on_load=DrepDetailState.on_load,
)
def governance_drep_detail_page() -> rx.Component:
    return rx.cond(
        DrepDetailState.load,
        rx.box(
            login_modal(),
            # DRep 委任確認モーダル (1 ページに 1 度だけマウント)
            drep_delegation_dialog(),
            rx.vstack(
                _breadcrumb(),
                governance_subnav("drep"),
                rx.cond(
                    DrepDetailState.not_found,
                    rx.callout(
                        AuthState.t["drep_not_found"],
                        icon="triangle-alert",
                        color_scheme="red",
                    ),
                    rx.vstack(
                        _profile_card(),
                        _profile_metadata_card(),
                        _compass_profile_section(),
                        _vote_stats(),
                        _vote_history(),
                        spacing="4", width="100%",
                    ),
                ),
                spacing="4", width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
