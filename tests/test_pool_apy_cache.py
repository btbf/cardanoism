"""Pool APY notification cache tests."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def _load_pool_db_module():
    """Load pool_db.py without initializing the application MariaDB pool."""
    db_connect = types.ModuleType("cardanoism.backend.db_connect")
    db_connect.get_db = lambda: None

    module_name = "_cardanoism_pool_db_apy_test_target"
    source = Path(__file__).resolve().parents[1] / "cardanoism" / "backend" / "pool_db.py"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {module_name: module, "cardanoism.backend.db_connect": db_connect},
    ):
        spec.loader.exec_module(module)
    return module


class _FakeCursor:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.executions: list[tuple[str, list[str]]] = []

    def execute(self, sql: str, params: list[str]):
        self.executions.append((sql, params))

    def fetchall(self):
        return self.rows


def _fake_get_db(rows: list[dict], cursors: list[_FakeCursor]):
    @contextmanager
    def factory():
        cursor = _FakeCursor(rows)
        cursors.append(cursor)
        yield cursor, object()

    return factory


class PoolApyCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool_db = _load_pool_db_module()

    def test_latest_cached_value_uses_newest_valid_entry(self):
        self.assertEqual(self.pool_db.latest_cached_pool_apy("[3.42, 3.21]"), 3.42)
        self.assertEqual(self.pool_db.latest_cached_pool_apy([None, "4.25", 3.0]), 4.25)

    def test_malformed_or_non_finite_history_is_missing(self):
        self.assertIsNone(self.pool_db.latest_cached_pool_apy("not-json"))
        self.assertIsNone(self.pool_db.latest_cached_pool_apy('{"apy": 3.0}'))
        self.assertIsNone(self.pool_db.latest_cached_pool_apy([None, "NaN", True]))

    def test_batch_lookup_deduplicates_and_keeps_missing_as_none(self):
        rows = [
            {"pool_id_bech32": "pool1a", "apy_history_7ep": "[3.5, 3.2]"},
            {"pool_id_bech32": "pool1b", "apy_history_7ep": "invalid"},
        ]
        cursors: list[_FakeCursor] = []
        with patch.object(
            self.pool_db,
            "get_db",
            new=_fake_get_db(rows, cursors),
        ):
            result = self.pool_db.get_cached_pool_apys(
                ["pool1a", "pool1b", "pool1missing", "pool1a"],
            )

        self.assertEqual(
            result,
            {"pool1a": 3.5, "pool1b": None, "pool1missing": None},
        )
        self.assertEqual(len(cursors), 1)
        self.assertEqual(cursors[0].executions[0][1], ["pool1a", "pool1b", "pool1missing"])

    def test_notify_worker_no_longer_calls_live_pool_apy(self):
        source = (
            Path(__file__).resolve().parents[1] / "notify_worker.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("get_pool_apy", called_names)


if __name__ == "__main__":
    unittest.main()
