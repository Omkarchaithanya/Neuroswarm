"""MLX speculative decoding controller — spawns mlx_lm.server subprocess."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from typing import Any
from urllib import error, request

# ---------------------------------------------------------------------------
# Env-gated configuration (NSA_* with safe defaults).
# ---------------------------------------------------------------------------


def _resolve_num_draft_tokens() -> int:
    try:
        return int(os.getenv("NSA_MLX_NUM_DRAFT_TOKENS", "5"))
    except ValueError:
        return 5


def _resolve_max_tokens() -> int:
    try:
        return int(os.getenv("NSA_MLX_MAX_TOKENS", "2048"))
    except ValueError:
        return 2048


def _resolve_model_path() -> str:
    return os.getenv("NSA_MLX_MODEL_PATH", "").strip()


def _resolve_draft_model_path() -> str:
    return os.getenv("NSA_MLX_DRAFT_MODEL_PATH", "").strip()


class MlxSpecController:
    """Manage ``mlx_lm.server`` subprocess for speculative decoding.

    The server exposes an OpenAI-compatible ``/v1/chat/completions``
    endpoint.  When ``--draft-model`` is provided, ``mlx_lm`` performs
    speculative decoding internally (draft propose + target verify) and
    returns the accepted tokens.

    ASCR's ``quality`` verifier (no target forward) and ``ngram``/``suffix``
    proposers can still be used for acceptance metrics on top of the
    server's output.
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        model_path: str = "",
        draft_model_path: str = "",
        port: int = 8080,
    ) -> None:
        self._port = port
        self._base_url = base_url or f"http://127.0.0.1:{port}"
        self._model_path = model_path or _resolve_model_path()
        self._draft_model_path = draft_model_path or _resolve_draft_model_path()
        self._num_draft_tokens = _resolve_num_draft_tokens()
        self._max_tokens = _resolve_max_tokens()
        self._proc: subprocess.Popen[str] | None = None
        self._started_at: float = 0.0
        self._lock = threading.RLock()
        self._last_error: str = ""

    # -- Lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Spawn ``mlx_lm.server`` with draft-model speculative decoding."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return  # already running

            cmd = self._build_command()
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                self._started_at = time.time()
                self._last_error = ""
            except Exception as exc:
                self._last_error = str(exc)
                raise

    def stop(self, timeout_s: float = 15.0) -> None:
        with self._lock:
            if self._proc is None:
                return
            if self._proc.poll() is None:
                try:
                    self._proc.send_signal(signal.SIGTERM)
                except Exception:
                    self._proc.kill()
                try:
                    self._proc.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None

    def is_ready(self) -> bool:
        try:
            req = request.Request(
                self._base_url + "/health", method="GET"
            )
            with request.urlopen(req, timeout=5.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def wait_ready(self, timeout_s: float = 120.0) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                self._last_error = (
                    f"mlx_lm.server exited with code {self._proc.returncode}"
                )
                return False
            if self.is_ready():
                return True
            time.sleep(0.5)
        return False

    # -- Speculative decode proxy -------------------------------------------

    def ensure_ready(self, timeout_s: float = 120.0) -> None:
        """Start server if needed and block until /health responds."""
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
        if not running:
            self.start()
        if self.is_ready():
            return
        if not self.wait_ready(timeout_s=timeout_s):
            err = self._last_error or "mlx_lm.server failed to become ready"
            raise RuntimeError(err)

    def propose_sync(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Send a chat request to the MLX server (sync, for asyncio.to_thread)."""
        self.ensure_ready()
        payload: dict[str, Any] = {
            "model": "default",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self._base_url.rstrip("/") + "/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(f"MLX server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"MLX server unavailable: {exc.reason}") from exc

    def verify_sync(
        self,
        messages: list[dict[str, str]],
        draft_tokens: list[int],
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Verify draft tokens against the target model via the MLX server.

        For mlx_lm.server, speculative decoding is handled server-side —
        this method sends the full context and lets the server's internal
        spec loop produce the accepted output.  ``draft_tokens`` is
        informational for ASCR metrics.
        """
        return self.propose_sync(messages, max_tokens, temperature)

    # -- Snapshot / diagnostics ---------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        running = self._proc is not None and self._proc.poll() is None
        return {
            "pid": self._proc.pid if self._proc else None,
            "running": running,
            "base_url": self._base_url,
            "model_path": self._model_path,
            "draft_model_path": self._draft_model_path,
            "num_draft_tokens": self._num_draft_tokens,
            "last_error": self._last_error,
            "uptime_s": (time.time() - self._started_at) if running else 0.0,
        }

    # -- Internal ------------------------------------------------------------

    def _build_command(self) -> list[str]:
        cmd = [
            "python",
            "-m",
            "mlx_lm.server",
            "--model",
            self._model_path,
            "--port",
            str(self._port),
            "--max-tokens",
            str(self._max_tokens),
        ]
        if self._draft_model_path:
            cmd.extend(["--draft-model", self._draft_model_path])
            cmd.extend(["--num-draft-tokens", str(self._num_draft_tokens)])
        return cmd
