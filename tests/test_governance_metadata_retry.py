"""Governance Action metadata retry state tests."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


def _load_governance_module():
    """Load governance.py without initializing the application MariaDB pool."""
    import cardanoism.backend.koios  # noqa: F401

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    db_connect = types.ModuleType("cardanoism.backend.db_connect")
    db_connect.get_db = lambda: None

    sync_lock = types.ModuleType("cardanoism.backend.sync_lock")
    sync_lock.SyncLockError = RuntimeError
    sync_lock.sync_job_lock = lambda *args, **kwargs: None

    translate = types.ModuleType("cardanoism.translate")
    translate.TranslateConfig = object
    translate.Translator = object

    module_name = "_cardanoism_governance_metadata_test_target"
    source = Path(__file__).resolve().parents[1] / "cardanoism" / "backend" / "governance.py"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    stubs = {
        module_name: module,
        "dotenv": dotenv,
        "cardanoism.backend.db_connect": db_connect,
        "cardanoism.backend.sync_lock": sync_lock,
        "cardanoism.translate": translate,
    }
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


class _FakeConnection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class _FakeCursor:
    def __init__(self, store: dict):
        self.store = store
        self._one = None

    def execute(self, sql: str, params: tuple):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT meta_fetch_attempts"):
            self._one = {"meta_fetch_attempts": self.store["meta_fetch_attempts"]}
        elif normalized.startswith("UPDATE governance_actions"):
            if "meta_fetched_at = NOW()" in normalized:
                self.store.update(
                    title=params[0] or self.store.get("title"),
                    abstract=params[1] or self.store.get("abstract"),
                    motivation=params[2] or self.store.get("motivation"),
                    rationale=params[3] or self.store.get("rationale"),
                    references_json=params[4] or self.store.get("references_json"),
                    authors_json=params[5] or self.store.get("authors_json"),
                    meta_fetch_attempts=params[6],
                    meta_fetch_next_at=None,
                    meta_fetched_at=True,
                    meta_fetch_error=None,
                )
            else:
                self.store.update(
                    meta_fetch_attempts=params[0],
                    meta_fetch_next_at=params[1],
                    meta_fetch_error=params[2],
                )
        elif normalized.startswith("SELECT id, proposal_id"):
            self._one = {
                "id": 1,
                "proposal_id": self.store["proposal_id"],
                "proposal_tx_hash": "tx-1",
                "title": self.store.get("title"),
                "abstract": self.store.get("abstract"),
                "motivation": self.store.get("motivation"),
                "rationale": self.store.get("rationale"),
                "title_ja": None,
                "abstract_ja": None,
                "motivation_ja": None,
                "rationale_ja": None,
            }
        else:  # pragma: no cover - makes unexpected SQL fail loudly
            raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        return self._one


def _fake_get_db(store: dict):
    @contextmanager
    def factory():
        yield _FakeCursor(store), _FakeConnection()

    return factory


class GovernanceMetadataRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.governance = _load_governance_module()

    def test_retry_delay_is_exponential_and_capped(self):
        delays = [
            self.governance._metadata_retry_delay_minutes(attempt)
            for attempt in range(1, 10)
        ]
        self.assertEqual(delays, [15, 30, 60, 120, 240, 480, 960, 1440, 1440])

    def test_failed_fetch_records_attempt_error_and_next_time(self):
        from cardanoism.backend import vote_meta_fetch

        store = {"proposal_id": "ga-1", "meta_fetch_attempts": 0, "title": None}
        with (
            patch.object(self.governance, "get_db", new=_fake_get_db(store)),
            patch.object(vote_meta_fetch, "fetch_vote_metadata_json", return_value=None),
        ):
            result = self.governance.fetch_and_save_proposal_metadata("ga-1", "ipfs://cid")

        self.assertFalse(result.fetched)
        self.assertEqual(store["meta_fetch_attempts"], 1)
        self.assertIsInstance(store["meta_fetch_next_at"], datetime)
        self.assertIn("no valid JSON body", store["meta_fetch_error"])

    def test_success_saves_body_and_clears_retry_state(self):
        from cardanoism.backend import vote_meta_fetch

        store = {
            "proposal_id": "ga-1",
            "meta_fetch_attempts": 2,
            "title": None,
            "meta_fetch_error": "old error",
        }
        metadata = {
            "body": {
                "title": {"@value": "A proposal"},
                "abstract": "Summary",
                "references": [{"label": "source", "uri": "https://example.com"}],
            },
            "authors": [{"name": {"@value": "Alice"}}],
        }
        with (
            patch.object(self.governance, "get_db", new=_fake_get_db(store)),
            patch.object(
                vote_meta_fetch,
                "fetch_vote_metadata_json",
                return_value=metadata,
            ) as fetch_mock,
        ):
            result = self.governance.fetch_and_save_proposal_metadata(
                "ga-1",
                "ipfs://cid",
                "ab" * 32,
            )

        self.assertTrue(result.fetched)
        self.assertEqual(result.row["title"], "A proposal")
        self.assertEqual(store["meta_fetch_attempts"], 3)
        self.assertTrue(store["meta_fetched_at"])
        self.assertIsNone(store["meta_fetch_next_at"])
        self.assertIsNone(store["meta_fetch_error"])
        self.assertIn("Alice", store["authors_json"])
        fetch_mock.assert_called_once_with("ipfs://cid", expected_hash="ab" * 32)


if __name__ == "__main__":
    unittest.main()
