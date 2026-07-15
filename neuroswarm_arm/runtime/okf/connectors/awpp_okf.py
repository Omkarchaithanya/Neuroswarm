from __future__ import annotations

from typing import Any


class AWPPOkfAdapter:
    """Implements SupportsOKF for AWPP pre-warm."""

    def __init__(self, okf_runtime: Any):
        self.okf = okf_runtime

    def load_index(self) -> Any:
        return self.okf.load_index()

    def load_topic(self, relative_path: str) -> Any:
        return self.okf.load_topic(relative_path)
