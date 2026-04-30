"""
governance_treasury.py
ガバナンス > トレジャリー（国庫）サブページ

- 現在のトレジャリー残高（Koios /totals）
- Net Change Limit（憲法で定められた年間引き出し上限）の消化状況
- 直近のトレジャリー引き出し履歴（/treasury_withdrawals）
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.treasury_db import (
    get_latest_treasury_snapshot,
    get_withdrawals_recent,
    sum_withdrawals_in_epoch_range,
    sum_enacted_withdrawals_in_epoch_range,
    get_treasury_proposals_in_epoch_range,
    get_treasury_history_recent,
    get_treasury_history_in_range,
    build_treasury_chart_svg,
    get_active_ncl,
)
from cardanoism.backend.fiat_db import get_fiat_rate
from cardanoism.backend.price import (
    format_ada,
    format_jpy_short,
    format_usd_short,
)
from cardanoism.components.governance_nav import governance_subnav
from cardanoism.components.login_modal import login_modal

logger = logging.getLogger(__name__)

# Cardano mainnet Shelley genesis (Ep.208 開始 = 2020-07-29 21:44:51 UTC)
# NCL 提案は mainnet 固定なのでこの基準で算出する
_SHELLEY_MAINNET_EPOCH = 208
_SHELLEY_MAINNET_UNIX  = 1596059091
_EPOCH_SECONDS         = 432_000     # 5日
_JST                   = timezone(timedelta(hours=9))


def _epoch_start_jst(epoch: int) -> datetime:
    """エポック開始時刻を JST の datetime で返す。"""
    ts = _SHELLEY_MAINNET_UNIX + (int(epoch) - _SHELLEY_MAINNET_EPOCH) * _EPOCH_SECONDS
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(_JST)


def _format_epoch_jst(epoch: int) -> str:
    """'2026/2/14 (613)' 形式で返す（JST 基準）。"""
    return f"{_epoch_start_jst(epoch):%Y/%m/%d} ({int(epoch)})"


def _fiat_pair(ada_amount: float, ada_jpy: float, ada_usd: float) -> tuple[str, str]:
    """ADA 金額から (JPY表示, USD表示) のタプルを返す。"""
    jpy = format_jpy_short(ada_amount * ada_jpy) if ada_jpy else ""
    usd = format_usd_short(ada_amount * ada_usd) if ada_usd else ""
    return jpy, usd


# ─── State ────────────────────────────────────────────────────────────────────


class TreasuryState(rx.State):
    load: bool = False
    error: str = ""

    # レート
    fiat_available: bool = False

    # 残高
    balance_ada_display: str = "-"
    balance_jpy_display: str = ""
    balance_usd_display: str = ""
    current_epoch: int = 0

    # NCL（動的取得）
    ncl_available: bool = False
    ncl_title: str = ""
    ncl_proposal_id: str = ""
    ncl_drep_yes_pct_display: str = "-"
    ncl_period_start: int = 0
    ncl_period_end: int = 0
    ncl_period_start_display: str = "-"
    ncl_period_end_display: str = "-"
    ncl_limit_ada_display: str = "-"
    ncl_limit_jpy_display: str = ""
    ncl_limit_usd_display: str = ""
    ncl_spent_ada_display: str = "-"
    ncl_spent_jpy_display: str = ""
    ncl_spent_usd_display: str = ""
    ncl_pending_ada_display: str = "-"
    ncl_pending_jpy_display: str = ""
    ncl_pending_usd_display: str = ""
    ncl_spent_pct: float = 0.0
    ncl_pending_pct: float = 0.0
    ncl_spent_pct_display: str = "0.0"
    ncl_pending_pct_display: str = "0.0"
    ncl_progress_pct: float = 0.0           # 後方互換（済み+予定）
    ncl_progress_pct_display: str = "0.0"

    # 引き出し履歴（新しい順）
    withdrawals: List[Dict[str, Any]] = []

    # 直近 N エポックのトレジャリー残高折れ線グラフ SVG
    treasury_chart_svg: str = ""
    treasury_chart_epoch_count: int = 0

    # NCL 期間内の TreasuryWithdrawals 提案
    proposals: List[Dict[str, Any]] = []

    # タブ
    active_tab: str = "proposals"

    # シミュレーション
    simulation_proposal_ids: list[str] = []
    # 計算用に保持（rx.var で参照）
    ncl_limit_lovelace: int = 0
    ncl_spent_lovelace: int = 0
    ncl_pending_lovelace: int = 0
    fiat_ada_jpy: float = 0.0
    fiat_ada_usd: float = 0.0

    @rx.var
    def simulation_lovelace(self) -> int:
        """チェックされたアクティブ提案の合計 lovelace。"""
        total = 0
        selected = set(self.simulation_proposal_ids)
        for p in self.proposals:
            if p.get("proposal_id") in selected:
                try:
                    total += int(p.get("amount_lovelace") or 0)
                except (TypeError, ValueError):
                    continue
        return total

    @rx.var
    def simulation_ada_display(self) -> str:
        return f"{self.simulation_lovelace // 1_000_000:,}"

    @rx.var
    def simulation_jpy_display(self) -> str:
        if not self.fiat_ada_jpy:
            return ""
        from cardanoism.backend.price import format_jpy_short
        ada = self.simulation_lovelace / 1_000_000
        return format_jpy_short(ada * self.fiat_ada_jpy)

    @rx.var
    def simulation_usd_display(self) -> str:
        if not self.fiat_ada_usd:
            return ""
        from cardanoism.backend.price import format_usd_short
        ada = self.simulation_lovelace / 1_000_000
        return format_usd_short(ada * self.fiat_ada_usd)

    @rx.var
    def simulation_pct(self) -> float:
        """NCL上限に対するシミュレーション割合。バーの幅計算。
        バーは 済み + 確定 + シミュ が上限を超えないようクランプ。
        """
        if self.ncl_limit_lovelace <= 0:
            return 0.0
        used_pct = self.ncl_spent_pct + self.ncl_pending_pct
        sim_pct = self.simulation_lovelace / self.ncl_limit_lovelace * 100.0
        return max(0.0, min(sim_pct, 100.0 - used_pct))

    @rx.var
    def simulation_pct_display(self) -> str:
        if self.ncl_limit_lovelace <= 0:
            return "0.0"
        raw = self.simulation_lovelace / self.ncl_limit_lovelace * 100.0
        return f"{raw:.1f}"

    @rx.var
    def simulation_active(self) -> bool:
        return len(self.simulation_proposal_ids) > 0

    @rx.var
    def show_select_all_button(self) -> bool:
        """アクティブ提案が存在し、かつ未選択のものが残っている場合に True。"""
        active_ids = {
            p["proposal_id"] for p in self.proposals
            if p.get("is_active") == "1" and p.get("proposal_id")
        }
        if not active_ids:
            return False
        return not active_ids.issubset(set(self.simulation_proposal_ids))

    # NCL 枠残り（シミュレーション額も減算して動的に反映）
    @rx.var
    def remaining_lovelace(self) -> int:
        return max(
            self.ncl_limit_lovelace
            - self.ncl_spent_lovelace
            - self.ncl_pending_lovelace
            - self.simulation_lovelace,
            0,
        )

    @rx.var
    def ncl_remaining_ada_display(self) -> str:
        return f"{self.remaining_lovelace // 1_000_000:,}"

    @rx.var
    def ncl_remaining_jpy_display(self) -> str:
        if not self.fiat_ada_jpy:
            return ""
        from cardanoism.backend.price import format_jpy_short
        ada = self.remaining_lovelace / 1_000_000
        return format_jpy_short(ada * self.fiat_ada_jpy)

    @rx.var
    def ncl_remaining_usd_display(self) -> str:
        if not self.fiat_ada_usd:
            return ""
        from cardanoism.backend.price import format_usd_short
        ada = self.remaining_lovelace / 1_000_000
        return format_usd_short(ada * self.fiat_ada_usd)

    # ── ドーナツチャート用 ────────────────────────────────────────────────
    @rx.var
    def ncl_remaining_pct(self) -> float:
        pct = 100.0 - self.ncl_spent_pct - self.ncl_pending_pct - self.simulation_pct
        return max(0.0, min(pct, 100.0))

    @rx.var
    def ncl_remaining_pct_display(self) -> str:
        return f"{self.ncl_remaining_pct:.1f}"

    @rx.var
    def ncl_donut_gradient(self) -> str:
        """CSS conic-gradient で4セグメントの円グラフを描画する背景値を返す。"""
        spent_end   = self.ncl_spent_pct
        pending_end = spent_end + self.ncl_pending_pct
        sim_end     = pending_end + self.simulation_pct
        return (
            f"conic-gradient("
            f"var(--amber-9) 0% {spent_end:.4f}%, "
            f"var(--violet-9) {spent_end:.4f}% {pending_end:.4f}%, "
            f"var(--green-9) {pending_end:.4f}% {sim_end:.4f}%, "
            f"var(--gray-4) {sim_end:.4f}% 100%)"
        )

    def on_load(self):
        self.load = False
        self.error = ""
        try:
            # 0) 法定通貨レート
            rate = get_fiat_rate()
            if rate:
                self.fiat_available = True
                ada_jpy = rate["ada_jpy"]
                ada_usd = rate["ada_usd"]
            else:
                self.fiat_available = False
                ada_jpy = 0.0
                ada_usd = 0.0
            self.fiat_ada_jpy = ada_jpy
            self.fiat_ada_usd = ada_usd
            # シミュレーション選択をリセット
            self.simulation_proposal_ids = []

            # 1) 残高スナップショット
            snap = get_latest_treasury_snapshot()
            if snap:
                self.current_epoch = int(snap["epoch_no"])
                treasury_lovelace = int(snap["treasury"])
                treasury_ada = treasury_lovelace / 1_000_000
                self.balance_ada_display = format_ada(treasury_lovelace, integer=True)
                self.balance_jpy_display, self.balance_usd_display = _fiat_pair(
                    treasury_ada, ada_jpy, ada_usd
                )

            # 2) 現在採用中の NCL
            ncl = get_active_ncl()
            if ncl:
                self.ncl_available = True
                self.ncl_title = str(ncl.get("title") or "")
                self.ncl_proposal_id = str(ncl.get("proposal_id") or "")
                yes_pct = float(ncl.get("drep_yes_pct") or 0)
                self.ncl_drep_yes_pct_display = f"{yes_pct:.1f}"
                self.ncl_period_start = int(ncl["start_epoch"])
                self.ncl_period_end = int(ncl["end_epoch"])
                self.ncl_period_start_display = _format_epoch_jst(self.ncl_period_start)
                end_jst = _epoch_start_jst(self.ncl_period_end + 1) - timedelta(seconds=1)
                self.ncl_period_end_display = f"{end_jst:%Y/%m/%d} ({self.ncl_period_end})"
                ncl_limit_ada = int(ncl["limit_ada"])
                self.ncl_limit_ada_display = f"{ncl_limit_ada:,}"
                self.ncl_limit_lovelace = ncl_limit_ada * 1_000_000
                self.ncl_limit_jpy_display, self.ncl_limit_usd_display = _fiat_pair(
                    ncl_limit_ada, ada_jpy, ada_usd
                )

                # 3) NCL期間内の消化状況
                # 引き出し済み（treasury_withdrawal に実際に記録されたもの）
                spent_lovelace = sum_withdrawals_in_epoch_range(
                    self.ncl_period_start, self.ncl_period_end
                )
                # 施行済み（ガバナンスで enact された TreasuryWithdrawals の合計）
                enacted_lovelace = sum_enacted_withdrawals_in_epoch_range(
                    self.ncl_period_start, self.ncl_period_end
                )
                # 予定 = 施行済み合計 − 実際に引き出された分
                pending_lovelace = max(enacted_lovelace - spent_lovelace, 0)
                self.ncl_spent_lovelace = spent_lovelace
                self.ncl_pending_lovelace = pending_lovelace

                spent_ada = spent_lovelace / 1_000_000
                pending_ada = pending_lovelace / 1_000_000

                self.ncl_spent_ada_display = f"{spent_ada:,.0f}"
                self.ncl_spent_jpy_display, self.ncl_spent_usd_display = _fiat_pair(
                    spent_ada, ada_jpy, ada_usd
                )
                self.ncl_pending_ada_display = f"{pending_ada:,.0f}"
                self.ncl_pending_jpy_display, self.ncl_pending_usd_display = _fiat_pair(
                    pending_ada, ada_jpy, ada_usd
                )

                if ncl_limit_ada > 0:
                    spent_pct = spent_ada / ncl_limit_ada * 100.0
                    pending_pct = pending_ada / ncl_limit_ada * 100.0
                else:
                    spent_pct = 0.0
                    pending_pct = 0.0
                self.ncl_spent_pct = max(0.0, min(spent_pct, 100.0))
                self.ncl_pending_pct = max(0.0, min(pending_pct, 100.0 - self.ncl_spent_pct))
                self.ncl_spent_pct_display = f"{spent_pct:.1f}"
                self.ncl_pending_pct_display = f"{pending_pct:.1f}"
                # 後方互換（済み + 予定）
                self.ncl_progress_pct = max(0.0, min(spent_pct + pending_pct, 100.0))
                self.ncl_progress_pct_display = f"{spent_pct + pending_pct:.1f}"

                # 4) NCL 期間内の TreasuryWithdrawals 提案リスト
                prop_rows = get_treasury_proposals_in_epoch_range(
                    self.ncl_period_start, self.ncl_period_end
                )
                prop_out: list[dict] = []
                for p in prop_rows:
                    wtotal = p.get("withdrawal_total_lovelace") or 0
                    try:
                        w_lovelace = int(wtotal)
                    except (TypeError, ValueError):
                        w_lovelace = 0
                    w_ada = w_lovelace / 1_000_000
                    jpy_d, usd_d = _fiat_pair(w_ada, ada_jpy, ada_usd)
                    enacted = p.get("enacted_epoch")
                    status_str = str(p.get("ga_status") or "active")
                    prop_out.append({
                        "proposal_id": str(p.get("proposal_id") or ""),
                        "title_ja": str(p.get("title_ja") or ""),
                        "title_en": str(p.get("title") or ""),
                        "proposed_epoch_display": str(int(p.get("proposed_epoch") or 0)),
                        "enacted_epoch_display": str(int(enacted)) if enacted is not None else "",
                        "is_enacted": "1" if enacted is not None else "",
                        "is_active": "1" if status_str == "active" else "",
                        "status": status_str,
                        "amount_lovelace": str(w_lovelace),
                        "amount_ada": format_ada(w_lovelace, integer=True) if w_lovelace else "-",
                        "amount_jpy": jpy_d,
                        "amount_usd": usd_d,
                    })
                self.proposals = prop_out
                # アクティブ提案はデフォルトで全てシミュレーション対象にする
                self.simulation_proposal_ids = [
                    p["proposal_id"] for p in prop_out if p.get("is_active") == "1" and p.get("proposal_id")
                ]
            else:
                self.ncl_available = False

            # 4) 引き出し履歴
            rows = get_withdrawals_recent(limit=100)
            out: list[dict] = []
            for r in rows:
                lovelace = int(r["amount_lovelace"])
                ada_v = lovelace / 1_000_000
                jpy_disp, usd_disp = _fiat_pair(ada_v, ada_jpy, ada_usd)
                out.append({
                    "earned_epoch": r["earned_epoch"],
                    "spendable_epoch": r["spendable_epoch"],
                    "amount_ada": format_ada(lovelace),
                    "amount_jpy": jpy_disp,
                    "amount_usd": usd_disp,
                    "stake_address": r["stake_address"],
                    "stake_address_short": _shorten_stake(r["stake_address"]),
                })
            self.withdrawals = out

        except Exception as e:
            logger.exception("TreasuryState.on_load: %s", e)
            self.error = str(e)
        finally:
            self._load_chart()
            self.load = True

    def _load_chart(self) -> None:
        """トレジャリー残高の折れ線グラフ SVG を State に格納する。
        NCL 期間が利用可能なら NCL 開始 〜 現在エポックの範囲を、
        無ければフォールバックで直近 10 エポックを表示する。
        """
        history: list[dict] = []
        try:
            if self.ncl_available and self.ncl_period_start > 0:
                # NCL 開始 〜 現在エポック（NCL end が未来なら end も上限）
                end_ep = self.current_epoch if self.current_epoch > 0 else self.ncl_period_end
                if end_ep > 0:
                    history = get_treasury_history_in_range(
                        self.ncl_period_start, end_ep
                    )
            if not history:
                # フォールバック: 直近 10 エポック
                history = get_treasury_history_recent(n_epochs=10)
        except Exception as e:
            logger.warning("get_treasury_history 失敗: %s", e)
            self.treasury_chart_svg = ""
            self.treasury_chart_epoch_count = 0
            return

        if not history or len(history) < 2:
            self.treasury_chart_svg = ""
            self.treasury_chart_epoch_count = 0
            return

        history = sorted(history, key=lambda r: int(r["epoch_no"]))
        self.treasury_chart_svg = build_treasury_chart_svg(history)
        self.treasury_chart_epoch_count = len(history)

    def set_active_tab(self, tab: str):
        self.active_tab = tab

    def toggle_simulation(self, proposal_id: str):
        """アクティブ提案のシミュレーション選択をトグルする。"""
        if not proposal_id:
            return
        if proposal_id in self.simulation_proposal_ids:
            self.simulation_proposal_ids = [i for i in self.simulation_proposal_ids if i != proposal_id]
        else:
            self.simulation_proposal_ids = self.simulation_proposal_ids + [proposal_id]

    def clear_simulation(self):
        self.simulation_proposal_ids = []

    def select_all_active(self):
        """すべてのアクティブ提案をシミュレーション対象に選択する。"""
        self.simulation_proposal_ids = [
            p["proposal_id"] for p in self.proposals
            if p.get("is_active") == "1" and p.get("proposal_id")
        ]


def _shorten_stake(addr: str) -> str:
    if not addr:
        return ""
    if len(addr) <= 20:
        return addr
    return f"{addr[:10]}...{addr[-6:]}"


# ─── UI パーツ ────────────────────────────────────────────────────────────────


def _fiat_inline(jpy_var, usd_var, color: str = "var(--gray-10)", size: str = "2") -> rx.Component:
    """ADA の後ろに括弧付きで法定通貨を出す（言語連動）。レート未取得時は空。"""
    jpy_part = rx.cond(
        jpy_var != "",
        rx.text("(≈ ", jpy_var, ")", size=size, color=color),
        rx.fragment(),
    )
    usd_part = rx.cond(
        usd_var != "",
        rx.text("(≈ ", usd_var, ")", size=size, color=color),
        rx.fragment(),
    )
    return rx.cond(
        AuthState.language == "en",
        usd_part,
        jpy_part,
    )


def _breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.link(AuthState.t["nav_governance"], href="/governance", size="2", underline="hover", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["gov_subnav_treasury"], size="2", weight="medium"),
        spacing="2",
        align="center",
        width="100%",
        padding_top="15px",
    )


# ─── トレジャリー残高 折れ線グラフ ─────────────────────────────────────────────

def _flow_card() -> rx.Component:
    """直近 N エポックのトレジャリー残高を折れ線グラフで表示する。"""
    head = rx.hstack(
        rx.icon("trending-up", size=16, color="var(--amber-11)"),
        rx.text(AuthState.t["treasury_chart_title"], size="2", weight="bold",
                color="var(--gray-12)"),
        rx.spacer(),
        rx.cond(
            TreasuryState.treasury_chart_epoch_count > 0,
            rx.text(
                TreasuryState.treasury_chart_epoch_count.to_string()
                + " " + AuthState.t["treasury_chart_epoch_unit"],
                size="1", color="var(--gray-9)",
            ),
            rx.fragment(),
        ),
        spacing="2", align="center", width="100%",
    )

    return rx.cond(
        TreasuryState.treasury_chart_svg != "",
        rx.box(
            rx.vstack(
                head,
                rx.box(
                    rx.html(TreasuryState.treasury_chart_svg),
                    width="100%",
                    overflow_x="auto",
                ),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            padding="16px 20px",
            border=f"1px solid {rx.color('gray', 4)}",
            border_radius="12px",
            background="var(--gray-2)",
            width="100%",
        ),
        rx.box(
            rx.hstack(
                rx.icon("info", size=14, color="var(--gray-9)"),
                rx.text(AuthState.t["treasury_chart_no_data"], size="2", color="var(--gray-10)"),
                spacing="2", align="center",
            ),
            padding="12px 16px",
            border=f"1px dashed {rx.color('gray', 5)}",
            border_radius="10px",
            background="var(--gray-2)",
            width="100%",
        ),
    )


def _balance_card() -> rx.Component:
    """残高は1行（折り返しあり）に圧縮し、エポック情報は右端に配置。"""
    return rx.box(
        rx.flex(
            rx.hstack(
                rx.icon("landmark", size=16, color="var(--amber-11)"),
                rx.text(AuthState.t["treasury_balance_title"], size="2", weight="bold"),
                spacing="2", align="center", flex_shrink="0",
            ),
            rx.hstack(
                rx.text(TreasuryState.balance_ada_display, size="6", weight="bold", color="var(--amber-11)"),
                rx.text("ADA", size="2", color="var(--gray-11)"),
                _fiat_inline(TreasuryState.balance_jpy_display, TreasuryState.balance_usd_display, size="2"),
                spacing="2", align="baseline", wrap="wrap",
            ),
            rx.spacer(),
            rx.text(
                AuthState.t["treasury_epoch_label"] + " " + TreasuryState.current_epoch.to_string(),
                size="1", color="var(--gray-10)", flex_shrink="0",
            ),
            wrap="wrap",
            align="center",
            spacing="3",
            width="100%",
        ),
        padding="10px 16px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


def _ncl_swatch(background: str) -> rx.Component:
    return rx.box(
        width="8px", height="8px",
        background=background,
        border_radius="2px",
        flex_shrink="0",
    )


def _ncl_breakdown_row(
    label_key: str,
    swatch: rx.Component,
    ada_var,
    jpy_var,
    usd_var,
    pct_var,
    accent_color: str,
) -> rx.Component:
    """ブレイクダウン1行（凡例 + ラベル(min幅でカラム揃え) + ADA + パーセント + 法定通貨）。"""
    return rx.hstack(
        swatch,
        rx.box(
            rx.text(AuthState.t[label_key], size="1", color="var(--gray-11)", weight="medium"),
            min_width="100px",
            flex_shrink="0",
        ),
        rx.text(ada_var, size="2", weight="bold"),
        rx.text("ADA", size="1", color="var(--gray-10)"),
        rx.text("(" + pct_var + "%)", size="1", color=accent_color, weight="medium"),
        _fiat_inline(jpy_var, usd_var, size="1"),
        spacing="2",
        align="baseline",
        wrap="wrap",
    )


def _ncl_card() -> rx.Component:
    spent_swatch = _ncl_swatch("var(--amber-9)")
    pending_swatch = _ncl_swatch("var(--violet-9)")
    sim_swatch = _ncl_swatch(
        "repeating-linear-gradient(45deg, var(--green-9), var(--green-9) 3px, var(--green-10) 3px, var(--green-10) 6px)"
    )

    return rx.box(
        rx.vstack(
            # ── ヘッダー：タイトル + 採用提案 + 期間 + 説明ツールチップ ──
            rx.flex(
                rx.hstack(
                    rx.icon("gauge", size=16, color="var(--blue-11)"),
                    rx.text(AuthState.t["ncl_title"], size="2", weight="bold"),
                    rx.tooltip(
                        rx.icon("info", size=14, color="var(--gray-9)", style={"cursor": "help"}),
                        content=AuthState.t["ncl_description"],
                    ),
                    spacing="2", align="center", flex_shrink="0",
                ),
                rx.cond(
                    TreasuryState.ncl_proposal_id != "",
                    rx.hstack(
                        rx.icon("file-check-2", size=12, color="var(--green-10)"),
                        rx.link(
                            TreasuryState.ncl_title,
                            href="/governance/" + TreasuryState.ncl_proposal_id,
                            size="1",
                            color_scheme="amber",
                        ),
                        rx.badge(
                            "DRep " + TreasuryState.ncl_drep_yes_pct_display + "%",
                            color_scheme="green",
                            variant="soft",
                            size="1",
                        ),
                        spacing="1", align="center",
                    ),
                    rx.fragment(),
                ),
                rx.spacer(),
                rx.hstack(
                    rx.text(AuthState.t["ncl_period_label"], size="1", color="var(--gray-10)"),
                    rx.text(TreasuryState.ncl_period_start_display, size="1", color="var(--gray-12)"),
                    rx.text("〜", size="1", color="var(--gray-10)"),
                    rx.text(TreasuryState.ncl_period_end_display, size="1", color="var(--gray-12)"),
                    spacing="1", align="center", flex_shrink="0",
                ),
                wrap="wrap",
                align="center",
                spacing="3",
                width="100%",
            ),
            # ── プログレスバー（残りをバー中央に / 上限をバー右端外に表示） ──
            rx.hstack(
                rx.box(
                    rx.hstack(
                        # 引き出し確定
                        rx.box(
                            width=TreasuryState.ncl_pending_pct.to_string() + "%",
                            height="100%",
                            background="linear-gradient(90deg, var(--violet-9), var(--purple-10))",
                            transition="width 0.5s ease",
                            flex_shrink="0",
                        ),
                        # シミュレーション
                        rx.box(
                            width=TreasuryState.simulation_pct.to_string() + "%",
                            height="100%",
                            background="repeating-linear-gradient(45deg, var(--green-9), var(--green-9) 6px, var(--green-10) 6px, var(--green-10) 12px)",
                            transition="width 0.5s ease",
                            flex_shrink="0",
                        ),
                        # 残り（テキスト入りセグメント）
                        rx.center(
                            rx.hstack(
                                rx.text(
                                    AuthState.t["ncl_remaining_label"],
                                    size="1", color="var(--gray-11)", weight="medium",
                                ),
                                rx.text(
                                    TreasuryState.ncl_remaining_ada_display,
                                    size="2", weight="bold", color="var(--gray-12)",
                                ),
                                rx.text("ADA", size="1", color="var(--gray-11)"),
                                rx.text(
                                    "(" + TreasuryState.ncl_remaining_pct_display + "%)",
                                    size="1", color="var(--gray-10)",
                                ),
                                spacing="1", align="baseline",
                                white_space="nowrap",
                            ),
                            width=TreasuryState.ncl_remaining_pct.to_string() + "%",
                            height="100%",
                            background="var(--gray-3)",
                            transition="width 0.5s ease",
                            overflow="hidden",
                            flex_shrink="0",
                        ),
                        spacing="0",
                        width="100%",
                        height="100%",
                        align="stretch",
                    ),
                    width="100%",
                    height="30px",
                    background="var(--gray-3)",
                    border_radius="9999px",
                    overflow="hidden",
                    border=f"1px solid {rx.color('gray', 5)}",
                    flex="1",
                    min_width="0",
                ),
                # 上限（バー右端の外側に配置）
                rx.hstack(
                    rx.text("/", size="4", color="var(--gray-9)"),
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                AuthState.t["ncl_limit_label"],
                                size="1", color="var(--gray-11)", weight="medium",
                            ),
                            rx.text(
                                TreasuryState.ncl_limit_ada_display,
                                size="3", weight="bold", color="var(--amber-11)",
                            ),
                            rx.text("ADA", size="1", color="var(--amber-11)"),
                            spacing="1", align="baseline",
                        ),
                        _fiat_inline(
                            TreasuryState.ncl_limit_jpy_display,
                            TreasuryState.ncl_limit_usd_display,
                            size="1",
                        ),
                        spacing="0", align="start",
                    ),
                    spacing="2", align="center", flex_shrink="0",
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            # ── 内訳（縦リスト：確定 / シミュレーション） ──
            rx.vstack(
                _ncl_breakdown_row(
                    "ncl_pending_label", pending_swatch,
                    TreasuryState.ncl_pending_ada_display,
                    TreasuryState.ncl_pending_jpy_display,
                    TreasuryState.ncl_pending_usd_display,
                    TreasuryState.ncl_pending_pct_display,
                    "var(--violet-11)",
                ),
                rx.cond(
                    TreasuryState.simulation_active,
                    _ncl_breakdown_row(
                        "ncl_simulation_label", sim_swatch,
                        TreasuryState.simulation_ada_display,
                        TreasuryState.simulation_jpy_display,
                        TreasuryState.simulation_usd_display,
                        TreasuryState.simulation_pct_display,
                        "var(--green-11)",
                    ),
                    rx.fragment(),
                ),
                spacing="1",
                align="start",
                width="100%",
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        padding="12px 16px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


def _withdrawal_row(row: Dict[str, Any]) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row["earned_epoch"].to_string(), size="2")),
        rx.table.cell(rx.text(row["spendable_epoch"].to_string(), size="2")),
        rx.table.cell(
            rx.vstack(
                rx.hstack(
                    rx.text(row["amount_ada"], size="2", weight="medium"),
                    rx.text("ADA", size="1", color="var(--gray-10)"),
                    spacing="1", align="baseline",
                ),
                _fiat_inline(row["amount_jpy"], row["amount_usd"], size="1"),
                spacing="0", align="start",
            )
        ),
        rx.table.cell(
            rx.code(row["stake_address_short"], size="1"),
        ),
    )


_STATUS_COLORS = {
    "active":   "green",
    "ratified": "blue",
    "enacted":  "violet",
    "dropped":  "gray",
    "expired":  "gray",
}


def _proposal_row(p) -> rx.Component:
    """1件の TreasuryWithdrawals 提案カード。active 提案にはシミュレーション用チェックボックス付き。"""
    status_badge = rx.match(
        p["status"],
        ("active",   rx.badge(AuthState.t["gov_status_active"],   color_scheme="green",  variant="soft")),
        ("ratified", rx.badge(AuthState.t["gov_status_ratified"], color_scheme="blue",   variant="soft")),
        ("enacted",  rx.badge(AuthState.t["gov_status_enacted"],  color_scheme="violet", variant="soft")),
        ("dropped",  rx.badge(AuthState.t["gov_status_dropped"],  color_scheme="gray",   variant="soft")),
        ("expired",  rx.badge(AuthState.t["gov_status_expired"],  color_scheme="gray",   variant="soft")),
        rx.badge(p["status"], variant="soft"),
    )
    title_display = rx.cond(
        AuthState.language == "en",
        rx.cond(p["title_en"] != "", p["title_en"], p["title_ja"]),
        rx.cond(p["title_ja"] != "", p["title_ja"], p["title_en"]),
    )

    body = rx.link(
        rx.vstack(
            rx.hstack(
                status_badge,
                rx.text(
                    AuthState.t["ncl_proposal_proposed_label"] + " " + p["proposed_epoch_display"],
                    size="1", color="var(--gray-10)",
                ),
                rx.cond(
                    p["is_enacted"] != "",
                    rx.text(
                        AuthState.t["ncl_proposal_enacted_label"] + " " + p["enacted_epoch_display"],
                        size="1", color="var(--violet-11)",
                    ),
                    rx.fragment(),
                ),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.text(title_display, size="3", weight="medium", color="var(--gray-12)"),
            rx.hstack(
                rx.text(p["amount_ada"], size="2", weight="bold", color="var(--amber-11)"),
                rx.text("ADA", size="1", color="var(--gray-10)"),
                _fiat_inline(p["amount_jpy"], p["amount_usd"], size="1"),
                spacing="2", align="baseline", wrap="wrap",
            ),
            spacing="2", align="start", width="100%",
            flex="1",
            min_width="0",
        ),
        href="/governance/" + p["proposal_id"],
        underline="none",
        color="inherit",
        width="100%",
    )

    # active 提案には左端にチェックボックス、それ以外はスペーサー
    left_slot = rx.cond(
        p["is_active"] != "",
        rx.box(
            rx.checkbox(
                checked=TreasuryState.simulation_proposal_ids.contains(p["proposal_id"]),
                on_change=TreasuryState.toggle_simulation(p["proposal_id"]),
                size="2",
                color_scheme="green",
            ),
            padding_top="4px",
            flex_shrink="0",
        ),
        rx.box(width="0px", flex_shrink="0"),
    )

    return rx.box(
        rx.hstack(
            left_slot,
            body,
            spacing="3",
            align="start",
            width="100%",
        ),
        padding="14px 16px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="10px",
        background="var(--gray-2)",
        width="100%",
        _hover={"background": "var(--gray-3)"},
        transition="background 0.15s",
    )


def _proposals_tab_content() -> rx.Component:
    return rx.cond(
        TreasuryState.proposals,
        rx.vstack(
            rx.hstack(
                rx.icon("flask-conical", size=16, color="var(--green-11)"),
                rx.text(AuthState.t["ncl_simulation_hint"], size="1", color="var(--gray-10)"),
                rx.spacer(),
                rx.cond(
                    TreasuryState.show_select_all_button,
                    rx.button(
                        rx.icon("check-check", size=14),
                        AuthState.t["ncl_simulation_select_all"],
                        on_click=TreasuryState.select_all_active,
                        variant="soft",
                        color_scheme="green",
                        size="1",
                        cursor="pointer",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    TreasuryState.simulation_active,
                    rx.button(
                        AuthState.t["ncl_simulation_clear"],
                        on_click=TreasuryState.clear_simulation,
                        variant="soft",
                        color_scheme="gray",
                        size="1",
                        cursor="pointer",
                    ),
                    rx.fragment(),
                ),
                spacing="2", align="center", width="100%", wrap="wrap",
            ),
            rx.foreach(
                TreasuryState.proposals.to(list[dict[str, str]]),
                _proposal_row,
            ),
            spacing="2", width="100%",
        ),
        rx.callout(
            AuthState.t["ncl_proposals_empty"],
            icon="info",
            color_scheme="gray",
        ),
    )


def _withdrawals_table() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("list", size=18, color="var(--gray-11)"),
                rx.text(AuthState.t["treasury_history_title"], size="3", weight="bold"),
                spacing="2", align="center",
            ),
            rx.cond(
                TreasuryState.withdrawals,
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell(AuthState.t["treasury_col_earned_epoch"]),
                                rx.table.column_header_cell(AuthState.t["treasury_col_spendable_epoch"]),
                                rx.table.column_header_cell(AuthState.t["treasury_col_amount"]),
                                rx.table.column_header_cell(AuthState.t["treasury_col_stake_addr"]),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(TreasuryState.withdrawals, _withdrawal_row),
                        ),
                        variant="surface",
                        size="2",
                    ),
                    width="100%",
                    overflow_x="auto",
                ),
                rx.callout(
                    AuthState.t["treasury_history_empty"],
                    icon="info",
                    color_scheme="gray",
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


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/governance/treasury",
    title="トレジャリー | ガバナンス | Cardanoism",
    on_load=TreasuryState.on_load,
)
def governance_treasury_page() -> rx.Component:
    return rx.cond(
        TreasuryState.load,
        rx.box(
            login_modal(),
            rx.vstack(
                _breadcrumb(),
                governance_subnav("treasury"),
                rx.cond(
                    TreasuryState.error != "",
                    rx.callout(
                        AuthState.t["treasury_load_error"],
                        icon="triangle-alert",
                        color_scheme="red",
                    ),
                    rx.vstack(
                        _balance_card(),
                        _flow_card(),
                        rx.cond(
                            TreasuryState.ncl_available,
                            _ncl_card(),
                            rx.callout(
                                AuthState.t["ncl_not_available"],
                                icon="info",
                                color_scheme="gray",
                            ),
                        ),
                        # 「引き出し履歴」タブ非表示中。proposals だけなのでタブ撤去
                        rx.box(
                            _proposals_tab_content(),
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
