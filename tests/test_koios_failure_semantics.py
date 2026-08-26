"""Koios障害時に部分値・偽の0件を返さないことを確認するテスト。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from cardanoism.backend import koios


class DrepDelegatorTotalTests(unittest.TestCase):
    def test_empty_response_is_valid_zero(self):
        with patch.object(koios, "_post", return_value=[]):
            self.assertEqual(koios.get_drep_delegators_total("drep1test"), 0)

    def test_first_page_failure_is_not_zero(self):
        with patch.object(koios, "_post", return_value=None):
            self.assertIsNone(koios.get_drep_delegators_total("drep1test"))

    def test_later_page_failure_discards_partial_total(self):
        responses = [
            [{"amount": "10"}, {"amount": "20"}],
            None,
        ]
        with patch.object(koios, "_post", side_effect=responses):
            self.assertIsNone(
                koios.get_drep_delegators_total("drep1test", page_size=2)
            )

    def test_all_pages_are_summed_when_complete(self):
        responses = [
            [{"amount": "10"}, {"amount": "20"}],
            [{"amount": "5"}],
        ]
        with patch.object(koios, "_post", side_effect=responses):
            self.assertEqual(
                koios.get_drep_delegators_total("drep1test", page_size=2),
                35,
            )


class BatchFetchTests(unittest.TestCase):
    def test_non_413_failure_aborts_without_recursive_split(self):
        with patch.object(koios, "_post", return_value=None) as mocked_post:
            with self.assertRaises(koios.KoiosIncompleteResponseError):
                koios._post_split_on_413("/drep_info", "_drep_ids", ["a", "b"])
        mocked_post.assert_called_once()

    def test_413_is_split_until_complete(self):
        def fake_post(endpoint, payload, timeout=10.0, params=None):
            ids = payload["_drep_ids"]
            if len(ids) > 1:
                raise koios.KoiosPayloadTooLargeError(endpoint)
            return [{"drep_id": ids[0]}]

        with patch.object(koios, "_post", side_effect=fake_post):
            rows = koios._post_split_on_413(
                "/drep_info",
                "_drep_ids",
                ["a", "b", "c"],
            )

        self.assertEqual([row["drep_id"] for row in rows], ["a", "b", "c"])


class EmptyVsFailureTests(unittest.TestCase):
    def test_pool_history_distinguishes_empty_from_failure(self):
        with patch.object(koios, "_get", return_value=[]):
            self.assertEqual(koios.get_pool_history("pool1test"), [])
        with patch.object(koios, "_get", return_value=None):
            self.assertIsNone(koios.get_pool_history("pool1test"))

    def test_paginated_drep_list_discards_partial_result(self):
        first_page = [{"drep_id": f"drep-{i}"} for i in range(1000)]
        with patch.object(koios, "_get", side_effect=[first_page, None]):
            self.assertIsNone(koios.get_drep_list())


if __name__ == "__main__":
    unittest.main()
