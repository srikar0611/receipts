"""Canonical manifest hashing and optional Ed25519 support."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def canonical_body(manifest: dict[str, Any]) -> bytes:
    body = {key: value for key, value in manifest.items() if key != "integrity"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_body(manifest)).hexdigest()


def default_key_paths(receipts_dir: Path) -> tuple[Path, Path]:
    key_dir = receipts_dir / "keys"
    return key_dir / "ed25519-private.pem", key_dir / "ed25519-public.pem"


def _crypto() -> Any:
    try:
        from cryptography.hazmat.primitives import serialization  # type: ignore
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # type: ignore
    except ImportError as error:
        raise RuntimeError("Ed25519 signing needs the optional dependency: pip install cryptography") from error
    return serialization, Ed25519PrivateKey


def keygen(receipts_dir: Path) -> tuple[Path, Path]:
    serialization, private_type = _crypto()
    private_path, public_path = default_key_paths(receipts_dir)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    if private_path.exists() or public_path.exists():
        raise RuntimeError(f"refusing to overwrite existing keypair in {private_path.parent}")
    private = private_type.generate()
    private_path.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public_path.write_bytes(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    os.chmod(private_path, 0o600)
    return private_path, public_path


def add_integrity(manifest: dict[str, Any], receipts_dir: Path) -> None:
    digest = manifest_sha256(manifest)
    integrity: dict[str, str] = {"sha256": digest}
    private_path, _public_path = default_key_paths(receipts_dir)
    if private_path.exists():
        serialization, _private_type = _crypto()
        private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        integrity["algorithm"] = "Ed25519"
        integrity["signature"] = base64.b64encode(private.sign(bytes.fromhex(digest))).decode("ascii")
    manifest["integrity"] = integrity


def verify_manifest(manifest: dict[str, Any], receipts_dir: Path, public_key: Path | None = None) -> tuple[bool, str]:
    integrity = manifest.get("integrity", {})
    expected = integrity.get("sha256")
    actual = manifest_sha256(manifest)
    if not expected or expected != actual:
        return False, "sha256 mismatch"
    signature = integrity.get("signature")
    if not signature:
        return True, "sha256 verified (unsigned)"
    key_path = public_key or default_key_paths(receipts_dir)[1]
    if not key_path.exists():
        return False, f"sha256 verified but public key is unavailable: {key_path}"
    try:
        serialization, _private_type = _crypto()
        public = serialization.load_pem_public_key(key_path.read_bytes())
        public.verify(base64.b64decode(signature), bytes.fromhex(actual))
    except Exception as error:
        return False, f"Ed25519 signature verification failed: {error}"
    return True, "sha256 and Ed25519 signature verified"
