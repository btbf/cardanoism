"""
treasury_db.py
トレジャリーページ用テーブル（treasury_snapshot / treasury_withdrawal / ncl_active）の CRUD。

同期は notify_worker.py --event treasury_sync で行う。
ページ側は常に DB を読むだけで、Koios は叩かない。
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


# ============================================================
# treasury_snapshot
# ============================================================

def upsert_treasury_snapshot(epoch_no: int, treasury: int,
                             reserves: int | None = None,
                             supply: int | None = None) -> None:
    """id=1 固定の単一行を常に上書き。ネットワーク切り替えにも追従する。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO treasury_snapshot (id, epoch_no, treasury, reserves, supply)
            VALUES (1, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              epoch_no = VALUES(epoch_no),
              treasury = VALUES(treasury),
              reserves = VALUES(reserves),
              supply   = VALUES(supply)
            """,
            (int(epoch_no), int(treasury), reserves, supply),
        )
        conn.commit()


def get_latest_treasury_snapshot() -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT epoch_no, treasury, reserves, supply, updated_at "
            "FROM treasury_snapshot WHERE id = 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# ============================================================
# treasury_history (エポック別残高)
# ============================================================

def upsert_treasury_history(epoch_no: int, treasury: int,
                            reserves: int | None = None,
                            supply: int | None = None) -> None:
    """treasury_history に1エポック分の残高を upsert する。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO treasury_history (epoch_no, treasury, reserves, supply)
            VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                treasury   = VALUES(treasury),
                reserves   = VALUES(reserves),
                supply     = VALUES(supply),
                fetched_at = CURRENT_TIMESTAMP
            """,
            (int(epoch_no), int(treasury), reserves, supply),
        )
        conn.commit()


def get_treasury_history_recent(n_epochs: int = 6) -> list[dict]:
    """直近 n_epochs エポックの履歴（新しい順）を返す。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT epoch_no, treasury, reserves, supply
            FROM treasury_history
            ORDER BY epoch_no DESC
            LIMIT ?
            """,
            (int(n_epochs),),
        )
        return [dict(r) for r in cursor.fetchall()]


def get_withdrawals_per_epoch(epochs: list[int]) -> dict[int, int]:
    """指定 epoch ごとの outflow 合計 (lovelace) を {epoch: total} で返す。
    treasury_withdrawal.spendable_epoch でグループ化（実際に引き出される時点）。
    対象に存在しないエポックも 0 で初期化。
    """
    out: dict[int, int] = {int(e): 0 for e in epochs}
    if not epochs:
        return out
    placeholders = ",".join(["?"] * len(epochs))
    with get_db() as (cursor, _):
        cursor.execute(
            f"""
            SELECT spendable_epoch AS epoch_no,
                   COALESCE(SUM(amount_lovelace), 0) AS total
            FROM treasury_withdrawal
            WHERE spendable_epoch IN ({placeholders})
            GROUP BY spendable_epoch
            """,
            [int(e) for e in epochs],
        )
        for r in cursor.fetchall():
            out[int(r["epoch_no"])] = int(r["total"] or 0)
    return out


def _format_ada_short(lovelace: int) -> str:
    """Lovelace を ADA に変換し B/M/K の短縮表記で返す（チャート軸ラベル用）。"""
    ada = lovelace / 1_000_000
    if ada >= 1e9:
        return f"{ada / 1e9:.2f}B"
    if ada >= 1e6:
        return f"{ada / 1e6:.1f}M"
    if ada >= 1e3:
        return f"{ada / 1e3:.0f}K"
    return f"{int(ada):,}"


def _select_label_indices(n: int, max_labels: int = 7) -> set[int]:
    """N 点の中から均等に max_labels 個だけインデックスを選ぶ。
    ポイント数が少ない場合は全点を選ぶ。
    """
    if n <= max_labels:
        return set(range(n))
    out: set[int] = set()
    for k in range(max_labels):
        out.add(round(k * (n - 1) / (max_labels - 1)))
    return out


def build_treasury_chart_svg(history: list[dict]) -> str:
    """treasury_history（古い順）から折れ線チャート SVG を生成する。
    ポイント数が多い場合は X 軸ラベルを間引き、値ラベルは省略する。

    Args:
        history: {epoch_no, treasury (lovelace)} の dict リスト（古い順）。

    Returns:
        SVG 文字列。データが 2 点未満なら空文字。
    """
    if len(history) < 2:
        return ""

    W, H = 760, 240
    pad_l, pad_r = 70, 20
    pad_t, pad_b = 36, 44
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b

    treasuries = [int(h["treasury"] or 0) for h in history]
    epochs = [int(h["epoch_no"]) for h in history]
    n = len(history)

    y_min = min(treasuries)
    y_max = max(treasuries)
    if y_max == y_min:
        y_max = y_min + 1
    span = y_max - y_min
    y_pad = span * 0.18
    y_lo = y_min - y_pad
    y_hi = y_max + y_pad

    def xy(i: int, val: int) -> tuple[float, float]:
        x = pad_l + (plot_w * i / (n - 1))
        y = pad_t + plot_h - (plot_h * (val - y_lo) / (y_hi - y_lo))
        return x, y

    points_xy = [xy(i, t) for i, t in enumerate(treasuries)]
    polyline_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points_xy)

    # ポイント数に応じて表示密度を調整
    show_value_labels = n <= 12
    label_indices = _select_label_indices(n, max_labels=7)
    dot_radius = 4.5 if n <= 20 else (3.0 if n <= 50 else 2.0)

    parts: list[str] = [
        f'<svg width="100%" viewBox="0 0 {W} {H}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="display:block;max-width:100%">'
    ]

    # 4 段階の水平グリッド + Y 軸ラベル
    for k in range(5):
        gy = pad_t + plot_h * k / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{W - pad_r}" y2="{gy:.1f}" '
            f'stroke="var(--gray-4)" stroke-width="1" stroke-dasharray="2 4"/>'
        )
        val = y_hi - (y_hi - y_lo) * k / 4
        label = _format_ada_short(int(val))
        parts.append(
            f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="var(--gray-10)">{label}</text>'
        )

    # 値ラベル（点数が少ない時のみ）
    if show_value_labels:
        for (x, y), t in zip(points_xy, treasuries):
            label = _format_ada_short(t)
            parts.append(
                f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" '
                f'font-size="10" font-weight="600" fill="var(--gray-12)">{label}</text>'
            )

    # 折れ線
    parts.append(
        f'<polyline points="{polyline_pts}" fill="none" '
        'stroke="var(--amber-10)" stroke-width="2.5" stroke-linejoin="round"/>'
    )

    # データポイント
    for x, y in points_xy:
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{dot_radius}" '
            'fill="var(--amber-9)" stroke="var(--gray-1)" stroke-width="2"/>'
        )

    # X 軸ラベル（密度を調整）
    for i, ep in enumerate(epochs):
        if i not in label_indices:
            continue
        x, _ = points_xy[i]
        parts.append(
            f'<text x="{x:.1f}" y="{H - pad_b + 18}" text-anchor="middle" '
            f'font-size="10" fill="var(--gray-10)">Epoch {ep}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def get_treasury_history_in_range(start_epoch: int, end_epoch: int) -> list[dict]:
    """指定エポック範囲の treasury_history を古い順で返す。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT epoch_no, treasury, reserves, supply
            FROM treasury_history
            WHERE epoch_no BETWEEN ? AND ?
            ORDER BY epoch_no ASC
            """,
            (int(start_epoch), int(end_epoch)),
        )
        return [dict(r) for r in cursor.fetchall()]


def get_existing_history_epochs(start_epoch: int, end_epoch: int) -> set[int]:
    """指定範囲で既に treasury_history に存在するエポック番号の set。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT epoch_no FROM treasury_history
            WHERE epoch_no BETWEEN ? AND ?
            """,
            (int(start_epoch), int(end_epoch)),
        )
        return {int(r["epoch_no"]) for r in cursor.fetchall()}


def get_treasury_flow_recent(n_epochs: int = 5) -> list[dict]:
    """直近 n_epochs エポックの「入金 / 出金」フローを計算して返す（新しい順）。

    計算式（end-of-epoch ベース）:
        delta              = treasury[N] - treasury[N-1]
        captured_outflow   = treasury_withdrawal の spendable_epoch=N の合計

        delta >= 0 (残高増加):
            inflow  = delta + captured_outflow
            outflow = captured_outflow
        delta < 0 (残高減少):
            inflow  = 0
            outflow = max(captured_outflow, -delta)
            （Koios の /treasury_withdrawals がまだ全件を返していない場合でも
             残高減少分を出金として表示できる）

    treasury_history に過去 n+1 エポック分のデータが必要。足りない時は計算可能な
    範囲（前のエポックがあるエポックのみ）だけ返す。
    """
    history = get_treasury_history_recent(n_epochs + 1)
    if len(history) < 2:
        return []

    # 古い順に並べ替えて (prev, curr) ペアを作る
    history = sorted(history, key=lambda r: int(r["epoch_no"]))
    epochs = [int(h["epoch_no"]) for h in history]
    outflow_by_ep = get_withdrawals_per_epoch(epochs)

    rows: list[dict] = []
    for i in range(1, len(history)):
        prev = history[i - 1]
        curr = history[i]
        ep_curr = int(curr["epoch_no"])
        captured_outflow = int(outflow_by_ep.get(ep_curr, 0))
        delta = int(curr["treasury"] or 0) - int(prev["treasury"] or 0)

        if delta >= 0:
            inflow = delta + captured_outflow
            outflow = captured_outflow
        else:
            inflow = 0
            outflow = max(captured_outflow, -delta)

        rows.append({
            "epoch_no":         ep_curr,
            "treasury_lovelace": int(curr["treasury"] or 0),
            "inflow_lovelace":  inflow,
            "outflow_lovelace": outflow,
        })
    # 新しい順
    rows.sort(key=lambda r: r["epoch_no"], reverse=True)
    return rows[:n_epochs]


# ============================================================
# treasury_withdrawal
# ============================================================

def insert_treasury_withdrawals(records: list[dict]) -> int:
    """新規の引き出し履歴を INSERT IGNORE で追加。戻り値は挿入件数。"""
    if not records:
        return 0
    rows = []
    for r in records:
        try:
            rows.append((
                r["stake_address"],
                int(r["amount_lovelace"]),
                int(r["earned_epoch"]),
                int(r["spendable_epoch"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return 0
    with get_db() as (cursor, conn):
        cursor.executemany(
            """
            INSERT IGNORE INTO treasury_withdrawal
              (stake_address, amount_lovelace, earned_epoch, spendable_epoch)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        inserted = cursor.rowcount or 0
        conn.commit()
        return inserted


def get_withdrawals_recent(limit: int = 100) -> list[dict]:
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT stake_address, amount_lovelace, earned_epoch, spendable_epoch
            FROM treasury_withdrawal
            ORDER BY earned_epoch DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return [dict(r) for r in cursor.fetchall()]


def sum_withdrawals_in_epoch_range(start_epoch: int, end_epoch: int) -> int:
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT COALESCE(SUM(amount_lovelace), 0) AS total
            FROM treasury_withdrawal
            WHERE earned_epoch BETWEEN ? AND ?
            """,
            (int(start_epoch), int(end_epoch)),
        )
        row = cursor.fetchone()
        if not row:
            return 0
        return int(row["total"] or 0)


# ============================================================
# NCL 期間内の TreasuryWithdrawals 提案（governance_actions ベース）
# ============================================================

def sum_enacted_withdrawals_in_epoch_range(start_epoch: int, end_epoch: int) -> int:
    """
    NCL 期間内に施行された TreasuryWithdrawals の合計 lovelace。
    実際に treasury_withdrawal に記録される前の「予定」額の計算に使う。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT COALESCE(SUM(withdrawal_total_lovelace), 0) AS total
            FROM governance_actions
            WHERE proposal_type = 'TreasuryWithdrawals'
              AND enacted_epoch IS NOT NULL
              AND enacted_epoch BETWEEN ? AND ?
            """,
            (int(start_epoch), int(end_epoch)),
        )
        row = cursor.fetchone()
        if not row:
            return 0
        return int(row["total"] or 0)


def get_treasury_proposals_in_epoch_range(start_epoch: int, end_epoch: int) -> list[dict]:
    """
    NCL 期間に関係する TreasuryWithdrawals 提案のリスト。
    - proposed_epoch が期間内、または
    - enacted_epoch が期間内
    のいずれかを含む（＝ステータスを問わず期間内に登場した提案）。

    並び順は新着順 (block_time DESC)。同一 Tx 内 (= 同 block_time) は
    proposal_index DESC で並べる (時間 DESC と同じ方向)。
    """
    from cardanoism.backend.db_connect import _GA_STATUS_SQL  # 循環 import 回避のため関数内
    with get_db() as (cursor, _):
        cursor.execute(
            f"""
            SELECT proposal_id, proposal_tx_hash, proposal_index,
                   title, title_ja, proposed_epoch,
                   ratified_epoch, enacted_epoch, dropped_epoch, expired_epoch,
                   withdrawal_total_lovelace,
                   {_GA_STATUS_SQL} AS ga_status
            FROM governance_actions
            WHERE proposal_type = 'TreasuryWithdrawals'
              AND (
                    (proposed_epoch BETWEEN ? AND ?)
                 OR (enacted_epoch  BETWEEN ? AND ?)
              )
            ORDER BY block_time DESC, proposed_epoch DESC, proposal_index DESC
            """,
            (int(start_epoch), int(end_epoch), int(start_epoch), int(end_epoch)),
        )
        return [dict(r) for r in cursor.fetchall()]


# ============================================================
# ncl_active
# ============================================================

def upsert_active_ncl(ncl: dict[str, Any]) -> None:
    """直近のDRep過半数賛成 NCL を 1 レコードとして保存（id=1 固定）。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO ncl_active
              (id, limit_ada, start_epoch, end_epoch, title,
               proposal_tx_hash, proposal_id, drep_yes_pct)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              limit_ada        = VALUES(limit_ada),
              start_epoch      = VALUES(start_epoch),
              end_epoch        = VALUES(end_epoch),
              title            = VALUES(title),
              proposal_tx_hash = VALUES(proposal_tx_hash),
              proposal_id      = VALUES(proposal_id),
              drep_yes_pct     = VALUES(drep_yes_pct)
            """,
            (
                int(ncl["limit_ada"]),
                int(ncl["start_epoch"]),
                int(ncl["end_epoch"]),
                str(ncl.get("title", ""))[:500],
                str(ncl.get("proposal_tx_hash", ""))[:64],
                str(ncl.get("proposal_id", ""))[:128],
                float(ncl.get("drep_yes_pct", 0.0)),
            ),
        )
        conn.commit()


def get_active_ncl() -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT limit_ada, start_epoch, end_epoch, title, "
            "proposal_tx_hash, proposal_id, drep_yes_pct, updated_at "
            "FROM ncl_active WHERE id = 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None
