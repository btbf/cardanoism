"""Tests for the low-request DRep dirty-marker sync path."""

from __future__ import annotations

import unittest

from cardanoism.backend.drep_dirty_sync import sync_dirty_drep_amounts


class DrepDirtySyncTests(unittest.TestCase):
    def test_only_active_dirty_dreps_are_fetched(self):
        fetched = []
        updated = []

        stats = sync_dirty_drep_amounts(
            marker_hours=2,
            limit=10,
            sleep_seconds=0,
            get_dirty=lambda hours: ["drep-a", "drep-b", "drep-a", "drep-c"],
            get_active=lambda: ["drep-a", "drep-c", "drep-z"],
            fetch_total=lambda drep_id: fetched.append(drep_id) or 123,
            update_amount=lambda drep_id, amount: updated.append((drep_id, amount)),
            cleanup=lambda hours: 0,
        )

        self.assertEqual(fetched, ["drep-a", "drep-c"])
        self.assertEqual(updated, [("drep-a", 123), ("drep-c", 123)])
        self.assertEqual(stats["dirty"], 3)
        self.assertEqual(stats["updated"], 2)

    def test_incomplete_response_keeps_existing_amount(self):
        updated = []
        stats = sync_dirty_drep_amounts(
            sleep_seconds=0,
            get_dirty=lambda hours: ["drep-a"],
            get_active=lambda: ["drep-a"],
            fetch_total=lambda drep_id: None,
            update_amount=lambda drep_id, amount: updated.append((drep_id, amount)),
            cleanup=lambda hours: 0,
        )

        self.assertEqual(updated, [])
        self.assertEqual(stats["failed"], 1)

    def test_zero_is_a_valid_amount(self):
        updated = []
        stats = sync_dirty_drep_amounts(
            sleep_seconds=0,
            get_dirty=lambda hours: ["drep-a"],
            get_active=lambda: ["drep-a"],
            fetch_total=lambda drep_id: 0,
            update_amount=lambda drep_id, amount: updated.append((drep_id, amount)),
            cleanup=lambda hours: 0,
        )

        self.assertEqual(updated, [("drep-a", 0)])
        self.assertEqual(stats["updated"], 1)

    def test_limit_defers_excess_dirty_dreps(self):
        fetched = []
        stats = sync_dirty_drep_amounts(
            limit=2,
            sleep_seconds=0,
            get_dirty=lambda hours: ["a", "b", "c"],
            get_active=lambda: ["a", "b", "c"],
            fetch_total=lambda drep_id: fetched.append(drep_id) or 1,
            update_amount=lambda drep_id, amount: None,
            cleanup=lambda hours: 0,
        )

        self.assertEqual(fetched, ["a", "b"])
        self.assertEqual(stats["deferred"], 1)


if __name__ == "__main__":
    unittest.main()
