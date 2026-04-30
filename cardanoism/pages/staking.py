"""
staking.py
ステーキング > ダッシュボード（/staking）

データソースは pools テーブル（notify_worker.py --event pool_sync で同期）。
ページ側は DB を読むだけで Koios を叩かない。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.fiat_db import get_fiat_rate
from cardanoism.backend.koios import get_totals
from cardanoism.backend.pool_db import get_network_summary
from cardanoism.backend.price import format_ada, format_jpy_short, format_usd_short
from cardanoism.backend.recent_blocks_db import get_recent_blocks
from cardanoism.backend.mempool_db import get_mempool_state

import json as _json
from cardanoism.components.staking_nav import staking_subnav
from cardanoism.components.login_modal import login_modal

# Cardano プロトコル定数
MAX_SUPPLY_LOVELACE = 45_000_000_000 * 1_000_000  # 45B ADA
OPTIMAL_POOL_COUNT_K = 500
# Cardano protocol params (mainnet): maxBlockBodySize=90112 + maxBlockHeaderSize=1100 = 91212
# Ogmios の block.size.bytes はヘッダ + ボディの全体サイズを返すので、ヘッダ込みの上限と比較する。
MAX_BLOCK_TOTAL_SIZE_BYTES = 91_212

logger = logging.getLogger(__name__)


# ─── State ────────────────────────────────────────────────────────────────────


class StakingDashboardState(rx.State):
    load: bool = False
    error: str = ""

    # ネットワーク集計
    total_pools: int = 0
    active_pools: int = 0
    retiring_pools: int = 0
    saturated_pools: int = 0
    total_delegators: int = 0
    total_live_stake_ada_display: str = "-"
    total_live_stake_jpy: str = ""
    total_live_stake_usd: str = ""

    # ソフトキャップ / 飽和点（Koios /totals の reserves から算出）
    soft_cap_ada_display: str = "-"
    saturation_point_ada_display: str = "-"
    # 飽和点 (lovelace) - 各プールの飽和率を自前計算するために保持
    saturation_point_lovelace: int = 0

    # ライブブロック一覧（5秒ポーリングで更新）
    live_blocks: list[dict[str, str]] = []
    # 直近で取り込んだブロックの最大 height — 新規分のアニメーション制御用
    latest_known_height: int = 0
    polling: bool = False
    # グリッドの行数 (キューブ総数 / COLS の天井)
    grid_rows: str = "1"
    # Mempool キューブの connector 方向（常にブロック数で決まる）
    mempool_connector: str = ""

    # 委任先プールカード（ログインユーザーの stake_addresses から構築）
    # 各 entry: format_pool_card_data の戻り値 + nickname / address フィールド
    user_delegated_pools: list[dict[str, str]] = []

    # ヒートマップ: アクティブプール全件をブロック生成数で色分け（重い集計なので on_load のみ実行）
    heatmap_pools: list[dict[str, str]] = []
    heatmap_count_green:  int = 0
    heatmap_count_yellow: int = 0
    heatmap_count_pink:   int = 0
    heatmap_count_gray:   int = 0

    # Mempool 状態（10秒間隔で ogmios_listener が更新、ページ側は 5秒で読みに行く）
    mempool_tx_count: int = 0
    mempool_size_kb: str = "0"
    mempool_capacity_kb: str = ""
    mempool_fullness_pct: str = "0.0"
    mempool_fullness_bar: str = "0.0"
    mempool_updated_label: str = ""

    def _fetch_summary(self):
        """ネットワーク集計とサチュレーション関連を取得する（軽い処理）。"""
        try:
            rate = get_fiat_rate() or {}
            ada_jpy = float(rate.get("ada_jpy") or 0)
            ada_usd = float(rate.get("ada_usd") or 0)

            # ソフトキャップ = 45B ADA - 残りリザーブ、飽和点 = ソフトキャップ / k(=500)
            saturation_lovelace = 0
            try:
                totals = get_totals() or {}
                reserves = int(totals.get("reserves") or 0)
                if reserves > 0:
                    soft_cap_lovelace = MAX_SUPPLY_LOVELACE - reserves
                    saturation_lovelace = soft_cap_lovelace // OPTIMAL_POOL_COUNT_K
                    self.soft_cap_ada_display = format_ada(soft_cap_lovelace, integer=True)
                    self.saturation_point_ada_display = format_ada(saturation_lovelace, integer=True)
                    self.saturation_point_lovelace = saturation_lovelace
            except Exception as e:
                logger.warning("get_totals failed: %s", e)

            saturated_threshold = int(saturation_lovelace * 0.8) if saturation_lovelace else None
            summary = get_network_summary(saturated_threshold_lovelace=saturated_threshold)
            self.total_pools = int(summary.get("total_pools") or 0)
            self.active_pools = int(summary.get("active_pools") or 0)
            self.retiring_pools = int(summary.get("retiring_pools") or 0)
            self.saturated_pools = int(summary.get("saturated_pools") or 0)
            self.total_delegators = int(summary.get("total_delegators") or 0)

            total_lovelace = int(summary.get("total_live_stake") or 0)
            ada = total_lovelace / 1_000_000 if total_lovelace else 0
            self.total_live_stake_ada_display = format_ada(total_lovelace, integer=True) if total_lovelace else "0"
            self.total_live_stake_jpy = format_jpy_short(ada * ada_jpy) if ada_jpy else ""
            self.total_live_stake_usd = format_usd_short(ada * ada_usd) if ada_usd else ""
        except Exception as e:
            logger.exception("StakingDashboardState._fetch_summary: %s", e)
            self.error = str(e)

    def _fetch_blocks_data(self):
        """ライブブロック + ヒートマップ用データを取得する（重い処理 / blocks ページ専用）。"""
        try:
            self._fetch_live_blocks()
            self._fetch_heatmap()
        except Exception as e:
            logger.exception("StakingDashboardState._fetch_blocks_data: %s", e)

    def _fetch_heatmap(self):
        """全アクティブプールの直近5エポック合計ブロック数を集計し、色分けする。
        重いので on_load のみ実行（polling では呼ばない）。
        """
        try:
            from cardanoism.backend.pool_db import get_pools_for_heatmap
            rows = get_pools_for_heatmap()
        except Exception as e:
            logger.warning("get_pools_for_heatmap failed: %s", e)
            return

        out: list[dict[str, str]] = []
        cnt = {"green": 0, "yellow": 0, "pink": 0, "gray": 0}
        for r in rows:
            history_raw = r.get("block_history_5ep")
            total = 0
            if history_raw:
                try:
                    parsed = _json.loads(history_raw) if isinstance(history_raw, str) else history_raw
                    if isinstance(parsed, list):
                        total = sum(int(x or 0) for x in parsed[:5])
                except (TypeError, ValueError, _json.JSONDecodeError):
                    total = 0
            if total >= 50:
                color = "green"
            elif total >= 10:
                color = "yellow"
            elif total >= 1:
                color = "pink"
            else:
                color = "gray"
            cnt[color] += 1
            out.append({
                "pool_id":  str(r.get("pool_id_bech32") or ""),
                "ticker":   str(r.get("ticker") or ""),
                "total":    str(total),
                "color":    color,
            })
        # ブロック数の多い順に並べてヒートマップ上で「活発なプール」が先頭に来るよう
        out.sort(key=lambda d: (-int(d["total"]), d["pool_id"]))
        self.heatmap_pools = out
        self.heatmap_count_green  = cnt["green"]
        self.heatmap_count_yellow = cnt["yellow"]
        self.heatmap_count_pink   = cnt["pink"]
        self.heatmap_count_gray   = cnt["gray"]

    def _fetch_live_blocks(self):
        """recent_blocks から直近20件を取得し、新規ブロックに is_new フラグを立てる。
        mempool_state も一緒に取得して State に反映する。
        """
        # mempool を先に取る（軽い）
        try:
            ms = get_mempool_state()
            if ms:
                tx_count = int(ms.get("tx_count") or 0)
                byte_size = int(ms.get("byte_size") or 0)
                cap = ms.get("capacity_bytes")
                self.mempool_tx_count = tx_count
                self.mempool_size_kb = f"{byte_size / 1024:.1f}"
                if cap:
                    cap = int(cap)
                    self.mempool_capacity_kb = f"{cap / 1024:.0f}"
                    pct = (byte_size / cap * 100.0) if cap > 0 else 0.0
                    self.mempool_fullness_pct = f"{pct:.1f}"
                    self.mempool_fullness_bar = f"{max(0.0, min(100.0, pct)):.1f}"
                else:
                    self.mempool_capacity_kb = ""
                    self.mempool_fullness_pct = "0.0"
                    self.mempool_fullness_bar = "0.0"
                updated = ms.get("updated_at")
                if isinstance(updated, datetime):
                    upd_aware = updated.replace(tzinfo=timezone.utc) if updated.tzinfo is None else updated
                    age = max(0, int((datetime.now(timezone.utc) - upd_aware).total_seconds()))
                    self.mempool_updated_label = f"{age}s ago"
        except Exception as e:
            logger.warning("get_mempool_state failed: %s", e)

        try:
            # mempool 1 セル + ブロック 34 = 合計 35 セル (7 列 × 5 段にぴったり収まる)
            rows = get_recent_blocks(limit=34)
        except Exception as e:
            logger.warning("get_recent_blocks failed: %s", e)
            return

        prev_max = int(self.latest_known_height or 0)
        out: list[dict[str, str]] = []
        new_max = prev_max
        total_cubes = 1 + len(rows)  # mempool + ブロック
        # grid 位置: idx=0 が Mempool（別途配置）なので、ブロックは idx=1 から始まる
        for grid_idx, r in enumerate(rows, start=1):
            height = int(r.get("block_height") or 0)
            if height > new_max:
                new_max = height
            slot = int(r.get("slot_no") or 0)
            epoch = int(r.get("epoch_no") or 0)
            tx_count = int(r.get("tx_count") or 0)
            block_size = int(r.get("block_size") or 0)
            block_size_kb = f"{block_size / 1024:.1f}" if block_size else "0"
            fullness_pct = (block_size / MAX_BLOCK_TOTAL_SIZE_BYTES * 100.0) if block_size else 0.0
            fullness_pct_clamped = max(0.0, min(100.0, fullness_pct))
            block_hash = str(r.get("block_hash") or "")
            block_hash_short = (block_hash[:10] + "..." + block_hash[-6:]) if len(block_hash) > 18 else block_hash
            ticker = str(r.get("pool_ticker") or "")
            pool_name = str(r.get("pool_name") or "")
            icon_url = str(r.get("pool_icon_url") or "")
            pool_id_bech32 = str(r.get("pool_id_bech32") or "")
            block_time = r.get("block_time")
            # 表示用: 何秒前 / 時刻文字列
            seconds_ago = 0
            time_label = ""
            if isinstance(block_time, datetime):
                bt_aware = block_time.replace(tzinfo=timezone.utc) if block_time.tzinfo is None else block_time
                seconds_ago = max(0, int((datetime.now(timezone.utc) - bt_aware).total_seconds()))
                time_label = bt_aware.astimezone().strftime("%H:%M:%S")
            row_g, col_g = _grid_position(grid_idx)
            connector = _connector_direction(grid_idx, total_cubes)
            out.append({
                "block_height":     str(height),
                "block_hash_short": block_hash_short,
                "slot_no":          str(slot),
                "epoch_no":         str(epoch),
                "tx_count":         str(tx_count),
                "block_size":       str(block_size),
                "block_size_kb":    block_size_kb,
                "fullness_pct":     f"{fullness_pct:.1f}",
                "fullness_bar":     f"{fullness_pct_clamped:.2f}",
                "ticker":           ticker,
                "pool_name":        pool_name,
                "icon_url":         icon_url,
                "pool_id_bech32":   pool_id_bech32,
                "time_label":       time_label,
                "seconds_ago":      str(seconds_ago),
                "grid_row":         str(row_g),
                "grid_col":         str(col_g),
                "connector":        connector,
                # is_new: 到着直後のブロック (約3秒以内) → 緑フラッシュのオーバーレイを表示
                "is_new":           "1" if seconds_ago <= 3 else "",
            })
        self.live_blocks = out
        # mempool の connector は次（= 最新ブロック）への向き。total_cubes=1 (ブロック0件)なら無し
        self.mempool_connector = _connector_direction(0, total_cubes) if total_cubes > 1 else ""
        # 5列レイアウトの行数（最低1行）
        self.grid_rows = str(max(1, (total_cubes + COLS - 1) // COLS))
        if new_max > prev_max:
            self.latest_known_height = new_max

    async def on_load_dashboard(self):
        """/staking 用: 集計 + 委任先プールカード + ブロック / ヒートマップ を一括取得。"""
        self.load = False
        self.error = ""
        self._fetch_summary()
        # AuthState から user_id / stake_addresses を取得して委任先プール情報を組み立て
        auth = await self.get_state(AuthState)
        if auth.is_logged_in:
            try:
                from cardanoism.backend.auth_db import get_stake_addresses
                addresses = get_stake_addresses(auth.user_id)
            except Exception as e:
                logger.warning("get_stake_addresses failed: %s", e)
                addresses = []
            self._fetch_user_delegated_pools(addresses)
        else:
            self.user_delegated_pools = []
        self._fetch_blocks_data()
        self.load = True

    def _fetch_user_delegated_pools(self, addresses: list[dict]) -> None:
        """ユーザーの stake_addresses から委任先プールを fetch して SPO カード形式に整形する。"""
        from cardanoism.backend.pool_db import get_pool
        from cardanoism.pages.staking_spo import format_pool_card_data

        out: list[dict[str, str]] = []
        for idx, addr in enumerate(addresses, start=1):
            pool_id = str(addr.get("delegated_pool_id") or "").strip()
            nickname = str(addr.get("nickname") or "")
            address = str(addr.get("address") or "")
            entry: dict[str, str]
            if pool_id:
                try:
                    row = get_pool(pool_id)
                except Exception as e:
                    logger.warning("get_pool(%s) failed: %s", pool_id, e)
                    row = None
                if row:
                    entry = format_pool_card_data(
                        row,
                        saturation_point_lovelace=self.saturation_point_lovelace,
                        rank=idx,
                    )
                else:
                    # DB に該当プールが見つからない（pool_sync 待ち / ティッカーだけ知ってる）
                    entry = {
                        "rank": str(idx),
                        "pool_id": pool_id,
                        "pool_id_short": (pool_id[:10] + "..." + pool_id[-8:]) if len(pool_id) > 22 else pool_id,
                        "ticker": "",
                        "pool_name": str(addr.get("delegated_pool_name") or ""),
                        "icon_url": "",
                        "homepage": "",
                        "about": "",
                        "twitter_url": "", "telegram_url": "", "youtube_url": "", "github_url": "",
                        "stake_ada": "0", "pledge_ada": "0",
                        "stake_ada_ja": "0", "stake_ada_en": "0",
                        "pledge_ada_ja": "0", "pledge_ada_en": "0",
                        "fixed_cost_ada": "0", "margin_pct": "0.00",
                        "saturation_pct": "0.0", "saturation_bar": "0.0",
                        "is_saturated": "",
                        "delegators": "0", "block_count": "0",
                        "status": "", "is_retiring": "", "retiring_epoch": "",
                        "relay_state": "unknown", "history_total": "0",
                    }
            else:
                entry = {
                    "rank": str(idx),
                    "pool_id": "", "pool_id_short": "",
                    "ticker": "", "pool_name": "", "icon_url": "",
                    "homepage": "", "about": "",
                    "twitter_url": "", "telegram_url": "", "youtube_url": "", "github_url": "",
                    "stake_ada": "0", "pledge_ada": "0",
                    "stake_ada_ja": "0", "stake_ada_en": "0",
                    "pledge_ada_ja": "0", "pledge_ada_en": "0",
                    "fixed_cost_ada": "0", "margin_pct": "0.00",
                    "saturation_pct": "0.0", "saturation_bar": "0.0",
                    "is_saturated": "",
                    "delegators": "0", "block_count": "0",
                    "status": "", "is_retiring": "", "retiring_epoch": "",
                    "relay_state": "unknown", "history_total": "0",
                }
            entry["nickname"] = nickname
            entry["address"] = address
            entry["has_pool"] = "1" if pool_id else ""
            out.append(entry)
        self.user_delegated_pools = out


    @rx.event(background=True)
    async def start_live_polling(self):
        """1秒間隔で recent_blocks / mempool_state を再取得する常駐タスク。
        ogmios_listener 側も 1 秒で書き込むので、合計ラグは最大 ~1秒。
        Reflex が State 更新を WebSocket でクライアントに push するため、
        ブラウザは即座に新しい値を受け取る = 体感リアルタイム。

        各ループ反復で例外を捕まえて継続するので、一時的な DB エラー等で
        ポーリングが死なない（停止すると UI のリアルタイム性が失われるため）。
        """
        # 二重起動ガード（同一セッションで既に走っているなら抜ける）
        async with self:
            if self.polling:
                return
            self.polling = True
        try:
            while True:
                try:
                    await asyncio.sleep(1)
                    async with self:
                        self._fetch_live_blocks()
                except asyncio.CancelledError:
                    raise
                except Exception as inner:
                    logger.warning("polling 反復で例外（継続）: %s", inner)
                    # 短く待って次のループへ
                    await asyncio.sleep(2)
        except asyncio.CancelledError:
            logger.info("start_live_polling キャンセル受信")
            raise
        except Exception as e:
            logger.warning("start_live_polling 異常終了: %s", e)
        finally:
            async with self:
                self.polling = False


# ─── UI パーツ ────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["nav_staking"], size="2", weight="medium"),
        spacing="2",
        align="center",
        width="100%",
        padding_top="15px",
    )


def _stat_card(icon: str, label, value, sub=None, accent: str = "var(--amber-9)") -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    rx.icon(icon, size=14, color=accent),
                    width="26px",
                    height="26px",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    border_radius="8px",
                    background=f"color-mix(in srgb, {accent} 18%, transparent)",
                    border=f"1px solid color-mix(in srgb, {accent} 32%, transparent)",
                ),
                rx.text(label, size="1", color="var(--gray-10)", weight="medium", letter_spacing="0.04em"),
                spacing="2", align="center", width="100%",
            ),
            rx.text(value, size="5", weight="bold", color="var(--gray-12)", style={"letterSpacing": "-0.02em"}),
            rx.cond(
                sub if sub is not None else False,
                rx.text(sub if sub is not None else "", size="1", color="var(--gray-10)"),
                rx.fragment(),
            ),
            spacing="2",
            align_items="start",
            width="100%",
        ),
        padding="12px 14px",
        border_radius="10px",
        border=f"1px solid {rx.color('gray', 4)}",
        background="var(--gray-2)",
        width="100%",
    )


DASHBOARD_CSS = """
<style>
/* CSS Houdini: 色 CSS 変数を <color> 型として登録すると keyframe 間で
   滑らかに補間できる（gradient stop も含めてフェード） */
@property --cube-fill     { syntax: '<color>'; inherits: true; initial-value: #f59e0b; }
@property --cube-empty    { syntax: '<color>'; inherits: true; initial-value: #fef3c7; }
@property --cube-top      { syntax: '<color>'; inherits: true; initial-value: #fde68a; }
@property --cube-side     { syntax: '<color>'; inherits: true; initial-value: #92400e; }
@property --cube-text     { syntax: '<color>'; inherits: true; initial-value: #1c1917; }
@property --cube-text-sub { syntax: '<color>'; inherits: true; initial-value: #44403c; }
@property --cube-icon-bg  { syntax: '<color>'; inherits: true; initial-value: #fef3c7; }

/* 新ブロック到着時: ボディ色が一時的にビビッドな緑へフェード→元の段別色に戻る。
   0%/100% は省略してクラス本来の値（段別色）を始終端に使う → 緑へ動いて戻る。
   段は amber/orange/ruby/violet/indigo なので、green は全段とコントラストが効く。 */
@keyframes cdn_cube_color_flash {
  20%, 55% {
    --cube-fill:  var(--green-9);
    --cube-empty: var(--green-3);
    --cube-top:   var(--green-5);
    --cube-side:  var(--green-11);
    --cube-text:     var(--green-12);
    --cube-text-sub: var(--green-11);
    --cube-icon-bg:  var(--green-2);
  }
}
@keyframes cdn_mempool_breathe {
  0%, 100% { filter: brightness(1.0); }
  50%      { filter: brightness(1.18); }
}
@keyframes cdn_chain_shine {
  0%, 100% { opacity: 0.55; }
  50%      { opacity: 0.95; }
}
@keyframes cdn_live_dot {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.55); }
  70%      { box-shadow: 0 0 0 7px rgba(239,68,68,0); }
  100%     { box-shadow: 0 0 0 0 rgba(239,68,68,0); }
}

.cdn-cubes-grid {
  --gap-x: 20px;
  --gap-y: 40px;
  display: grid;
  /* 7 列 × 5 段でぴったり 35 セル。各キューブ最大 140px。 */
  grid-template-columns: repeat(7, minmax(0, 140px));
  justify-content: center;
  gap: var(--gap-y) var(--gap-x);
  width: 100%;
  padding: 14px 14px 0 0;
  box-sizing: border-box;
  position: relative;
}

/* 各キューブを isometric 3D で見せる:
   ::before = 上面 (skewX で平行四辺形)
   ::after  = 右面 (skewY で平行四辺形)
   本体     = 前面 (block_size に応じた充填グラデ) */
.cdn-cube {
  position: relative;
  aspect-ratio: 1 / 1;
  transition: filter 0.4s ease;
  border-radius: 4px;
  color: white;
  text-align: center;
  /* 充填グラデーション: 下から fullness % 分が濃い色、それ以上は薄い色 */
  background: linear-gradient(
    to top,
    var(--cube-fill, #d97706) 0%,
    var(--cube-fill, #d97706) var(--cube-fill-pct, 0%),
    var(--cube-empty, rgba(217,119,6,0.35)) var(--cube-fill-pct, 0%),
    var(--cube-empty, rgba(217,119,6,0.35)) 100%
  );
  /* 下端に重さ感（接地影） */
  box-shadow: 0 8px 14px rgba(0,0,0,0.22);
  transition: transform 0.2s ease, filter 0.2s ease;
  /* isolation を外すことでコネクタ (z-index 高) がキューブ群の上面まで突き抜けて表示できる */
}
.cdn-cube::before {
  /* 上面 */
  content: '';
  position: absolute;
  top: -12px;
  left: 0;
  right: 0;
  height: 12px;
  background: var(--cube-top, #f59e0b);
  transform: skewX(-45deg);
  transform-origin: bottom left;
  border-radius: 3px 3px 0 0;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.4);
}
.cdn-cube::after {
  /* 右面 */
  content: '';
  position: absolute;
  top: 0;
  right: -12px;
  bottom: 0;
  width: 12px;
  background: var(--cube-side, #92400e);
  transform: skewY(-45deg);
  transform-origin: top left;
  border-radius: 0 3px 3px 0;
  box-shadow: inset -1px 0 0 rgba(0,0,0,0.25);
}
.cdn-cube:hover {
  filter: brightness(1.10);
  z-index: 2;
}

/* 充填率テキスト、tx数/サイズ、ブロック高、ticker 等が入るレイヤ */
.cdn-cube-content {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 8px 6px;
  pointer-events: none;
}

/* チェーンコネクタ: 各キューブから次のキューブへ向かってチェーンアイコンで繋ぐ。
   色はテーマ追従の前景色で、ライト/ダーク両方で視認できるよう drop-shadow 付き。
   キューブの上面/右面 + 隣接キューブ本体より前に来るよう z-index を最大級に持ち上げる。 */
.cdn-conn {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 100;
  color: var(--gray-12);
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.55)) drop-shadow(0 0 4px rgba(255,255,255,0.4));
  animation: cdn_chain_shine 2.4s ease-in-out infinite;
}
.cdn-conn-right {
  top: 50%;
  right: calc(-1 * var(--gap-x, 28px));
  width: var(--gap-x, 28px);
  transform: translateY(-50%);
}
.cdn-conn-left {
  top: 50%;
  left: calc(-1 * var(--gap-x, 28px));
  width: var(--gap-x, 28px);
  transform: translateY(-50%);
}
.cdn-conn-down {
  bottom: calc(-1 * var(--gap-y, 32px));
  left: 50%;
  height: var(--gap-y, 32px);
  transform: translateX(-50%);
  flex-direction: column;
}

/* プール活動ヒートマップ — アクティブプール全件を色付きの小マスで表示 */
.cdn-heatmap-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10px, 1fr));
  gap: 2px;
  width: 100%;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--gray-2);
  border: 1px solid var(--gray-4);
}
.cdn-heatmap-cell {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 1px;
  transition: transform 0.1s ease, outline 0.1s ease;
}
.cdn-heatmap-cell:hover {
  transform: scale(1.6);
  outline: 1px solid var(--gray-12);
  z-index: 2;
}
.cdn-heatmap-cell-green  { background: var(--green-9);  }
.cdn-heatmap-cell-yellow { background: var(--yellow-9); }
.cdn-heatmap-cell-pink   { background: var(--pink-9);   }
.cdn-heatmap-cell-gray   { background: var(--gray-6);   }
/* 凡例用の小さな色見本（cdn-heatmap-cell の 100% 幅を継承させない） */
.cdn-heatmap-legend-swatch {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  flex-shrink: 0;
  display: inline-block;
}

/* Mempool 専用の「流れ込む」インジケータ — チェーンではなく右方向の動きで
   "これから次のブロックに tx が入る" を表現する */
@keyframes cdn_mempool_flow {
  0%, 100% { transform: translateY(-50%) translateX(-6px); opacity: 0.4; }
  50%      { transform: translateY(-50%) translateX(4px);  opacity: 1; }
}
.cdn-conn-mempool {
  /* "次の (アンバー) ブロックへ流れ込む" を示唆するため、矢印は流入先のアンバー系で目立たせる */
  color: var(--amber-10);
  filter: drop-shadow(0 0 6px rgba(245,158,11,0.65)) drop-shadow(0 1px 2px rgba(0,0,0,0.3));
  animation: cdn_mempool_flow 1.4s ease-in-out infinite !important;
}

/* 色テーマ — 段ごとにハッキリ違う色相。1段目アンバー → 5段目インディゴで暖色→寒色へ。 */
.cdn-cube-block {
  /* 1段目（最新）: アンバー */
  --cube-fill:  var(--amber-8);
  --cube-empty: var(--amber-3);
  --cube-top:   var(--amber-4);
  --cube-side:  var(--amber-11);
  --cube-text:     var(--amber-12);
  --cube-text-sub: var(--amber-11);
  --cube-icon-bg:  var(--amber-2);
}
/* 2段目: オレンジ */
.cdn-cube-block[data-row="2"] {
  --cube-fill:  var(--orange-8);
  --cube-empty: var(--orange-3);
  --cube-top:   var(--orange-4);
  --cube-side:  var(--orange-11);
  --cube-text:     var(--orange-12);
  --cube-text-sub: var(--orange-11);
  --cube-icon-bg:  var(--orange-2);
}
/* 3段目: ルビー（赤系） */
.cdn-cube-block[data-row="3"] {
  --cube-fill:  var(--ruby-8);
  --cube-empty: var(--ruby-3);
  --cube-top:   var(--ruby-4);
  --cube-side:  var(--ruby-11);
  --cube-text:     var(--ruby-12);
  --cube-text-sub: var(--ruby-11);
  --cube-icon-bg:  var(--ruby-2);
}
/* 4段目: バイオレット */
.cdn-cube-block[data-row="4"] {
  --cube-fill:  var(--violet-8);
  --cube-empty: var(--violet-3);
  --cube-top:   var(--violet-4);
  --cube-side:  var(--violet-11);
  --cube-text:     var(--violet-12);
  --cube-text-sub: var(--violet-11);
  --cube-icon-bg:  var(--violet-2);
}
/* 5段目（最古）: インディゴ */
.cdn-cube-block[data-row="5"] {
  --cube-fill:  var(--indigo-8);
  --cube-empty: var(--indigo-3);
  --cube-top:   var(--indigo-4);
  --cube-side:  var(--indigo-11);
  --cube-text:     var(--indigo-12);
  --cube-text-sub: var(--indigo-11);
  --cube-icon-bg:  var(--indigo-2);
}
/* 新ブロック到着のキューブに緑色フェードを適用。
   --cube-* の CSS 変数が gradient と ::before/::after の background を駆動しているので、
   この変数を keyframe で動かすだけで前面・上面・右面が同期して amber → green → amber と変化する。 */
.cdn-cube-block.cdn-cube-new {
  animation: cdn_cube_color_flash 2.6s ease-in-out;
}
/* コンテンツ層は z-index 2 (将来のオーバーレイに備えて確保) */
.cdn-cube-content {
  z-index: 2;
}
.cdn-cube-mempool {
  --cube-fill:  var(--blue-8);
  --cube-empty: var(--blue-3);
  --cube-top:   var(--blue-4);
  --cube-side:  var(--blue-11);
  animation: cdn_mempool_breathe 2.6s ease-in-out infinite;
}

@media (max-width: 768px) {
  /* スマホは 1 カラム縦並び。Mempool 最上段、その下に新しいブロック順 */
  .cdn-cubes-grid {
    grid-template-columns: minmax(0, 170px);
    justify-content: center;
    --gap-x: 0;
    --gap-y: 16px;
    padding: 12px;
  }
  /* ジグザグ配置を無効化、DOM 順 (mempool → 新→古) で並べる */
  .cdn-cubes-grid > * {
    grid-row: auto !important;
    grid-column: auto !important;
  }
  /* 縦並びでは横方向のチェーンが意味を成さないので非表示 */
  .cdn-conn {
    display: none;
  }
}
</style>
"""


# ジグザグ（ブストロフェドン）配置: 偶数行は左→右、奇数行は右→左
# idx=0 が Mempool (左上)、idx=1 以降が新しい順のブロック
COLS = 7


def _grid_position(idx: int, cols: int = COLS) -> tuple[int, int]:
    row = idx // cols
    col = idx % cols
    if row % 2 == 1:
        col = (cols - 1) - col
    return row + 1, col + 1


def _connector_direction(idx: int, total: int, cols: int = COLS) -> str:
    """idx 番目のキューブから次のキューブ (idx+1) への「接続方向」を返す。

    raw idx 順では同じ raw row 内で col が 0→cols-1 と進むが、奇数行は visual で
    右→左に反転して並べる（ジグザグ）。よって:
      - raw col が cols-1 (= raw 行の末尾) → 次は新しい raw 行 → "down"
      - 偶数行の中間 (going_right): 次は visual 右隣 → "right"
      - 奇数行の中間 (going_left):  次は visual 左隣 → "left"
    最後のキューブ (idx == total - 1) は次がないので空文字。
    """
    if idx >= total - 1:
        return ""
    row = idx // cols
    col = idx % cols
    if col == cols - 1:
        return "down"
    going_right = (row % 2 == 0)
    return "right" if going_right else "left"


def _mempool_flow_node(direction) -> rx.Component:
    """Mempool から次のブロックへの "流れ込む" インジケータ。
    チェーンアイコンではなく chevrons-right で「これから tx がブロックに入る」感を表現。
    """
    return rx.match(
        direction,
        ("right", rx.box(
            rx.icon("chevrons-right", size=44, stroke_width=3.5),
            class_name="cdn-conn cdn-conn-mempool cdn-conn-right",
        )),
        ("down", rx.box(
            rx.icon("chevrons-down", size=44, stroke_width=3.5),
            class_name="cdn-conn cdn-conn-mempool cdn-conn-down",
        )),
        rx.fragment(),
    )


def _connector_node(direction) -> rx.Component:
    """次のキューブへ伸びるチェーンアイコン（rx.match で direction 別に向きを決定）。
    視認性のためサイズ大きめ・stroke 太め。
    """
    return rx.match(
        direction,
        ("right", rx.box(
            rx.icon("link", size=22, stroke_width=2.4),
            class_name="cdn-conn cdn-conn-right",
        )),
        ("left", rx.box(
            rx.icon("link", size=22, stroke_width=2.4, style={"transform": "scaleX(-1)"}),
            class_name="cdn-conn cdn-conn-left",
        )),
        ("down", rx.box(
            rx.icon("link", size=22, stroke_width=2.4, style={"transform": "rotate(90deg)"}),
            class_name="cdn-conn cdn-conn-down",
        )),
        rx.fragment(),
    )


def _block_cube(b) -> rx.Component:
    """3D キューブでブロックを描画。
    - 位置: --row / --col を CSS 変数で渡し、transform で配置 → CSS transition で滑らかに移動
    - 充填率: block_size / max_block_body_size を --cube-fill-pct に注入
    - チェーン: 次のキューブへの connector アイコン（右 / 左 / 下）
    - is_new=="1" の時は色とアニメで強調
    - key=block_height で React が DOM を block 単位で追跡 → 位置変更がスムーズ
    """
    return rx.box(
        rx.box(
            rx.text("#", b["block_height"], size="3", weight="bold",
                    color="var(--cube-text)",
                    style={"fontFamily": "ui-monospace, monospace", "letterSpacing": "0.02em"}),
            # 中段: プールアイコン + ticker をまとめて表示
            rx.box(
                rx.cond(
                    b["icon_url"] != "",
                    rx.image(
                        src=b["icon_url"],
                        width="34px",
                        height="34px",
                        border_radius="50%",
                        style={
                            "objectFit": "cover",
                            "border": "2px solid var(--cube-side)",
                            "background": "var(--cube-icon-bg)",
                            "boxShadow": "0 2px 6px rgba(0,0,0,0.18)",
                        },
                        custom_attrs={"referrerpolicy": "no-referrer", "loading": "lazy"},
                    ),
                    rx.center(
                        rx.icon("box", size=18, color="var(--cube-text-sub)"),
                        width="34px",
                        height="34px",
                        border_radius="50%",
                        background="var(--cube-icon-bg)",
                        border="2px solid var(--cube-side)",
                    ),
                ),
                rx.cond(
                    b["ticker"] != "",
                    rx.text(b["ticker"], size="2", weight="bold", color="var(--cube-text)",
                            style={"letterSpacing": "0.04em"}),
                    rx.fragment(),
                ),
                style={"display": "flex", "flexDirection": "column",
                       "alignItems": "center", "gap": "4px"},
            ),
            rx.box(
                rx.text(b["tx_count"], " tx", size="1", weight="bold",
                        color="var(--cube-text)"),
                rx.text(b["block_size_kb"], " KB", size="1",
                        color="var(--cube-text-sub)"),
                style={"display": "flex", "flexDirection": "column",
                       "alignItems": "center", "gap": "1px"},
            ),
            class_name="cdn-cube-content",
        ),
        _connector_node(b["connector"]),
        class_name=rx.cond(
            b["is_new"] == "1",
            "cdn-cube cdn-cube-block cdn-cube-new",
            "cdn-cube cdn-cube-block",
        ),
        key=b["block_height"],
        custom_attrs={"data-row": b["grid_row"]},
        style={
            "gridRow": b["grid_row"],
            "gridColumn": b["grid_col"],
            "--cube-fill-pct": b["fullness_bar"] + "%",
        },
    )


def _mempool_cube() -> rx.Component:
    """Mempool キューブ（青系、左上固定）。容量に対する充填率も同じく可視化。
    最初のブロックへチェーンコネクタが伸びる。
    """
    return rx.box(
        rx.box(
            rx.text("MEMPOOL", size="1", weight="bold",
                    color="var(--blue-12)",
                    style={"letterSpacing": "0.14em"}),
            rx.text(StakingDashboardState.mempool_tx_count.to_string(),
                    size="5", weight="bold", color="var(--blue-12)",
                    style={"letterSpacing": "-0.02em"}),
            rx.box(
                rx.text(StakingDashboardState.mempool_size_kb, " KB", size="1",
                        weight="bold", color="var(--blue-12)"),
                rx.cond(
                    StakingDashboardState.mempool_capacity_kb != "",
                    rx.text("(", StakingDashboardState.mempool_fullness_pct, "%)",
                            size="1", color="var(--blue-11)"),
                    rx.text(AuthState.t["staking_mempool_tx_unit"], size="1",
                            color="var(--blue-11)"),
                ),
                style={"display": "flex", "flexDirection": "column",
                       "alignItems": "center", "gap": "1px"},
            ),
            class_name="cdn-cube-content",
        ),
        _mempool_flow_node(StakingDashboardState.mempool_connector),
        class_name="cdn-cube cdn-cube-mempool",
        key="__mempool__",
        style={
            "gridRow": "1",
            "gridColumn": "1",
            "--cube-fill-pct": StakingDashboardState.mempool_fullness_bar + "%",
        },
    )


def _saturation_info_card() -> rx.Component:
    """飽和点とソフトキャップの解説カード。"""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("info", size=14, color="var(--blue-9)"),
                rx.text(AuthState.t["staking_saturation_info_title"], size="1", weight="bold", color="var(--gray-12)", letter_spacing="0.04em"),
                spacing="2", align="center",
            ),
            rx.grid(
                rx.vstack(
                    rx.text(AuthState.t["staking_soft_cap_label"], size="1", color="var(--gray-10)", weight="medium"),
                    rx.hstack(
                        rx.text(StakingDashboardState.soft_cap_ada_display, size="3", weight="bold", color="var(--gray-12)"),
                        rx.text("ADA", size="1", color="var(--gray-10)"),
                        spacing="1", align="baseline",
                    ),
                    rx.text(AuthState.t["staking_soft_cap_formula"], size="1", color="var(--gray-9)"),
                    spacing="0", align_items="start",
                ),
                rx.vstack(
                    rx.text(AuthState.t["staking_saturation_point_label"], size="1", color="var(--gray-10)", weight="medium"),
                    rx.hstack(
                        rx.text(StakingDashboardState.saturation_point_ada_display, size="3", weight="bold", color="var(--amber-11)"),
                        rx.text("ADA", size="1", color="var(--gray-10)"),
                        spacing="1", align="baseline",
                    ),
                    rx.text(AuthState.t["staking_saturation_point_formula"], size="1", color="var(--gray-9)"),
                    spacing="0", align_items="start",
                ),
                columns={"base": "1", "sm": "2"},
                spacing="3",
                width="100%",
            ),
            spacing="2", align_items="start", width="100%",
        ),
        padding="12px 14px",
        border_radius="10px",
        border=f"1px solid {rx.color('gray', 4)}",
        background="var(--gray-2)",
        width="100%",
    )


def _mempool_card() -> rx.Component:
    """Mempool 状態の小カード。tx数・バイトサイズ・容量上限・飽和率バー。"""
    bar = rx.box(
        rx.box(
            width=StakingDashboardState.mempool_fullness_bar + "%",
            height="100%",
            background="var(--blue-9)",
            border_radius="999px",
            transition="width 0.4s ease-out",
        ),
        width="100%",
        height="6px",
        background="var(--gray-4)",
        border_radius="999px",
        overflow="hidden",
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("inbox", size=18, color="var(--blue-9)"),
                rx.text(AuthState.t["staking_mempool_title"], size="2", weight="bold", color="var(--gray-12)"),
                rx.spacer(),
                rx.text(StakingDashboardState.mempool_updated_label, size="1", color="var(--gray-9)"),
                width="100%", align="center",
            ),
            rx.hstack(
                rx.hstack(
                    rx.text(StakingDashboardState.mempool_tx_count.to_string(),
                            size="6", weight="bold", color="var(--gray-12)",
                            style={"letterSpacing": "-0.02em"}),
                    rx.text(AuthState.t["staking_mempool_tx_unit"], size="2", color="var(--gray-10)"),
                    spacing="1", align="baseline",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.text(StakingDashboardState.mempool_size_kb, size="3", weight="bold", color="var(--gray-12)"),
                    rx.text("KB", size="1", color="var(--gray-10)"),
                    rx.cond(
                        StakingDashboardState.mempool_capacity_kb != "",
                        rx.hstack(
                            rx.text("/", size="1", color="var(--gray-9)"),
                            rx.text(StakingDashboardState.mempool_capacity_kb, size="2", color="var(--gray-10)"),
                            rx.text("KB", size="1", color="var(--gray-10)"),
                            spacing="1", align="baseline",
                        ),
                        rx.fragment(),
                    ),
                    rx.cond(
                        StakingDashboardState.mempool_capacity_kb != "",
                        rx.text("(", StakingDashboardState.mempool_fullness_pct, "%)", size="1", color="var(--gray-10)"),
                        rx.fragment(),
                    ),
                    spacing="1", align="baseline",
                ),
                width="100%", align="baseline", wrap="wrap",
            ),
            bar,
            spacing="2", align_items="stretch", width="100%",
        ),
        padding="14px 18px",
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 4)}",
        background="var(--gray-2)",
        width="100%",
    )


def _live_blocks_section() -> rx.Component:
    """直近ブロックをキューブで表示。Mempool 左上 → 右へ新ブロック → 折り返してジグザグ。"""
    live_dot = rx.box(
        width="8px",
        height="8px",
        border_radius="999px",
        background="var(--red-9)",
        flex_shrink="0",
        style={"animation": "cdn_live_dot 1.5s ease-in-out infinite"},
    )
    grid = rx.box(
        _mempool_cube(),
        rx.foreach(StakingDashboardState.live_blocks.to(list[dict[str, str]]), _block_cube),
        class_name="cdn-cubes-grid",
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading(AuthState.t["staking_live_blocks_title"], size="5", as_="h2"),
                rx.hstack(
                    live_dot,
                    rx.text("LIVE", size="1", weight="bold", color="var(--red-11)", letter_spacing="0.16em"),
                    spacing="2",
                    align="center",
                    padding="3px 10px 3px 8px",
                    border_radius="999px",
                    background="var(--red-3)",
                    border="1px solid var(--red-6)",
                ),
                rx.spacer(),
                rx.text(AuthState.t["staking_live_blocks_poll_hint"], size="1", color="var(--gray-10)"),
                width="100%", align="center", wrap="wrap",
            ),
            rx.text(AuthState.t["staking_live_blocks_subtitle"], size="2", color="var(--gray-10)"),
            rx.cond(
                StakingDashboardState.live_blocks,
                grid,
                rx.callout(AuthState.t["staking_live_blocks_empty"], icon="info", color_scheme="gray"),
            ),
            spacing="3", width="100%", align_items="stretch",
        ),
        padding_top="8px", width="100%",
    )


def _heatmap_cell(p) -> rx.Component:
    color_class = rx.match(
        p["color"],
        ("green",  "cdn-heatmap-cell cdn-heatmap-cell-green"),
        ("yellow", "cdn-heatmap-cell cdn-heatmap-cell-yellow"),
        ("pink",   "cdn-heatmap-cell cdn-heatmap-cell-pink"),
        "cdn-heatmap-cell cdn-heatmap-cell-gray",
    )
    return rx.box(
        class_name=color_class,
        custom_attrs={"title": p["ticker"] + " — " + p["total"] + " blocks (last 5 ep)"},
    )


def _heatmap_legend_item(swatch_class: str, label, count) -> rx.Component:
    return rx.hstack(
        rx.box(class_name="cdn-heatmap-legend-swatch " + swatch_class),
        rx.text(label, " (", count.to_string(), ")",
                size="1", color="var(--gray-11)", weight="medium",
                style={"whiteSpace": "nowrap"}),
        spacing="2", align="center", flex_shrink="0",
    )


def _heatmap_section() -> rx.Component:
    """全アクティブプールを直近5エポックのブロック数で色分けしたヒートマップ。
    凡例: 50+ 緑 / 10-49 黄 / 1-9 ピンク / 0 グレー。
    親コンテナ (max-width 1130px) を突き抜けてビューポート全幅まで広げる。
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading(AuthState.t["staking_heatmap_title"], size="5", as_="h2"),
                rx.spacer(),
                rx.text(AuthState.t["staking_heatmap_subtitle"], size="1", color="var(--gray-10)"),
                width="100%", align="center", wrap="wrap",
            ),
            rx.hstack(
                _heatmap_legend_item("cdn-heatmap-cell-green",  "50+",   StakingDashboardState.heatmap_count_green),
                _heatmap_legend_item("cdn-heatmap-cell-yellow", "10-49", StakingDashboardState.heatmap_count_yellow),
                _heatmap_legend_item("cdn-heatmap-cell-pink",   "1-9",   StakingDashboardState.heatmap_count_pink),
                _heatmap_legend_item("cdn-heatmap-cell-gray",   "0",     StakingDashboardState.heatmap_count_gray),
                spacing="4", align="center", wrap="wrap",
            ),
            rx.cond(
                StakingDashboardState.heatmap_pools,
                rx.box(
                    rx.foreach(StakingDashboardState.heatmap_pools.to(list[dict[str, str]]), _heatmap_cell),
                    class_name="cdn-heatmap-grid",
                ),
                rx.callout(AuthState.t["staking_heatmap_empty"], icon="info", color_scheme="gray"),
            ),
            spacing="3", align_items="stretch", width="100%",
        ),
        padding_top="8px", width="100%",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


def _user_delegation_card(p) -> rx.Component:
    """1 件のステークアドレスとその委任先プールカードを上下に並べて表示する。
    プールカードは SPO 一覧と同じ意匠（_pool_card）を再利用。
    """
    from cardanoism.pages.staking_spo import _pool_card

    address_label = rx.hstack(
        rx.icon("wallet", size=14, color="var(--amber-11)"),
        rx.text(p["nickname"], size="2", weight="bold", color="var(--gray-12)"),
        rx.text(
            p["address"],
            size="1", color="var(--gray-9)",
            style={
                "fontFamily": "var(--code-font-family, ui-monospace, monospace)",
                "whiteSpace": "nowrap",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                "maxWidth": "320px",
            },
        ),
        spacing="2", align="center", wrap="wrap", width="100%",
    )

    body = rx.cond(
        p["has_pool"] != "",
        _pool_card(p),
        rx.box(
            rx.hstack(
                rx.icon("info", size=14, color="var(--gray-9)"),
                rx.text(
                    AuthState.t["staking_delegation_unset"],
                    size="2", color="var(--gray-10)",
                ),
                spacing="2", align="center",
            ),
            padding="14px 18px",
            border=f"1px dashed {rx.color('gray', 5)}",
            border_radius="10px",
            background="var(--gray-2)",
            width="100%",
        ),
    )

    return rx.vstack(
        address_label,
        body,
        spacing="2", align="stretch", width="100%",
    )


def _user_delegation_section() -> rx.Component:
    """ログインユーザーのステークアドレスとその委任先を表示する。
    未ログイン: ログイン CTA
    アドレス未登録: 登録への導線
    """
    head = rx.hstack(
        rx.icon("wallet", size=16, color="var(--amber-11)"),
        rx.text(
            AuthState.t["staking_my_delegations_title"],
            size="3", weight="bold", color="var(--gray-12)",
        ),
        rx.spacer(),
        rx.cond(
            AuthState.is_logged_in,
            rx.link(
                rx.button(
                    rx.icon("settings", size=14),
                    rx.text(AuthState.t["staking_my_delegations_manage"], size="1"),
                    variant="soft",
                    color_scheme="amber",
                    size="1",
                    cursor="pointer",
                ),
                href="/mypage?tab=stake",
                underline="none",
            ),
            rx.fragment(),
        ),
        spacing="2", align="center", width="100%",
    )

    logged_out_body = rx.vstack(
        rx.icon("lock", size=22, color="var(--gray-9)"),
        rx.text(
            AuthState.t["staking_my_delegations_login_required"],
            size="2", color="var(--gray-10)", text_align="center",
        ),
        rx.button(
            rx.icon("log-in", size=14),
            rx.text(AuthState.t["ga_ai_login_required_btn"], size="2"),
            color_scheme="amber",
            cursor="pointer",
            on_click=AuthState.open_login_modal,
        ),
        spacing="2",
        align="center",
        padding="20px",
    )

    empty_body = rx.vstack(
        rx.icon("wallet-minimal", size=22, color="var(--gray-9)"),
        rx.text(
            AuthState.t["staking_my_delegations_empty"],
            size="2", color="var(--gray-10)", text_align="center",
        ),
        rx.link(
            rx.button(
                rx.icon("plus", size=14),
                rx.text(AuthState.t["staking_my_delegations_add"], size="2"),
                color_scheme="amber",
                cursor="pointer",
            ),
            href="/mypage?tab=stake",
            underline="none",
        ),
        spacing="2",
        align="center",
        padding="20px",
    )

    list_body = rx.vstack(
        rx.foreach(StakingDashboardState.user_delegated_pools, _user_delegation_card),
        spacing="4",
        width="100%",
        align="stretch",
    )

    body = rx.cond(
        AuthState.is_logged_in,
        rx.cond(
            StakingDashboardState.user_delegated_pools.length() == 0,
            empty_body,
            list_body,
        ),
        logged_out_body,
    )

    return rx.box(
        rx.vstack(
            head,
            body,
            spacing="3",
            width="100%",
            align="stretch",
        ),
        padding="16px 20px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-1)",
        width="100%",
    )


@template(
    route="/staking",
    title="ステーキング | Cardanoism",
    on_load=StakingDashboardState.on_load_dashboard,
)
def staking_page() -> rx.Component:
    return rx.cond(
        StakingDashboardState.load,
        rx.box(
            rx.html(DASHBOARD_CSS),
            login_modal(),
            rx.vstack(
                _breadcrumb(),
                staking_subnav("dashboard"),
                _saturation_info_card(),
                _user_delegation_section(),
                _live_blocks_section(),
                _heatmap_section(),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
            on_mount=StakingDashboardState.start_live_polling,
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
