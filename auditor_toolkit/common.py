from __future__ import annotations

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


def _is_private_host(host):
    if host.lower().rstrip(".") == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
        return not address.is_global
    except ValueError:
        return False


def validate_url(url, allow_private=False):
    """Validate a URL's scheme and host, returning the URL and (if pinned) the
    resolved IP address to connect to.  When allow_private is False the host is
    resolved immediately and every resolved address is checked — this closes the
    DNS-rebinding TOCTOU gap that existed when validation resolved DNS but the
    HTTP client re-resolved later.
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



def workspace_path(value, *, must_exist=False, file_only=False, root=None):
    """Resolve an operator path beneath a trusted workspace root.

    Existing symlink components are resolved before the containment check, so a
    workspace symlink cannot be used to escape the allowed tree.
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

def public_headers(headers):
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
    return {k: v for k, v in headers.items() if k.lower() in allowed and k.lower() != "location"}


class Fetcher:
    def __init__(
        self,
        timeout=8.0,
        max_bytes=2_000_000,
        allow_private=False,
        transport=None,
        cache_dir=None,
        min_interval=0.1,
        cache_namespace="",
    ):
        self.allow_private = allow_private
        self._uses_custom_transport = transport is not None
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.min_interval = min_interval
        self.cache_namespace = str(cache_namespace)
        self.last_request = {}
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            trust_env=False,
            headers={"user-agent": "WebsiteAuditorToolkit/2"},
            transport=transport,
        )

    def close(self):
        self.client.close()

    def _build_pinned_client(self, url, pinned_ip):
        transport = self._build_pinned_transport(pinned_ip)
        return httpx.Client(
            timeout=self.client.timeout,
            follow_redirects=False,
            trust_env=False,
            headers=self.client.headers,
            transport=transport,
        )

    def _build_pinned_transport(self, pinned_ip):
        # Connect to pinned_ip while preserving the original Host header.
        # We can achieve this by overriding the request's URL to use the IP
        # and ensuring the 'Host' header is set to the original hostname.
        class PinnedTransport(httpx.HTTPTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                # Store original hostname
                original_host = request.headers.get("Host")
                if not original_host:
                    original_host = request.url.host

                if request.url.scheme == "https":
                    request.extensions["sni_hostname"] = request.url.host

                # Replace the network destination with the validated address
                # while retaining the original Host header and TLS hostname.
                request.url = request.url.copy_with(host=pinned_ip)

                # Ensure original host is in Host header
                request.headers["Host"] = original_host

                return super().handle_request(request)

        return PinnedTransport()

    def get(self, url):
        import hashlib

        current = url
        chain = []
        for _ in range(6):
            current, pinned_ip = validate_url(current, self.allow_private)
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
                    for key, conditional in [
                        ("etag", "if-none-match"),
                        ("last-modified", "if-modified-since"),
                    ]:
                        if cached["headers"].get(key):
                            headers[conditional] = cached["headers"][key]
            started = time.monotonic()
            request_client = (
                self._build_pinned_client(current, pinned_ip)
                if pinned_ip and not self._uses_custom_transport
                else self.client
            )
            try:
                with request_client.stream("GET", current, headers=headers) as response:
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes or time.monotonic() - started > self.timeout:
                            raise ValueError("Response exceeded configured byte/time limit")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    response_request = response.request
                    if request_client is not self.client:
                        response_request.url = httpx.URL(current)
                    result = httpx.Response(
                        response.status_code,
                        headers=response.headers,
                        content=body,
                        request=response_request,
                    )
            finally:
                if request_client is not self.client:
                    request_client.close()
            if result.status_code in (301, 302, 303, 307, 308):
                location = result.headers.get("location")
                if not location:
                    raise ValueError("Redirect missing location")
                chain.append({"url": current, "status": result.status_code})
                current = urljoin(current, location)
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
            elif cache_path and result.status_code == 200 and not result.headers.get("set-cookie"):
                if "no-store" not in result.headers.get("cache-control", "").lower():
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


def atomic_write_json(path, data):
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")



def atomic_write_bytes(path, data):
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

def atomic_write_text(path, text):
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
