"""Deprecated path — use ``neuroswarm_arm.runtime.memory.adapter.sdk_client``."""

from neuroswarm_arm.runtime.memory.adapter.sdk_client import (  # noqa: F401
    Mem0Client,
    Mem0SdkClient,
    build_mem0_config,
)

__all__ = ["Mem0Client", "Mem0SdkClient", "build_mem0_config"]
