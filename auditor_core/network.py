"""Safe network primitives for public website auditing.

Every redirect target is resolved and checked before a request is made. Private,
loopback, link-local, reserved and other non-global addresses are blocked.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
import urllib.parse
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".test")
_DOMAIN_SEMAPHORES: dict[tuple[int, str], asyncio.Semaphore] = {}
_DOMAIN_START_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_DOMAIN_LAST_START: dict[tuple[int, str], float] = {}


class NetworkSafetyError(RuntimeError):
    pass


class ResponseTooLarge(NetworkSafetyError):
    pass


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    headers: dict[str, str]
    text: str = ""
    bytes_read: int = 0
    redirect_chain: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_http_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        raise NetworkSafetyError("empty URL")
    if "://" not in value:
        value = "https://" + value
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise NetworkSafetyError("only http/https URLs are allowed")
    if not parsed.hostname:
        raise NetworkSafetyError("URL has no hostname")
    if parsed.username or parsed.password:
        raise NetworkSafetyError("credential-bearing URLs are not allowed")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, "")
    )


def _assert_public_ip(value: str) -> None:
    ip = ipaddress.ip_address(value)
    if not ip.is_global:
        raise NetworkSafetyError(f"non-public target blocked: {ip.compressed}")


async def ensure_public_url(url: str) -> str:
    normalized = normalize_http_url(url)
    parsed = urllib.parse.urlsplit(normalized)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise NetworkSafetyError(f"local/reserved hostname blocked: {host}")

    try:
        _assert_public_ip(host)
        return normalized
    except ValueError:
        pass

    def resolve() -> set[str]:
        records = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        return {record[4][0].split("%", 1)[0] for record in records}

    try:
        addresses = await asyncio.to_thread(resolve)
    except socket.gaierror as exc:
        raise NetworkSafetyError(f"DNS resolution failed for {host}: {exc}") from exc

    if not addresses:
        raise NetworkSafetyError(f"DNS resolution returned no addresses for {host}")
    for address in addresses:
        _assert_public_ip(address)
    return normalized


class _DomainGate:
    def __init__(self, host: str, concurrency: int, delay_seconds: float):
        self.host = host
        loop_id = id(asyncio.get_running_loop())
        self.key = (loop_id, host)
        self.sem = _DOMAIN_SEMAPHORES.setdefault(
            self.key, asyncio.Semaphore(max(1, concurrency))
        )
        self.lock = _DOMAIN_START_LOCKS.setdefault(self.key, asyncio.Lock())
        self.delay_seconds = max(0.0, delay_seconds)

    async def __aenter__(self):
        await self.sem.acquire()
        async with self.lock:
            last = _DOMAIN_LAST_START.get(self.key, 0.0)
            remaining = self.delay_seconds - (time.monotonic() - last)
            if remaining > 0:
                await asyncio.sleep(remaining)
            _DOMAIN_LAST_START[self.key] = time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.sem.release()


class SafeFetcher:
    def __init__(
        self,
        session: httpx.AsyncClient,
        *,
        timeout: float = 15,
        max_redirects: int = 5,
        max_body_bytes: int = 5_000_000,
        per_domain_concurrency: int = 2,
        delay_seconds: float = 0.25,
    ):
        self.session = session
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.max_body_bytes = max_body_bytes
        self.per_domain_concurrency = per_domain_concurrency
        self.delay_seconds = delay_seconds

    def _gate(self, url: str) -> _DomainGate:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        return _DomainGate(host, self.per_domain_concurrency, self.delay_seconds)

    async def get_text(self, url: str, *, max_body_bytes: int | None = None) -> FetchResult:
        requested = await ensure_public_url(url)
        current = requested
        chain: list[dict[str, Any]] = []
        limit = max_body_bytes or self.max_body_bytes

        for hop in range(self.max_redirects + 1):
            current = await ensure_public_url(current)
            async with self._gate(current):
                async with self.session.stream(
                    "GET", current, timeout=self.timeout, follow_redirects=False
                ) as response:
                    status = response.status_code
                    headers = dict(response.headers)
                    location = headers.get("location")
                    chain.append({"url": current, "status": status, "location": location})

                    if status in REDIRECT_STATUSES and location:
                        if hop >= self.max_redirects:
                            raise NetworkSafetyError("redirect limit exceeded")
                        current = urllib.parse.urljoin(current, location)
                        continue

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > limit:
                            raise ResponseTooLarge(f"response exceeded {limit} bytes")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    text = body.decode(encoding, errors="replace")
                    return FetchResult(
                        requested_url=requested,
                        final_url=current,
                        status=status,
                        headers=headers,
                        text=text,
                        bytes_read=total,
                        redirect_chain=chain,
                    )
        raise NetworkSafetyError("redirect resolution failed")

    async def head_status(self, url: str) -> FetchResult:
        requested = await ensure_public_url(url)
        current = requested
        chain: list[dict[str, Any]] = []
        for hop in range(self.max_redirects + 1):
            current = await ensure_public_url(current)
            async with self._gate(current):
                response = await self.session.head(
                    current, timeout=self.timeout, follow_redirects=False
                )
            status = response.status_code
            headers = dict(response.headers)
            location = headers.get("location")
            chain.append({"url": current, "status": status, "location": location})
            if status in REDIRECT_STATUSES and location:
                if hop >= self.max_redirects:
                    raise NetworkSafetyError("redirect limit exceeded")
                current = urllib.parse.urljoin(current, location)
                continue
            if status == 405:
                fallback = await self.get_text(current, max_body_bytes=64_000)
                fallback.requested_url = requested
                fallback.redirect_chain = chain + fallback.redirect_chain
                return fallback
            return FetchResult(
                requested_url=requested,
                final_url=current,
                status=status,
                headers=headers,
                redirect_chain=chain,
            )
        raise NetworkSafetyError("redirect resolution failed")


async def robots_policy(
    session: httpx.AsyncClient,
    url: str,
    *,
    user_agent: str,
    timeout: float = 10,
) -> dict[str, Any]:
    target = await ensure_public_url(url)
    parsed = urllib.parse.urlsplit(target)
    robots_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    fetcher = SafeFetcher(session, timeout=timeout, max_body_bytes=512_000)
    try:
        result = await fetcher.get_text(robots_url, max_body_bytes=512_000)
    except (httpx.HTTPError, NetworkSafetyError) as exc:
        return {
            "allowed": True,
            "robots_url": robots_url,
            "reason": f"robots unavailable: {exc}",
            "crawl_delay": None,
        }

    if result.status >= 400:
        return {
            "allowed": True,
            "robots_url": robots_url,
            "status": result.status,
            "reason": "robots.txt not available",
            "crawl_delay": None,
        }

    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(result.text.splitlines())
    allowed = parser.can_fetch(user_agent, target)
    delay = parser.crawl_delay(user_agent) or parser.crawl_delay("*")
    return {
        "allowed": bool(allowed),
        "robots_url": robots_url,
        "status": result.status,
        "reason": "allowed" if allowed else "disallowed by robots.txt",
        "crawl_delay": delay,
    }
