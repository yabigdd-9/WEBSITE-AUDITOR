"""A single-request HTTP transport that pins DNS results to the TCP connection.

This is a defense-in-depth component for a future isolated worker. It is not a
replacement for worker/container egress restrictions, resource quotas, or the
release gate that currently keeps customer scanning disabled.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable

import dns.exception
import dns.resolver
import httpx

from .security import is_public_ip_address


class EgressPolicyError(ValueError):
    """The target or response violates the worker's outbound policy."""


class EgressTransportError(RuntimeError):
    """A bounded outbound request failed without exposing internal details."""


class EgressCancelledError(RuntimeError):
    """The active audit was cancelled or lost its queue lease."""


class PinnedEgressTransport(httpx.BaseTransport):
    """Resolve, vet, and connect to the same public IP for one HTTP request."""

    def __init__(
        self,
        *,
        max_bytes: int = 2_000_000,
        timeout: float = 8.0,
        dns_timeout: float = 2.0,
        resolver: dns.resolver.Resolver | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ):
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.dns_timeout = dns_timeout
        self.cancel_check = cancel_check or (lambda: False)
        self._resolver = resolver or dns.resolver.Resolver(configure=True)
        self._ssl_context = ssl.create_default_context()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._raise_if_cancelled()
        if request.method != "GET":
            raise EgressPolicyError("Only GET requests are allowed")
        if request.url.scheme not in {"http", "https"} or not request.url.host:
            raise EgressPolicyError("Only public HTTP(S) targets are allowed")
        if request.url.username or request.url.password:
            raise EgressPolicyError("Credentials in target URLs are not allowed")
        if len(str(request.url).encode("utf-8")) > 2048:
            raise EgressPolicyError("Target URL exceeds the allowed length")
        host = request.url.host.rstrip(".").lower()
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        if port not in {80, 443} or (request.url.scheme == "https" and port != 443) or (request.url.scheme == "http" and port != 80):
            raise EgressPolicyError("Target port is not allowed")
        target = request.url.raw_path.decode("ascii", errors="strict")
        if not target.startswith("/") or "\r" in target or "\n" in target:
            raise EgressPolicyError("Target path is invalid")
        addresses = self._resolve_public(host, port)
        self._raise_if_cancelled()
        last_error = None
        for family, socktype, proto, sockaddr in addresses:
            raw_socket = socket.socket(family, socktype, proto)
            try:
                raw_socket.settimeout(self.timeout)
                raw_socket.connect(sockaddr)
                raw_socket.settimeout(self.timeout)
                connection = raw_socket
                if request.url.scheme == "https":
                    connection = self._ssl_context.wrap_socket(raw_socket, server_hostname=host)
                    connection.settimeout(self.timeout)
                try:
                    return self._send_and_read(request, connection, host, port, target)
                finally:
                    connection.close()
            except EgressPolicyError:
                raw_socket.close()
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError) as exc:
                raw_socket.close()
                last_error = exc
        if last_error:
            raise EgressTransportError("Target request failed under outbound limits") from None
        raise EgressPolicyError("No public target address is available")

    def _resolve_public(self, host: str, port: int):
        try:
            literal = ipaddress.ip_address(host)
            results = [(socket.AF_INET6 if literal.version == 6 else socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, (host, port, 0, 0) if literal.version == 6 else (host, port))]
        except ValueError:
            name = host.rstrip(".") + "."
            deadline = time.monotonic() + self.dns_timeout
            results = []
            try:
                for record_type, family in (("A", socket.AF_INET), ("AAAA", socket.AF_INET6)):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise EgressTransportError("Target name could not be resolved within the DNS time limit")
                    try:
                        records = self._resolver.resolve(
                            name, record_type, lifetime=remaining, search=False
                        )
                    except dns.resolver.NoAnswer:
                        continue
                    for record in records:
                        address = ipaddress.ip_address(record.address)
                        sockaddr = (
                            (str(address), port, 0, 0)
                            if family == socket.AF_INET6
                            else (str(address), port)
                        )
                        results.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, sockaddr))
            except (dns.exception.DNSException, OSError, ValueError):
                raise EgressTransportError("Target name could not be resolved") from None
        if not results:
            raise EgressTransportError("Target name has no address")
        vetted = []
        for family, socktype, proto, sockaddr in results:
            if family not in {socket.AF_INET, socket.AF_INET6}:
                raise EgressPolicyError("Target resolved to an unsupported address family")
            try:
                address = ipaddress.ip_address(sockaddr[0].split("%", 1)[0])
            except ValueError:
                raise EgressPolicyError("Target resolved to an invalid address") from None
            if not is_public_ip_address(address):
                raise EgressPolicyError("Target resolves to a non-public address")
            vetted.append((family, socktype, proto, sockaddr))
        return vetted

    def _send_and_read(self, request: httpx.Request, connection, host: str, port: int, target: str):
        started = time.monotonic()
        authority = f"[{host}]" if ":" in host and not host.startswith("[") else host
        if port != (443 if request.url.scheme == "https" else 80):
            authority += f":{port}"
        wire = (
            f"GET {target} HTTP/1.1\r\n"
            f"Host: {authority}\r\n"
            "User-Agent: CatalyxLabs-Website-Auditor/1\r\n"
            "Accept: text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.1\r\n"
            "Accept-Encoding: identity\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        self._raise_if_cancelled()
        connection.sendall(wire)
        response = http.client.HTTPResponse(connection, method="GET")
        response.begin()
        raw_headers = response.getheaders()
        if len(raw_headers) > 100 or sum(len(key) + len(value) for key, value in raw_headers) > 32_768:
            raise EgressPolicyError("Response headers exceed the allowed size")
        headers = httpx.Headers(raw_headers)
        encoding = headers.get("content-encoding", "identity").strip().lower()
        if encoding not in {"", "identity"}:
            raise EgressPolicyError("Compressed responses are not accepted")
        media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        allowed_types = {"", "text/html", "application/xhtml+xml", "application/xml", "text/xml", "text/plain", "application/rss+xml", "application/atom+xml"}
        if media_type not in allowed_types:
            raise EgressPolicyError("Response content type is not supported")
        length = headers.get("content-length")
        if length:
            try:
                declared_length = int(length)
                if declared_length < 0:
                    raise EgressPolicyError("Response length is invalid")
                if declared_length > self.max_bytes:
                    raise EgressPolicyError("Response exceeds the configured byte limit")
            except ValueError:
                raise EgressPolicyError("Response length is invalid") from None
        body = bytearray()
        while True:
            self._raise_if_cancelled()
            remaining = self.timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise EgressPolicyError("Response exceeded the configured time limit")
            connection.settimeout(min(self.timeout, remaining))
            chunk = response.read1(min(65_536, self.max_bytes + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > self.max_bytes:
                raise EgressPolicyError("Response exceeds the configured byte limit")
        if time.monotonic() - started > self.timeout:
            raise EgressPolicyError("Response exceeded the configured time limit")
        self._raise_if_cancelled()
        response.close()
        return httpx.Response(response.status, headers=headers, content=bytes(body), request=request)

    def _raise_if_cancelled(self) -> None:
        if self.cancel_check():
            raise EgressCancelledError("The audit is no longer active")

    def close(self) -> None:
        return None
