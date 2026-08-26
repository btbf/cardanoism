"""Cross-process advisory locks for scheduled Cardanoism jobs.

The same sync can be started by cron, the Ogmios epoch listener, or an
operator.  A MariaDB named lock gives those independent processes one common
singleton guard without adding a schema migration.  The lock is tied to the
dedicated database connection kept open by :func:`sync_job_lock`, so MariaDB
also releases it automatically if the process exits unexpectedly.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)

_LOCK_PREFIX = "cardanoism"
_MAX_LOCK_NAME_LENGTH = 64


class SyncLockError(RuntimeError):
    """Raised when MariaDB cannot determine whether a job lock was acquired."""


def build_lock_name(job_name: str, *, network: str | None = None) -> str:
    """Return a stable, server-wide lock name scoped to a Cardano network."""
    job = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(job_name).strip()).lower()
    if not job:
        raise ValueError("job_name must not be empty")

    network_name = re.sub(
        r"[^a-zA-Z0-9_.:-]+",
        "_",
        str(network or os.getenv("KOIOS_NETWORK", "mainnet")).strip(),
    ).lower() or "mainnet"
    raw_name = f"{_LOCK_PREFIX}:{network_name}:{job}"
    if len(raw_name) <= _MAX_LOCK_NAME_LENGTH:
        return raw_name

    digest = hashlib.sha256(raw_name.encode("utf-8")).hexdigest()[:16]
    suffix = f":{digest}"
    return f"{raw_name[:_MAX_LOCK_NAME_LENGTH - len(suffix)]}{suffix}"


def _open_lock_connection():
    # Import lazily so this small module remains testable without constructing
    # the application's MariaDB connection pool at import time.
    from cardanoism.backend.db_connect import dbConnect

    return dbConnect()


def _result_value(row: object, key: str) -> object:
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (tuple, list)) and row:
        return row[0]
    return None


@contextmanager
def sync_job_lock(
    job_name: str,
    *,
    network: str | None = None,
    timeout: float = 0,
) -> Iterator[bool]:
    """Try to hold a MariaDB named lock for the duration of the context.

    Yields ``True`` when the caller owns the lock and ``False`` when another
    process already owns it.  Database errors fail closed via
    :class:`SyncLockError`; running an unprotected duplicate is less safe than
    retrying the scheduled job later.
    """
    lock_name = build_lock_name(job_name, network=network)
    cursor = None
    conn = None
    acquired = False

    try:
        cursor, conn = _open_lock_connection()
        cursor.execute(
            "SELECT GET_LOCK(?, ?) AS acquired",
            (lock_name, float(timeout)),
        )
        value = _result_value(cursor.fetchone(), "acquired")
        if value is None:
            raise SyncLockError(f"GET_LOCK returned NULL for {lock_name}")
        acquired = int(value) == 1
    except SyncLockError:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                logger.debug("Failed to close sync lock cursor", exc_info=True)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.debug("Failed to close sync lock connection", exc_info=True)
        raise
    except Exception as exc:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                logger.debug("Failed to close sync lock cursor", exc_info=True)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.debug("Failed to close sync lock connection", exc_info=True)
        raise SyncLockError(f"failed to acquire sync lock {lock_name}") from exc

    try:
        yield acquired
    finally:
        if acquired and cursor is not None:
            try:
                cursor.execute(
                    "SELECT RELEASE_LOCK(?) AS released",
                    (lock_name,),
                )
            except Exception:
                logger.exception("Failed to release sync lock %s", lock_name)
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                logger.debug("Failed to close sync lock cursor", exc_info=True)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.debug("Failed to close sync lock connection", exc_info=True)
