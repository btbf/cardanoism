"""
home_state.py
TOP ページ (/) のライブ数値を集約する軽量 State。
"""
from __future__ import annotations

import logging
from typing import Any

import reflex as rx

from cardanoism.backend.db_connect import ensure_warm, get_db
from cardanoism.backend.price import format_ada_short_ja, format_ada_short_en

logger = logging.getLogger(__name__)


class HomeState(rx.State):
    """TOP ページ用の集計値。on_load で初回取得する。"""

    loaded: bool = False

    # 表示用の文字列（既に書式化済み）
    treasury_ada_ja:    str = "—"   # 例: "1.5 億 ADA"
    treasury_ada_en:    str = "—"   # 例: "1.5B ADA"
    active_ga_count:    str = "0"
    drep_count:         str = "0"
    blocks_24h:         str = "0"

    # Cardano 憲法バージョン（タイトル抽出 / 例: "v1.0"）
    constitution_version_label: str = ""

    def warm_up(self):
        """軽い warm-up + 集計取得。失敗しても TOP 表示には影響しない。"""
        ensure_warm()
        self.loaded = False
        try:
            self._fetch_treasury()
            self._fetch_governance_counts()
            self._fetch_drep_count()
            self._fetch_blocks_24h()
            self._fetch_constitution_version()
        except Exception as e:
            logger.warning("HomeState.warm_up: %s", e)
        self.loaded = True

    def _fetch_treasury(self) -> None:
        try:
            with get_db() as (cursor, _):
                cursor.execute(
                    "SELECT treasury FROM treasury_snapshot WHERE id = 1"
                )
                row = cursor.fetchone()
            if row and row.get("treasury"):
                lovelace = int(row["treasury"])
                ada = lovelace // 1_000_000
                self.treasury_ada_ja = format_ada_short_ja(ada) + " ADA"
                self.treasury_ada_en = format_ada_short_en(ada) + " ADA"
        except Exception as e:
            logger.debug("home _fetch_treasury: %s", e)

    def _fetch_governance_counts(self) -> None:
        try:
            with get_db() as (cursor, _):
                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM governance_actions
                    WHERE ratified_epoch IS NULL
                      AND enacted_epoch IS NULL
                      AND dropped_epoch IS NULL
                      AND expired_epoch IS NULL
                    """
                )
                row = cursor.fetchone()
                if row:
                    self.active_ga_count = f"{int(row['cnt']):,}"
        except Exception as e:
            logger.debug("home _fetch_governance_counts: %s", e)

    def _fetch_drep_count(self) -> None:
        try:
            with get_db() as (cursor, _):
                # registered かつ active な DRep をカウント（dreps テーブルのフラグ）
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM dreps "
                    "WHERE registered = 1 AND active = 1"
                )
                row = cursor.fetchone()
                if row:
                    self.drep_count = f"{int(row['cnt']):,}"
        except Exception as e:
            logger.debug("home _fetch_drep_count: %s", e)

    def _fetch_blocks_24h(self) -> None:
        try:
            with get_db() as (cursor, _):
                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM recent_blocks
                    WHERE block_time >= (NOW() - INTERVAL 1 DAY)
                    """
                )
                row = cursor.fetchone()
                if row:
                    self.blocks_24h = f"{int(row['cnt']):,}"
        except Exception as e:
            logger.debug("home _fetch_blocks_24h: %s", e)

    def _fetch_constitution_version(self) -> None:
        try:
            import re
            with get_db() as (cursor, _):
                cursor.execute(
                    """
                    SELECT title, title_ja FROM governance_actions
                    WHERE proposal_type = 'NewConstitution'
                      AND enacted_epoch IS NOT NULL
                    ORDER BY enacted_epoch DESC LIMIT 1
                    """
                )
                row = cursor.fetchone()
            if row:
                source = (str(row.get("title") or "") + " " +
                          str(row.get("title_ja") or "")).strip()
                m = re.search(r"\b[vV]\s*(\d+(?:\.\d+)?)", source)
                if not m:
                    m = re.search(r"\bversion\s+(\d+(?:\.\d+)?)", source, re.IGNORECASE)
                if m:
                    self.constitution_version_label = "v" + m.group(1)
        except Exception as e:
            logger.debug("home _fetch_constitution_version: %s", e)
