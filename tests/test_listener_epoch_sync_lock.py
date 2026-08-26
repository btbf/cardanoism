"""The epoch sync chain must be a singleton across listener processes."""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import call, patch

from cardanoism.backend import listener_epoch_sync


def _lock_result(acquired: bool):
    @contextmanager
    def fake_lock(*args, **kwargs):
        yield acquired

    return fake_lock


class EpochSyncChainLockTests(unittest.TestCase):
    def test_busy_chain_is_skipped(self):
        with (
            patch.object(
                listener_epoch_sync,
                "sync_job_lock",
                new=_lock_result(False),
            ),
            patch.object(listener_epoch_sync, "_run_one_sync") as run_one,
        ):
            listener_epoch_sync._run_epoch_sync_chain(600)

        run_one.assert_not_called()

    def test_lock_owner_runs_each_job_in_order(self):
        with (
            patch.object(
                listener_epoch_sync,
                "sync_job_lock",
                new=_lock_result(True),
            ),
            patch.object(listener_epoch_sync, "_run_one_sync") as run_one,
        ):
            listener_epoch_sync._run_epoch_sync_chain(600)

        self.assertEqual(
            run_one.call_args_list,
            [call(event) for event in listener_epoch_sync._EPOCH_SYNC_SEQUENCE],
        )


if __name__ == "__main__":
    unittest.main()
