"""Untrusted on-chain URL fetch policy tests."""

from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from cardanoism.backend import safe_remote_fetch as target


class _FakeResponse:
    def __init__(self, status: int, content: bytes = b"", headers: dict | None = None):
        self.status_code = status
        self._content = content
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size: int):
        del chunk_size
        midpoint = len(self._content) // 2
        if midpoint:
            yield self._content[:midpoint]
            yield self._content[midpoint:]
        elif self._content:
            yield self._content

    def close(self):
        self.closed = True


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []
        self.trust_env = True

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class SafeRemoteFetchTests(unittest.TestCase):
    def test_rejects_local_and_credential_urls(self):
        for url in (
            "http://127.0.0.1/secret",
            "http://[::1]/secret",
            "http://localhost/secret",
            "https://user:password@example.com/file",
        ):
            with self.subTest(url=url):
                with self.assertRaises(target.UnsafeRemoteURLError):
                    target.validate_remote_url(url)

    def test_rejects_hostname_when_any_dns_answer_is_private(self):
        with self.assertRaises(target.UnsafeRemoteURLError):
            target.validate_remote_url(
                "https://metadata.example/file",
                resolver=lambda _host, _port: {"93.184.216.34", "10.0.0.8"},
            )

    def test_ipfs_uses_only_fixed_https_gateways(self):
        candidates = target.remote_url_candidates("ipfs://bafy-test/path/data.json")
        self.assertEqual(len(candidates), len(target.IPFS_GATEWAYS))
        self.assertTrue(all(url.startswith("https://") for url in candidates))
        self.assertTrue(all(url.endswith("bafy-test/path/data.json") for url in candidates))

    def test_redirect_target_is_revalidated_before_request(self):
        response = _FakeResponse(302, headers={"Location": "http://169.254.169.254/latest"})
        session = _FakeSession([response])
        with (
            patch.object(target, "_resolve_host_ips", return_value={"93.184.216.34"}),
            self.assertRaises(target.UnsafeRemoteURLError),
        ):
            target.fetch_remote_document("https://metadata.example/start", session=session)

        self.assertEqual(len(session.calls), 1)
        self.assertTrue(response.closed)
        self.assertFalse(session.trust_env)

    def test_blake2b_hash_is_checked_on_raw_bytes(self):
        content = b'{"body":{"title":"proposal"}}\n'
        expected = hashlib.blake2b(content, digest_size=32).hexdigest()
        session = _FakeSession([_FakeResponse(200, content)])
        with patch.object(target, "_resolve_host_ips", return_value={"93.184.216.34"}):
            document = target.fetch_remote_document(
                "https://metadata.example/data.json",
                expected_hash=expected,
                session=session,
            )
        self.assertEqual(document.content, content)

        bad_session = _FakeSession([_FakeResponse(200, content)])
        with (
            patch.object(target, "_resolve_host_ips", return_value={"93.184.216.34"}),
            self.assertRaises(target.RemoteHashMismatchError),
        ):
            target.fetch_remote_document(
                "https://metadata.example/data.json",
                expected_hash="00" * 32,
                session=bad_session,
            )

    def test_streamed_response_size_is_limited(self):
        session = _FakeSession([_FakeResponse(200, b"123456")])
        with (
            patch.object(target, "_resolve_host_ips", return_value={"93.184.216.34"}),
            self.assertRaises(target.RemoteContentTooLargeError),
        ):
            target.fetch_remote_document(
                "https://metadata.example/data.json",
                max_bytes=5,
                session=session,
            )

    def test_vote_metadata_forwards_on_chain_hash(self):
        from cardanoism.backend import vote_meta_fetch

        with patch.object(
            vote_meta_fetch,
            "fetch_remote_json",
            return_value=({"body": {}}, object()),
        ) as fetch_mock:
            result = vote_meta_fetch.fetch_vote_metadata_json(
                "ipfs://bafy-test",
                expected_hash="ab" * 32,
            )
        self.assertEqual(result, {"body": {}})
        fetch_mock.assert_called_once_with(
            "ipfs://bafy-test",
            expected_hash="ab" * 32,
            timeout=15.0,
        )

    def test_pool_name_fallback_forwards_pool_metadata_hash(self):
        from cardanoism.backend import koios

        info = {
            "meta_json": {},
            "meta_url": "https://metadata.example/pool.json",
            "meta_hash": "cd" * 32,
        }
        with (
            patch.object(koios, "_post", return_value=[info]),
            patch.object(
                target,
                "fetch_remote_json",
                return_value=({"ticker": "TEST"}, object()),
            ) as fetch_mock,
        ):
            self.assertEqual(koios.get_pool_name("pool1test"), "TEST")
        fetch_mock.assert_called_once_with(
            info["meta_url"],
            expected_hash=info["meta_hash"],
            timeout=5,
            max_bytes=64 * 1024,
        )


if __name__ == "__main__":
    unittest.main()
