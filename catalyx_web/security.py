from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import struct
import sys
import time
from urllib.parse import urlsplit, urlunsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PASSWORD_ITERATIONS = 310_000
TOTP_ENVELOPE_PREFIX = "enc:v1:"
_NUMERIC_HOST_PART = re.compile(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)\Z")
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
CONSENT_VERSION = "2026-09-27-v1"
CONSENT_TEXT = (
    "I own this website or have permission from its owner to request an audit. "
    "I understand this preview records the request for review and does not scan the site."
)
_DISABLED_MONEY_MACHINE_MODULES = frozenset(
    {"mm_transport", "mm_model_router", "mm_approval"}
)


def assert_money_machine_integrations_disabled() -> None:
    """Fail before startup if this app process loaded Money Machine authority."""
    loaded = sorted(
        module_name
        for module_name in sys.modules
        if module_name.rsplit(".", 1)[-1] in _DISABLED_MONEY_MACHINE_MODULES
    )
    if loaded:
        raise RuntimeError(
            "Catalyx web runtime cannot load Money Machine transport, model, or approval modules."
        )


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Use a password between 12 and 1024 characters.")
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def valid_email_address(value: str) -> bool:
    """Accept one plain mailbox address and reject header/list syntax."""
    if not isinstance(value, str) or len(value) > 254 or value.count("@") != 1:
        return False
    local, domain = value.rsplit("@", 1)
    if not local or not domain:
        return False
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    local_pattern = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    return bool(
        re.fullmatch(local_pattern, local)
        and re.fullmatch(rf"{label}(?:\.{label})+", domain)
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
    )


def parse_totp_encryption_key(encoded: str) -> bytes:
    """Decode the required base64url representation of a 256-bit TOTP key."""
    try:
        key = base64.b64decode(encoded.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise ValueError("The TOTP encryption key must be base64url-encoded 32-byte data.") from None
    if len(key) != 32:
        raise ValueError("The TOTP encryption key must be base64url-encoded 32-byte data.")
    return key


def is_public_ip_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether an address is globally routable unicast space."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not (
        address.is_multicast
        or address.is_private
        or address.is_reserved
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
    )


def encrypt_totp_secret(secret: str, key: bytes, workspace_id: str, user_id: str) -> str:
    """Protect an administrator TOTP seed with versioned, authenticated encryption."""
    nonce = secrets.token_bytes(12)
    associated_data = _totp_associated_data(workspace_id, user_id)
    try:
        encrypted = AESGCM(key).encrypt(nonce, secret.encode("ascii"), associated_data)
    except (UnicodeEncodeError, ValueError):
        raise ValueError("The administrator TOTP secret could not be protected.") from None
    envelope = base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")
    return TOTP_ENVELOPE_PREFIX + envelope


def decrypt_totp_secret(envelope: str, key: bytes, workspace_id: str, user_id: str) -> str:
    """Decrypt and authenticate a versioned administrator TOTP seed."""
    if not envelope.startswith(TOTP_ENVELOPE_PREFIX):
        raise ValueError("The administrator TOTP secret is not encrypted.")
    try:
        payload = base64.b64decode(
            envelope[len(TOTP_ENVELOPE_PREFIX) :].encode("ascii"), altchars=b"-_", validate=True
        )
        if len(payload) < 28:
            raise ValueError
        plaintext = AESGCM(key).decrypt(
            payload[:12], payload[12:], _totp_associated_data(workspace_id, user_id)
        )
        return plaintext.decode("ascii")
    except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, InvalidTag, ValueError):
        raise ValueError("The administrator TOTP secret could not be authenticated.") from None


def _totp_associated_data(workspace_id: str, user_id: str) -> bytes:
    return (
        b"catalyx-web:totp:v1\0"
        + workspace_id.encode("utf-8")
        + b"\0"
        + user_id.encode("utf-8")
    )


def totp_code(secret: str, at_time: float | None = None) -> str:
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    counter = int((at_time if at_time is not None else time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret: str, submitted: str, at_time: float | None = None) -> bool:
    if len(submitted) != 6 or not submitted.isdigit():
        return False
    now = at_time if at_time is not None else time.time()
    return any(
        hmac.compare_digest(totp_code(secret, now + offset * 30), submitted)
        for offset in (-1, 0, 1)
    )


def normalize_site(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if len(candidate) > 2048 or any(ord(char) < 32 for char in candidate):
        raise ValueError("Enter a valid public website URL.")
    parts = urlsplit(candidate if "://" in candidate else "https://" + candidate)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Enter a website address beginning with https:// or http://.")
    if parts.username or parts.password:
        raise ValueError("Website addresses cannot include a username or password.")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("The website address has an invalid port.") from exc
    if port is not None and not (
        (parts.scheme.lower() == "http" and port == 80)
        or (parts.scheme.lower() == "https" and port == 443)
    ):
        raise ValueError("Only the standard port for the selected web scheme is accepted.")
    raw_host = parts.hostname
    if "%" in raw_host:
        raise ValueError("Scoped IP addresses cannot be added.")
    if ":" in raw_host:
        try:
            address = ipaddress.IPv6Address(raw_host)
        except ValueError as exc:
            raise ValueError("Enter a valid public website hostname.") from exc
        if not is_public_ip_address(address):
            raise ValueError("Local or reserved network addresses cannot be added.")
        host = address.compressed
        netloc_host = f"[{host}]"
    else:
        host = raw_host.encode("idna").decode("ascii").lower()
        if host.endswith("."):
            host = host[:-1]
        if host in {"localhost", "localhost.localdomain"} or ".localhost" in host:
            raise ValueError("Local network addresses cannot be added.")
        if len(host) > 253 or not host or host.startswith(".") or host.endswith("."):
            raise ValueError("Enter a valid public website hostname.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            if not is_public_ip_address(address):
                raise ValueError("Local or reserved network addresses cannot be added.")
            netloc_host = host
        else:
            labels = host.split(".")
            if (
                len(labels) < 2
                or not all(_DNS_LABEL.fullmatch(label) for label in labels)
            ):
                raise ValueError("Enter a valid public website hostname.")
            if all(_NUMERIC_HOST_PART.fullmatch(label) for label in labels):
                raise ValueError("Non-standard numeric IP addresses cannot be added.")
            netloc_host = host
    scheme = parts.scheme.lower()
    netloc = netloc_host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    origin = urlunsplit((scheme, netloc, "", "", ""))
    return origin, host


def production_mode() -> bool:
    configured = os.getenv("CATALYX_ENV")
    platform_runtime = bool(
        os.getenv("VERCEL") or os.getenv("K_SERVICE") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    )
    if platform_runtime:
        # A mistaken or stale environment label must never make a deployed
        # serverless function behave like localhost (insecure cookies/mailbox).
        return True
    if configured:
        return configured.lower() not in {"development", "local"}
    return False


def production_deployment() -> bool:
    """Distinguish a production deployment from a hosted preview environment."""
    configured = os.getenv("CATALYX_ENV", "").strip().lower()
    vercel_environment = os.getenv("VERCEL_ENV", "").strip().lower()
    if vercel_environment:
        return vercel_environment == "production"
    if configured in {"development", "local", "staging", "preview"}:
        return False
    if configured:
        return configured == "production"
    return bool(os.getenv("K_SERVICE") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
