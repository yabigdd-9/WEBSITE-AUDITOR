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
    if not allow_private:
        if _is_private_host(host):
            raise ValueError("Private and non-global URLs are disabled")
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve host: {host}") from exc
        if not infos or any(_is_private_host(info[4][0]) for info in infos):
            raise ValueError("URL resolves to a non-global address")
    return urlunparse(parts._replace(fragment=""))



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
    ):
        self.allow_private = allow_private
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.min_interval = min_interval
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

    def get(self, url):
        import hashlib

        current = validate_url(url, self.allow_private)
        chain = []
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
                cache_path = self.cache_dir / (
                    hashlib.sha256(current.encode()).hexdigest() + ".json"
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
            with self.client.stream("GET", current, headers=headers) as response:
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
