"""governance_why.py
ガバナンス > 「なぜ参加が重要か」啓発ページ (/governance/why)

ターゲット:
  - 自分には関係ないと思っている ADA ホルダー
  - 棄権 (Always Abstain) のまま放置している人
  - よくわからず DRep に委任している人

核メッセージ:
  「あなたの 1 ADA = 1 票。沈黙はトレジャリーの使い道とプロトコル変更を
   他人に委ねること。決めにくいなら DRep に任せればいい」

構成 (縦スクロール 1 ページ):
  A. ヒーロー (問いかけ)
  B. なぜ参加が重要か
     B-1. 棄権 ≠ 中立
     B-2. トレジャリー (家族の貯金比喩 + 動的データ)
     B-3. プロトコル変更
  C. 仕組み (1 ADA = 1 票、三権分立、閾値)
  D. DRep (代表者) に任せる選択肢
  E. メリデメ早見
  F. CTA
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.db_connect import get_db
from cardanoism.backend.treasury_db import (
    get_latest_treasury_snapshot,
    sum_enacted_withdrawals_in_epoch_range,
    get_active_ncl,
)
from cardanoism.backend.drep_db import get_dreps, sum_total_delegation
from cardanoism.backend.koios import get_current_epoch
from cardanoism.backend.price import format_ada, format_ada_short_ja, format_ada_short_en
from cardanoism.components.governance_nav import governance_subnav
from cardanoism.components.login_modal import login_modal

logger = logging.getLogger(__name__)


# ─── State ────────────────────────────────────────────────


class GovernanceWhyState(rx.State):
    """啓発ページの動的データ。"""

    load: bool = False

    # B-2: トレジャリー関連
    treasury_balance_ada: str = ""           # "○○億 ADA" 短縮
    treasury_balance_full: str = ""          # 整数 ADA
    treasury_epoch_str: str = ""             # スナップショットエポック
    recent_withdrawals_ada: str = ""         # 直近 6 ep の承認済み合計 (短縮)
    active_treasury_ga_count: str = "0"      # 進行中 TreasuryWithdrawals 件数
    active_treasury_ga_total_ada: str = ""   # 進行中 TreasuryWithdrawals 合計 (短縮)
    ncl_remaining_ada: str = ""              # NCL 残額 (短縮)
    ncl_used_pct: str = ""                   # NCL 消化率 %

    # B-1: 上位 DRep 集中
    top_drep_share_pct: str = ""             # 上位 N DRep の合計シェア %
    top_drep_count: int = 10
    top_dreps_list: list[dict[str, str]] = []  # 上位 10 DRep の内訳 [{rank, name, pct, width}]

    @rx.event
    async def on_load(self):
        self.load = False
        try:
            self._load_treasury()
            self._load_drep_concentration()
        except Exception as e:  # noqa: BLE001
            logger.exception("GovernanceWhyState.on_load: %s", e)
        finally:
            self.load = True

    def _load_treasury(self) -> None:
        # トレジャリー残高
        try:
            snap = get_latest_treasury_snapshot()
        except Exception as e:  # noqa: BLE001
            logger.warning("get_latest_treasury_snapshot failed: %s", e)
            snap = None
        if snap:
            try:
                lov = int(snap.get("treasury") or 0)
                self.treasury_balance_full = format_ada(lov, integer=True) if lov else "0"
                self.treasury_balance_ada = format_ada_short_ja(lov / 1_000_000) if lov else "0"
                self.treasury_epoch_str = str(snap.get("epoch_no") or "")
            except (TypeError, ValueError):
                pass

        # 直近 6 ep の承認済み引き出し合計
        cur = None
        try:
            cur = get_current_epoch()
        except Exception:
            pass
        if cur:
            try:
                lov = sum_enacted_withdrawals_in_epoch_range(cur - 6, cur)
                self.recent_withdrawals_ada = format_ada_short_ja(lov / 1_000_000) if lov else "0"
            except Exception as e:  # noqa: BLE001
                logger.warning("sum_enacted_withdrawals_in_epoch_range failed: %s", e)

        # 進行中の TreasuryWithdrawals (DB から直接 SELECT)
        try:
            with get_db() as (cursor, _):
                cursor.execute(
                    "SELECT COUNT(*) AS c, SUM(withdrawal_total_lovelace) AS t "
                    "FROM governance_actions "
                    "WHERE proposal_type = 'TreasuryWithdrawals' "
                    "  AND ratified_epoch IS NULL AND dropped_epoch IS NULL "
                    "  AND expired_epoch IS NULL AND enacted_epoch IS NULL"
                )
                row = cursor.fetchone()
                if row:
                    cnt = int((row.get("c") or 0))
                    total = int((row.get("t") or 0))
                    self.active_treasury_ga_count = str(cnt)
                    self.active_treasury_ga_total_ada = (
                        format_ada_short_ja(total / 1_000_000) if total else "0"
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("active treasury GA query failed: %s", e)

        # NCL の残額と消化率
        try:
            ncl = get_active_ncl()
        except Exception as e:  # noqa: BLE001
            logger.warning("get_active_ncl failed: %s", e)
            ncl = None
        if ncl:
            try:
                limit_lov = int(ncl.get("ncl_lovelace") or 0)
                used_lov = int(ncl.get("withdrawn_lovelace") or 0)
                remain = max(0, limit_lov - used_lov)
                self.ncl_remaining_ada = (
                    format_ada_short_ja(remain / 1_000_000) if remain else "0"
                )
                if limit_lov > 0:
                    self.ncl_used_pct = f"{(used_lov / limit_lov * 100):.0f}"
            except (TypeError, ValueError):
                pass

    def _load_drep_concentration(self) -> None:
        """上位 N DRep の総委任シェア%と内訳を計算する。"""
        try:
            top = get_dreps(only_registered=True, sort="amount_desc", limit=self.top_drep_count) or []
            total = sum_total_delegation(only_registered=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("DRep concentration query failed: %s", e)
            return
        if total <= 0:
            return

        rows: list[dict[str, str]] = []
        top_sum = 0
        for i, d in enumerate(top, start=1):
            amt = int(d.get("amount") or 0)
            top_sum += amt
            pct = amt / total * 100.0
            name = (d.get("given_name") or "").strip()
            if not name:
                drep_id = str(d.get("drep_id") or "")
                name = (drep_id[:12] + "…") if len(drep_id) > 12 else drep_id
            rows.append({
                "rank": str(i),
                "name": name,
                "pct": f"{pct:.2f}",
                "width": f"{pct:.2f}%",
            })
        self.top_dreps_list = rows
        self.top_drep_share_pct = f"{top_sum / total * 100:.1f}"


# ─── 共通 UI パーツ ─────────────────────────────────────────


def _section_card(
    title,
    body,
    icon: str = "info",
    step: str = "",
    accent: str = "amber",
) -> rx.Component:
    """モダンなセクションカード。

    - step: "1/7" のようにステップ番号を表示
    - accent: "amber" / "red" / "blue" / "green" でアクセントカラーを切替
    """
    accent_bg = rx.color(accent, 3)
    accent_border = rx.color(accent, 6)
    accent_text = rx.color(accent, 11)

    icon_circle = rx.box(
        rx.icon(icon, size=22, color="white"),
        background=rx.color(accent, 9),
        border_radius="999px",
        width="44px", height="44px",
        display="flex", align_items="center", justify_content="center",
        flex_shrink="0",
        style={"boxShadow": f"0 4px 12px -4px {rx.color(accent, 8)}"},
    )

    step_badge = rx.cond(
        step != "",
        rx.box(
            rx.text(
                step, size="1", weight="bold", color=accent_text,
                style={"letterSpacing": "0.08em"},
            ),
            padding="3px 10px",
            border_radius="999px",
            background=accent_bg,
            border=f"1px solid {accent_border}",
        ),
        rx.fragment(),
    )

    header = rx.hstack(
        icon_circle,
        rx.vstack(
            step_badge,
            rx.text(title, size="6", weight="bold", color="var(--gray-12)",
                    style={"lineHeight": "1.3"}),
            spacing="1", align_items="start",
        ),
        spacing="3", align="center", width="100%",
    )

    return rx.box(
        rx.vstack(
            header,
            rx.divider(color_scheme="gray", margin_y="6px"),
            body,
            spacing="4", align="stretch", width="100%",
        ),
        padding="28px 26px",
        border_radius="18px",
        border=f"1px solid {rx.color('gray', 4)}",
        background="var(--gray-1)",
        width="100%",
        style={
            "boxShadow": rx.color_mode_cond(
                "0 1px 3px rgba(15,23,42,0.04), 0 1px 2px rgba(15,23,42,0.06)",
                "0 1px 3px rgba(0,0,0,0.5), 0 1px 2px rgba(0,0,0,0.3)",
            ),
        },
    )


def _bold_metric(value: str, unit: str = "", color: str = "var(--amber-11)") -> rx.Component:
    """大きい数値表示用。"""
    return rx.hstack(
        rx.text(value, size="7", weight="bold", color=color, style={"letterSpacing": "-0.01em"}),
        rx.cond(
            unit != "",
            rx.text(unit, size="3", color="var(--gray-10)"),
            rx.fragment(),
        ),
        spacing="1", align="baseline",
    )


def _breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.link(AuthState.t["nav_governance"], href="/governance",
                size="2", underline="hover", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["gov_subnav_why"], size="2", weight="medium"),
        spacing="2", align="center", width="100%",
        padding_top="15px",
    )


# ─── S1: ガバナンスとは？ ─────────────────────────────────


def _what_section() -> rx.Component:
    """S1: Cardano の重要事項はコミュニティで決める + 三権分立。"""
    role = lambda emoji, name, role_label, color_name: rx.box(
        rx.vstack(
            # 巨大絵文字 in グラデ円 (キャラっぽく)
            rx.box(
                rx.text(
                    emoji,
                    style={
                        "fontSize": "60px",
                        "lineHeight": "1",
                        "filter": "drop-shadow(0 4px 8px rgba(0,0,0,0.15))",
                    },
                ),
                background=f"radial-gradient(circle at 30% 30%, {rx.color(color_name, 4)}, {rx.color(color_name, 7)})",
                border_radius="999px",
                width="120px", height="120px",
                display="flex", align_items="center", justify_content="center",
                border=f"3px solid {rx.color(color_name, 8)}",
                style={
                    "boxShadow": f"0 12px 32px -8px {rx.color(color_name, 9)}, inset 0 -6px 12px rgba(0,0,0,0.08)",
                    "flexShrink": "0",
                },
            ),
            # ラベル (色付きバッジ)
            rx.box(
                rx.text(
                    name, size="4", weight="bold",
                    color=rx.color(color_name, 12),
                ),
                padding="6px 14px",
                border_radius="999px",
                background=rx.color(color_name, 3),
                border=f"1px solid {rx.color(color_name, 6)}",
            ),
            rx.text(
                role_label, size="2", color="var(--gray-11)",
                style={"lineHeight": "1.7", "textAlign": "center"},
            ),
            spacing="3", align="center",
        ),
        padding="28px 22px",
        border_radius="20px",
        background=rx.color_mode_cond(
            f"linear-gradient(180deg, white, {rx.color(color_name, 2)})",
            f"linear-gradient(180deg, rgba(255,255,255,0.02), {rx.color(color_name, 3)})",
        ),
        border=f"2px solid {rx.color(color_name, 5)}",
        width="100%",
        style={
            "boxShadow": rx.color_mode_cond(
                f"0 4px 16px -4px rgba(15,23,42,0.08)",
                f"0 4px 16px -4px rgba(0,0,0,0.4)",
            ),
            "transition": "transform 0.18s ease, box-shadow 0.18s ease",
        },
        _hover={
            "transform": "translateY(-2px)",
            "box_shadow": rx.color_mode_cond(
                f"0 8px 24px -6px {rx.color(color_name, 8)}",
                f"0 8px 24px -6px rgba(0,0,0,0.5)",
            ),
        },
    )

    what_card = lambda num, icon, head, desc, color_name: rx.box(
        rx.hstack(
            # 番号 (大きく装飾的)
            rx.text(
                num,
                color=rx.color(color_name, 9),
                style={
                    "fontSize": "40px",
                    "fontWeight": "800",
                    "lineHeight": "1",
                    "letterSpacing": "-0.04em",
                    "fontFamily": "ui-monospace, monospace",
                    "minWidth": "52px",
                    "flexShrink": "0",
                },
            ),
            # アイコン (lucide、控えめ)
            rx.icon(icon, size=22, color=rx.color(color_name, 11), flex_shrink="0"),
            # 見出し + 説明
            rx.vstack(
                rx.text(head, size="3", weight="bold", color="var(--gray-12)"),
                rx.text(
                    desc, size="2", color="var(--gray-11)",
                    style={"lineHeight": "1.6"},
                ),
                spacing="1", align_items="start",
            ),
            spacing="3", align="center", width="100%",
        ),
        padding="16px 20px",
        border_radius="12px",
        background=rx.color_mode_cond("var(--gray-2)", "rgba(255,255,255,0.02)"),
        border=f"1px solid {rx.color('gray', 4)}",
        # 太い left-border で「リスト項目」感を演出
        border_left=f"4px solid {rx.color(color_name, 9)}",
        width="100%",
        style={"transition": "background 0.15s ease"},
        _hover={
            "background": rx.color_mode_cond(
                f"{rx.color(color_name, 2)}",
                f"rgba(255,255,255,0.04)",
            ),
        },
    )

    body = rx.vstack(
        rx.text(
            AuthState.t["gov_why_s1_lead"],
            size="4", color="var(--gray-12)", style={"lineHeight": "1.7"},
        ),
        # 何が決まる
        rx.text(
            AuthState.t["gov_why_s1_what_title"],
            size="3", weight="bold", color="var(--gray-12)",
            style={"marginTop": "8px"},
        ),
        rx.vstack(
            what_card(
                "01",
                "coins",
                AuthState.t["gov_why_s1_what_money"],
                AuthState.t["gov_why_s1_what_money_d"],
                "amber",
            ),
            what_card(
                "02",
                "settings-2",
                AuthState.t["gov_why_s1_what_rules"],
                AuthState.t["gov_why_s1_what_rules_d"],
                "blue",
            ),
            what_card(
                "03",
                "rocket",
                AuthState.t["gov_why_s1_what_dev"],
                AuthState.t["gov_why_s1_what_dev_d"],
                "violet",
            ),
            what_card(
                "04",
                "scale",
                AuthState.t["gov_why_s1_what_cc"],
                AuthState.t["gov_why_s1_what_cc_d"],
                "crimson",
            ),
            spacing="2",
            width="100%",
        ),
        # 三権分立
        rx.text(
            AuthState.t["gov_why_s1_three_title"],
            size="3", weight="bold", color="var(--gray-12)",
            style={"marginTop": "8px"},
        ),
        rx.grid(
            role("🗳️", AuthState.t["gov_why_c_drep_name"], AuthState.t["gov_why_c_drep_role"], "amber"),
            role("🖥️", AuthState.t["gov_why_c_spo_name"], AuthState.t["gov_why_c_spo_role"], "blue"),
            role("⚖️", AuthState.t["gov_why_c_cc_name"], AuthState.t["gov_why_c_cc_role"], "violet"),
            columns={"base": "1", "md": "3"},
            spacing="4", width="100%",
        ),
        rx.text(
            AuthState.t["gov_why_c_threshold_intro"],
            size="2", color="var(--gray-11)", style={"lineHeight": "1.7"},
        ),
        spacing="3", align="stretch", width="100%",
    )
    return _section_card(
        AuthState.t["gov_why_s1_title"], body, "lightbulb",
        step="STEP 1 / 6", accent="amber",
    )


# ─── S2: あなたの 1 ADA = 1 票 ────────────────────────────


def _hero_section() -> rx.Component:
    """S2: 1 ADA = 1 票。巨大タイポ + amber グラデで存在感最大化。"""
    step_badge = rx.box(
        rx.text(
            "STEP 2 / 6", size="1", weight="bold", color="var(--amber-11)",
            style={"letterSpacing": "0.12em"},
        ),
        padding="4px 12px",
        border_radius="999px",
        background="var(--amber-3)",
        border=f"1px solid {rx.color('amber', 7)}",
        width="fit-content",
    )

    # 巨大なヒーロー文字
    headline = rx.heading(
        AuthState.t["gov_why_hero_title"],
        weight="bold", color="var(--gray-12)",
        style={
            "fontSize": "clamp(36px, 6vw, 64px)",
            "lineHeight": "1.15",
            "letterSpacing": "-0.02em",
        },
    )

    # "1 ADA = 1 票" 部分のグラデ強調用に補助バッジ
    accent_badge = rx.box(
        rx.text(
            "1 ADA = 1 vote",
            weight="bold",
            color="var(--amber-11)",
            style={
                "fontSize": "clamp(18px, 2.4vw, 24px)",
                "letterSpacing": "0.04em",
            },
        ),
        padding="8px 18px",
        border_radius="999px",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.06)"),
        border=f"2px solid {rx.color('amber', 8)}",
        style={"display": "inline-block"},
    )

    sub = rx.text(
        AuthState.t["gov_why_hero_sub"],
        size="4", color="var(--gray-11)",
        style={"lineHeight": "1.7", "maxWidth": "640px"},
    )
    cta_loggedin = rx.link(
        rx.button(
            rx.icon("user-cog", size=18),
            rx.text(AuthState.t["gov_why_hero_cta_check"], size="3"),
            color_scheme="amber", size="3", cursor="pointer",
        ),
        href="/mypage",
        underline="none",
    )
    cta_loggedout = rx.link(
        rx.button(
            rx.icon("log-in", size=18),
            rx.text(AuthState.t["gov_why_hero_cta_login"], size="3"),
            color_scheme="amber", size="3", cursor="pointer",
        ),
        href="/login",
        underline="none",
    )
    return rx.box(
        rx.vstack(
            step_badge,
            accent_badge,
            headline,
            sub,
            rx.cond(AuthState.is_logged_in, cta_loggedin, cta_loggedout),
            spacing="4", align_items="start", width="100%",
        ),
        padding="56px 32px",
        border_radius="22px",
        background=rx.color_mode_cond(
            "radial-gradient(ellipse at top right, var(--amber-4), var(--amber-2) 50%, var(--amber-1))",
            "radial-gradient(ellipse at top right, rgba(245,158,11,0.22), rgba(245,158,11,0.08) 50%, rgba(245,158,11,0.02))",
        ),
        border=f"1px solid {rx.color('amber', 6)}",
        width="100%",
        style={
            "boxShadow": rx.color_mode_cond(
                "0 12px 32px -12px rgba(245,158,11,0.30), 0 4px 12px -4px rgba(245,158,11,0.20)",
                "0 12px 32px -12px rgba(245,158,11,0.45), 0 4px 12px -4px rgba(0,0,0,0.5)",
            ),
            "position": "relative",
            "overflow": "hidden",
        },
    )


# ─── B. なぜ参加が重要か ─────────────────────────────────


def _drep_concentration_box() -> rx.Component:
    """上位 10 DRep の投票力集中シェアと内訳を見せる。"""
    summary = rx.cond(
        GovernanceWhyState.top_drep_share_pct != "",
        rx.box(
            rx.hstack(
                rx.icon("triangle-alert", size=18, color="var(--red-10)"),
                rx.vstack(
                    rx.text(
                        AuthState.t["gov_why_b1_concentration_title"],
                        size="2", weight="bold", color="var(--gray-12)",
                    ),
                    rx.hstack(
                        rx.text(AuthState.t["gov_why_b1_concentration_prefix"], size="2", color="var(--gray-11)"),
                        rx.text(GovernanceWhyState.top_drep_share_pct, "%",
                                size="5", weight="bold", color="var(--red-11)"),
                        rx.text(AuthState.t["gov_why_b1_concentration_suffix"], size="2", color="var(--gray-11)"),
                        spacing="2", align="baseline", wrap="wrap",
                    ),
                    spacing="1", align_items="start",
                ),
                spacing="3", align="start", width="100%",
            ),
            padding="14px 16px",
            border_radius="10px",
            background=rx.color("red", 2),
            border=f"1px solid {rx.color('red', 6)}",
            width="100%",
        ),
        rx.fragment(),
    )

    row = lambda d: rx.hstack(
        rx.text(
            d["rank"], size="1", weight="bold", color="var(--gray-10)",
            style={
                "width": "24px",
                "fontFamily": "ui-monospace, monospace",
                "flexShrink": "0",
            },
        ),
        rx.text(
            d["name"], size="2", color="var(--gray-12)",
            style={
                "minWidth": "0",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
                "flex": "1 1 30%",
            },
        ),
        rx.box(
            rx.box(
                background=rx.color("red", 9),
                height="100%",
                border_radius="999px",
                style={"width": d["width"]},
            ),
            background=rx.color("gray", 4),
            height="8px",
            border_radius="999px",
            style={"flex": "1 1 50%", "overflow": "hidden", "minWidth": "60px"},
        ),
        rx.text(
            d["pct"], "%",
            size="2", weight="bold", color="var(--red-11)",
            style={
                "width": "56px",
                "textAlign": "right",
                "fontFamily": "ui-monospace, monospace",
                "flexShrink": "0",
            },
        ),
        spacing="2", align="center", width="100%",
    )

    list_box = rx.cond(
        GovernanceWhyState.top_dreps_list.length() > 0,
        rx.box(
            rx.vstack(
                rx.text(
                    AuthState.t["gov_why_s4_list_title"],
                    size="2", weight="bold", color="var(--gray-11)",
                    style={"letterSpacing": "0.02em"},
                ),
                rx.foreach(GovernanceWhyState.top_dreps_list, row),
                spacing="2", width="100%", align_items="stretch",
            ),
            padding="14px 16px",
            border_radius="10px",
            background="var(--gray-2)",
            border=f"1px solid {rx.color('gray', 4)}",
            width="100%",
        ),
        rx.fragment(),
    )

    return rx.vstack(summary, list_box, spacing="3", width="100%")


def _family_analogy() -> rx.Component:
    """B-2 冒頭: 家族の貯金で考えてみよう。"""
    return rx.box(
        rx.vstack(
            # ファミリー絵文字 + 説明
            rx.hstack(
                rx.text("👨", style={"fontSize": "32px"}),
                rx.text("👩", style={"fontSize": "32px"}),
                rx.text("👧", style={"fontSize": "32px"}),
                rx.text("👦", style={"fontSize": "32px"}),
                rx.text("👶", style={"fontSize": "32px"}),
                spacing="2", justify="center", width="100%",
            ),
            rx.text(
                AuthState.t["gov_why_b2_family_setup"],
                size="3", color="var(--gray-12)", style={"lineHeight": "1.8", "textAlign": "center"},
            ),
            # 大きい "300 万円"
            rx.center(
                rx.hstack(
                    rx.text("💰", style={"fontSize": "28px"}),
                    rx.text(
                        AuthState.t["gov_why_b2_family_amount"],
                        size="8", weight="bold", color="var(--amber-11)",
                    ),
                    spacing="2", align="center",
                ),
                width="100%", padding_y="8px",
            ),
            # 強い問いかけ
            rx.text(
                AuthState.t["gov_why_b2_family_question"],
                size="5", weight="bold", color="var(--gray-12)",
                style={"lineHeight": "1.6", "textAlign": "center"},
            ),
            rx.text(
                AuthState.t["gov_why_b2_family_followup"],
                size="3", color="var(--gray-11)",
                style={"lineHeight": "1.7", "textAlign": "center"},
            ),
            spacing="3", align="stretch", width="100%",
        ),
        padding="22px 22px",
        border_radius="14px",
        background=rx.color_mode_cond("var(--amber-2)", "rgba(245,158,11,0.08)"),
        border=f"1px solid {rx.color('amber', 5)}",
        width="100%",
    )


def _treasury_metrics() -> rx.Component:
    """B-2 後半: 動的データで現実の規模を見せる。"""
    metric_box = lambda label, value, suffix="ADA": rx.vstack(
        rx.text(label, size="1", color="var(--gray-10)"),
        rx.hstack(
            rx.text(value, size="5", weight="bold", color="var(--gray-12)"),
            rx.text(suffix, size="2", color="var(--gray-10)"),
            spacing="1", align="baseline",
        ),
        spacing="0", align_items="start",
    )
    return rx.box(
        rx.grid(
            metric_box(
                AuthState.t["gov_why_b2_metric_balance"],
                GovernanceWhyState.treasury_balance_ada,
            ),
            metric_box(
                AuthState.t["gov_why_b2_metric_recent"],
                rx.cond(
                    GovernanceWhyState.recent_withdrawals_ada != "",
                    GovernanceWhyState.recent_withdrawals_ada,
                    "—",
                ),
            ),
            metric_box(
                AuthState.t["gov_why_b2_metric_active"],
                GovernanceWhyState.active_treasury_ga_total_ada,
                suffix="ADA",
            ),
            metric_box(
                AuthState.t["gov_why_b2_metric_ncl_remain"],
                rx.cond(
                    GovernanceWhyState.ncl_remaining_ada != "",
                    GovernanceWhyState.ncl_remaining_ada,
                    "—",
                ),
            ),
            columns={"base": "2", "md": "4"},
            spacing="4", width="100%",
        ),
        padding="16px 18px",
        border_radius="10px",
        background="var(--gray-2)",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )


def _why_section_b2() -> rx.Component:
    """B-2: トレジャリーの使い道はあなたが決める (家族の貯金比喩 + 規模感)。"""
    # 比喩 → アナロジー表 → 現実数値
    analogy_table = rx.box(
        rx.vstack(
            rx.text(AuthState.t["gov_why_b2_table_intro"], size="3", weight="medium", color="var(--gray-12)"),
            rx.box(
                rx.vstack(
                    _analogy_row(
                        AuthState.t["gov_why_b2_table_h_family"],
                        AuthState.t["gov_why_b2_table_h_cardano"],
                        is_header=True,
                    ),
                    _analogy_row(
                        AuthState.t["gov_why_b2_table_a1_l"],
                        AuthState.t["gov_why_b2_table_a1_r"],
                    ),
                    _analogy_row(
                        AuthState.t["gov_why_b2_table_a2_l"],
                        AuthState.t["gov_why_b2_table_a2_r"],
                    ),
                    _analogy_row(
                        AuthState.t["gov_why_b2_table_a3_l"],
                        AuthState.t["gov_why_b2_table_a3_r"],
                    ),
                    _analogy_row(
                        AuthState.t["gov_why_b2_table_a4_l"],
                        AuthState.t["gov_why_b2_table_a4_r"],
                    ),
                    spacing="0", align="stretch", width="100%",
                ),
                width="100%",
            ),
            spacing="2", align="stretch", width="100%",
        ),
        width="100%",
    )

    body = rx.vstack(
        _family_analogy(),
        analogy_table,
        _treasury_metrics(),
        rx.text(
            AuthState.t["gov_why_b2_punchline"],
            size="4", weight="bold", color="var(--red-11)",
            style={"lineHeight": "1.7", "textAlign": "center"},
        ),
        spacing="4", align="stretch", width="100%",
    )
    return _section_card(
        AuthState.t["gov_why_b2_title"], body, "landmark",
        step="STEP 3 / 6", accent="amber",
    )


# ─── S4: DRep 投票権集中 ──────────────────────────────────


def _concentration_section() -> rx.Component:
    """S4: DRep の投票権が集中している現実を見せる + 棄権の罠。"""
    body = rx.vstack(
        rx.text(
            AuthState.t["gov_why_s4_lead"],
            size="3", color="var(--gray-12)", style={"lineHeight": "1.8"},
        ),
        _drep_concentration_box(),
        spacing="3", align="stretch", width="100%",
    )
    return _section_card(
        AuthState.t["gov_why_s4_title"], body, "triangle-alert",
        step="STEP 4 / 6", accent="red",
    )


def _analogy_row(left, right, is_header: bool = False) -> rx.Component:
    """2 列対比表の 1 行。"""
    cell_style = {
        "padding": "10px 14px",
        "fontSize": "14px",
        "lineHeight": "1.6",
    }
    bg_left = "var(--gray-3)" if is_header else "var(--gray-2)"
    bg_right = rx.color("amber", 3) if is_header else rx.color("amber", 2)
    weight = "bold" if is_header else "medium"
    return rx.grid(
        rx.box(
            rx.text(left, weight=weight, color="var(--gray-12)"),
            background=bg_left,
            **cell_style,
            border=f"1px solid {rx.color('gray', 4)}",
        ),
        rx.box(
            rx.text(right, weight=weight, color="var(--amber-12)"),
            background=bg_right,
            **cell_style,
            border=f"1px solid {rx.color('amber', 5)}",
        ),
        columns="2", spacing="0", width="100%",
    )


# ─── S5: 委任先を見直そう ────────────────────────────────


def _drep_section() -> rx.Component:
    # 2 つの選択肢: DRep になる / DRep に委任する
    def option_card(emoji, color_name, title, subtitle, desc,
                    cta_label, cta_href, is_external):
        return rx.box(
            rx.vstack(
                # アイコン (グラデ円)
                rx.box(
                    rx.text(emoji, style={"fontSize": "44px", "lineHeight": "1"}),
                    background=f"linear-gradient(135deg, {rx.color(color_name, 4)}, {rx.color(color_name, 7)})",
                    border_radius="999px",
                    width="88px", height="88px",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    style={"boxShadow": f"0 8px 24px -8px {rx.color(color_name, 8)}"},
                ),
                rx.text(
                    title,
                    size="6", weight="bold", color="var(--gray-12)",
                    style={"textAlign": "center", "lineHeight": "1.3"},
                ),
                rx.text(
                    subtitle,
                    size="3", weight="medium", color=rx.color(color_name, 11),
                    style={"textAlign": "center", "lineHeight": "1.6"},
                ),
                rx.text(
                    desc,
                    size="2", color="var(--gray-11)",
                    style={"lineHeight": "1.7", "textAlign": "center"},
                ),
                rx.link(
                    rx.button(
                        rx.icon(
                            "arrow-up-right" if is_external else "arrow-right",
                            size=16,
                        ),
                        rx.text(cta_label, size="3"),
                        color_scheme=color_name, size="3", cursor="pointer",
                    ),
                    href=cta_href,
                    is_external=is_external,
                    underline="none",
                ),
                spacing="3", align="center", width="100%",
            ),
            padding="32px 24px",
            border_radius="16px",
            background=rx.color_mode_cond(
                f"linear-gradient(180deg, {rx.color(color_name, 2)}, var(--gray-1))",
                "linear-gradient(180deg, rgba(255,255,255,0.04), rgba(0,0,0,0))",
            ),
            border=f"1px solid {rx.color(color_name, 6)}",
            width="100%", height="100%",
            style={"transition": "transform 0.15s, border-color 0.15s, box-shadow 0.15s"},
            _hover={
                "transform": "translateY(-2px)",
                "borderColor": rx.color(color_name, 8),
                "boxShadow": f"0 12px 32px -12px {rx.color(color_name, 8)}",
            },
        )

    options = rx.grid(
        option_card(
            "🗳️", "amber",
            AuthState.t["gov_why_s5_opt1_title"],
            AuthState.t["gov_why_s5_opt1_subtitle"],
            AuthState.t["gov_why_s5_opt1_desc"],
            AuthState.t["gov_why_s5_opt1_cta"],
            "https://gov.tools/", True,
        ),
        option_card(
            "🤝", "blue",
            AuthState.t["gov_why_s5_opt2_title"],
            AuthState.t["gov_why_s5_opt2_subtitle"],
            AuthState.t["gov_why_s5_opt2_desc"],
            AuthState.t["gov_why_s5_opt2_cta"],
            "/governance/drep", False,
        ),
        columns={"base": "1", "md": "2"},
        spacing="4", width="100%",
    )

    # D-2 良い DRep の選び方
    d2 = rx.box(
        rx.vstack(
            rx.text(AuthState.t["gov_why_d2_title"], size="4", weight="bold", color="var(--gray-12)"),
            *[
                rx.hstack(
                    rx.icon(icon, size=14, color=color),
                    rx.text(item, size="2", color="var(--gray-12)", style={"lineHeight": "1.7"}),
                    spacing="2", align="start",
                )
                for icon, color, item in [
                    ("circle-check", "var(--green-10)", AuthState.t["gov_why_d2_good1"]),
                    ("circle-check", "var(--green-10)", AuthState.t["gov_why_d2_good2"]),
                    ("circle-check", "var(--green-10)", AuthState.t["gov_why_d2_good3"]),
                    ("triangle-alert", "var(--amber-10)", AuthState.t["gov_why_d2_warn"]),
                ]
            ],
            spacing="2", align_items="start", width="100%",
        ),
        padding="16px 18px",
        border_radius="10px",
        background="var(--gray-2)",
        border=f"1px solid {rx.color('gray', 4)}",
        width="100%",
    )

    # D-3 比較表
    d3_rows = [
        # (方法, 手間, 影響力, ターゲット, recommended?)
        (AuthState.t["gov_why_d3_o1_method"], AuthState.t["gov_why_d3_o1_effort"],
         AuthState.t["gov_why_d3_o1_impact"], AuthState.t["gov_why_d3_o1_target"], False, False),
        (AuthState.t["gov_why_d3_o2_method"], AuthState.t["gov_why_d3_o2_effort"],
         AuthState.t["gov_why_d3_o2_impact"], AuthState.t["gov_why_d3_o2_target"], True, False),
        (AuthState.t["gov_why_d3_o3_method"], AuthState.t["gov_why_d3_o3_effort"],
         AuthState.t["gov_why_d3_o3_impact"], AuthState.t["gov_why_d3_o3_target"], False, False),
        (AuthState.t["gov_why_d3_o4_method"], AuthState.t["gov_why_d3_o4_effort"],
         AuthState.t["gov_why_d3_o4_impact"], AuthState.t["gov_why_d3_o4_target"], False, False),
        (AuthState.t["gov_why_d3_o5_method"], AuthState.t["gov_why_d3_o5_effort"],
         AuthState.t["gov_why_d3_o5_impact"], AuthState.t["gov_why_d3_o5_target"], False, True),
    ]

    def _row(method, effort, impact, target, recommended: bool, danger: bool):
        bg = (rx.color("amber", 3) if recommended
              else (rx.color("red", 2) if danger
                    else "var(--gray-2)"))
        weight = "bold" if (recommended or danger) else "medium"
        return rx.grid(
            rx.box(rx.text(method, weight=weight, size="2"),
                   padding="10px 12px", background=bg,
                   border=f"1px solid {rx.color('gray', 4)}"),
            rx.box(rx.text(effort, size="2"),
                   padding="10px 12px", background=bg,
                   border=f"1px solid {rx.color('gray', 4)}"),
            rx.box(rx.text(impact, size="2"),
                   padding="10px 12px", background=bg,
                   border=f"1px solid {rx.color('gray', 4)}"),
            rx.box(rx.text(target, size="2"),
                   padding="10px 12px", background=bg,
                   border=f"1px solid {rx.color('gray', 4)}"),
            columns="4", spacing="0", width="100%",
        )

    def _header_row():
        return rx.grid(
            rx.box(rx.text(AuthState.t["gov_why_d3_h_method"], weight="bold", size="2"),
                   padding="10px 12px", background="var(--gray-3)",
                   border=f"1px solid {rx.color('gray', 4)}"),
            rx.box(rx.text(AuthState.t["gov_why_d3_h_effort"], weight="bold", size="2"),
                   padding="10px 12px", background="var(--gray-3)",
                   border=f"1px solid {rx.color('gray', 4)}"),
            rx.box(rx.text(AuthState.t["gov_why_d3_h_impact"], weight="bold", size="2"),
                   padding="10px 12px", background="var(--gray-3)",
                   border=f"1px solid {rx.color('gray', 4)}"),
            rx.box(rx.text(AuthState.t["gov_why_d3_h_target"], weight="bold", size="2"),
                   padding="10px 12px", background="var(--gray-3)",
                   border=f"1px solid {rx.color('gray', 4)}"),
            columns="4", spacing="0", width="100%",
        )

    d3 = rx.box(
        rx.vstack(
            rx.text(AuthState.t["gov_why_d3_title"], size="4", weight="bold", color="var(--gray-12)"),
            _header_row(),
            *[_row(*r) for r in d3_rows],
            spacing="0", align="stretch", width="100%",
        ),
        width="100%",
        style={"overflowX": "auto"},
    )

    body = rx.vstack(
        rx.text(
            AuthState.t["gov_why_s5_lead"],
            size="3", color="var(--gray-12)", style={"lineHeight": "1.8"},
        ),
        options,
        d2,
        d3,
        spacing="4", align="stretch", width="100%",
    )
    return _section_card(
        AuthState.t["gov_why_s5_title"], body, "users",
        step="STEP 5 / 6", accent="blue",
    )


# ─── F. CTA ──────────────────────────────────────────────


def _cta_section() -> rx.Component:
    def _cta_card(icon, label, sub, href):
        return rx.link(
            rx.box(
                rx.hstack(
                    rx.icon(icon, size=20, color="var(--amber-11)"),
                    rx.vstack(
                        rx.text(label, size="3", weight="bold", color="var(--gray-12)"),
                        rx.text(sub, size="1", color="var(--gray-10)",
                                style={"lineHeight": "1.5"}),
                        spacing="0", align_items="start",
                        style={"flex": "1 1 auto", "minWidth": "0"},
                    ),
                    rx.spacer(),
                    rx.icon("chevron-right", size=18, color="var(--gray-10)"),
                    spacing="3", align="center", width="100%",
                ),
                padding="16px 18px",
                border_radius="12px",
                border=f"1px solid {rx.color('amber', 6)}",
                background=rx.color("amber", 2),
                width="100%",
                height="100%",
                _hover={
                    "border_color": rx.color("amber", 8),
                    "background": rx.color("amber", 3),
                },
                style={"transition": "background 0.15s, border-color 0.15s"},
            ),
            href=href,
            underline="none",
            width="100%",
            height="100%",
            style={"display": "flex"},
        )

    cards = rx.grid(
        rx.cond(
            AuthState.is_logged_in,
            _cta_card(
                "user-cog", AuthState.t["gov_why_f_cta2_label"],
                AuthState.t["gov_why_f_cta2_sub"], "/mypage",
            ),
            _cta_card(
                "log-in", AuthState.t["gov_why_f_cta_login_label"],
                AuthState.t["gov_why_f_cta_login_sub"], "/login",
            ),
        ),
        _cta_card(
            "gavel", AuthState.t["gov_why_f_cta3_label"],
            AuthState.t["gov_why_f_cta3_sub"], "/governance",
        ),
        _cta_card(
            "landmark", AuthState.t["gov_why_f_cta4_label"],
            AuthState.t["gov_why_f_cta4_sub"], "/governance/treasury",
        ),
        columns={"base": "1", "md": "3"},
        spacing="3", width="100%",
    )

    return _section_card(
        AuthState.t["gov_why_f_title"], cards, "rocket",
        step="STEP 6 / 6", accent="amber",
    )


# ─── ページ ───────────────────────────────────────────────


@template(
    route="/governance/why",
    title="ガバナンスとは？ | Cardanoism",
    on_load=GovernanceWhyState.on_load,
)
def governance_why_page() -> rx.Component:
    return rx.box(
        login_modal(),
        rx.vstack(
            _breadcrumb(),
            governance_subnav("why"),
            _what_section(),         # S1: ガバナンスとは？
            _hero_section(),         # S2: あなたの 1 ADA = 1 票
            _why_section_b2(),       # S3: 家族の比喩でわかるトレジャリー
            _concentration_section(),# S4: DRep 投票権集中
            _drep_section(),         # S5: 委任先を見直そう
            _cta_section(),          # S6: 次のアクション
            spacing="6",
            width="100%",
            padding_y="20px",
        ),
        width="100%",
        max_width="1130px",
    )
