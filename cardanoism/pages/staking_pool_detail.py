"""
staking_pool_detail.py
ステークプール個別ページ（/pool/[pool_id]）

pools テーブルの 1 プールについて、委任者向けの情報をまとめて表示する。
委任 CTA は SPO 一覧と同じ WalletState.request_delegate_to_pool + delegation_dialog を再利用する。
SPO 向け / メタデータ整合性チェックは Phase B で追加予定。
"""
from __future__ import annotations

import logging
import time

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.wallet_state import WalletState
from cardanoism.backend.pool_db import get_pool
from cardanoism.backend.koios import get_totals, get_pool_history
from cardanoism.components.breadcrumb import breadcrumb
from cardanoism.components.staking_nav import staking_subnav
from cardanoism.components.delegation_dialog import delegation_dialog
from cardanoism.pages.staking_spo import (
    format_pool_card_data,
    _saturation_bar,
    _relay_status,
    _social_link,
    _metric,
    _ada_metric_with_tooltip,
    SPO_CSS,
    MAX_SUPPLY_LOVELACE,
    OPTIMAL_POOL_COUNT_K,
)

logger = logging.getLogger(__name__)

# ブロック生成履歴のオンデマンド取得キャッシュ（pool_id ごと、TTL 10 分）。
# プール詳細ページが連打されたときに毎回 Koios を叩かないための軽いメモリキャッシュ。
_HISTORY_TTL = 600.0
_history_cache: dict[str, tuple[float, list]] = {}


def _fetch_pool_history_cached(pool_id: str) -> list[dict]:
    """Koios /pool_history を全エポック取得する（TTL 付きメモリキャッシュ）。"""
    now = time.time()
    hit = _history_cache.get(pool_id)
    if hit is not None and now - hit[0] < _HISTORY_TTL:
        return hit[1]
    try:
        data = get_pool_history(pool_id, limit=1000, timeout=15.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("pool history fetch failed %s: %s", pool_id, e)
        data = None
    if data is None:
        # 通信失敗を正常な0件としてキャッシュしない。期限切れでもlast-goodがあれば返す。
        logger.warning("pool history unavailable; keeping last-good cache: %s", pool_id)
        return hit[1] if hit is not None else []
    _history_cache[pool_id] = (now, data)
    return data


# ─── State ────────────────────────────────────────────────────────────────────


class PoolDetailState(rx.State):
    not_found: bool = False
    error: str = ""

    # 現在 state に読み込まれているプール ID。URL のプール ID と一致するまで
    # ページはスピナーを表示する（別プールへ遷移直後に前回プールが一瞬出るのを防ぐ）。
    loaded_pool_id: str = ""

    # pools 1 行を整形した表示用 dict（format_pool_card_data + 詳細用フィールド）
    pool: dict[str, str] = {}

    # ブロック生成履歴（エポック降順）。各要素: epoch / block_cnt / bar_pct
    block_history: list[dict[str, str]] = []
    # ブロック生成履歴の Koios フェッチ中フラグ（履歴セクションのスピナー制御）
    history_loading: bool = False

    @rx.var
    def ready(self) -> bool:
        """state 上のプールが現在 URL のプールと一致しているか。

        ナビゲーション直後の最初のレンダリング時点では loaded_pool_id が前回
        プールのままなので False になり、前回プールが一瞬表示されるのを防ぐ。
        """
        path = self.router.url.path or ""
        parts = [p for p in path.split("/") if p]
        url_pool_id = parts[-1] if parts else ""
        return self.loaded_pool_id == url_pool_id

    def on_load(self):
        # 1) 前回プールの残留 state を消す。loaded_pool_id を空にすることで
        #    ready が False となり、ページはスピナー表示に切り替わる。
        self.not_found = False
        self.error = ""
        self.pool = {}
        self.block_history = []
        self.history_loading = False
        self.loaded_pool_id = ""
        yield

        # 2) URL 末尾から pool_id を取得
        path = self.router.url.path or ""
        parts = [p for p in path.split("/") if p]
        pool_id = parts[-1] if parts else ""
        if not pool_id:
            self.not_found = True
            self.loaded_pool_id = pool_id
            return

        try:
            # 3) プール本体（DB + /totals）をロード。ここまでは速いので即表示する。
            row = get_pool(pool_id)
            if not row:
                self.not_found = True
                return

            # 飽和点（= ソフトキャップ / 500）を /totals から確定
            sat_point = 0
            try:
                totals = get_totals() or {}
                reserves = int(totals.get("reserves") or 0)
                if reserves > 0:
                    sat_point = (MAX_SUPPLY_LOVELACE - reserves) // OPTIMAL_POOL_COUNT_K
            except Exception as e:  # noqa: BLE001
                logger.warning("get_totals failed: %s", e)

            data = format_pool_card_data(row, saturation_point_lovelace=sat_point)

            # 詳細ページ専用の追加フィールド
            about_full = str(row.get("extended_about") or "").strip()
            if not about_full:
                about_full = str(row.get("description") or "").strip()
            data["about_full"] = about_full

            self.pool = data
            self.history_loading = True   # 履歴セクションはスピナー表示
            self.loaded_pool_id = pool_id  # ready=True: プール本体を即表示
            yield

            # 4) ブロック生成履歴を Koios からオンデマンド取得（重い・エポック降順）
            hist = _fetch_pool_history_cached(pool_id)
            max_blocks = max(
                (int(h.get("block_cnt") or 0) for h in hist), default=0
            ) or 1
            history_out: list[dict[str, str]] = []
            for h in hist:
                bc = int(h.get("block_cnt") or 0)
                history_out.append({
                    "epoch":     str(h.get("epoch_no") or ""),
                    "block_cnt": str(bc),
                    "bar_pct":   f"{(bc / max_blocks * 100.0):.1f}",
                })
            self.block_history = history_out
        except Exception as e:  # noqa: BLE001
            logger.exception("PoolDetailState.on_load: %s", e)
            self.error = str(e)
        finally:
            self.history_loading = False
            self.loaded_pool_id = pool_id


# ─── UI ────────────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return breadcrumb(
        [("nav_staking", "/staking"), ("staking_subnav_spo", "/staking/spo")],
        "pool_detail_breadcrumb",
    )


def _pool_share_btn() -> rx.Component:
    """Pool ページのシェアメニュー (X / LINE / URL コピー)。
    ガバナンス提案モーダルのシェアボタンと同じ挙動。"""
    return rx.menu.root(
        rx.menu.trigger(
            rx.icon(
                "share-2", size=26, color="var(--gray-11)",
                cursor="pointer", padding="4px",
            ),
        ),
        rx.menu.content(
            rx.menu.item(
                "X (Twitter)",
                on_click=rx.call_script(
                    "const t = document.querySelector('.pool-title')?.innerText ?? '';"
                    "const url = 'https://x.com/intent/tweet'"
                    "  + '?text=' + encodeURIComponent(t)"
                    "  + '&url=' + encodeURIComponent(window.location.href);"
                    "window.open(url,'x-share',"
                    "'width=550,height=420,menubar=no,toolbar=no,"
                    "location=no,status=no,resizable=yes,scrollbars=yes');"
                ),
            ),
            rx.menu.item(
                "LINE",
                on_click=rx.call_script(
                    "const t = document.querySelector('.pool-title')?.innerText ?? '';"
                    "const url = 'https://social-plugins.line.me/lineit/share'"
                    "  + '?url=' + encodeURIComponent(window.location.href)"
                    "  + '&text=' + encodeURIComponent(t);"
                    "window.open(url,'line-share',"
                    "'width=520,height=520,menubar=no,toolbar=no,"
                    "location=no,status=no,resizable=yes,scrollbars=yes');"
                ),
            ),
            rx.menu.item(
                AuthState.t["proposal_copy_url"],
                on_click=[
                    rx.call_script("navigator.clipboard.writeText(window.location.href);"),
                    rx.toast(
                        AuthState.t["pool_url_copied"],
                        position="top-center",
                        style={
                            "background-color": "var(--indigo-11)",
                            "color": "white",
                            "border-radius": "0.5rem",
                        },
                    ),
                ],
            ),
        ),
    )


def _pool_fav_btn() -> rx.Component:
    """Pool お気に入り (ハート) トグルボタン。"""
    pid = PoolDetailState.pool["pool_id"]
    return rx.box(
        rx.cond(
            AuthState.pool_favorite_ids.contains(pid),
            rx.icon("heart", size=22, color="var(--red-9)",
                    style={"fill": "var(--red-9)"}),
            rx.icon("heart", size=22, color="var(--gray-8)"),
        ),
        on_click=AuthState.toggle_pool_favorite(pid),
        cursor="pointer",
        padding="6px",
        flex_shrink="0",
        style={"display": "flex", "alignItems": "center"},
    )


def _header() -> rx.Component:
    p = PoolDetailState.pool
    icon = rx.cond(
        p["icon_url"] != "",
        rx.image(
            src=p["icon_url"],
            width="64px", height="64px",
            border_radius="12px",
            style={"objectFit": "cover"},
            flex_shrink="0",
            custom_attrs={"referrerpolicy": "no-referrer", "loading": "lazy"},
        ),
        rx.center(
            rx.icon("hexagon", size=28, color="var(--gray-9)"),
            min_width="64px", height="64px",
            border_radius="12px",
            background="var(--gray-4)",
            flex_shrink="0",
        ),
    )
    name_row = rx.hstack(
        rx.cond(
            p["ticker"] != "",
            rx.badge(p["ticker"], variant="solid", color_scheme="amber", radius="full", size="2"),
            rx.fragment(),
        ),
        rx.cond(
            p["pool_name"] != "",
            rx.heading(p["pool_name"], size="6", weight="bold",
                       color="var(--gray-12)", class_name="pool-title"),
            rx.heading(AuthState.t["staking_no_name"], size="6", weight="bold",
                       color="var(--gray-10)", class_name="pool-title"),
        ),
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
    social_row = rx.hstack(
        _social_link(p["homepage"], rx.icon("house", size=14, color="var(--amber-11)")),
        _social_link(p["twitter_url"], rx.icon("twitter", size=14, color="#1DA1F2")),
        _social_link(p["telegram_url"], rx.icon("send", size=14, color="#2AABEE")),
        _social_link(p["youtube_url"], rx.icon("youtube", size=14, color="#FF0000")),
        _social_link(p["github_url"], rx.icon("github", size=14, color="var(--gray-12)")),
        spacing="2", align="center", wrap="wrap",
    )
    pool_id_row = rx.hstack(
        rx.text(
            p["pool_id"], size="1", color="var(--gray-10)",
            style={"fontFamily": "ui-monospace, monospace", "wordBreak": "break-all"},
        ),
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
        _relay_status(p["relay_state"]),
        spacing="2", align="center", wrap="wrap",
    )
    about = rx.cond(
        p["about_full"] != "",
        rx.text(
            p["about_full"],
            size="2", color="var(--gray-11)", line_height="1.7",
            style={"whiteSpace": "pre-wrap"},
        ),
        rx.fragment(),
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                icon,
                rx.vstack(
                    name_row,
                    social_row,
                    pool_id_row,
                    spacing="2", align_items="start", flex="1", min_width="0",
                ),
                # 右上: シェア + お気に入り
                rx.hstack(
                    _pool_share_btn(),
                    _pool_fav_btn(),
                    spacing="1", align="center", flex_shrink="0",
                ),
                spacing="4", align="start", width="100%", wrap="wrap",
            ),
            about,
            # 右下: 委任 CTA
            rx.hstack(
                rx.spacer(),
                _delegate_cta(),
                width="100%", align="center", padding_top="4px",
            ),
            spacing="4", align_items="stretch", width="100%",
        ),
        padding="20px 22px",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.05)"),
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        width="100%",
    )


def _delegate_cta() -> rx.Component:
    """委任 CTA。SPO 一覧カードと同じ 3 状態・同じボタンスタイル。"""
    pid = PoolDetailState.pool["pool_id"]
    is_currently_delegated = (
        WalletState.connected
        & (WalletState.current_delegated_pool_id == pid)
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
    btn_style = {
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
    }
    btn_hover = {
        "background": "var(--amber-3)",
        "border_color": "var(--amber-10)",
        "transform": "translateY(-1px)",
        "box_shadow": "0 4px 10px -2px rgba(245,158,11,0.25)",
    }
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
        on_click=WalletState.request_delegate_to_pool(pid),
        cursor="pointer",
        style=btn_style,
        _hover=btn_hover,
    )
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
        style=btn_style,
        _hover=btn_hover,
    )
    return rx.cond(
        is_currently_delegated,
        delegated_badge,
        rx.cond(WalletState.connected, delegate_active, delegate_prompt_auth),
    )


def _saturation_row() -> rx.Component:
    p = PoolDetailState.pool
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
    return rx.hstack(
        rx.text(AuthState.t["staking_metric_saturation"], size="2", color="var(--gray-10)", weight="medium"),
        rx.box(_saturation_bar(p), flex="1"),
        rx.box(sat_label, flex_shrink="0", min_width="110px"),
        spacing="3", align="center", width="100%",
    )


def _metrics_grid() -> rx.Component:
    p = PoolDetailState.pool
    return rx.box(
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
        width="100%",
        style={
            "display": "grid",
            "gap": "16px",
            "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
            "@media (min-width: 768px)": {
                "gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
            },
        },
    )


def _note_row(icon: str, label, value, color: str) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=15, color=color, flex_shrink="0"),
        rx.text(label, size="2", color="var(--gray-11)"),
        rx.text(value, size="2", weight="bold", color="var(--gray-12)"),
        spacing="2", align="center",
    )


def _info_section() -> rx.Component:
    p = PoolDetailState.pool
    return rx.box(
        rx.vstack(
            rx.text(
                AuthState.t["pool_detail_section_info"],
                size="3", weight="bold", color="var(--gray-12)",
            ),
            _saturation_row(),
            _metrics_grid(),
            # 手数料変更予告 / 退役予告
            rx.cond(
                p["has_pending_fee_change"] != "",
                _note_row(
                    "triangle-alert",
                    AuthState.t["pool_detail_pending_fee_epoch"],
                    p["pending_effective_epoch"],
                    "var(--amber-10)",
                ),
                rx.fragment(),
            ),
            rx.cond(
                p["is_retiring"] != "",
                _note_row(
                    "circle-x",
                    AuthState.t["pool_detail_retiring_epoch"],
                    p["retiring_epoch"],
                    "var(--red-10)",
                ),
                rx.fragment(),
            ),
            spacing="4", align_items="stretch", width="100%",
        ),
        padding="20px 22px",
        background=rx.color_mode_cond("var(--gray-2)", "rgba(255,255,255,0.015)"),
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        width="100%",
    )


def _bh_header() -> rx.Component:
    """ブロック生成履歴の列ヘッダー（エポック / ブロック数）。"""
    return rx.hstack(
        rx.text(
            AuthState.t["pool_detail_bh_epoch"],
            size="1", color="var(--gray-9)", weight="medium",
            width="56px", flex_shrink="0", text_align="right",
        ),
        rx.text(
            AuthState.t["pool_detail_bh_blocks"],
            size="1", color="var(--gray-9)", weight="medium",
            width="60px", flex_shrink="0",
        ),
        rx.box(flex="1"),
        spacing="3", align="center", width="100%",
    )


def _bh_row(h) -> rx.Component:
    """ブロック生成履歴の 1 エポック行（エポック番号 + ブロック数 + 比率バー）。

    数字はバーの前 (左寄り) に固定配置し、バーはボックス全幅に伸ばす。
    """
    return rx.hstack(
        rx.text(
            h["epoch"],
            size="2", color="var(--gray-12)", weight="medium",
            width="56px", flex_shrink="0", text_align="right",
            style={"fontFamily": "ui-monospace, monospace"},
        ),
        rx.text(
            h["block_cnt"],
            size="2", weight="bold", color="var(--gray-12)",
            width="60px", flex_shrink="0",
        ),
        rx.box(
            rx.box(
                width=h["bar_pct"] + "%",
                height="100%",
                background="var(--amber-9)",
                border_radius="999px",
                transition="width 0.3s",
            ),
            flex="1",
            height="10px",
            background="var(--gray-4)",
            border_radius="999px",
            overflow="hidden",
        ),
        spacing="3", align="center", width="100%",
    )


def _block_history_section() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(
                AuthState.t["pool_detail_block_history"],
                size="3", weight="bold", color="var(--gray-12)",
            ),
            rx.cond(
                PoolDetailState.history_loading,
                rx.center(
                    rx.spinner(size="2"),
                    padding_y="30px", width="100%",
                ),
                rx.cond(
                    PoolDetailState.block_history,
                    rx.vstack(
                        _bh_header(),
                        rx.box(
                            rx.vstack(
                                rx.foreach(PoolDetailState.block_history, _bh_row),
                                spacing="2", width="100%",
                                padding_right="12px",
                            ),
                            max_height="360px",
                            overflow_y="auto",
                            width="100%",
                        ),
                        spacing="2", align_items="stretch", width="100%",
                    ),
                    rx.text(
                        AuthState.t["pool_detail_block_history_empty"],
                        size="2", color="var(--gray-10)",
                    ),
                ),
            ),
            spacing="3", align_items="stretch", width="100%",
        ),
        padding="20px 22px",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.05)"),
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        width="100%",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/pool/[pool_id]",
    title="ステークプール詳細 | ステーキング | Cardanoism",
    on_load=PoolDetailState.on_load,
)
def staking_pool_detail_page() -> rx.Component:
    return rx.cond(
        PoolDetailState.ready,
        rx.box(
            rx.html(SPO_CSS),
            # 委任確認モーダル（1 ページに 1 度だけマウント）
            delegation_dialog(),
            rx.vstack(
                _breadcrumb(),
                staking_subnav("spo"),
                rx.cond(
                    PoolDetailState.not_found,
                    rx.callout(
                        AuthState.t["pool_detail_not_found"],
                        icon="triangle-alert",
                        color_scheme="red",
                    ),
                    rx.vstack(
                        _header(),
                        _info_section(),
                        _block_history_section(),
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
