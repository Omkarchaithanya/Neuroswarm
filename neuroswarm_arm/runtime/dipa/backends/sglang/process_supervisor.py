"""SGLang process supervisor — optional local launch_server ownership."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Proc:
    popen: subprocess.Popen[Any] | None = None
    command: list[str] = field(default_factory=list)
    base_url: str = ""


class SGLangProcessSupervisor:
    """Best-effort process ownership; compose/K8s usually owns the process."""

    def __init__(self) -> None:
        self._procs: dict[str, _Proc] = {}

    def start(
        self,
        name: str,
        command: list[str],
        *,
        base_url: str = "",
        env: dict[str, str] | None = None,
    ) -> None:
        if name in self._procs and self._procs[name].popen is not None:
            return
        merged = dict(os.environ)
        merged.setdefault("SGLANG_USE_CPU_ENGINE", "1")
        if env:
            merged.update(env)
        popen = subprocess.Popen(  # noqa: S603 — operator-supplied command
            command,
            env=merged,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._procs[name] = _Proc(popen=popen, command=list(command), base_url=base_url)

    def stop(self, name: str) -> None:
        proc = self._procs.pop(name, None)
        if proc is None or proc.popen is None:
            return
        proc.popen.terminate()
        try:
            proc.popen.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.popen.kill()

    def wait_ready(self, name: str, check, timeout_s: float = 180.0) -> bool:  # type: ignore[no-untyped-def]
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                if check():
                    return True
            except Exception:
                pass
            time.sleep(1.0)
        return False

    def snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, proc in self._procs.items():
            alive = proc.popen is not None and proc.popen.poll() is None
            out[name] = {
                "alive": alive,
                "base_url": proc.base_url,
                "command": list(proc.command),
            }
        return out
