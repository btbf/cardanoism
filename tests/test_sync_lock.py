"""Tests for cross-process scheduled-job exclusion."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from cardanoism.backend import sync_lock


class _FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeCursor:
    def __init__(self, acquire_result):
        self.acquire_result = acquire_result
        self.executions = []
        self.closed = False

    def execute(self, sql, params):
        self.executions.append((sql, params))

    def fetchone(self):
        return {"acquired": self.acquire_result}

    def close(self):
        self.closed = True


class SyncJobLockTests(unittest.TestCase):
    def _factory(self, acquire_result):
        cursor = _FakeCursor(acquire_result)
        conn = _FakeConnection()
        return cursor, conn

    def test_acquired_lock_is_released_and_connection_is_closed(self):
        cursor, conn = self._factory(1)
        with patch.object(sync_lock, "_open_lock_connection", return_value=(cursor, conn)):
            with sync_lock.sync_job_lock("drep_sync", network="mainnet") as acquired:
                self.assertTrue(acquired)

        self.assertEqual(len(cursor.executions), 2)
        self.assertIn("GET_LOCK", cursor.executions[0][0])
        self.assertIn("RELEASE_LOCK", cursor.executions[1][0])
        self.assertTrue(cursor.closed)
        self.assertTrue(conn.closed)

    def test_busy_lock_yields_false_without_releasing_someone_elses_lock(self):
        cursor, conn = self._factory(0)
        with patch.object(sync_lock, "_open_lock_connection", return_value=(cursor, conn)):
            with sync_lock.sync_job_lock("summary_sync") as acquired:
                self.assertFalse(acquired)

        self.assertEqual(len(cursor.executions), 1)
        self.assertTrue(cursor.closed)
        self.assertTrue(conn.closed)

    def test_null_result_fails_closed(self):
        cursor, conn = self._factory(None)
        with patch.object(sync_lock, "_open_lock_connection", return_value=(cursor, conn)):
            with self.assertRaises(sync_lock.SyncLockError):
                with sync_lock.sync_job_lock("pool_sync"):
                    self.fail("the protected body must not run")

        self.assertEqual(len(cursor.executions), 1)
        self.assertTrue(cursor.closed)
        self.assertTrue(conn.closed)

    def test_lock_is_released_when_job_raises(self):
        cursor, conn = self._factory(1)
        with patch.object(sync_lock, "_open_lock_connection", return_value=(cursor, conn)):
            with self.assertRaisesRegex(RuntimeError, "job failed"):
                with sync_lock.sync_job_lock("vote_sync") as acquired:
                    self.assertTrue(acquired)
                    raise RuntimeError("job failed")

        self.assertEqual(len(cursor.executions), 2)
        self.assertIn("RELEASE_LOCK", cursor.executions[1][0])

    def test_long_names_are_stable_and_bounded(self):
        first = sync_lock.build_lock_name("x" * 200, network="preview")
        second = sync_lock.build_lock_name("x" * 200, network="preview")
        other = sync_lock.build_lock_name("y" * 200, network="preview")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertLessEqual(len(first), 64)


if __name__ == "__main__":
    unittest.main()
