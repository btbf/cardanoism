"""DashboardState: ログインユーザー向けトップダッシュボードの State。

Phase A:
  - お気に入り (catalyst / governance)
  - 委任先 SPO + DRep のサマリー (リレー警告含む)
  - 委任先 DRep の直近投票
  - 通知設定サマリー (channel + event)

Phase B:
  - 委任先プールの実績 (block_history_5ep / apy_history_7ep)
  - 直近ステーキング報酬 (stake_rewards テーブルから)
  - 未投票 GA リスト (本人 DRep / 委任先 DRep の両方)
  - 締切が近い GA
  - エポック情報 + トレジャリー残高ミニカード
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import reflex as rx

from cardanoism.backend import auth_db
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.db_connect import get_db, _epoch_to_date, _attach_voting_summary
from cardanoism.backend.pool_db import get_pool
from cardanoism.backend.drep_db import get_drep
from cardanoism.backend.vote_db import get_votes_by_drep
from cardanoism.backend.stake_rewards_db import (
    get_recent_rewards,
    get_total_rewards,
    has_rewards_for_addresses,
)
from cardanoism.backend.koios import get_tip
from cardanoism.backend.treasury_db import get_latest_treasury_snapshot
from cardanoism.backend.price import format_ada

logger = logging.getLogger(__name__)

# 各セクションでの最大表示件数
FAVORITES_PREVIEW_LIMIT = 5
DREP_VOTES_PREVIEW_LIMIT = 5
UNVOTED_GA_LIMIT = 5
RECENT_REWARDS_EPOCHS = 5

# Cardano mainnet エポック長 (= 5 days)
EPOCH_LENGTH_SECONDS = 432000


class DashboardState(rx.State):
    """ログイン時トップ (`/`) のダッシュボード用 State。"""

    load: bool = False
    # セクションごとの「データ取得中」フラグ。on_load の各ステップで
    # 順次 False に倒して、UI 側が rx.cond でスピナー → 中身に切替できるように。
    favorites_loading: bool = False
    delegations_loading: bool = False
    pool_perf_loading: bool = False
    unvoted_gas_loading: bool = False
    epoch_treasury_loading: bool = False
    notifications_loading: bool = False

    # お気に入り (プレビュー上位 N + 総数)
    catalyst_favorites: list[dict[str, str]] = []
    catalyst_fav_count: int = 0
    governance_favorites: list[dict[str, str]] = []
    governance_fav_count: int = 0

    # 委任先サマリー (stake_address 単位)
    # 各 entry: nickname / address / verified / pool_id / pool_ticker / pool_name /
    #          relay_alive / drep_id / drep_name / drep_role
    delegations: list[dict[str, str]] = []

    # 委任先 DRep ごとの直近投票 (drep_id → [vote, ...])
    # vote: { proposal_id, proposal_title, vote, block_time }
    drep_recent_votes: dict[str, list[dict[str, str]]] = {}

    # 通知 channel サマリー: {channel_type: enabled_bool_str}
    notification_channels: dict[str, str] = {}
    # 通知 event サマリー: {event_type: "1" | "0"}
    notification_events: dict[str, str] = {}

    # リレー警告 (relay_alive=0 の委任先)
    relay_warnings_count: int = 0

    # ── Phase B 追加 ──────────────────────────────────────

    # 委任先プールの実績 (各 stake_address ごと)
    # entry: { nickname, pool_id, pool_ticker, blocks_5ep_total, apy_avg_pct }
    pool_performances: list[dict[str, str]] = []

    # stake_address 軸での報酬データ (プール実績カード内に popover で表示)
    # rewards_by_address: { address: [{epoch_no, amount_ada}, ...] }
    rewards_by_address: dict[str, list[dict[str, str]]] = {}
    # total_rewards_by_address: { address: total_ada_str }
    total_rewards_by_address: dict[str, str] = {}
    # 通知 OFF などで報酬キャッシュが無い stake_address
    rewards_missing_addresses: list[str] = []

    # 未投票 GA: 本人 DRep が未投票な active GA
    # entry: { proposal_id, title, title_ja, proposal_type, expiration, drep_id, drep_name }
    unvoted_gas_self: list[dict[str, str]] = []
    # 委任先 DRep が未投票な active GA
    unvoted_gas_delegated: list[dict[str, str]] = []

    # エポック情報
    current_epoch_str: str = ""
    next_epoch_in_seconds: int = 0
    next_epoch_in_label: str = ""  # "残り 2日 4時間" 等

    # トレジャリー残高ミニカード
    treasury_balance_ada: str = ""
    treasury_epoch_str: str = ""

    @rx.event
    async def on_load(self):
        """段階的に各セクションのデータをロードする。

        各 `_load_*` の前後で *_loading を切り替え、yield でフレームに反映する
        ことで「データが揃ったセクションから順に表示」する UX を実現する。
        """
        # まずレイアウトを表示できるよう load=True にしつつ、全セクションを
        # ロード中マーク。これで UI は各セクションでスピナーを出せる。
        self.favorites_loading = True
        self.delegations_loading = True
        self.pool_perf_loading = True
        self.unvoted_gas_loading = True
        self.epoch_treasury_loading = True
        self.notifications_loading = True
        self.load = True
        yield

        try:
            auth = await self.get_state(AuthState)
            if not auth.user_id:
                self._reset()
                # ロード中フラグを全部 False に
                self.favorites_loading = False
                self.delegations_loading = False
                self.pool_perf_loading = False
                self.unvoted_gas_loading = False
                self.epoch_treasury_loading = False
                self.notifications_loading = False
                return

            # UI が dict[key] アクセスで undefined エラーにならないよう、
            # データ取得前に全キーを空値で埋めておく。
            stake_addrs = [
                str(a.get("address") or "")
                for a in (auth.stake_addresses or [])
                if a.get("address")
            ]
            self.rewards_by_address = {a: [] for a in stake_addrs}
            self.total_rewards_by_address = {a: "0" for a in stake_addrs}
            yield

            # 軽い処理から並べる (DB SELECT のみで Koios 不要なものを優先)
            self._load_favorites(auth.user_id)
            self.favorites_loading = False
            yield

            self._load_notifications(auth.user_id)
            self.notifications_loading = False
            yield

            self._load_delegations(auth.stake_addresses or [])
            self.delegations_loading = False
            yield

            self._load_governance_actions(auth.stake_addresses or [])
            self.unvoted_gas_loading = False
            yield

            # Koios `/totals` 1 回叩く (重め)
            self._load_pool_performances(auth.stake_addresses or [])
            self.pool_perf_loading = False
            yield

            # Koios `/tip` 1 回叩く
            self._load_epoch_and_treasury()
            self.epoch_treasury_loading = False
            yield

            # 報酬は popover で個別に表示するためグローバル loading 無し
            self._load_rewards(auth.stake_addresses or [])
        except Exception as e:  # noqa: BLE001
            logger.exception("DashboardState.on_load: %s", e)
        finally:
            # エラーで途中終了した場合もすべての loading を False にして UI を solidify
            self.favorites_loading = False
            self.delegations_loading = False
            self.pool_perf_loading = False
            self.unvoted_gas_loading = False
            self.epoch_treasury_loading = False
            self.notifications_loading = False

    # ── 内部ロード ──────────────────────────────

    def _reset(self) -> None:
        self.catalyst_favorites = []
        self.catalyst_fav_count = 0
        self.governance_favorites = []
        self.governance_fav_count = 0
        self.delegations = []
        self.drep_recent_votes = {}
        self.notification_channels = {}
        self.notification_events = {}
        self.relay_warnings_count = 0
        self.pool_performances = []
        self.rewards_by_address = {}
        self.total_rewards_by_address = {}
        self.rewards_missing_addresses = []
        self.unvoted_gas_self = []
        self.unvoted_gas_delegated = []
        self.current_epoch_str = ""
        self.next_epoch_in_seconds = 0
        self.next_epoch_in_label = ""
        self.treasury_balance_ada = ""
        self.treasury_epoch_str = ""

    def _load_favorites(self, user_id: int) -> None:
        try:
            cat = auth_db.get_favorites(user_id, type="catalyst") or []
        except Exception as e:  # noqa: BLE001
            logger.warning("get_favorites(catalyst) failed: %s", e)
            cat = []
        try:
            gov = auth_db.get_ga_favorites(user_id) or []
        except Exception as e:  # noqa: BLE001
            logger.warning("get_ga_favorites failed: %s", e)
            gov = []

        self.catalyst_fav_count = len(cat)
        self.governance_fav_count = len(gov)

        self.catalyst_favorites = [
            {
                "proposal_uuid": str(r.get("proposal_uuid") or ""),
                "title": str(r.get("title") or ""),
                "title_ja": str(r.get("title_ja") or ""),
                "fund_label": str(r.get("fund_label") or ""),
                "funding_status": str(r.get("funding_status") or ""),
            }
            for r in cat[:FAVORITES_PREVIEW_LIMIT]
        ]

        self.governance_favorites = [
            {
                "proposal_uuid": str(r.get("proposal_uuid") or ""),
                "title": str(r.get("title") or ""),
                "title_ja": str(r.get("title_ja") or ""),
                "proposal_type": str(r.get("proposal_type") or ""),
                "ratified_epoch": "" if r.get("ratified_epoch") is None else str(r.get("ratified_epoch")),
                "enacted_epoch":  "" if r.get("enacted_epoch")  is None else str(r.get("enacted_epoch")),
            }
            for r in gov[:FAVORITES_PREVIEW_LIMIT]
        ]

    def _load_notifications(self, user_id: int) -> None:
        try:
            channels = auth_db.get_notification_channels(user_id) or []
        except Exception as e:  # noqa: BLE001
            logger.warning("get_notification_channels failed: %s", e)
            channels = []
        # {channel_type: "1" if enabled else "0"}
        self.notification_channels = {
            str(c.get("channel_type") or ""): "1" if c.get("enabled") else "0"
            for c in channels
            if c.get("channel_type")
        }

        try:
            settings = auth_db.get_notification_settings(user_id) or {}
        except Exception as e:  # noqa: BLE001
            logger.warning("get_notification_settings failed: %s", e)
            settings = {}
        # 既存戻り値が dict[event_type → bool] か dict[event_type → "1"/"0"] か
        # auth_db 側の実装に依存するが、bool でも str でも辞書化して扱えるよう正規化。
        self.notification_events = {
            str(k): "1" if (v if isinstance(v, bool) else str(v) in ("1", "true", "True")) else "0"
            for k, v in settings.items()
        }

    def _load_delegations(self, stake_addresses: list[dict]) -> None:
        out: list[dict[str, str]] = []
        votes_map: dict[str, list[dict[str, str]]] = {}
        relay_warning_cnt = 0

        for addr in stake_addresses:
            entry: dict[str, str] = {
                "nickname":   str(addr.get("nickname") or ""),
                "address":    str(addr.get("address") or ""),
                "verified":   "1" if addr.get("verified") else "0",
                "role":       str(addr.get("role") or ""),
                "pool_id":    "",
                "pool_ticker": "",
                "pool_name":  "",
                "relay_alive": "1",  # 未取得は OK 扱い
                "drep_id":    "",
                "drep_name":  "",
            }

            pool_id = str(addr.get("delegated_pool_id") or "")
            if pool_id:
                try:
                    p = get_pool(pool_id)
                except Exception as e:  # noqa: BLE001
                    logger.warning("get_pool(%s) failed: %s", pool_id, e)
                    p = None
                entry["pool_id"] = pool_id
                if p:
                    entry["pool_ticker"] = str(p.get("ticker") or "")
                    entry["pool_name"]   = str(p.get("pool_name") or "")
                    relay = p.get("relay_alive")
                    # NULL/未確認は alive 扱い、明示的に 0 のときだけ警告
                    if relay is not None and int(relay) == 0:
                        entry["relay_alive"] = "0"
                        relay_warning_cnt += 1

            drep_id = str(addr.get("delegated_drep_id") or "")
            if drep_id:
                entry["drep_id"] = drep_id
                try:
                    d = get_drep(drep_id)
                except Exception as e:  # noqa: BLE001
                    logger.warning("get_drep(%s) failed: %s", drep_id, e)
                    d = None
                if d:
                    entry["drep_name"] = str(d.get("given_name") or "")
                # アクティブ GA × この DRep の投票状況を 1 SQL で取得 (LEFT JOIN)。
                # 「投票していれば Yes/No/Abstain + rationale、未投票なら vote が空」になる。
                if drep_id not in votes_map:
                    try:
                        votes_map[drep_id] = self._select_active_gas_with_drep_vote(drep_id)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "active GA + drep vote query failed (drep=%s): %s", drep_id, e,
                        )
                        votes_map[drep_id] = []
            elif str(addr.get("role") or "") == "abstain":
                # always_abstain はテーブルに無いが UI で表示分岐したいので drep_id だけ補完
                entry["drep_id"] = "always_abstain"

            out.append(entry)

        # UI 側で `drep_recent_votes[drep_id]` を参照するため、delegations に
        # 含まれる全 drep_id (always_abstain 含む) を空リストで保証しておく。
        # これがないと未取得 key へのアクセスで undefined エラーになる。
        for entry in out:
            drep_id = str(entry.get("drep_id") or "")
            if drep_id:
                votes_map.setdefault(drep_id, [])

        self.delegations = out
        self.drep_recent_votes = votes_map
        self.relay_warnings_count = relay_warning_cnt

    # ── Phase B ローダ ─────────────────────────────

    def _load_pool_performances(self, stake_addresses: list[dict]) -> None:
        """委任先プールの実績 (live_stake / 飽和率 / 委任者数 / 5ep ブロック / 7ep APY 等) を整形する。

        staking_spo.format_pool_card_data を流用して SPO 一覧と表記を揃える。
        """
        # 循環 import を避けるためここでのみ import
        from cardanoism.pages.staking_spo import format_pool_card_data
        from cardanoism.backend.koios import get_totals

        # サチュレーション点を 1 回だけ計算する
        # (45B ADA - 残リザーブ) / k=500
        MAX_SUPPLY_LOVELACE = 45_000_000_000 * 1_000_000
        OPTIMAL_POOL_COUNT_K = 500
        saturation_point_lovelace = 0
        try:
            totals = get_totals() or {}
            reserves = int(totals.get("reserves") or 0)
            if reserves > 0:
                soft_cap = MAX_SUPPLY_LOVELACE - reserves
                saturation_point_lovelace = soft_cap // OPTIMAL_POOL_COUNT_K
        except Exception as e:  # noqa: BLE001
            logger.warning("get_totals for saturation calc failed: %s", e)

        out: list[dict[str, str]] = []
        seen_pools: set[str] = set()
        for addr in stake_addresses:
            pool_id = str(addr.get("delegated_pool_id") or "")
            if not pool_id or pool_id in seen_pools:
                continue
            seen_pools.add(pool_id)
            try:
                p = get_pool(pool_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("get_pool(%s) failed: %s", pool_id, e)
                continue
            if not p:
                continue
            formatted = format_pool_card_data(
                p,
                saturation_point_lovelace=saturation_point_lovelace,
            )
            formatted["nickname"] = str(addr.get("nickname") or "")
            # popover で rewards_by_address / total_rewards_by_address を引くために stake_address も保持
            formatted["address"] = str(addr.get("address") or "")
            out.append(formatted)
        self.pool_performances = out

    def _load_rewards(self, stake_addresses: list[dict]) -> None:
        """stake_rewards テーブルから直近 N エポック分と累積を取得し、address 軸で dict 化する。

        プール実績カード内の popover で `rewards_by_address[address]` で参照する。
        """
        addrs = [
            str(a.get("address") or "") for a in stake_addresses if a.get("address")
        ]
        if not addrs:
            self.rewards_by_address = {}
            self.total_rewards_by_address = {}
            self.rewards_missing_addresses = []
            return

        rows = get_recent_rewards(addrs, n_epochs=RECENT_REWARDS_EPOCHS)
        by_addr: dict[str, list[dict[str, str]]] = {}
        for r in rows:
            sa = str(r.get("stake_address") or "")
            lov = int(r.get("amount_lovelace") or 0)
            by_addr.setdefault(sa, []).append({
                "epoch_no":   str(r.get("epoch_no") or ""),
                "amount_ada": format_ada(lov, integer=False) if lov else "0",
            })
        # 取れなかったアドレスは空リストで埋めて UI 側の参照ミスを避ける
        for sa in addrs:
            by_addr.setdefault(sa, [])
        self.rewards_by_address = by_addr

        totals_map = get_total_rewards(addrs)
        self.total_rewards_by_address = {
            sa: (format_ada(total, integer=False) if total else "0")
            for sa, total in totals_map.items()
        }
        # キャッシュ無しアドレスも空文字で初期化
        for sa in addrs:
            self.total_rewards_by_address.setdefault(sa, "0")

        cached = has_rewards_for_addresses(addrs)
        self.rewards_missing_addresses = [a for a in addrs if a not in cached]

    def _load_epoch_and_treasury(self) -> None:
        """エポック残時間とトレジャリー残高を取得する。"""
        try:
            tip = get_tip()
        except Exception as e:  # noqa: BLE001
            logger.warning("get_tip failed: %s", e)
            tip = None

        if tip:
            epoch_no = tip.get("epoch_no")
            epoch_slot = tip.get("epoch_slot")
            if epoch_no is not None:
                self.current_epoch_str = str(epoch_no)
            if epoch_slot is not None:
                remaining = max(0, EPOCH_LENGTH_SECONDS - int(epoch_slot))
                self.next_epoch_in_seconds = remaining
                days = remaining // 86400
                hours = (remaining % 86400) // 3600
                minutes = (remaining % 3600) // 60
                if days > 0:
                    self.next_epoch_in_label = f"{days}日{hours}時間"
                elif hours > 0:
                    self.next_epoch_in_label = f"{hours}時間{minutes}分"
                else:
                    self.next_epoch_in_label = f"{minutes}分"

        try:
            snap = get_latest_treasury_snapshot()
        except Exception as e:  # noqa: BLE001
            logger.warning("get_latest_treasury_snapshot failed: %s", e)
            snap = None
        if snap:
            try:
                self.treasury_balance_ada = format_ada(int(snap.get("treasury") or 0), integer=True)
                self.treasury_epoch_str = str(snap.get("epoch_no") or "")
            except (TypeError, ValueError):
                pass

    def _load_governance_actions(self, stake_addresses: list[dict]) -> None:
        """未投票 GA (本人 / 委任先) と締切が近い GA を取得する。"""
        # 現在エポックは _load_epoch_and_treasury で設定済みのものを利用
        try:
            cur_epoch = int(self.current_epoch_str) if self.current_epoch_str else 0
        except (TypeError, ValueError):
            cur_epoch = 0

        # 自分が DRep として登録された stake_address (role="drep")
        own_drep_ids = [
            str(a.get("delegated_drep_id") or "")
            for a in stake_addresses
            if str(a.get("role") or "") == "drep" and a.get("delegated_drep_id")
        ]
        # 重複除去
        own_drep_ids = list(dict.fromkeys(own_drep_ids))
        try:
            self.unvoted_gas_self = self._select_unvoted_gas_for_dreps(own_drep_ids, cur_epoch)
        except Exception as e:  # noqa: BLE001
            logger.warning("unvoted_gas_self failed: %s", e)
            self.unvoted_gas_self = []

        # 委任先 DRep (role != "drep" の通常委任者の delegated_drep_id)
        delegated_drep_ids = [
            str(a.get("delegated_drep_id") or "")
            for a in stake_addresses
            if str(a.get("role") or "") != "drep"
            and a.get("delegated_drep_id")
        ]
        delegated_drep_ids = list(dict.fromkeys(delegated_drep_ids))
        try:
            self.unvoted_gas_delegated = self._select_unvoted_gas_for_dreps(
                delegated_drep_ids, cur_epoch,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("unvoted_gas_delegated failed: %s", e)
            self.unvoted_gas_delegated = []

    # ── 内部 SQL ───────────────────────────────────

    @staticmethod
    def _select_active_gas_with_drep_vote(drep_id: str) -> list[dict[str, str]]:
        """active GA に対して指定 DRep の投票状況を LEFT JOIN で取得する。

        戻り値の vote が空文字なら「未投票」、Yes/No/Abstain なら投票済み。
        rationale_ja / rationale が含まれていれば UI で「理由ボタン」を出せる。
        """
        if not drep_id:
            return []
        sql = (
            "SELECT g.proposal_id, g.title, g.title_ja, g.proposal_type, g.expiration, "
            "       v.vote, v.rationale, v.rationale_ja, v.meta_url "
            "FROM governance_actions g "
            "LEFT JOIN proposal_votes v ON g.proposal_id = v.proposal_id "
            "                          AND v.voter_role = 'DRep' "
            "                          AND v.voter_id = ? "
            "WHERE g.ratified_epoch IS NULL "
            "  AND g.dropped_epoch IS NULL "
            "  AND g.expired_epoch IS NULL "
            "  AND g.enacted_epoch IS NULL "
            "ORDER BY g.expiration ASC "
            f"LIMIT {DREP_VOTES_PREVIEW_LIMIT}"
        )
        with get_db() as (cursor, _):
            cursor.execute(sql, (drep_id,))
            rows = [dict(r) for r in cursor.fetchall()]
        return [
            {
                "proposal_id":   str(r.get("proposal_id") or ""),
                "title":         str(r.get("title") or ""),
                "title_ja":      str(r.get("title_ja") or ""),
                "proposal_type": str(r.get("proposal_type") or ""),
                "expiration":    "" if r.get("expiration") is None else str(r.get("expiration")),
                "vote":          str(r.get("vote") or ""),
                "rationale":     str(r.get("rationale") or ""),
                "rationale_ja":  str(r.get("rationale_ja") or ""),
                "meta_url":      str(r.get("meta_url") or ""),
            }
            for r in rows
        ]

    @staticmethod
    def _select_unvoted_gas_for_dreps(
        drep_ids: list[str], current_epoch: int,
    ) -> list[dict[str, str]]:
        """指定 DRep が未投票な active GA を返す。drep_ids 空ならスキップ。"""
        if not drep_ids:
            return []
        # 重複時に同じ GA を 1 回だけ返すため、UNION ではなく EXISTS の否定で表現する。
        # drep_ids のうち「いずれか 1 つでも投票していれば対象から除外」する。
        placeholders = ",".join(["?"] * len(drep_ids))
        where = [
            "g.ratified_epoch IS NULL",
            "g.dropped_epoch IS NULL",
            "g.expired_epoch IS NULL",
            "g.enacted_epoch IS NULL",
            "NOT EXISTS ("
            "  SELECT 1 FROM proposal_votes v "
            f"  WHERE v.proposal_id = g.proposal_id "
            f"    AND v.voter_role = 'DRep' "
            f"    AND v.voter_id IN ({placeholders})"
            ")",
        ]
        params: list = list(drep_ids)
        if current_epoch > 0:
            where.append("g.expiration > ?")
            params.append(current_epoch)
        sql = (
            "SELECT g.proposal_id, g.title, g.title_ja, g.proposal_type, g.expiration, "
            "g.block_time, g.proposed_epoch, "
            "s.drep_yes_pct, s.drep_no_pct, "
            "s.pool_yes_pct, s.pool_no_pct, "
            "s.committee_yes_pct, s.committee_no_pct "
            "FROM governance_actions g "
            "LEFT JOIN proposal_voting_summary s ON g.proposal_id = s.proposal_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY g.expiration ASC "
            f"LIMIT {UNVOTED_GA_LIMIT}"
        )
        with get_db() as (cursor, _):
            cursor.execute(sql, params)
            rows = [dict(r) for r in cursor.fetchall()]

        from cardanoism.backend.params_db import get_protocol_params
        protocol_params = get_protocol_params() or {}

        out: list[dict[str, str]] = []
        for r in rows:
            exp = r.get("expiration")
            _attach_voting_summary(r, protocol_params)
            out.append({
                "proposal_id":     str(r.get("proposal_id") or ""),
                "title":           str(r.get("title") or ""),
                "title_ja":        str(r.get("title_ja") or ""),
                "proposal_type":   str(r.get("proposal_type") or ""),
                "expiration":      "" if exp is None else str(exp),
                "expiration_date": _epoch_to_date(
                    exp, r.get("proposed_epoch"), r.get("block_time"),
                ),
                "drep_yes_pct":       str(r.get("drep_yes_pct") or "0"),
                "drep_threshold_pct": str(r.get("drep_threshold_pct") or ""),
                "drep_status":        str(r.get("drep_status") or ""),
                "drep_applicable":    str(r.get("drep_applicable") or "no"),
            })
        return out
