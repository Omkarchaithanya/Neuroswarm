"""Backward-compatible HAOE facade.

Historical import path: ``from neuroswarm_arm.router import HAOEScheduler``.
The production kernel lives at ``neuroswarm_arm.runtime.haoe``.
"""

from __future__ import annotations

from neuroswarm_arm.runtime.haoe import HAOERuntime, HAOEScheduler, build_haoe

__all__ = ["HAOEScheduler", "HAOERuntime", "build_haoe"]
