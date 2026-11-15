"""Optional public-key encryption for review-only GitHub Actions artifacts.

The PUBLIC repository contains only ciphertext. The private key must NEVER
enter GitHub, the repository, Actions secrets/logs, or ChatGPT messages.
This module performs no network calls and never sends or deploys anything.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import zlib

FORMAT = "website-auditor-encrypted-review-v1"
AAD = FORMAT.encode("ascii")
MAX_PLAINTEXT_BYTES = 1_000_000
MAX_ENVELOPE_BYTES = 1_500_000


def _crypto():
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError as exc:
        raise RuntimeError("Install the optional vault dependency: pip install -e '.[vault]'") from exc
    return hashes, serialization, x25519, AESGCM, HKDF


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _decode_key(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("A base64-encoded 32-byte key is required")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Invalid base64 key") from exc
    if len(raw) != 32:
        raise ValueError("Key must be exactly 32 bytes")
    return raw


def new_keypair() -> tuple[str, str]:
    """Returns (private_key_b64, public_key_b64); caller protects private key."""
    _, serialization, x25519, _, _ = _crypto()
    private = x25519.X25519PrivateKey.generate()
    public = private.public_key()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = public.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return _b64(private_raw), _b64(public_raw)


def encrypt_document(document: dict, public_key_b64: str) -> bytes:
    """Seal bounded JSON with X25519+HKDF-SHA256+AES-256-GCM."""
    hashes, serialization, x25519, AESGCM, HKDF = _crypto()
    raw = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    if len(raw) > MAX_PLAINTEXT_BYTES:
        raise ValueError("Report is too large for bounded encrypted artifact")
    recipient = x25519.X25519PublicKey.from_public_bytes(_decode_key(public_key_b64))
    ephemeral = x25519.X25519PrivateKey.generate()
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    secret = ephemeral.exchange(recipient)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=AAD).derive(secret)
    encrypted = AESGCM(key).encrypt(nonce, zlib.compress(raw, level=6), AAD)
    envelope = {
        "format": FORMAT,
        "ephemeral_public_key": _b64(ephemeral.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )),
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "ciphertext": _b64(encrypted),
    }
    result = (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(result) > MAX_ENVELOPE_BYTES:
        raise ValueError("Encrypted artifact exceeds configured size limit")
    return result


def decrypt_document(envelope_bytes: bytes, private_key_b64: str) -> dict:
    """Decrypt locally with the owner's private key (never on GitHub runners)."""
    hashes, _, x25519, AESGCM, HKDF = _crypto()
    if len(envelope_bytes) > MAX_ENVELOPE_BYTES:
        raise ValueError("Encrypted artifact exceeds configured size limit")
    envelope = json.loads(envelope_bytes)
    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT:
        raise ValueError("Unexpected encrypted artifact format")
    private = x25519.X25519PrivateKey.from_private_bytes(_decode_key(private_key_b64))
    ephemeral = x25519.X25519PublicKey.from_public_bytes(
        _decode_key(envelope["ephemeral_public_key"])
    )
    salt = base64.b64decode(envelope["salt"], validate=True)
    nonce = base64.b64decode(envelope["nonce"], validate=True)
    if len(salt) != 16 or len(nonce) != 12:
        raise ValueError("Malformed salt or nonce")
    ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
    secret = private.exchange(ephemeral)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=AAD).derive(secret)
    compressed = AESGCM(key).decrypt(nonce, ciphertext, AAD)
    # Bounds are enforced on decompression, not just encryption, to avoid bombs.
    dec = zlib.decompressobj()
    raw = dec.decompress(compressed, MAX_PLAINTEXT_BYTES + 1)
    if len(raw) > MAX_PLAINTEXT_BYTES or not dec.eof or dec.unconsumed_tail:
        raise ValueError("Decoded report exceeded size bound or was incomplete")
    if dec.flush():
        raise ValueError("Unexpected trailing decompressed content")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Report must be a JSON object")
    return value


def _write_new_file(path: Path, data: bytes) -> None:
    """Create a new file with private permissions; never overwrite or follow symlinks."""
    path = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as destination:
            destination.write(data)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def write_encrypted(document: dict, public_key_b64: str, output: Path) -> None:
    ciphertext = encrypt_document(document, public_key_b64)
    _write_new_file(output, ciphertext)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local key setup and decryption")
    command = parser.add_subparsers(dest="operation", required=True)
    keygen = command.add_parser("keygen", help="Generate a local key; print PUBLIC key only")
    keygen.add_argument("--private-out", type=Path, required=True)
    decrypt = command.add_parser("decrypt", help="Decrypt downloaded ciphertext locally")
    decrypt.add_argument("--private-key-file", type=Path, required=True)
    decrypt.add_argument("--input", type=Path, required=True)
    decrypt.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.operation == "keygen":
        private, public = new_keypair()
        _write_new_file(args.private_out, (private + "\n").encode())
        print("Public key (add to GitHub Actions variable MM_REPORT_PUBLIC_KEY_B64):")
        print(public)
        print("Private key saved locally. Never commit, upload, or share it.")
    elif args.operation == "decrypt":
        # Caller uses a local private key file; never echo its contents.
        private = args.private_key_file.read_text(encoding="ascii").strip()
        result = decrypt_document(args.input.read_bytes(), private)
        _write_new_file(args.output, (json.dumps(result, indent=2) + "\n").encode())
        print("Decrypted locally. Never commit the output to a public repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
