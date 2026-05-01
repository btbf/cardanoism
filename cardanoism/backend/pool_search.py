"""SPO 検索ヘルパー (Phase 3 委任切替用)。

`pools` テーブルからティッカー / プール名 / pool_id_bech32 でフィルタした
最小限のフィールドを返す。フロントエンドの SPO ピッカーから呼ばれる。
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


_BASE_FIELDS = (
    "pool_id_bech32, pool_id_hex, ticker, pool_name, "
    "live_saturation, live_stake, live_delegators, "
    "margin, fixed_cost, pledge, live_pledge, "
    "pool_status, pool_icon_url"
)


def _row_to_dict(row) -> dict[str, Any]:
    if row is None:
        return {}
    out: dict[str, Any] = {}
    for k, v in row.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, bool):
            out[k] = bool(v)
        elif isinstance(v, (int, float)):
            out[k] = v
        else:
            out[k] = str(v)

    # 表示用に整形 (フロント側で Var 演算しないで済ませる)
    # NOTE: live_saturation は Koios → pools テーブルへ格納される時点で
    #       既にパーセント値 (例: 15.15 = 15.15%)。× 100 してはいけない。
    sat_raw = out.get("live_saturation")
    if isinstance(sat_raw, (int, float)):
        out["saturation_pct"] = f"{sat_raw:.1f}%"
    else:
        out["saturation_pct"] = "—"

    deleg = out.get("live_delegators")
    if isinstance(deleg, (int, float)):
        out["delegators_text"] = f"{int(deleg):,}"
    else:
        out["delegators_text"] = "—"

    return out


def search_pools(query: str, limit: int = 30) -> list[dict[str, Any]]:
    """ティッカー / プール名 / pool_id (bech32 prefix) でフィルタする。

    クエリが空の場合はライブステーク降順で先頭 N 件を返す。
    """
    query = (query or "").strip()
    limit = max(1, min(int(limit or 30), 100))

    try:
        with get_db() as (cursor, _):
            if not query:
                cursor.execute(
                    f"""
                    SELECT {_BASE_FIELDS}
                    FROM pools
                    WHERE pool_status = 'registered'
                    ORDER BY live_stake DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                like = f"%{query}%"
                # ティッカー完全一致を最優先、次にティッカー部分一致 / 名前部分一致 / pool_id 前方一致
                cursor.execute(
                    f"""
                    SELECT {_BASE_FIELDS}
                    FROM pools
                    WHERE pool_status = 'registered'
                      AND (
                            ticker = ?
                         OR ticker LIKE ?
                         OR pool_name LIKE ?
                         OR pool_id_bech32 LIKE ?
                      )
                    ORDER BY
                        (ticker = ?) DESC,
                        (ticker LIKE ?) DESC,
                        live_stake DESC
                    LIMIT ?
                    """,
                    (query, like, like, f"{query}%", query, like, limit),
                )
            rows = cursor.fetchall() or []
    except Exception as e:  # noqa: BLE001
        logger.exception("search_pools failed: %s", e)
        return []

    return [_row_to_dict(r) for r in rows if r is not None]


def get_pool_by_bech32(pool_id_bech32: str) -> dict[str, Any]:
    pool_id_bech32 = (pool_id_bech32 or "").strip()
    if not pool_id_bech32:
        return {}
    try:
        with get_db() as (cursor, _):
            cursor.execute(
                f"SELECT {_BASE_FIELDS} FROM pools WHERE pool_id_bech32 = ? LIMIT 1",
                (pool_id_bech32,),
            )
            row = cursor.fetchone()
    except Exception as e:  # noqa: BLE001
        logger.exception("get_pool_by_bech32 failed: %s", e)
        return {}
    return _row_to_dict(row) if row else {}
