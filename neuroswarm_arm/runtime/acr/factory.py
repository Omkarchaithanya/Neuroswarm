"""Factory for Adaptive Context Runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neuroswarm_arm.runtime.acr.config import ACRConfig, load_acr_config
from neuroswarm_arm.runtime.acr.kernel import AdaptiveContextRuntime
from neuroswarm_arm.runtime.acr.metrics import ACRMetrics


def build_acr(
    work_dir: Path | str | None = None,
    *,
    config: ACRConfig | None = None,
    memory: Any | None = None,
    okf: Any | None = None,
    metrics_bridge: Any = None,
) -> AdaptiveContextRuntime:
    cfg = config or load_acr_config(work_dir)
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    metrics = ACRMetrics()
    runtime = AdaptiveContextRuntime(cfg, memory=memory, okf=okf, metrics=metrics)
    if metrics_bridge is not None and hasattr(metrics_bridge, "register_provider"):
        try:
            metrics_bridge.register_provider("acr", runtime.prometheus_text)
        except Exception:
            pass
    return runtime
