"""rtp-llm inference backend stub (HAL-registered)."""

from __future__ import annotations

from neuroswarm_arm.runtime.dipa.backends.unavailable import UnavailableBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import DeviceClass


class RtpLlmBackend(UnavailableBackend):
    def __init__(self, name: str = "rtp_llm", tier: int = 0) -> None:
        super().__init__(
            name,
            feature="rtp-llm",
            tier=tier,
            device_classes=(DeviceClass.CPU, DeviceClass.GPU),
            continuous_batching=True,
            streaming=True,
        )
