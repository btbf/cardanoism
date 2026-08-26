"""Notification freshness and recovery-baseline policy tests."""

from __future__ import annotations

import ast
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from cardanoism.backend.notification_freshness import (
    chain_notification_deadline,
    is_chain_event_fresh,
    is_current_epoch_event_fresh,
    is_delivery_deadline_open,
    is_epoch_window_open,
    should_rebaseline_state,
    utc_now_iso,
)


ROOT = Path(__file__).resolve().parents[1]


def _load_function(source: Path, function_name: str, namespace: dict):
    """対象関数だけを読み込み、DBや外部APIのmodule初期化なしで検証する。"""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(source), "exec"), namespace)
    return namespace[function_name]


class NotificationFreshnessTests(unittest.TestCase):
    def test_chain_event_accepts_live_block_and_rejects_catchup(self):
        self.assertTrue(
            is_chain_event_fresh(1_000_000, 1_001_800, max_lag_slots=1_800)
        )
        self.assertFalse(
            is_chain_event_fresh(1_000_000, 1_001_801, max_lag_slots=1_800)
        )

    def test_chain_event_fails_closed_without_tip(self):
        self.assertFalse(is_chain_event_fresh(100, None, max_lag_slots=1_800))
        self.assertFalse(is_chain_event_fresh(None, 100, max_lag_slots=1_800))

    def test_slightly_delayed_tip_is_treated_as_live(self):
        self.assertTrue(is_chain_event_fresh(101, 100, max_lag_slots=0))

    def test_async_delivery_deadline_uses_remaining_chain_window(self):
        deadline = chain_notification_deadline(
            1_000,
            1_600,
            max_lag_slots=1_800,
            now_monotonic=10_000,
        )
        self.assertEqual(deadline, 11_200)
        self.assertTrue(
            is_delivery_deadline_open(True, deadline, now_monotonic=11_200)
        )
        self.assertFalse(
            is_delivery_deadline_open(True, deadline, now_monotonic=11_200.001)
        )
        self.assertIsNone(
            chain_notification_deadline(
                1_000,
                2_801,
                max_lag_slots=1_800,
                now_monotonic=10_000,
            )
        )

    def test_epoch_window_has_inclusive_boundary(self):
        self.assertTrue(is_epoch_window_open(43_200, window_seconds=43_200))
        self.assertFalse(is_epoch_window_open(43_201, window_seconds=43_200))
        self.assertFalse(is_epoch_window_open(None, window_seconds=43_200))

    def test_current_epoch_event_rejects_old_epoch(self):
        self.assertTrue(
            is_current_epoch_event_fresh(651, 651, 1_000, window_seconds=43_200)
        )
        self.assertFalse(
            is_current_epoch_event_fresh(649, 651, 1_000, window_seconds=43_200)
        )

    def test_missing_invalid_or_stale_success_requires_baseline(self):
        now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(should_rebaseline_state(None, now=now, max_gap_seconds=1_800))
        self.assertTrue(should_rebaseline_state("invalid", now=now, max_gap_seconds=1_800))
        self.assertTrue(
            should_rebaseline_state(
                utc_now_iso(now - timedelta(seconds=1_801)),
                now=now,
                max_gap_seconds=1_800,
            )
        )
        self.assertFalse(
            should_rebaseline_state(
                utc_now_iso(now - timedelta(seconds=1_800)),
                now=now,
                max_gap_seconds=1_800,
            )
        )


class NotificationFreshnessWiringTests(unittest.TestCase):
    def _listener_block_function(self, *, tip_lag: int):
        calls = {
            "set_state": Mock(),
            "epoch": Mock(),
            "performance": Mock(),
            "sync": Mock(),
            "tx": Mock(),
            "recent": Mock(),
            "cursor": Mock(),
        }
        namespace = {
            "_epoch_from_slot": lambda _slot: 651,
            "logger": Mock(),
            "get_state": Mock(return_value="650"),
            "set_state": calls["set_state"],
            "_notify_epoch_start": calls["epoch"],
            "_notify_pool_epoch_performance": calls["performance"],
            "trigger_epoch_syncs": calls["sync"],
            "_process_tx": calls["tx"],
            "_record_recent_block": calls["recent"],
            "_save_cursor": calls["cursor"],
            "is_chain_event_fresh": is_chain_event_fresh,
            "chain_notification_deadline": chain_notification_deadline,
            "REALTIME_MAX_LAG_SLOTS": 1_800,
            "EPOCH_MAX_LAG_SLOTS": 7_200,
        }
        process_block = _load_function(
            ROOT / "ogmios_listener.py",
            "_process_block",
            namespace,
        )
        block = {
            "slot": 1_000_000,
            "id": "block-651",
            "transactions": [{"id": "tx-1"}],
        }
        result = process_block(
            block,
            650,
            tip_slot=block["slot"] + tip_lag,
        )
        return result, block, calls

    def test_listener_catchup_suppresses_notifications_but_processes_data(self):
        result, block, calls = self._listener_block_function(tip_lag=7_201)

        self.assertEqual(result, 651)
        calls["epoch"].assert_not_called()
        calls["performance"].assert_not_called()
        calls["sync"].assert_not_called()
        calls["tx"].assert_called_once_with(
            block["transactions"][0],
            block["slot"],
            651,
            False,
            None,
        )
        calls["recent"].assert_called_once_with(block, 651)
        calls["cursor"].assert_called_once_with(block["slot"], block["id"])

    def test_listener_live_block_keeps_notifications_enabled(self):
        result, block, calls = self._listener_block_function(tip_lag=100)

        self.assertEqual(result, 651)
        calls["epoch"].assert_called_once_with(651)
        calls["performance"].assert_called_once_with(650)
        calls["sync"].assert_called_once_with(651)
        calls["tx"].assert_called_once_with(
            block["transactions"][0],
            block["slot"],
            651,
            True,
            ANY,
        )

    def test_reward_worker_does_not_fetch_history_outside_window(self):
        reward_fetch = Mock()
        namespace = {
            "logger": Mock(),
            "is_epoch_window_open": is_epoch_window_open,
            "REWARD_WINDOW_SECONDS": 43_200,
            "batch_account_reward_history_by_type": reward_fetch,
        }
        check_rewards = _load_function(
            ROOT / "notify_worker.py",
            "_check_pool_reward_received_batch",
            namespace,
        )

        check_rewards(
            {},
            {},
            651,
            {},
            current_epoch_slot=43_201,
        )

        reward_fetch.assert_not_called()

    def test_pool_state_recovery_updates_baseline_without_delivery(self):
        deliver = Mock()
        set_state = Mock()
        namespace = {
            "get_state": Mock(return_value="0"),
            "set_state": set_state,
            "CARDANOISM_URL": "https://example.test",
        }
        check_pool_event = _load_function(
            ROOT / "notify_worker.py",
            "_check_pool_event",
            namespace,
        )
        templates = types.ModuleType("cardanoism.backend.notify_templates")
        templates.__path__ = []
        templates.deliver = deliver
        saturation = types.ModuleType(
            "cardanoism.backend.notify_templates.pool_saturation"
        )
        saturation.context = Mock(return_value={})
        pledge = types.ModuleType(
            "cardanoism.backend.notify_templates.pool_pledge_shortage"
        )
        pledge.context = Mock(return_value={})
        modules = {
            "cardanoism.backend.notify_templates": templates,
            "cardanoism.backend.notify_templates.pool_saturation": saturation,
            "cardanoism.backend.notify_templates.pool_pledge_shortage": pledge,
        }
        addr = {
            "stake_id": 1,
            "user_id": 2,
            "line_notify_id": None,
            "language": "ja",
            "delegated_pool_id": "pool1test",
            "delegated_pool_name": "TEST",
            "nickname": "wallet",
        }

        with patch.dict(sys.modules, modules):
            check_pool_event(
                "pool_saturation",
                addr,
                {"live_saturation": 120},
                baseline_only=True,
            )

        set_state.assert_called_once_with(
            "stake_address",
            1,
            "pool_saturated",
            "1",
        )
        deliver.assert_not_called()

    def test_tip_epoch_info_fails_closed_without_epoch_slot(self):
        namespace = {
            "datetime": datetime,
            "timezone": timezone,
        }
        get_tip = _load_function(
            ROOT / "notify_worker.py",
            "_get_tip_epoch_info",
            namespace,
        )
        koios = types.ModuleType("cardanoism.backend.koios")
        koios._get = Mock(return_value=[{"epoch_no": 651}])

        with patch.dict(sys.modules, {"cardanoism.backend.koios": koios}):
            self.assertIsNone(get_tip())
            koios._get.return_value = [123]
            self.assertIsNone(get_tip())

    def test_tip_epoch_info_accepts_koios_unix_block_time(self):
        namespace = {
            "datetime": datetime,
            "timezone": timezone,
        }
        get_tip = _load_function(
            ROOT / "notify_worker.py",
            "_get_tip_epoch_info",
            namespace,
        )
        koios = types.ModuleType("cardanoism.backend.koios")
        koios._get = Mock(
            return_value=[
                {
                    "epoch_no": "651",
                    "epoch_slot": "1234",
                    "block_time": 1_725_000_000,
                }
            ]
        )

        with patch.dict(sys.modules, {"cardanoism.backend.koios": koios}):
            result = get_tip()

        self.assertEqual(result["epoch_no"], 651)
        self.assertEqual(result["epoch_slot"], 1_234)
        self.assertEqual(result["block_time"].tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
