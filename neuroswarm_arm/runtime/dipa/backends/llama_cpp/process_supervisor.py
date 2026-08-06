"""ProcessSupervisor — own llama-server lifecycle (spawn/stop/log scrape)."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kleidiai_verifier import KleidiaiVerifier


def _shm_enabled() -> bool:
    """Check if NSA KV shared memory is enabled via environment."""
    val = os.getenv("NSA_KV_SHM_ENABLED", "0").strip()
    return val in {"1", "true", "TRUE", "yes"}


def _get_shm_name(session_id: str | None = None) -> str:
    """Generate shared memory name for session."""
    if session_id:
        return f"nsa_kv_{session_id}"
    return f"nsa_kv_{os.getpid()}"


@dataclass
class SupervisedProcess:
    name: str
    pid: int | None = None
    base_url: str = ""
    command: list[str] = field(default_factory=list)
    started_at: float = 0.0
    kleidiai_ok: bool = False
    last_error: str = ""
    draft_pid: int | None = None
    draft_base_url: str = ""
    draft_command: list[str] = field(default_factory=list)
    draft_started_at: float = 0.0
    draft_kleidiai_ok: bool = False
    draft_last_error: str = ""


class ProcessSupervisor:
    """Manage local llama-server child processes with KleidiAI log verification."""

    def __init__(
        self,
        *,
        require_kleidiai: bool | None = None,
        log_dir: Path | None = None,
    ) -> None:
        env_req = os.getenv("NSA_REQUIRE_KLEIDIAI", "0").strip() in {
            "1",
            "true",
            "TRUE",
            "yes",
        }
        self.require_kleidiai = (
            env_req if require_kleidiai is None else require_kleidiai
        )
        self.log_dir = log_dir or Path("work/llama_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._procs: dict[str, subprocess.Popen[str]] = {}
        self._meta: dict[str, SupervisedProcess] = {}
        self._verifiers: dict[str, KleidiaiVerifier] = {}
        self._readers: dict[str, threading.Thread] = {}

    def start(
        self,
        name: str,
        command: Sequence[str],
        *,
        base_url: str,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        numa_bind: Sequence[str] | None = None,
        session_id: str | None = None,
    ) -> SupervisedProcess:
        with self._lock:
            if name in self._procs and self._procs[name].poll() is None:
                return self._meta[name]
            cmd = list(command)
            if numa_bind:
                # Topology-gated: callers only pass numa_bind when nodes > 1.
                cmd = list(numa_bind) + cmd
                if "--numa" not in cmd:
                    cmd.extend(["--numa", "isolate"])
            elif env and env.get("NSA_TASKSET_CPUS"):
                # Single-UMA cache-aware pin via taskset (Axion path).
                cpus = str(env["NSA_TASKSET_CPUS"])
                cmd = ["taskset", "-c", cpus] + cmd
            
            # Add KV SHM backend if enabled
            if _shm_enabled():
                shm_name = _get_shm_name(session_id)
                cmd.extend(["--kv-backend", "shm", "--kv-shm-name", shm_name])
            
            log_path = self.log_dir / f"{name}.log"
            log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
            full_env = dict(os.environ)
            if env:
                full_env.update({k: str(v) for k, v in env.items()})
            # Leave GGML_KLEIDIAI_SME unset for auto unless caller sets it.
            try:
                # Pass the SHM fd to child process if SHM enabled
                pass_fds = ()
                if _shm_enabled() and hasattr(os, 'get_inheritable'):
                    # The fd will be inherited by child process
                    pass_fds = ()
                
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=full_env,
                    cwd=cwd,
                    bufsize=1,
                    pass_fds=pass_fds,
                )
            except Exception as exc:
                log_f.close()
                meta = SupervisedProcess(
                    name=name,
                    base_url=base_url,
                    command=cmd,
                    last_error=str(exc),
                )
                self._meta[name] = meta
                raise
            verifier = KleidiaiVerifier(require=self.require_kleidiai)
            self._procs[name] = proc
            self._verifiers[name] = verifier
            meta = SupervisedProcess(
                name=name,
                pid=proc.pid,
                base_url=base_url,
                command=cmd,
                started_at=time.time(),
            )
            self._meta[name] = meta

            def _read() -> None:
                assert proc.stdout is not None
                try:
                    for line in proc.stdout:
                        log_f.write(line)
                        log_f.flush()
                        if verifier.feed(line):
                            meta.kleidiai_ok = True
                finally:
                    try:
                        log_f.close()
                    except Exception:
                        pass

            t = threading.Thread(target=_read, name=f"llama-log-{name}", daemon=True)
            t.start()
            self._readers[name] = t
            return meta

    def start_draft(
        self,
        name: str,
        command: Sequence[str],
        *,
        base_url: str,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        session_id: str | None = None,
    ) -> SupervisedProcess:
        with self._lock:
            meta = self._meta.get(name)
            if meta is None:
                raise KeyError(f"No target process named '{name}'")
            if meta.draft_pid is not None:
                proc = self._procs.get(f"{name}-draft")
                if proc is not None and proc.poll() is None:
                    return meta
            cmd = list(command)
            
            # Add KV SHM backend if enabled
            if _shm_enabled():
                shm_name = _get_shm_name(session_id)
                cmd.extend(["--kv-backend", "shm", "--kv-shm-name", shm_name])
            
            log_path = self.log_dir / f"{name}-draft.log"
            log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
            full_env = dict(os.environ)
            if env:
                full_env.update({k: str(v) for k, v in env.items()})
            try:
                pass_fds = ()
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=full_env,
                    cwd=cwd,
                    bufsize=1,
                    pass_fds=pass_fds,
                )
            except Exception as exc:
                log_f.close()
                meta.draft_last_error = str(exc)
                raise
            verifier = KleidiaiVerifier(require=self.require_kleidiai)
            self._procs[f"{name}-draft"] = proc
            self._verifiers[f"{name}-draft"] = verifier
            meta.draft_pid = proc.pid
            meta.draft_base_url = base_url
            meta.draft_command = cmd
            meta.draft_started_at = time.time()

            def _read_draft() -> None:
                assert proc.stdout is not None
                try:
                    for line in proc.stdout:
                        log_f.write(line)
                        log_f.flush()
                        if verifier.feed(line):
                            meta.draft_kleidiai_ok = True
                finally:
                    try:
                        log_f.close()
                    except Exception:
                        pass

            t = threading.Thread(
                target=_read_draft,
                name=f"llama-log-{name}-draft",
                daemon=True,
            )
            t.start()
            self._readers[f"{name}-draft"] = t
            return meta

    def wait_kleidiai(self, name: str, timeout_s: float = 120.0) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            meta = self._meta.get(name)
            if meta and meta.kleidiai_ok:
                return True
            proc = self._procs.get(name)
            if proc is not None and proc.poll() is not None:
                break
            if not self.require_kleidiai:
                # Soft path: process alive is enough if not requiring KleidiAI.
                if proc is not None and proc.poll() is None and time.time() - (
                    meta.started_at if meta else 0
                ) > 2.0:
                    return True
            time.sleep(0.2)
        verifier = self._verifiers.get(name)
        if verifier is not None:
            verifier.assert_ready()
            return verifier.result().ok
        return False

    def stop(self, name: str, timeout_s: float = 15.0) -> None:
        with self._lock:
            proc = self._procs.get(name)
            if proc is None:
                return
            if proc.poll() is None:
                try:
                    if os.name == "nt":
                        proc.terminate()
                    else:
                        proc.send_signal(signal.SIGTERM)
                except Exception:
                    proc.kill()
                try:
                    proc.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    proc.kill()
            self._procs.pop(name, None)

    def stop_draft(self, name: str, timeout_s: float = 15.0) -> None:
        with self._lock:
            proc = self._procs.get(f"{name}-draft")
            if proc is None:
                return
            if proc.poll() is None:
                try:
                    if os.name == "nt":
                        proc.terminate()
                    else:
                        proc.send_signal(signal.SIGTERM)
                except Exception:
                    proc.kill()
                try:
                    proc.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    proc.kill()
            self._procs.pop(f"{name}-draft", None)
            meta = self._meta.get(name)
            if meta:
                meta.draft_pid = None

    def wait_draft_ready(self, name: str, timeout_s: float = 60.0) -> bool:
        import urllib.request
        import urllib.error

        meta = self._meta.get(name)
        if meta is None:
            return False
        draft_url = meta.draft_base_url.rstrip("/") + "/health"
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            proc = self._procs.get(f"{name}-draft")
            if proc is not None and proc.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(draft_url, timeout=2.0) as resp:
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                pass
            time.sleep(0.5)
        return False

    def stop_all(self) -> None:
        for name in list(self._procs):
            self.stop(name)

    def snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        with self._lock:
            for name, meta in self._meta.items():
                proc = self._procs.get(name)
                draft_proc = self._procs.get(f"{name}-draft")
                out[name] = {
                    "pid": meta.pid,
                    "base_url": meta.base_url,
                    "command": meta.command,
                    "kleidiai_ok": meta.kleidiai_ok,
                    "running": proc is not None and proc.poll() is None,
                    "last_error": meta.last_error,
                    "verify": (
                        asdict(self._verifiers[name].result())
                        if name in self._verifiers
                        else {}
                    ),
                    "draft": {
                        "pid": meta.draft_pid,
                        "base_url": meta.draft_base_url,
                        "command": meta.draft_command,
                        "kleidiai_ok": meta.draft_kleidiai_ok,
                        "running": draft_proc is not None and draft_proc.poll() is None,
                        "last_error": meta.draft_last_error,
                        "verify": (
                            asdict(self._verifiers[f"{name}-draft"].result())
                            if f"{name}-draft" in self._verifiers
                            else {}
                        ),
                    },
                }
        return out
