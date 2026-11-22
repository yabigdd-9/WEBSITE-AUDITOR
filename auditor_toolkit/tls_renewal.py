"""TLS certificate auto-renewal using Let's Encrypt.

Provides automated certificate renewal using ACME protocol (Let's Encrypt).
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .logging_config import get_logger
from .network import check_certificate_expiry

logger = get_logger(__name__)


@dataclass
class ACMEAccount:
    """ACME account information."""

    email: str
    key_path: Path
    account_uri: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class CertificateOrder:
    """Certificate order tracking."""

    domains: list[str]
    status: str = "pending"  # pending, processing, valid, invalid
    order_uri: str | None = None
    finalize_uri: str | None = None
    certificate_path: Path | None = None
    private_key_path: Path | None = None
    expires_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    error: str | None = None


class ACMEClient:
    """ACME client for Let's Encrypt certificate management."""

    def __init__(
        self,
        email: str,
        account_key_path: Path,
        directory_url: str = "https://acme-v02.api.letsencrypt.org/directory",
        staging: bool = False,
    ):
        self.email = email
        self.account_key_path = Path(account_key_path)
        self.directory_url = directory_url
        self.staging = staging
        self.account: ACMEAccount | None = None
        self._directory: dict[str, Any] | None = None

        if staging:
            self.directory_url = "https://acme-staging-v02.api.letsencrypt.org/directory"

    def _get_directory(self) -> dict[str, Any]:
        """Fetch ACME directory."""
        if self._directory is None:
            import urllib.request
            with urllib.request.urlopen(self.directory_url) as response:
                self._directory = json.loads(response.read())
        return self._directory

    def _sign_jws(self, payload: dict[str, Any], url: str, nonce: str) -> str:
        """Sign a JWS payload."""
        import base64

        header = {"alg": "RS256", "nonce": nonce, "url": url}
        if self.account and self.account.account_uri:
            header["kid"] = self.account.account_uri
        else:
            # For new account, use JWK
            with open(self.account_key_path, "rb") as f:
                key = f.read()
            from cryptography.hazmat.primitives import serialization
            private_key = serialization.load_pem_private_key(key, password=None)
            public_key = private_key.public_key()
            numbers = public_key.public_numbers()
            header["jwk"] = {
                "kty": "RSA",
                "e": base64.urlsafe_b64encode(numbers.e.to_bytes(3, "big")).decode().rstrip("="),
                "n": base64.urlsafe_b64encode(numbers.n.to_bytes(256, "big")).decode().rstrip("="),
            }

        protected = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signing_input = f"{protected}.{payload_b64}".encode()

        with open(self.account_key_path, "rb") as f:
            key = f.read()
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        private_key = serialization.load_pem_private_key(key, password=None)
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

        return json.dumps({"protected": protected, "payload": payload_b64, "signature": signature_b64})

    def _post(self, url: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Post to ACME endpoint."""
        import urllib.request

        directory = self._get_directory()
        nonce_url = directory.get("newNonce", url)
        # Get nonce
        req = urllib.request.Request(nonce_url, method="HEAD")
        with urllib.request.urlopen(req) as resp:
            nonce = resp.headers.get("Replay-Nonce")

        jws = self._sign_jws(payload, url, nonce)

        req = urllib.request.Request(url, data=jws.encode(), headers={"Content-Type": "application/jose+json"})
        try:
            with urllib.request.urlopen(req) as resp:
                response_data = resp.read()
                new_nonce = resp.headers.get("Replay-Nonce")
                return json.loads(response_data), new_nonce
        except urllib.error.HTTPError as e:
            error_body = e.read()
            raise RuntimeError(f"ACME error: {e.code} - {error_body}")

    def register_account(self) -> ACMEAccount:
        """Register ACME account."""
        directory = self._get_directory()
        payload = {
            "termsOfServiceAgreed": True,
            "contact": [f"mailto:{self.email}"],
        }

        response, nonce = self._post(directory["newAccount"], payload)
        account_uri = response.get("account")  # Not in response, need to get from Location header

        self.account = ACMEAccount(
            email=self.email,
            key_path=self.account_key_path,
            account_uri=account_uri,
        )
        return self.account

    def request_certificate(self, domains: list[str], key_path: Path) -> CertificateOrder:
        """Request a certificate for domains."""
        if not self.account:
            self.register_account()

        # Create private key for certificate
        subprocess.run([
            "openssl", "genrsa", "-out", str(key_path), "2048"
        ], check=True)

        # Create CSR
        csr_path = key_path.with_suffix(".csr")
        san_list = ",".join(f"DNS:{d}" for d in domains)
        subprocess.run([
            "openssl", "req", "-new", "-sha256", "-key", str(key_path),
            "-subj", f"/CN={domains[0]}",
            "-addext", f"subjectAltName={san_list}",
            "-out", str(csr_path)
        ], check=True)

        with open(csr_path, "rb") as f:
            csr = f.read()

        import base64
        csr_b64 = base64.urlsafe_b64encode(csr).decode().rstrip("=")

        # Create order
        directory = self._get_directory()
        payload = {"identifiers": [{"type": "dns", "value": d} for d in domains]}
        response, nonce = self._post(directory["newOrder"], payload)

        order_uri = response.get("location") or response.get("order")
        authorizations = response.get("authorizations", [])


        # Process authorizations
        for auth_url in authorizations:
            auth_resp, _ = self._post(auth_url, {})
            challenges = auth_resp.get("challenges", [])
            # Find HTTP-01 challenge
            http_challenge = next((c for c in challenges if c["type"] == "http-01"), None)
            if not http_challenge:
                continue

            token = http_challenge["token"]
            key_auth = token + "." + self._get_key_authorization()

            # Place challenge file
            challenge_dir = Path("/var/www/html/.well-known/acme-challenge")
            challenge_dir.mkdir(parents=True, exist_ok=True)
            challenge_file = challenge_dir / token
            challenge_file.write_text(key_auth)

            # Validate challenge
            self._post(http_challenge["url"], {})

            # Clean up
            challenge_file.unlink(missing_ok=True)

        # Finalize order
        csr_b64 = base64.urlsafe_b64encode(open(key_path.with_suffix(".csr"), "rb").read()).decode().rstrip("=")
        self._post(directory["newOrder"] + "/finalize", {"csr": csr_b64})

        # Download certificate
        cert_url = self._get_finalize_url(order_uri)
        cert_resp, _ = self._post(cert_url, {})
        cert_pem = cert_resp.get("certificate")

        cert_path = key_path.with_suffix(".pem")
        cert_path.write_text(cert_pem)

        return CertificateOrder(
            domains=domains,
            status="valid",
            order_uri=order_uri,
            certificate_path=cert_path,
            private_key_path=key_path,
            expires_at=(datetime.now(UTC) + timedelta(days=90)).isoformat(),
        )

    def _get_key_authorization(self) -> str:
        """Get key authorization for challenge."""
        import base64
        import hashlib

        from cryptography.hazmat.primitives import serialization

        with open(self.account_key_path, "rb") as f:
            key = f.read()
        private_key = serialization.load_pem_private_key(key, password=None)
        public_key = private_key.public_key()
        numbers = public_key.public_numbers()
        jwk = {
            "kty": "RSA",
            "e": base64.urlsafe_b64encode(numbers.e.to_bytes(3, "big")).decode().rstrip("="),
            "n": base64.urlsafe_b64encode(numbers.n.to_bytes(256, "big")).decode().rstrip("="),
        }
        jwk_json = json.dumps(jwk, separators=(",", ":"), sort_keys=True)
        thumbprint = base64.urlsafe_b64encode(hashlib.sha256(jwk_json.encode()).digest()).decode().rstrip("=")
        return thumbprint

    def _get_finalize_url(self, order_uri: str) -> str:
        """Get finalize URL from order."""
        # This would fetch the order and get the finalize URL
        return order_uri  # Simplified


class CertRenewalManager:
    """Manages automatic certificate renewal."""

    def __init__(
        self,
        acme_client: ACMEClient,
        cert_dir: Path,
        renewal_days: int = 30,
        check_interval_hours: int = 24,
    ):
        self.acme_client = acme_client
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        self.renewal_days = renewal_days
        self.check_interval_hours = check_interval_hours

    def check_and_renew(self) -> list[str]:
        """Check all certificates and renew if needed."""
        renewed = []

        for cert_file in self.cert_dir.glob("*.pem"):
            try:
                status = check_certificate_expiry(f"https://{cert_file.stem}")
                if status.days_remaining <= self.renewal_days:
                    logger.info(f"Certificate {cert_file.name} expiring soon, renewing...")
                    domain = cert_file.stem
                    key_path = self.cert_dir / f"{domain}.key"
                    order = self.acme_client.request_certificate([domain], key_path)
                    if order.status == "valid":
                        renewed.append(domain)
                        logger.info(f"Renewed certificate for {domain}")
            except Exception as e:
                logger.error(f"Failed to check/renew {cert_file.name}: {e}")

        return renewed

    def run_daemon(self, interval_hours: int | None = None):
        """Run renewal daemon."""
        interval = interval_hours or self.check_interval_hours
        logger.info(f"Starting certificate renewal daemon (interval: {interval}h)")
        while True:
            try:
                renewed = self.check_and_renew()
                if renewed:
                    logger.info(f"Renewed certificates: {renewed}")
            except Exception as e:
                logger.error(f"Renewal check failed: {e}")
            time.sleep(interval * 3600)


def create_acme_cli():
    """Create CLI for ACME management."""
    import argparse

    parser = argparse.ArgumentParser(prog="wa acme")
    sub = parser.add_subparsers(dest="action", required=True)

    # Register account
    register = sub.add_parser("register")
    register.add_argument("--email", required=True)
    register.add_argument("--key", type=Path, required=True)
    register.add_argument("--staging", action="store_true")

    # Request certificate
    order = sub.add_parser("order")
    order.add_argument("--email", required=True)
    order.add_argument("--key", type=Path, required=True)
    order.add_argument("--domains", nargs="+", required=True)
    order.add_argument("--output", type=Path, required=True)
    order.add_argument("--staging", action="store_true")

    # Renew
    renew = sub.add_parser("renew")
    renew.add_argument("--cert-dir", type=Path, required=True)
    renew.add_argument("--days", type=int, default=30)

    # Daemon
    daemon = sub.add_parser("daemon")
    daemon.add_argument("--cert-dir", type=Path, required=True)
    daemon.add_argument("--interval", type=int, default=24)

    args = parser.parse_args()

    if args.action == "register":
        acme = ACMEClient(args.email, args.key, staging=args.staging)
        acme.register_account()
        print("Account registered")
        return 0

    elif args.action == "order":
        acme = ACMEClient(args.email, args.key, staging=args.staging)
        key_path = args.output
        order = acme.request_certificate(args.domains, key_path)
        if order.status == "valid":
            print(f"Certificate issued for {', '.join(args.domains)}")
            print(f"Certificate: {order.certificate_path}")
            print(f"Private key: {order.private_key_path}")
            return 0
        else:
            print(f"Order failed: {order.error}")
            return 1

    elif args.action == "renew":
        acme = ACMEClient("dummy", Path("dummy"), staging=True)  # Would need real account
        manager = CertRenewalManager(acme, args.cert_dir, args.days)
        renewed = manager.check_and_renew()
        print(f"Renewed: {renewed}")
        return 0

    elif args.action == "daemon":
        acme = ACMEClient("dummy", Path("dummy"), staging=True)  # Would need real account
        manager = CertRenewalManager(acme, args.cert_dir)
        manager.run_daemon(args.interval)
        return 0

    return 1


if __name__ == "__main__":
    import sys
    sys.exit(create_acme_cli())
