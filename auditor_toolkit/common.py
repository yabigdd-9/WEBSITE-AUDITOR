from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx


def _is_private_host(host: str) -> bool:
    """Check if a host is private/non-global.

    Args:
        host: Hostname or IP address.

    Returns:
        True if host is localhost or a non-global IP address.
    """
    if host.lower().rstrip(".") == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
        return not address.is_global
    except ValueError:
        return False


def validate_url(url: str, allow_private: bool = False) -> tuple[str, str | None]:
    """Validate a URL's scheme and host, returning the URL and pinned IP.

    Performs immediate DNS resolution and validates all resolved addresses
    to prevent DNS rebinding attacks (TOCTOU gap between validation and
    HTTP connection).

    Args:
        url: Absolute HTTP(S) URL to validate.
        allow_private: If True, allow private/non-global IP addresses.

    Returns:
        Tuple of (validated URL with fragment removed, pinned IP or None).

    Raises:
        ValueError: If URL is invalid, contains credentials, resolves to
            private addresses (when not allowed), or cannot be resolved.
    """
    if any(ord(c) < 32 for c in url):
        raise ValueError("Control characters are not allowed in URLs")
    parts = urlparse(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Only absolute HTTP(S) URLs without credentials are supported")
    host = parts.hostname
    port = parts.port or (443 if parts.scheme == "https" else 80)
    pinned_ip = None
    if not allow_private:
        if _is_private_host(host):
            raise ValueError("Private and non-global URLs are disabled")
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve host: {host}") from exc
        if not infos:
            raise ValueError("No addresses resolved for host")
        if any(_is_private_host(info[4][0]) for info in infos):
            raise ValueError("URL resolves to a non-global address")
        # Pin to the first resolved global address so the HTTP client cannot
        # be redirected to a different IP by a malicious DNS response later.
        pinned_ip = infos[0][4][0]
    return urlunparse(parts._replace(fragment="")), pinned_ip



def workspace_path(
    value: str | Path,
    *,
    must_exist: bool = False,
    file_only: bool = False,
    root: str | Path | None = None,
) -> Path:
    """Resolve an operator path beneath a trusted workspace root.

    Resolves symlinks before containment check to prevent path traversal
    via workspace symlinks.

    Args:
        value: Path to resolve (relative or absolute).
        must_exist: If True, raise if path does not exist.
        file_only: If True, raise if path is not a file.
        root: Workspace root directory (defaults to current working directory).

    Returns:
        Resolved absolute Path within the workspace.

    Raises:
        ValueError: If path escapes workspace, doesn't exist (must_exist),
            or is not a file (file_only).
    """
    base = Path(root or Path.cwd()).resolve()
    raw = Path(value)
    candidate = (raw if raw.is_absolute() else base / raw).resolve()
    if not candidate.is_relative_to(base):
        raise ValueError("Path must remain inside the current workspace")
    if must_exist and not candidate.exists():
        raise ValueError("Required workspace path does not exist")
    if file_only and (not candidate.is_file()):
        raise ValueError("Required workspace file does not exist")
    return candidate

def public_headers(headers: dict) -> dict:
    """Filter headers to only include safe, public-facing ones.

    Excludes sensitive headers like Set-Cookie, Authorization, and Location
    to prevent information leakage in cached responses.

    Args:
        headers: Raw HTTP response headers.

    Returns:
        Filtered dictionary of safe headers.
    """
    allowed = {
        "content-type",
        "content-length",
        "cache-control",
        "etag",
        "last-modified",
        "strict-transport-security",
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
        "server",
        "location",
    }
    return {
        k: v
        for k, v in headers.items()
        if k.lower() in allowed and k.lower() != "location"
    }


class Fetcher:
    """HTTP client with DNS pinning, caching, and rate limiting.

    Features:
        - DNS rebinding defense via IP pinning
        - Conditional request caching (ETag, Last-Modified)
        - Per-host rate limiting
        - Configurable timeout and byte limits
        - Redirect following (max 6) with chain tracking

    Args:
        timeout: Request timeout in seconds.
        max_bytes: Maximum response body size.
        allow_private: Allow private/non-global IP addresses.
        transport: Custom httpx transport.
        cache_dir: Directory for response caching.
        min_interval: Minimum interval between requests to same host.
        cache_namespace: Namespace prefix for cache keys.
    """

    def __init__(
        self,
        timeout: float = 8.0,
        max_bytes: int = 2_000_000,
        allow_private: bool = False,
        transport: httpx.BaseTransport | None = None,
        cache_dir: str | Path | None = None,
        min_interval: float = 0.1,
        cache_namespace: str = "",
        cache_ttl_seconds: int | None = None,
    ):
        self.allow_private = allow_private
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.min_interval = min_interval
        self.cache_namespace = str(cache_namespace)
        self.cache_ttl_seconds = cache_ttl_seconds
        self.last_request: dict[str, float] = {}
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            trust_env=False,
            # Request uncompressed content to avoid malformed encoding from sites.
            headers={
                "user-agent": "WebsiteAuditorToolkit/2",
                "accept-encoding": "identity",
            },
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.client.close()

    def __enter__(self) -> "Fetcher":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, closing the client."""
        self.close()

    def _build_pinned_client(self, url: str, pinned_ip: str) -> httpx.Client:
        """Build a client that connects to a pinned IP."""
        transport = self._build_pinned_transport(pinned_ip)
        return httpx.Client(
            timeout=self.client.timeout,
            follow_redirects=False,
            trust_env=False,
            headers=self.client.headers,
            transport=transport,
        )

    def _build_pinned_transport(self, pinned_ip: str) -> httpx.HTTPTransport:
        """Create a transport that connects to pinned_ip with original Host header."""

        class PinnedTransport(httpx.HTTPTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                # Store original hostname
                original_host = request.headers.get("Host")
                if not original_host:
                    original_host = request.url.host

                # Replace host with pinned_ip
                request.url = request.url.copy_with(host=pinned_ip)

                # Ensure original host is in Host header
                request.headers["Host"] = original_host

                return super().handle_request(request)

        return PinnedTransport()

    def invalidate_cache(self, url: str | None = None) -> int:
        """Invalidate cache entries.

        Args:
            url: Specific URL to invalidate. If None, invalidates all cache entries.

        Returns:
            Number of cache entries removed.
        """
        if not self.cache_dir or not self.cache_dir.exists():
            return 0

        removed = 0
        if url is None:
            # Invalidate all
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                    removed += 1
                except OSError:
                    pass
        else:
            # Invalidate specific URL
            cache_key = url + "|" + self.cache_namespace
            cache_path = self.cache_dir / (
                hashlib.sha256(cache_key.encode()).hexdigest() + ".json"
            )
            if cache_path.exists():
                try:
                    cache_path.unlink()
                    removed = 1
                except OSError:
                    pass
        return removed

    def _build_pinned_transport(self, pinned_ip: str) -> httpx.HTTPTransport:
        """Create a transport that connects to pinned_ip with original Host header."""

        class PinnedTransport(httpx.HTTPTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                # Store original hostname
                original_host = request.headers.get("Host")
                if not original_host:
                    original_host = request.url.host

                # Replace host with pinned_ip
                request.url = request.url.copy_with(host=pinned_ip)

                # Ensure original host is in Host header
                request.headers["Host"] = original_host

                return super().handle_request(request)

        return PinnedTransport()

    def get(self, url: str) -> httpx.Response:
        """Fetch a URL with caching, rate limiting, and DNS pinning.

        Args:
            url: Absolute HTTP(S) URL to fetch.

        Returns:
            httpx.Response with extensions:
                - observed_at: ISO timestamp of response
                - redirect_chain: List of redirect steps
                - revalidated_at: Timestamp if served from cache (304)

        Raises:
            ValueError: If URL is invalid, too many redirects, or response
                exceeds byte/time limits.
        """
        current, pinned_ip = validate_url(url, self.allow_private)
        chain = []
        # Build a client that connects to the pinned IP (DNS rebinding defense)
        client = self._build_pinned_client(current, pinned_ip) if pinned_ip else self.client
        for _ in range(6):
            host = urlparse(current).netloc
            delay = self.min_interval - (time.monotonic() - self.last_request.get(host, 0))
            if delay > 0:
                time.sleep(delay)
            self.last_request[host] = time.monotonic()
            cached = None
            cache_path = None
            headers = {}
            if self.cache_dir:
                cache_key = current + "|" + self.cache_namespace
                cache_path = self.cache_dir / (
                    hashlib.sha256(cache_key.encode()).hexdigest() + ".json"
                )
                if cache_path.exists():
                    cached = json.loads(cache_path.read_text())
                    # Check TTL-based cache invalidation
                    if self.cache_ttl_seconds is not None:
                        try:
                            observed_at = datetime.fromisoformat(cached.get("observed_at", ""))
                            if datetime.now(UTC) - observed_at > timedelta(seconds=self.cache_ttl_seconds):
                                cached = None  # Invalidate expired cache
                                cache_path.unlink(missing_ok=True)
                        except (ValueError, KeyError):
                            pass  # If parsing fails, treat as no cache
                    if cached is not None:
                        for key, conditional in [
                            ("etag", "if-none-match"),
                            ("last-modified", "if-modified-since"),
                        ]:
                            if cached["headers"].get(key):
                                headers[conditional] = cached["headers"][key]
            started = time.monotonic()
            with client.stream("GET", current, headers=headers) as response:
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes or time.monotonic() - started > self.timeout:
                        raise ValueError("Response exceeded configured byte/time limit")
                    chunks.append(chunk)
                body = b"".join(chunks)
                result = httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=body,
                    request=response.request,
                )
            if result.status_code in (301, 302, 303, 307, 308):
                location = result.headers.get("location")
                if not location:
                    raise ValueError("Redirect missing location")
                chain.append({"url": current, "status": result.status_code})
                current = validate_url(urljoin(current, location), self.allow_private)
                continue
            observed = datetime.now(UTC).isoformat()
            if result.status_code == 304 and cached:
                result = httpx.Response(
                    cached["status"],
                    headers=cached["headers"],
                    content=bytes.fromhex(cached["body"]),
                    request=result.request,
                )
                observed = cached["observed_at"]
                result.extensions["revalidated_at"] = datetime.now(UTC).isoformat()
            elif (
    cache_path
    and result.status_code == 200
    and not result.headers.get("set-cookie")
    and "no-store" not in result.headers.get("cache-control", "").lower()
):
                    atomic_write_json(
                        cache_path,
                        {
                            "status": result.status_code,
                            "headers": public_headers(result.headers),
                            "body": result.content.hex(),
                            "observed_at": observed,
                        },
                    )
            result.extensions.update({"observed_at": observed, "redirect_chain": chain})
            return result
        raise ValueError("Too many redirects")


def atomic_write_json(path: str | Path, data: object) -> None:
    """Atomically write JSON data to a file.

    Uses a temporary file and atomic rename to prevent partial writes.

    Args:
        path: Target file path.
        data: JSON-serializable object.
    """
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """Atomically write bytes to a file.

    Uses a temporary file and atomic rename to prevent partial writes.

    Args:
        path: Target file path.
        data: Bytes to write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_text(path: str | Path, text: str) -> None:
    """Atomically write text to a file.

    Uses a temporary file and atomic rename to prevent partial writes.

    Args:
        path: Target file path.
        text: Text to write (UTF-8).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
