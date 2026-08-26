"""Incremental DRep voting-power refresh driven by Ogmios dirty markers.

The frequent cron path must not fetch the complete DRep registry.  The Ogmios
listener already records DReps affected by vote-delegation certificates, so
this module refreshes only those rows through Koios ``/drep_delegators``.
Full registry, status, and metadata refreshes remain epoch/daily jobs until
they are replaced by Ogmios LocalStateQuery.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


def _get_recent_dirty(hours: int) -> list[str]:
    from cardanoism.backend.drep_db import get_recent_dirty_dreps

    return get_recent_dirty_dreps(hours=hours)


def _get_active() -> list[str]:
    from cardanoism.backend.drep_db import get_active_drep_ids

    return get_active_drep_ids()


def _fetch_total(drep_id: str) -> int | None:
    from cardanoism.backend.koios import get_drep_delegators_total

    return get_drep_delegators_total(drep_id)


def _update_amount(drep_id: str, amount: int) -> None:
    from cardanoism.backend.drep_db import update_drep_amount

    update_drep_amount(drep_id, amount)


def _cleanup(retention_hours: int) -> int:
    from cardanoism.backend.drep_db import cleanup_drep_dirty_marker

    return cleanup_drep_dirty_marker(retention_hours=retention_hours)


def _default_limit() -> int:
    try:
        return max(1, int(os.getenv("DREP_DIRTY_SYNC_LIMIT", "250")))
    except (TypeError, ValueError):
        return 250


def sync_dirty_drep_amounts(
    *,
    marker_hours: int = 1,
    limit: int | None = None,
    sleep_seconds: float = 0.05,
    get_dirty: Callable[[int], list[str]] = _get_recent_dirty,
    get_active: Callable[[], list[str]] = _get_active,
    fetch_total: Callable[[str], int | None] = _fetch_total,
    update_amount: Callable[[str, int], None] = _update_amount,
    cleanup: Callable[[int], int] = _cleanup,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """Refresh dirty, active DReps and return counters for observability.

    Successful markers deliberately remain eligible for ``marker_hours``.
    This makes the lightweight job self-healing if a later delegation for the
    same DRep arrives while a run is in progress, without needing a marker
    claim/version schema migration.
    """
    effective_limit = _default_limit() if limit is None else max(1, int(limit))
    dirty_ids = list(dict.fromkeys(str(item) for item in get_dirty(marker_hours) if item))
    active_ids = set(str(item) for item in get_active() if item)
    eligible = [drep_id for drep_id in dirty_ids if drep_id in active_ids]
    target_ids = eligible[:effective_limit]

    stats = {
        "dirty": len(dirty_ids),
        "active_dirty": len(eligible),
        "attempted": len(target_ids),
        "updated": 0,
        "failed": 0,
        "deferred": max(0, len(eligible) - len(target_ids)),
    }
    logger.info(
        "DRep dirty amount sync: dirty=%d active=%d target=%d deferred=%d",
        stats["dirty"],
        stats["active_dirty"],
        stats["attempted"],
        stats["deferred"],
    )

    for index, drep_id in enumerate(target_ids):
        try:
            total = fetch_total(drep_id)
            if total is None:
                stats["failed"] += 1
                logger.warning(
                    "DRep dirty amount fetch incomplete; existing value retained: %s",
                    drep_id,
                )
                continue
            update_amount(drep_id, int(total))
            stats["updated"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            logger.warning("DRep dirty amount refresh failed (%s): %s", drep_id, exc)
        finally:
            if sleep_seconds > 0 and index + 1 < len(target_ids):
                sleep(sleep_seconds)

    try:
        deleted = cleanup(24)
        if deleted:
            logger.info("drep_dirty_marker cleanup: %d rows", deleted)
    except Exception:  # noqa: BLE001
        logger.debug("drep_dirty_marker cleanup failed", exc_info=True)

    logger.info(
        "DRep dirty amount sync complete: updated=%d failed=%d deferred=%d",
        stats["updated"],
        stats["failed"],
        stats["deferred"],
    )
    return stats
