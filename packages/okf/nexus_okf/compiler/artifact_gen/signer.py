from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from nexus_okf.internal.mmap_json import dump_json, load_json


def sign_manifest(manifest_path: Path, private_key_pem: bytes | None = None) -> dict[str, Any]:
    """Attach integrity signature to manifest.

    Uses HMAC-SHA256 with provided key, or content digest-only when no key.
    Ed25519 optional when cryptography is installed and PEM provided.
    """
    manifest = load_json(manifest_path)
    payload = repr(sorted((manifest.get("artifacts") or {}).items())).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    sig: dict[str, Any] = {"alg": "sha256", "digest": digest}
    if private_key_pem:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import load_pem_private_key

            key = load_pem_private_key(private_key_pem, password=None)
            if isinstance(key, Ed25519PrivateKey):
                signature = key.sign(payload)
                sig = {
                    "alg": "ed25519",
                    "digest": digest,
                    "signature": base64.b64encode(signature).decode("ascii"),
                }
        except Exception:
            # fallback HMAC
            import hmac

            sig = {
                "alg": "hmac-sha256",
                "digest": digest,
                "signature": hmac.new(private_key_pem, payload, hashlib.sha256).hexdigest(),
            }
    manifest["signature"] = sig
    dump_json(manifest_path, manifest)
    return sig


def verify_manifest(manifest_path: Path) -> bool:
    manifest = load_json(manifest_path)
    sig = manifest.get("signature") or {}
    payload = repr(sorted((manifest.get("artifacts") or {}).items())).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return sig.get("digest") == digest
