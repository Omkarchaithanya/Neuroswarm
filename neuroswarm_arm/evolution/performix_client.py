from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


# Human/legacy names → Arm Performix recipe ids (underscores).
_RECIPE_ALIASES = {
    "code-hotspots": "code_hotspots",
    "code_hotspots": "code_hotspots",
    "cpu-microarch": "cpu_microarchitecture",
    "cpu-microarchitecture": "cpu_microarchitecture",
    "cpu_microarchitecture": "cpu_microarchitecture",
    "instruction-mix": "instruction_mix",
    "instruction_mix": "instruction_mix",
    "memory-access": "memory_access",
    "memory_access": "memory_access",
    "system-utilization": "system_utilization",
    "system_utilization": "system_utilization",
    "syscall-trace-summary": "syscall_trace_summary",
    "syscall_trace_summary": "syscall_trace_summary",
    "asct": "asct",
}


def normalize_recipe(recipe: str) -> str:
    key = (recipe or "").strip()
    if key in _RECIPE_ALIASES:
        return _RECIPE_ALIASES[key]
    return key.replace("-", "_")


@dataclass(slots=True)
class PerformixClient:
    binary: str = "apx"
    use_nsenter: bool = False

    def __post_init__(self) -> None:
        if not self.use_nsenter:
            import os

            self.use_nsenter = os.getenv("NSA_PERFORMIX_NSENTER", "0") not in {
                "0",
                "false",
                "False",
                "no",
                "NO",
            }

    def _cmd_prefix(self) -> list[str]:
        """Optionally run apx in the host mount namespace (Compose bridge container)."""
        if self.use_nsenter and Path("/usr/bin/nsenter").exists():
            return ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "--", self.binary]
        return [self.binary]

    def run_recipe(
        self,
        recipe: str,
        output: Path,
        target: str | None = None,
        binary: str | None = None,
        duration: int | None = None,
        *,
        system_wide: bool = True,
        pid: int | None = None,
    ) -> dict:
        """Run an Arm Performix recipe and materialize JSON at ``output``.

        Current ``apx`` has no ``--output`` / ``--duration`` flags. Flow:
        ``apx recipe run … --json`` → parse run id → ``apx run export`` → unzip → write ``output``.
        """
        recipe_id = normalize_recipe(recipe)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)

        cmd = self._cmd_prefix() + ["recipe", "run", recipe_id, "--json", "--deploy-tools"]
        if target:
            cmd.extend(["--target", target])
        if binary:
            cmd.extend(["--workload", binary])
        elif pid is not None:
            cmd.extend(["--pid", str(pid)])
        elif system_wide:
            cmd.append("--system-wide")
        if duration is not None:
            cmd.extend(["--timeout", str(int(duration))])

        result = subprocess.run(cmd, capture_output=True, text=True)
        payload: dict = {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output": str(output),
            "recipe": recipe_id,
            "cmd": cmd,
        }
        # Export whenever a run_id appears — apx often exits non-zero after starting a run.
        run_id = self._parse_run_id(result.stdout) or self._parse_run_id(result.stderr)
        payload["run_id"] = run_id
        if not run_id:
            if result.returncode == 0:
                return payload
            return payload

        export_dir = Path(tempfile.mkdtemp(prefix="apx-export-"))
        try:
            export_cmd = self._cmd_prefix() + ["run", "export", run_id, str(export_dir), "--json"]
            export = subprocess.run(export_cmd, capture_output=True, text=True)
            payload["export_returncode"] = export.returncode
            payload["export_stdout"] = export.stdout
            payload["export_stderr"] = export.stderr
            # Prefer shared normalizer (rejects failed recipe metadata / empty exports).
            norm_script = Path(__file__).resolve().parents[2] / "scripts" / "performix_normalize_export.py"
            if norm_script.is_file():
                norm = subprocess.run(
                    [sys.executable, str(norm_script), str(export_dir), str(output), run_id],
                    capture_output=True,
                    text=True,
                )
                token = (norm.stdout or "").strip().splitlines()[-1] if norm.stdout else ""
                payload["normalize_token"] = token
                payload["normalize_stderr"] = norm.stderr
                if norm.returncode == 0 and token == "ok":
                    payload["returncode"] = 0
                    payload["extracted"] = str(output)
                else:
                    payload["returncode"] = result.returncode or export.returncode or 1
                    payload["stderr"] = (payload.get("stderr") or "") + f"\nnormalize:{token or norm.stderr}"
            else:
                extracted = self._materialize_export(export_dir, output)
                payload["extracted"] = extracted
                if extracted:
                    try:
                        data = json.loads(output.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            data["source"] = "apx"
                            output.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    payload["returncode"] = 0
                else:
                    payload["returncode"] = export.returncode or result.returncode or 1
                    payload["stderr"] = (payload.get("stderr") or "") + "\nexport produced no JSON"
        finally:
            shutil.rmtree(export_dir, ignore_errors=True)
        return payload

    def compare(self, baseline: Path, optimized: Path, output: Path) -> dict:
        # Compare may still use legacy flags on some builds; keep best-effort.
        cmd = [
            self.binary,
            "recipe",
            "compare",
            "--baseline",
            str(baseline),
            "--optimized",
            str(optimized),
            "--output",
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

    @staticmethod
    def _parse_run_id(text: str) -> str | None:
        if not text:
            return None

        def _as_id(val: Any) -> str | None:
            if val is None:
                return None
            if isinstance(val, dict):
                for k in ("value", "id", "run_id", "runId"):
                    if val.get(k):
                        return str(val[k])
                return None
            s = str(val).strip()
            return s or None

        blobs: list[Any] = []
        try:
            blobs.append(json.loads(text))
        except json.JSONDecodeError:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    blobs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for data in blobs:
            if not isinstance(data, dict):
                continue
            for key in ("run_id", "id", "runId"):
                rid = _as_id(data.get(key))
                if rid:
                    return rid
            nested = data.get("data")
            if isinstance(nested, dict):
                for key in ("run_id", "id", "runId", "run"):
                    rid = _as_id(nested.get(key))
                    if rid:
                        return rid
        match = re.search(r'"run_id"\s*:\s*\{\s*"value"\s*:\s*"([0-9a-fA-F]{8,})"', text)
        if match:
            return match.group(1)
        match = re.search(r"\brun[_-]?id[\"'\s:=]+([A-Za-z0-9_-]+)", text, re.I)
        if match:
            return match.group(1)
        match = re.search(
            r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
            text,
            re.I,
        )
        return match.group(1) if match else None

    @staticmethod
    def _materialize_export(export_dir: Path, output: Path) -> str | None:
        zips = sorted(export_dir.rglob("*.zip"))
        search_roots = [export_dir]
        unpack = export_dir / "_unpacked"
        for zpath in zips:
            try:
                with zipfile.ZipFile(zpath, "r") as zf:
                    zf.extractall(unpack)
                search_roots.append(unpack)
            except Exception:
                continue

        candidates: list[Path] = []
        for root in search_roots:
            candidates.extend(root.rglob("*.json"))
        # Prefer filenames that look like recipe / hotspot summaries.
        preferred = [
            p
            for p in candidates
            if any(tok in p.name.lower() for tok in ("hotspot", "code_hotspot", "summary", "result", "metrics"))
        ]
        chosen = (preferred or candidates)
        if not chosen:
            return None
        src = chosen[0]
        shutil.copy2(src, output)
        return str(src)
