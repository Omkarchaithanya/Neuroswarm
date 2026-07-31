"""Draft model registry: (target_model, host_arch) → (draft_path, draft_quant)."""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Any, Mapping

# (target_model, host_arch) → (draft_model_id, quant)
PAIRS: dict[tuple[str, str], tuple[str, str]] = {
    ("Qwen2.5-3B-Instruct-4bit", "neoverse-v2"): (
        "Qwen2.5-0.5B-Instruct-4bit",
        "Q4_0",
    ),
    ("Qwen2.5-3B-Instruct-4bit", "neoverse-v3"): (
        "Qwen2.5-0.5B-Instruct-4bit",
        "Q4_0",
    ),
    ("Llama-3.2-3B-Instruct-4bit", "neoverse-v2"): (
        "Llama-3.2-1B-Instruct-4bit",
        "Q4_0",
    ),
    ("Llama-3.2-3B-Instruct-4bit", "neoverse-v3"): (
        "Llama-3.2-1B-Instruct-4bit",
        "Q4_0",
    ),
    ("SmolLM2-1.7B-Instruct-4bit", "neoverse-v2"): (
        "SmolLM2-135M-Instruct-4bit",
        "Q4_0",
    ),
    ("SmolLM2-1.7B-Instruct-4bit", "neoverse-v3"): (
        "SmolLM2-135M-Instruct-4bit",
        "Q4_0",
    ),
    ("Llama-3.2-3B-Instruct-4bit", "apple-m"): (
        "Llama-3.2-1B-Instruct-4bit",
        "Q4_0",
    ),
    ("Llama-3.2-3B-Instruct-4bit", "apple-pro"): (
        "Llama-3.2-1B-Instruct-4bit",
        "Q4_0",
    ),
    ("Llama-3.2-3B-Instruct-4bit", "apple-max"): (
        "Llama-3.2-1B-Instruct-4bit",
        "Q4_0",
    ),
    ("Qwen2.5-3B-Instruct-4bit", "apple-m"): (
        "Qwen2.5-0.5B-Instruct-4bit",
        "Q4_0",
    ),
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def detect_host_arch() -> str:
    """Return one of: neoverse-v2, neoverse-v3, apple-m, apple-pro, apple-max, x86."""
    override = (os.getenv("NSA_HOST_ARCH") or "").strip()
    if override:
        return override.lower()

    if platform.system() == "Darwin":
        return _detect_apple_arch()

    machine = platform.machine().lower()
    if machine in {"aarch64", "arm64"}:
        try:
            from neuroswarm_arm.runtime.dipa.backends.llama_cpp.kleidiai_verifier import (
                probe_cpu_features,
            )

            feats = probe_cpu_features()
            if feats.sme2:
                return "neoverse-v3"
            if feats.ok:  # sve2 + i8mm + asimddp → Axion / Neoverse-V2 class
                return "neoverse-v2"
        except Exception:  # noqa: BLE001 — best-effort probe
            pass
        return "neoverse-v2"

    return "x86"


def _detect_apple_arch() -> str:
    model = ""
    try:
        model = (
            subprocess.check_output(
                ["sysctl", "-n", "hw.model"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            .strip()
            .lower()
        )
    except (OSError, subprocess.CalledProcessError):
        model = ""
    if "ultr" in model or "max" in model:
        return "apple-max"
    if "pro" in model:
        return "apple-pro"
    return "apple-m"


def _pairs_from_config(cfg: Mapping[str, Any] | None) -> dict[tuple[str, str], tuple[str, str]]:
    """Merge hardcoded PAIRS with optional config overlay."""
    out = dict(PAIRS)
    if not cfg:
        return out
    raw = cfg.get("pairs")
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        if isinstance(key, (list, tuple)) and len(key) == 2:
            t, h = str(key[0]), str(key[1])
        elif isinstance(key, str) and "|" in key:
            t, h = key.split("|", 1)
        else:
            continue
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            out[(t.strip(), h.strip())] = (str(val[0]), str(val[1]))
        elif isinstance(val, dict):
            draft = val.get("draft") or val.get("draft_path")
            quant = val.get("quant") or val.get("draft_quant") or "Q4_0"
            if draft:
                out[(t.strip(), h.strip())] = (str(draft), str(quant))
    return out


class DraftModelRegistry:
    """Resolve draft model id + quant for a (target, host_arch) pair."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self._pairs = _pairs_from_config(config)

    def resolve(
        self, target_model: str, host_arch: str
    ) -> tuple[str, str] | None:
        if not target_model or not host_arch:
            return None
        key = (str(target_model).strip(), str(host_arch).strip().lower())
        hit = self._pairs.get(key)
        if hit is None:
            return None
        return (hit[0], hit[1])
