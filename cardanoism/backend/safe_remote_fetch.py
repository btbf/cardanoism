"""安全にオンチェーン参照先のリモートコンテンツを取得する。

Governance / vote / stake-pool metadata の URL は第三者がオンチェーンへ
登録できるため、そのまま requests に渡すと SSRF になる。このモジュールは
URL・名前解決・redirect・response size を一箇所で検証し、必要なら
オンチェーンの Blake2b-256 hash も照合する。
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests


IPFS_GATEWAYS = (
    "https://ipfs.io/ipfs/",
    "https://dweb.link/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
)

DEFAULT_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class RemoteFetchError(RuntimeError):
    """リモートコンテンツを安全に取得できなかった。"""


class UnsafeRemoteURLError(RemoteFetchError):
    """URL または名前解決結果が SSRF policy に違反している。"""


class RemoteContentTooLargeError(RemoteFetchError):
    """レスポンスが許可サイズを超えている。"""


class RemoteHashMismatchError(RemoteFetchError):
    """取得内容がオンチェーン hash と一致しない。"""


@dataclass(frozen=True)
class RemoteDocument:
    content: bytes
    final_url: str
    content_type: str


def remote_url_candidates(url: str | None) -> list[str]:
    """http(s) URL または ipfs:// URI を取得候補へ変換する。"""
    if not isinstance(url, str):
        return []
    value = url.strip()
    if not value:
        return []
    parsed = urlsplit(value)
    if parsed.scheme.lower() == "ipfs":
        if parsed.query or parsed.fragment or not parsed.netloc:
            return []
        cid_path = parsed.netloc + parsed.path
        if not cid_path or "\\" in cid_path or any(c.isspace() for c in cid_path):
            return []
        return [gateway + cid_path.lstrip("/") for gateway in IPFS_GATEWAYS]
    if parsed.scheme.lower() in {"http", "https"}:
        return [value]
    return []


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_global


def _resolve_host_ips(host: str, port: int) -> set[str]:
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeRemoteURLError(f"hostname could not be resolved: {host}") from exc
    addresses = {str(row[4][0]) for row in rows if row[4]}
    if not addresses:
        raise UnsafeRemoteURLError(f"hostname returned no addresses: {host}")
    return addresses


def validate_remote_url(
    url: str,
    *,
    resolver: Callable[[str, int], set[str]] | None = None,
) -> str:
    """URL と全名前解決結果を検証し、fragment を除いた URL を返す。"""
    if not isinstance(url, str) or not url:
        raise UnsafeRemoteURLError("empty URL")
    if "\\" in url or any(ord(char) < 32 for char in url):
        raise UnsafeRemoteURLError("URL contains forbidden characters")

    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeRemoteURLError(f"unsupported URL scheme: {scheme or '(none)'}")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeRemoteURLError("URL credentials are not allowed")
    if not parsed.hostname:
        raise UnsafeRemoteURLError("URL hostname is required")

    host = parsed.hostname.rstrip(".")
    if not host or host.lower() == "localhost" or "%" in host:
        raise UnsafeRemoteURLError("local hostname is not allowed")
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeRemoteURLError("invalid URL port") from exc
    if not 1 <= port <= 65535:
        raise UnsafeRemoteURLError("invalid URL port")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        addresses = (resolver or _resolve_host_ips)(host, port)
    else:
        addresses = {str(literal)}
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise UnsafeRemoteURLError("URL resolves to a non-public address")

    # fragments are client-side only and must not affect the fetched document/hash.
    return urlunsplit((scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _normalize_expected_hash(expected_hash: str | bytes | bytearray | memoryview) -> str:
    if isinstance(expected_hash, (bytes, bytearray, memoryview)):
        value = bytes(expected_hash).hex()
    else:
        value = str(expected_hash).strip().lower()
        if value.startswith("0x"):
            value = value[2:]
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RemoteHashMismatchError("expected Blake2b-256 hash is not 32-byte hex")
    return value


def verify_blake2b_256(
    content: bytes,
    expected_hash: str | bytes | bytearray | memoryview | None,
) -> None:
    """expected_hash が指定された場合だけ、生bytesの Blake2b-256 を照合する。"""
    if expected_hash is None or expected_hash == "":
        return
    expected = _normalize_expected_hash(expected_hash)
    actual = hashlib.blake2b(content, digest_size=32).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise RemoteHashMismatchError(
            f"Blake2b-256 mismatch (expected={expected}, actual={actual})"
        )


def _read_limited_response(response: requests.Response, max_bytes: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise RemoteContentTooLargeError(
                    f"response Content-Length exceeds {max_bytes} bytes"
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise RemoteContentTooLargeError(f"response exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _fetch_one_candidate(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    max_redirects: int,
    accept: str,
    session: requests.Session,
) -> RemoteDocument:
    current_url = url
    redirects = 0
    while True:
        current_url = validate_remote_url(current_url)
        response: requests.Response | None = None
        try:
            response = session.get(
                current_url,
                allow_redirects=False,
                stream=True,
                timeout=(min(float(timeout), 5.0), float(timeout)),
                headers={
                    "Accept": accept,
                    "User-Agent": "cardanoism-metadata-fetch/1.0",
                },
            )
            if response.status_code in _REDIRECT_STATUSES:
                if redirects >= max_redirects:
                    raise RemoteFetchError("too many redirects")
                location = response.headers.get("Location")
                if not location:
                    raise RemoteFetchError("redirect has no Location header")
                # The next loop validates DNS/IP again before any request is sent.
                current_url = urljoin(current_url, location)
                redirects += 1
                continue
            if response.status_code != 200:
                raise RemoteFetchError(f"remote server returned HTTP {response.status_code}")
            content = _read_limited_response(response, max_bytes)
            return RemoteDocument(
                content=content,
                final_url=current_url,
                content_type=response.headers.get("Content-Type") or "",
            )
        except requests.RequestException as exc:
            raise RemoteFetchError(f"remote request failed: {type(exc).__name__}") from exc
        finally:
            if response is not None:
                response.close()


def fetch_remote_document(
    url: str,
    *,
    expected_hash: str | bytes | bytearray | memoryview | None = None,
    timeout: float = 15.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    accept: str = "*/*",
    session: requests.Session | None = None,
) -> RemoteDocument:
    """全候補を安全に取得し、hash が一致した最初の document を返す。"""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    candidates = remote_url_candidates(url)
    if not candidates:
        raise UnsafeRemoteURLError("URL is neither http(s) nor a valid ipfs URI")

    owned_session = session is None
    active_session = session or requests.Session()
    # Metadata fetches must not be rerouted through ambient HTTP(S)_PROXY settings.
    active_session.trust_env = False
    last_error: RemoteFetchError | None = None
    try:
        for candidate in candidates:
            try:
                document = _fetch_one_candidate(
                    candidate,
                    timeout=timeout,
                    max_bytes=max_bytes,
                    max_redirects=max_redirects,
                    accept=accept,
                    session=active_session,
                )
                verify_blake2b_256(document.content, expected_hash)
                return document
            except RemoteFetchError as exc:
                last_error = exc
        raise last_error or RemoteFetchError("no remote URL candidates succeeded")
    finally:
        if owned_session:
            active_session.close()


def fetch_remote_json(
    url: str,
    *,
    expected_hash: str | bytes | bytearray | memoryview | None = None,
    timeout: float = 15.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[Any, RemoteDocument]:
    """hash 検証済みbytesを UTF-8 JSON として解析する。"""
    document = fetch_remote_document(
        url,
        expected_hash=expected_hash,
        timeout=timeout,
        max_bytes=max_bytes,
        accept="application/json",
    )
    try:
        parsed = json.loads(document.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RemoteFetchError("remote content is not valid UTF-8 JSON") from exc
    return parsed, document
