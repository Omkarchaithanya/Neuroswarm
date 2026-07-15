from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class OKFConfig:
    source_root: Path
    artifact_root: Path
    auto_build: bool = True
    token_budget: int = 1200
    enabled: bool = True


def load_okf_config(source_root: Path | None = None) -> OKFConfig:
    source = Path(os.getenv("NSA_OKF_ROOT", str(source_root or "okf")))
    artifacts = Path(os.getenv("NSA_OKF_ARTIFACTS", str(source / ".okf" / "artifacts")))
    return OKFConfig(
        source_root=source,
        artifact_root=artifacts,
        auto_build=os.getenv("NSA_OKF_AUTO_BUILD", "1") not in {"0", "false", "False"},
        token_budget=int(os.getenv("NSA_OKF_TOKEN_BUDGET", "1200")),
        enabled=os.getenv("NSA_OKF_ENABLED", "1") not in {"0", "false", "False"},
    )


def build_okf(config: OKFConfig | None = None, metrics_bridge: Any = None) -> "OKFNexusRuntime":
    from .kernel import OKFNexusRuntime

    cfg = config or load_okf_config()
    return OKFNexusRuntime(cfg, metrics_bridge=metrics_bridge)
