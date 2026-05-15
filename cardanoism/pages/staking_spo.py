"""
staking_spo.py
ステーキング > SPO 一覧（/staking/spo）

データソースは pools テーブル（notify_worker.py --event pool_sync で同期）。
"""
from __future__ import annotations

import json
import logging
import random
from typing import Any

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.wallet_state import WalletState
from cardanoism.backend.fiat_db import get_fiat_rate
from cardanoism.backend.koios import get_totals
from cardanoism.backend.pool_db import get_pools, count_pools
from cardanoism.backend.price import format_ada, format_ada_short_ja, format_ada_short_en
from cardanoism.components.breadcrumb import breadcrumb
from cardanoism.components.staking_nav import staking_subnav
from cardanoism.components.delegation_dialog import delegation_dialog

# Cardano プロトコル定数（staking.py と同期）
MAX_SUPPLY_LOVELACE = 45_000_000_000 * 1_000_000
OPTIMAL_POOL_COUNT_K = 500


# リレー稼働状況バッジ用のパルスアニメーション（緑のドットを波紋風に光らせる）
SPO_CSS = """
<style>
@keyframes cdn_relay_pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(34,197,94,0.55);
    transform: scale(1);
  }
  70% {
    box-shadow: 0 0 0 7px rgba(34,197,94,0);
    transform: scale(1);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(34,197,94,0);
    transform: scale(1);
  }
}
</style>
"""

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 30


# ─── State ────────────────────────────────────────────────────────────────────


def format_pool_card_data(
    r: dict,
    *,
    saturation_point_lovelace: int = 0,
    rank: int = 0,
) -> dict[str, str]:
    """pools テーブルの 1 レコードを SPO カード描画用の文字列 dict に整形する。
    /staking/spo の SPO 一覧と /staking ダッシュボードの委任先カードで共有する。
    """
    pool_id = str(r.get("pool_id_bech32") or "")
    if len(pool_id) > 22:
        pool_id_short = f"{pool_id[:10]}...{pool_id[-8:]}"
    else:
        pool_id_short = pool_id

    live_stake = int(r.get("live_stake") or 0)
    pledge = int(r.get("live_pledge") or 0)
    fixed_cost = int(r.get("fixed_cost") or 0)
    stake_ada_int = live_stake // 1_000_000
    pledge_ada_int = pledge // 1_000_000
    margin_raw = r.get("margin")
    margin_pct = float(margin_raw) * 100.0 if margin_raw is not None else 0.0

    if saturation_point_lovelace > 0 and live_stake > 0:
        sat_pct = live_stake / saturation_point_lovelace * 100.0
    else:
        sat_pct = 0.0
    sat_bar = max(0.0, min(100.0, sat_pct))

    status = str(r.get("pool_status") or "")
    retiring_epoch = r.get("retiring_epoch")
    # 次エポックでの手数料変更予告 (listener が cert 検知時に書込む pending_effective_epoch を見る)
    pending_effective_epoch = r.get("pending_effective_epoch")
    has_pending_fee_change = pending_effective_epoch is not None
    relay_alive_raw = r.get("relay_alive")
    if relay_alive_raw is None:
        relay_state = "unknown"
    elif int(relay_alive_raw) == 1:
        relay_state = "alive"
    else:
        relay_state = "dead"

    history_raw = r.get("block_history_5ep")
    history_counts: list[int] = []
    if history_raw:
        try:
            parsed = json.loads(history_raw) if isinstance(history_raw, str) else history_raw
            if isinstance(parsed, list):
                history_counts = [int(x) for x in parsed[:5]]
        except (TypeError, ValueError, json.JSONDecodeError):
            history_counts = []
    while len(history_counts) < 5:
        history_counts.append(0)
    history_total = sum(history_counts)

    # APY (直近 7 エポックの epoch_ros 配列を平均、pool_block_history_sync で取得)
    apy_raw = r.get("apy_history_7ep")
    apy_str = "—"
    if apy_raw:
        try:
            apy_arr = json.loads(apy_raw) if isinstance(apy_raw, str) else apy_raw
            if isinstance(apy_arr, list) and apy_arr:
                values = [float(x) for x in apy_arr if x is not None]
                if values:
                    apy_str = f"{sum(values) / len(values):.2f}"
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    tw = str(r.get("twitter_handle") or "").strip()
    tg = str(r.get("telegram_handle") or "").strip()
    yt = str(r.get("youtube_handle") or "").strip()
    gh = str(r.get("github_handle") or "").strip()
    twitter_url  = tw  if tw.startswith(("http://", "https://"))  else (f"https://twitter.com/{tw}"   if tw else "")
    telegram_url = tg  if tg.startswith(("http://", "https://"))  else (f"https://t.me/{tg}"          if tg else "")
    youtube_url  = yt  if yt.startswith(("http://", "https://"))  else (f"https://youtube.com/{yt}"   if yt else "")
    github_url   = gh  if gh.startswith(("http://", "https://"))  else (f"https://github.com/{gh}"    if gh else "")

    return {
        "rank":            str(rank),
        "pool_id":         pool_id,
        "pool_id_short":   pool_id_short,
        "ticker":          str(r.get("ticker") or ""),
        "pool_name":       str(r.get("pool_name") or ""),
        "icon_url":        str(r.get("pool_icon_url") or ""),
        "homepage":        str(r.get("homepage") or ""),
        "about":           str(r.get("extended_about") or "")[:280],
        "twitter_url":     twitter_url,
        "telegram_url":    telegram_url,
        "youtube_url":     youtube_url,
        "github_url":      github_url,
        "stake_ada":       format_ada(live_stake, integer=True) if live_stake else "0",
        "pledge_ada":      format_ada(pledge, integer=True) if pledge else "0",
        "stake_ada_ja":    format_ada_short_ja(stake_ada_int),
        "stake_ada_en":    format_ada_short_en(stake_ada_int),
        "pledge_ada_ja":   format_ada_short_ja(pledge_ada_int),
        "pledge_ada_en":   format_ada_short_en(pledge_ada_int),
        "fixed_cost_ada":  format_ada(fixed_cost, integer=True) if fixed_cost else "0",
        "margin_pct":      f"{margin_pct:.2f}",
        "saturation_pct":  f"{sat_pct:.1f}",
        "saturation_bar":  f"{sat_bar:.1f}",
        "is_saturated":    "1" if sat_pct >= 100.0 else ("warn" if sat_pct >= 80.0 else ""),
        "delegators":      str(int(r.get("live_delegators") or 0)),
        "block_count":     str(int(r.get("block_count") or 0)),
        "status":          status,
        "is_retiring":     "1" if status == "retiring" else "",
        "retiring_epoch":  str(retiring_epoch) if retiring_epoch is not None else "",
        "has_pending_fee_change": "1" if has_pending_fee_change else "",
        "pending_effective_epoch": str(pending_effective_epoch) if pending_effective_epoch is not None else "",
        "relay_state":     relay_state,
        "history_total":   str(history_total),
        "apy_avg":         apy_str,
    }


class StakingSPOState(rx.State):
    load: bool = False
    error: str = ""

    inputed_value: str = ""
    search_query: str = ""
    sort: str = "random"
    only_active: bool = True
    # ランダム並びはセッション内で固定 seed を使うことでページングを安定させる
    random_seed: int = 0
    # 1プール飽和点 (lovelace)。on_load で /totals から確定し、_fetch で再利用。
    saturation_point_lovelace: int = 0

    current_page: int = 1
    total_pages: int = 0
    total_items: int = 0
    start_page: int = 1
    end_page: int = 1
    middle_page: list[int] = []

    pools: list[dict[str, str]] = []

    def _fetch(self):
        offset = (self.current_page - 1) * ITEMS_PER_PAGE
        try:
            rows = get_pools(
                search=self.search_query,
                only_active=self.only_active,
                sort=self.sort,
                limit=ITEMS_PER_PAGE,
                offset=offset,
                random_seed=self.random_seed,
            )
            total = count_pools(search=self.search_query, only_active=self.only_active)

            out: list[dict[str, str]] = []
            for idx, r in enumerate(rows):
                out.append(format_pool_card_data(
                    r,
                    saturation_point_lovelace=self.saturation_point_lovelace,
                    rank=offset + idx + 1,
                ))
            self.pools = out
            self.total_items = total
            self.total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            self.start_page = max(1, self.current_page - 3)
            self.end_page   = min(self.total_pages, self.current_page + 3)
            self.middle_page = list(range(self.start_page, self.end_page + 1))
        except Exception as e:
            logger.exception("StakingSPOState._fetch: %s", e)
            self.error = str(e)

    def on_load(self):
        self.load = False
        self.error = ""
        self.inputed_value = ""
        self.search_query = ""
        self.sort = "random"
        self.only_active = True
        self.current_page = 1
        # 1〜2,147,483,647 の整数 seed をセッション開始時に確定（MariaDB の RAND() に渡す）
        self.random_seed = random.randint(1, 2_147_483_647)
        # 飽和点 (= ソフトキャップ / 500) を /totals から確定。失敗時は 0 のまま。
        try:
            totals = get_totals() or {}
            reserves = int(totals.get("reserves") or 0)
            if reserves > 0:
                soft_cap = MAX_SUPPLY_LOVELACE - reserves
                self.saturation_point_lovelace = soft_cap // OPTIMAL_POOL_COUNT_K
        except Exception as e:
            logger.warning("get_totals failed: %s", e)
        self._fetch()
        self.load = True

    def reshuffle(self):
        """ランダム表示の seed を引き直す。"""
        self.sort = "random"
        self.random_seed = random.randint(1, 2_147_483_647)
        self.current_page = 1
        self._fetch()

    def set_input(self, v: str):
        self.inputed_value = v
        self.search_query = v
        self.current_page = 1
        self._fetch()

    def set_sort(self, v: str):
        self.sort = v
        self.current_page = 1
        self._fetch()

    def toggle_only_active(self, v: bool):
        self.only_active = bool(v)
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


# ─── UI パーツ ────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return breadcrumb([("nav_staking", "/staking")], "staking_subnav_spo")


def _saturation_bar(p) -> rx.Component:
    fill_color = rx.match(
        p["is_saturated"],
        ("1", "var(--red-9)"),
        ("warn", "var(--amber-9)"),
        "var(--green-9)",
    )
    return rx.box(
        rx.box(
            width=p["saturation_bar"] + "%",
            height="100%",
            background=fill_color,
            border_radius="999px",
            transition="width 0.3s",
        ),
        width="100%",
        height="6px",
        background="var(--gray-4)",
        border_radius="999px",
        overflow="hidden",
    )


def _relay_status(state) -> rx.Component:
    """リレー稼働状況のピル状バッジ。alive=緑+波紋アニメ / dead=赤 / unknown=非表示。
    pool_id_inline (size="1") と並ぶインライン要素なのでコンパクトに。
    """
    return rx.match(
        state,
        ("alive", rx.hstack(
            rx.box(
                width="7px",
                height="7px",
                border_radius="999px",
                background="var(--green-10)",
                flex_shrink="0",
                style={"animation": "cdn_relay_pulse 1.6s ease-in-out infinite"},
            ),
            rx.text(
                AuthState.t["staking_badge_alive"],
                color="var(--green-12)",
                style={
                    "fontSize": "11px",
                    "fontWeight": "700",
                    "lineHeight": "1.0",
                    "whiteSpace": "nowrap",
                },
            ),
            spacing="1",
            align="center",
            padding="3px 8px 3px 7px",
            border_radius="999px",
            background="var(--green-3)",
            border="1px solid var(--green-7)",
            style={
                "display": "inline-flex",
                "flexShrink": "0",
            },
        )),
        ("dead", rx.hstack(
            rx.box(
                width="7px",
                height="7px",
                border_radius="999px",
                background="var(--red-10)",
                flex_shrink="0",
            ),
            rx.text(
                AuthState.t["staking_badge_dead"],
                color="var(--red-12)",
                style={
                    "fontSize": "11px",
                    "fontWeight": "700",
                    "lineHeight": "1.0",
                    "whiteSpace": "nowrap",
                },
            ),
            spacing="1",
            align="center",
            padding="3px 8px 3px 7px",
            border_radius="999px",
            background="var(--red-3)",
            border="1px solid var(--red-7)",
            style={
                "display": "inline-flex",
                "flexShrink": "0",
            },
        )),
        rx.fragment(),
    )


def _social_link(url, icon_node) -> rx.Component:
    """ソーシャルアイコンの外部リンク。url が空なら描画しない。"""
    return rx.cond(
        url != "",
        rx.link(
            rx.box(
                icon_node,
                width="26px",
                height="26px",
                display="flex",
                align_items="center",
                justify_content="center",
                border_radius="999px",
                background="var(--gray-3)",
                style={"transition": "background 0.15s, color 0.15s"},
                _hover={"background": "var(--amber-4)"},
            ),
            href=url,
            is_external=True,
            underline="none",
        ),
        rx.fragment(),
    )


def _pool_card(p) -> rx.Component:
    # アイコンが取れていればそれを表示、なければ # ランク表示にフォールバック
    icon_or_rank = rx.cond(
        p["icon_url"] != "",
        rx.image(
            src=p["icon_url"],
            width="48px",
            height="48px",
            border_radius="10px",
            style={"objectFit": "cover"},
            flex_shrink="0",
            custom_attrs={"referrerpolicy": "no-referrer", "loading": "lazy"},
        ),
        rx.center(
            rx.text("#", p["rank"], size="3", weight="bold", color="var(--gray-11)"),
            min_width="48px",
            height="48px",
            border_radius="10px",
            background="var(--gray-4)",
            flex_shrink="0",
        ),
    )
    name = rx.hstack(
        rx.cond(
            p["ticker"] != "",
            rx.badge(p["ticker"], variant="solid", color_scheme="amber", radius="full"),
            rx.fragment(),
        ),
        rx.cond(
            p["pool_name"] != "",
            rx.text(p["pool_name"], size="3", weight="bold", color="var(--gray-12)"),
            rx.text(AuthState.t["staking_no_name"], size="3", weight="bold", color="var(--gray-10)"),
        ),
        # ホームページ + ソーシャルアイコン群（プール名の右隣に並べる）
        _social_link(
            p["homepage"],
            rx.icon("house", size=14, color="var(--amber-11)"),
        ),
        _social_link(p["twitter_url"],  rx.icon("twitter", size=14, color="#1DA1F2")),
        _social_link(p["telegram_url"], rx.icon("send",    size=14, color="#2AABEE")),
        _social_link(p["youtube_url"],  rx.icon("youtube", size=14, color="#FF0000")),
        _social_link(p["github_url"],   rx.icon("github",  size=14, color="var(--gray-12)")),
        rx.cond(
            p["is_retiring"] != "",
            rx.badge(AuthState.t["staking_badge_retiring"], color_scheme="red", variant="soft"),
            rx.fragment(),
        ),
        rx.cond(
            p["has_pending_fee_change"] != "",
            rx.badge(AuthState.t["staking_badge_pending_fee"], color_scheme="amber", variant="soft"),
            rx.fragment(),
        ),
        spacing="2", align="center", wrap="wrap",
    )
    pool_id_inline = rx.hstack(
        rx.text(p["pool_id_short"], size="1", color="var(--gray-10)",
                style={"fontFamily": "ui-monospace, monospace", "wordBreak": "break-all"}),
        rx.el.button(
            rx.icon("copy", size=12),
            on_click=[
                rx.set_clipboard(p["pool_id"]),
                rx.toast(
                    AuthState.t["staking_pool_id_copied"],
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
                "border": "none",
                "background": "transparent",
                "color": "var(--gray-10)",
                "cursor": "pointer",
                "padding": "0 4px",
            },
            _hover={"color": "var(--gray-12)"},
        ),
        # コピーボタンの右隣にリレー稼働状況バッジ
        _relay_status(p["relay_state"]),
        spacing="2", align="center", wrap="wrap",
    )

    sat_label = rx.hstack(
        rx.text(p["saturation_pct"], "%", size="2", weight="bold", color="var(--gray-12)"),
        rx.cond(
            p["is_saturated"] == "1",
            rx.badge(AuthState.t["staking_badge_saturated"], color_scheme="red", variant="soft", size="1"),
            rx.cond(
                p["is_saturated"] == "warn",
                rx.badge(AuthState.t["staking_badge_warning"], color_scheme="amber", variant="soft", size="1"),
                rx.fragment(),
            ),
        ),
        spacing="2", align="center",
    )

    # 委任状態の判定:
    #   - 接続中ウォレットの現在委任先 == このカードのプール: 「委任中」 (amber バッジ、クリック不可)
    #   - 接続中: 「委任する」 (amber アクティブボタン)
    #   - 未接続: 「委任する」 (gray, disabled)
    is_currently_delegated = (
        WalletState.connected
        & (WalletState.current_delegated_pool_id == p["pool_id"])
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
        on_click=WalletState.request_delegate_to_pool(p["pool_id"]),
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
    delegate_disabled = rx.hstack(
        rx.icon("zap", size=14, color="var(--gray-9)"),
        rx.text(
            AuthState.t["delegate_btn"],
            color="var(--gray-10)",
            style={
                "fontSize": "13px",
                "fontWeight": "600",
                "lineHeight": "1.0",
                "whiteSpace": "nowrap",
            },
        ),
        spacing="2",
        align="center",
        padding="8px 16px",
        border_radius="999px",
        background="var(--gray-3)",
        border="1.5px solid var(--gray-6)",
        cursor="not-allowed",
        style={
            "opacity": "0.7",
            "display": "inline-flex",
            "flexShrink": "0",
        },
    )
    delegate_button = rx.cond(
        is_currently_delegated,
        delegated_badge,
        rx.cond(
            WalletState.connected,
            delegate_active,
            delegate_disabled,
        ),
    )

    metrics = rx.box(
        _ada_metric_with_tooltip(
            AuthState.t["staking_metric_stake"],
            p["stake_ada_ja"], p["stake_ada_en"], p["stake_ada"],
            emphasis=True,
        ),
        _ada_metric_with_tooltip(
            AuthState.t["staking_metric_pledge"],
            p["pledge_ada_ja"], p["pledge_ada_en"], p["pledge_ada"],
        ),
        _metric(AuthState.t["staking_metric_margin"], p["margin_pct"], "%"),
        _metric(AuthState.t["staking_metric_fixed_cost"], p["fixed_cost_ada"], "ADA"),
        _metric(AuthState.t["staking_metric_delegators"], p["delegators"], ""),
        _metric(AuthState.t["staking_metric_blocks"], p["block_count"], ""),
        _metric(AuthState.t["staking_metric_recent5ep"], p["history_total"], "", emphasis=True),
        _metric(AuthState.t["staking_metric_apy"], p["apy_avg"], "%", emphasis=True),
        # 委任ボタン (9 番目のセル)
        rx.box(
            delegate_button,
            style={
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "flex-start",
                "minWidth": "0",
                "minHeight": "28px",
            },
        ),
        width="100%",
        style={
            "display": "grid",
            "gap": "12px",
            "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
            "@media (min-width: 1024px)": {
                "gridTemplateColumns": "repeat(9, minmax(0, 1fr))",
            },
        },
    )

    saturation_row = rx.hstack(
        rx.text(AuthState.t["staking_metric_saturation"], size="1", color="var(--gray-10)", weight="medium"),
        rx.box(_saturation_bar(p), flex="1"),
        rx.box(sat_label, flex_shrink="0", min_width="100px"),
        spacing="3", align="center", width="100%",
    )

    about_row = rx.cond(
        p["about"] != "",
        rx.text(
            p["about"],
            size="1",
            color="var(--gray-10)",
            line_height="1.55",
            style={
                "display": "-webkit-box",
                "WebkitLineClamp": "2",
                "WebkitBoxOrient": "vertical",
                "overflow": "hidden",
            },
        ),
        rx.fragment(),
    )

    # お気に入りトグル (heart アイコン、DRep / catalyst / GA と同パターン)
    fav_button = rx.box(
        rx.cond(
            AuthState.pool_favorite_ids.contains(p["pool_id"]),
            rx.icon("heart", size=22, color="var(--red-9)", style={"fill": "var(--red-9)"}),
            rx.icon("heart", size=22, color="var(--gray-8)"),
        ),
        on_click=AuthState.toggle_pool_favorite(p["pool_id"]),
        cursor="pointer",
        padding="6px",
        flex_shrink="0",
    )

    # ── ヘッダー: プール名 / ID / 概要 (明るい白ベース) ─────
    header_section = rx.box(
        rx.vstack(
            rx.hstack(
                icon_or_rank,
                rx.vstack(
                    name,
                    pool_id_inline,
                    spacing="1", align_items="start", flex="1", min_width="0",
                ),
                fav_button,
                spacing="3", align="center", width="100%",
            ),
            about_row,
            spacing="3", align_items="stretch", width="100%",
        ),
        padding="16px 18px 14px 18px",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.05)"),
        width="100%",
    )

    # ── ボディ: 飽和率 + メトリクス (淡いグレーで読みやすさ重視) ──
    body_section = rx.box(
        rx.vstack(
            saturation_row,
            metrics,
            spacing="3", align_items="stretch", width="100%",
        ),
        padding="14px 18px 16px 18px",
        background=rx.color_mode_cond("var(--gray-2)", "rgba(255,255,255,0.015)"),
        border_top=f"1px solid {rx.color('gray', 5)}",
        width="100%",
    )

    return rx.box(
        header_section,
        body_section,
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        overflow="hidden",  # 角の丸みで内側の背景を綺麗にクリップ
        width="100%",
        # デフォルトでも軽いシャドウを付けてカードのエッジを浮かせる
        box_shadow=rx.color_mode_cond(
            "0 1px 3px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04)",
            "0 1px 3px rgba(0,0,0,0.35), 0 1px 2px rgba(0,0,0,0.20)",
        ),
        _hover={
            "border_color": rx.color("amber", 8),
            "transform": "translateY(-1px)",
            "box_shadow": rx.color_mode_cond(
                "0 8px 22px -6px rgba(15,23,42,0.16), 0 4px 10px -4px rgba(245,158,11,0.18)",
                "0 8px 22px -6px rgba(0,0,0,0.55), 0 4px 10px -4px rgba(245,158,11,0.22)",
            ),
        },
        style={"transition": "border-color 0.15s, box-shadow 0.18s, transform 0.18s"},
    )


def _ada_metric_with_tooltip(label, value_ja, value_en, full_value, emphasis: bool = False) -> rx.Component:
    """ADA メトリクスを言語別の短縮表記で表示し、マウスホバー時にフル数値の tooltip を出す。"""
    value_color = "var(--amber-11)" if emphasis else "var(--gray-12)"
    display_value = rx.cond(AuthState.language == "en", value_en, value_ja)
    return rx.tooltip(
        rx.box(
            rx.text(label, size="1", color="var(--gray-10)", weight="medium"),
            rx.hstack(
                rx.text(display_value, size="3", weight="bold", color=value_color,
                        style={"wordBreak": "break-all"}),
                rx.text("ADA", size="1", color="var(--gray-10)"),
                spacing="1", align="baseline",
            ),
            style={"display": "flex", "flexDirection": "column",
                   "alignItems": "start", "minWidth": "0",
                   "cursor": "help"},
        ),
        content=full_value + " ADA",
    )


def _metric(label, value, unit: str, emphasis: bool = False) -> rx.Component:
    value_color = "var(--amber-11)" if emphasis else "var(--gray-12)"
    return rx.vstack(
        rx.text(label, size="1", color="var(--gray-10)", weight="medium"),
        rx.hstack(
            rx.text(value, size="3", weight="bold", color=value_color, style={"wordBreak": "break-all"}),
            rx.cond(
                unit != "",
                rx.text(unit, size="1", color="var(--gray-10)"),
                rx.fragment(),
            ),
            spacing="1", align="baseline",
        ),
        spacing="0", align_items="start",
        min_width="0",
    )


def _filter_bar() -> rx.Component:
    return rx.hstack(
        rx.input(
            rx.cond(
                StakingSPOState.inputed_value != "",
                rx.input.slot(
                    rx.icon(
                        "x",
                        size=16,
                        cursor="pointer",
                        on_click=StakingSPOState.set_input(""),
                        style={"_hover": {"color": "var(--gray-12)"}},
                    ),
                    side="right",
                    color="var(--gray-9)",
                ),
                rx.fragment(),
            ),
            placeholder=AuthState.t["staking_search_placeholder"],
            size="3",
            max_length=100,
            value=StakingSPOState.inputed_value,
            on_change=lambda v: StakingSPOState.set_input(v).debounce(400),
            flex="1",
            min_width="0",
        ),
        rx.cond(
            StakingSPOState.sort == "random",
            # シャッフルボタンはモバイルでは非表示
            rx.tablet_and_desktop(
                rx.el.button(
                    rx.icon("shuffle", size=14, color="var(--gray-12)"),
                    rx.text(
                        AuthState.t["staking_reshuffle"],
                        color="var(--gray-12)",
                        style={
                            "fontSize": "13px",
                            "fontWeight": "600",
                            "letterSpacing": "0.02em",
                        },
                    ),
                    on_click=StakingSPOState.reshuffle,
                    cursor="pointer",
                    style={
                        "display": "inline-flex",
                        "alignItems": "center",
                        "gap": "8px",
                        "padding": "9px 18px",
                        "borderRadius": "999px",
                        "background": "transparent",
                        "border": "1px solid var(--gray-6)",
                        "transition": "background 0.15s ease, border-color 0.15s ease, transform 0.15s ease",
                        "lineHeight": "1.0",
                        "flexShrink": "0",
                    },
                    _hover={
                        "background": rx.color_mode_cond("var(--gray-3)", "rgba(255,255,255,0.04)"),
                        "border_color": "var(--gray-8)",
                        "transform": "translateY(-1px)",
                    },
                ),
            ),
            rx.fragment(),
        ),
        rx.select.root(
            rx.select.trigger(),
            rx.select.content(
                rx.select.item(AuthState.t["staking_sort_random"],          value="random"),
                rx.select.item(AuthState.t["staking_sort_stake_desc"],      value="stake_desc"),
                rx.select.item(AuthState.t["staking_sort_pledge_desc"],     value="pledge_desc"),
                rx.select.item(AuthState.t["staking_sort_saturation_desc"], value="saturation_desc"),
                rx.select.item(AuthState.t["staking_sort_saturation_asc"],  value="saturation_asc"),
                rx.select.item(AuthState.t["staking_sort_fee_asc"],         value="fee_asc"),
                rx.select.item(AuthState.t["staking_sort_blocks_desc"],     value="blocks_desc"),
                rx.select.item(AuthState.t["staking_sort_delegators_desc"], value="delegators_desc"),
                rx.select.item(AuthState.t["staking_sort_ticker_asc"],      value="ticker_asc"),
            ),
            value=StakingSPOState.sort,
            on_change=StakingSPOState.set_sort,
            size="3",
        ),
        spacing="2", wrap="wrap", width="100%",
    )


def _pagination() -> rx.Component:
    def btn(page):
        is_active = page == StakingSPOState.current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: StakingSPOState.set_page(page),
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
            on_click=StakingSPOState.prev_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=StakingSPOState.current_page == 1,
            _hover={"cursor": "pointer"},
        ),
        rx.foreach(StakingSPOState.middle_page, btn),
        rx.button(
            rx.icon(tag="chevron-right"),
            on_click=StakingSPOState.next_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=StakingSPOState.current_page == StakingSPOState.total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="pagination gap-2",
        padding_top="1.5em",
        justify="end",
        align="center",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/staking/spo",
    title="SPO一覧 | ステーキング | Cardanoism",
    on_load=StakingSPOState.on_load,
)
def staking_spo_page() -> rx.Component:
    return rx.cond(
        StakingSPOState.load,
        rx.box(
            rx.html(SPO_CSS),
            # 委任確認モーダル (1 ページに 1 度だけマウント)
            delegation_dialog(),
            rx.vstack(
                _breadcrumb(),
                staking_subnav("spo"),
                _filter_bar(),
                rx.hstack(
                    rx.text(AuthState.t["gov_search_results"], size="3"),
                    rx.text(StakingSPOState.total_items, size="5", weight="bold", color="var(--amber-11)"),
                    rx.text(AuthState.t["gov_results_unit"], size="3"),
                    spacing="2", align="baseline", width="100%", wrap="wrap",
                ),
                rx.cond(
                    StakingSPOState.pools,
                    rx.vstack(
                        rx.foreach(StakingSPOState.pools.to(list[dict[str, str]]), _pool_card),
                        spacing="3", width="100%",
                    ),
                    rx.callout(AuthState.t["staking_no_pools"], icon="info", color_scheme="gray"),
                ),
                rx.cond(StakingSPOState.pools, _pagination(), rx.fragment()),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
