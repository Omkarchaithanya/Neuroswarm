"""Fast tool-call drafter — predict tool before main model emits tool_calls.

Backends (``NSA_TOOL_PREDICTOR_BACKEND``):
  * ``embedding`` (default) — BGE/hash cosine over ToolRegistry, zero LLM cost
  * ``tier1_llm`` — constrained JSON call to ``NSA_TIER1_URL`` (~150ms Axion);
    unreachable → fall back to embedding + ``tool_predictor_fallback_total``
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from time import perf_counter
from typing import Any, Mapping
from urllib import error, request

import numpy as np

from .models import ToolRecord
from .registry import ToolRegistry
from .similarity import cosine_scores, keyword_overlap, l2_normalize

try:
    import jsonschema as _jsonschema
except ImportError:  # pragma: no cover
    _jsonschema = None  # type: ignore[assignment]

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(slots=True)
class DraftCall:
    tool_id: str
    arguments: dict[str, Any]
    score: float
    backend: str
    latency_ms: float


def _env_backend(default: str = "embedding") -> str:
    raw = (os.getenv("NSA_TOOL_PREDICTOR_BACKEND") or default).strip().lower()
    return raw if raw in {"embedding", "tier1_llm"} else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _args_template(tool: ToolRecord) -> dict[str, Any]:
    """Pull example args from ToolRecord.example_args or input_schema examples."""
    ea = getattr(tool, "example_args", None)
    if isinstance(ea, Mapping) and ea:
        return dict(ea)

    schema = tool.input_schema or {}
    if not isinstance(schema, dict):
        return {}

    if "example" in schema and isinstance(schema["example"], dict):
        return dict(schema["example"])

    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        first = examples[0]
        if isinstance(first, dict):
            return dict(first)

    props = schema.get("properties") or {}
    out: dict[str, Any] = {}
    if isinstance(props, dict):
        for key, spec in props.items():
            if not isinstance(spec, dict):
                continue
            if "example" in spec:
                out[str(key)] = spec["example"]
            elif "default" in spec:
                out[str(key)] = spec["default"]
    return out


def _tool_summary(tool: ToolRecord) -> dict[str, Any]:
    return {
        "id": tool.id,
        "name": tool.name,
        "description": (tool.description or "")[:240],
        "parameters": tool.input_schema or {
            "type": "object",
            "properties": {k: {"type": "string", "description": str(v)} for k, v in tool.params.items()},
        },
    }


def _minimal_schema_check(args: dict[str, Any], schema: dict[str, Any]) -> bool:
    """Hand-rolled required-keys + rough type check when jsonschema missing."""
    if not schema:
        return True
    required = schema.get("required") or []
    if isinstance(required, list):
        for key in required:
            if str(key) not in args:
                return False
    props = schema.get("properties") or {}
    if not isinstance(props, dict):
        return True
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for key, value in args.items():
        spec = props.get(key)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        if expected in type_map:
            py_t = type_map[expected]
            if expected == "number" and isinstance(value, bool):
                return False
            if not isinstance(value, py_t):
                return False
    return True


def _validate_args(args: dict[str, Any], schema: dict[str, Any]) -> bool:
    if not schema:
        return True
    if _jsonschema is not None:
        try:
            _jsonschema.validate(instance=args, schema=schema)
            return True
        except Exception:
            return False
    return _minimal_schema_check(args, schema)


def _parse_tool_json(text: str) -> tuple[str | None, dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None, {}
    raw = _JSON_FENCE_RE.sub("", raw).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None, {}
        try:
            obj = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None, {}
    if not isinstance(obj, dict) or not obj:
        return None, {}
    name = obj.get("name") or obj.get("tool") or obj.get("tool_id")
    args = obj.get("arguments") if "arguments" in obj else obj.get("args")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    return (str(name) if name else None), dict(args)


def _resolve_tool(registry: ToolRegistry, name: str) -> ToolRecord | None:
    needle = name.strip().lower()
    for tool in registry.as_list():
        if tool.id.lower() == needle or tool.name.lower() == needle:
            return tool
    return None


def _candidate_tools(registry: ToolRegistry) -> list[ToolRecord]:
    tools = registry.as_list()
    executable = [t for t in tools if getattr(t, "executable", False)]
    return executable if executable else tools


def _clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


class ToolCallPredictor:
    """Predict next tool call before the main model generates tool_calls."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        embedder: Any,
        tier1_url: str | None = None,
        backend: str | None = None,
        n_drafts: int | None = None,
        confidence_threshold: float | None = None,
        timeout_ms: int | None = None,
        metrics: Any | None = None,
    ) -> None:
        self.registry = registry
        self.embedder = embedder
        self.tier1_url = (
            tier1_url
            or os.getenv("NSA_TIER1_URL")
            or "http://tier1:8080"
        ).rstrip("/")
        if backend is None:
            self.backend = _env_backend("embedding")
        else:
            self.backend = backend if backend in {"embedding", "tier1_llm"} else "embedding"
        self.n_drafts = max(1, int(n_drafts if n_drafts is not None else _env_int("NSA_TOOL_PREDICTOR_N", 2)))
        self.confidence_threshold = float(
            confidence_threshold
            if confidence_threshold is not None
            else _env_float("NSA_TOOL_PREDICTOR_THRESHOLD", 0.55)
        )
        self.timeout_ms = int(
            timeout_ms if timeout_ms is not None else _env_int("NSA_TOOL_PREDICTOR_TIMEOUT_MS", 250)
        )
        self.metrics = metrics
        self._fallback_total = 0.0

    def predict(self, query: str, *, context: dict | None = None) -> list[DraftCall]:
        """Return up to ``n_drafts`` draft calls, score-desc, all score >= threshold."""
        backend = self.backend
        if backend == "tier1_llm":
            drafts, ok = self._predict_tier1(query, context=context)
            if ok:
                return drafts
            self._record_fallback()
            return self._predict_embedding(query, context=context, backend_label="embedding")
        return self._predict_embedding(query, context=context, backend_label="embedding")

    def _record_fallback(self) -> None:
        self._fallback_total += 1.0
        if self.metrics is not None and hasattr(self.metrics, "inc"):
            try:
                self.metrics.inc("tool_predictor_fallback_total")
            except Exception:
                pass

    def _predict_embedding(
        self,
        query: str,
        *,
        context: dict | None,
        backend_label: str,
    ) -> list[DraftCall]:
        t0 = perf_counter()
        tools = _candidate_tools(self.registry)
        if not tools or not (query or "").strip():
            return []

        encode_q = getattr(self.embedder, "encode_query", None)
        encode = getattr(self.embedder, "encode")
        qvec = encode_q(query) if callable(encode_q) else encode(query)
        qvec = l2_normalize(np.asarray(qvec, dtype=np.float32).reshape(-1))

        texts = [t.index_text() for t in tools]
        if hasattr(self.embedder, "encode_batch"):
            matrix = np.asarray(self.embedder.encode_batch(texts), dtype=np.float32)
        else:
            matrix = np.stack([np.asarray(encode(t), dtype=np.float32).reshape(-1) for t in texts])
        matrix = l2_normalize(matrix)
        scores = cosine_scores(qvec, matrix)

        # Optional context bias: prior tool ids get a small lift.
        prior: set[str] = set()
        if context:
            for key in ("previous_tools", "tool_chain"):
                vals = context.get(key) or []
                if isinstance(vals, list):
                    prior.update(str(v) for v in vals)

        ranked: list[tuple[ToolRecord, float]] = []
        for tool, raw in zip(tools, scores):
            semantic = float(raw)
            lexical = keyword_overlap(query, tool.index_text())
            # Short queries often under-score on pure cosine — take the better signal.
            score = max(semantic, lexical)
            if tool.id in prior:
                score = min(1.0, score + 0.05)
            ranked.append((tool, _clamp01(score)))
        ranked.sort(key=lambda x: x[1], reverse=True)

        latency = (perf_counter() - t0) * 1000.0
        drafts: list[DraftCall] = []
        for tool, score in ranked:
            if score < self.confidence_threshold:
                continue
            drafts.append(
                DraftCall(
                    tool_id=tool.id,
                    arguments=_args_template(tool),
                    score=score,
                    backend=backend_label,
                    latency_ms=latency,
                )
            )
            if len(drafts) >= self.n_drafts:
                break
        return drafts

    def _predict_tier1(
        self,
        query: str,
        *,
        context: dict | None,
    ) -> tuple[list[DraftCall], bool]:
        """Return (drafts, reachable). reachable=False → caller should fall back."""
        t0 = perf_counter()
        tools = _candidate_tools(self.registry)
        if not tools:
            return [], True

        summaries = [_tool_summary(t) for t in tools]
        convo = query
        if context and context.get("conversation_excerpt"):
            convo = f"{context['conversation_excerpt']}\nUser: {query}"

        prompt = (
            "Given this conversation, output the most likely tool call as JSON "
            '{name, arguments}. If uncertain, output {}. '
            f"Tools: {json.dumps(summaries, separators=(',', ':'))}.\n\n"
            f"Conversation:\n{convo}"
        )
        try:
            content = self._tier1_complete(prompt)
        except Exception:
            return [], False

        name, args = _parse_tool_json(content)
        latency = (perf_counter() - t0) * 1000.0
        if not name:
            return [], True

        tool = _resolve_tool(self.registry, name)
        if tool is None:
            return [], True

        schema = tool.input_schema or {}
        if schema and not _validate_args(args, schema):
            return [], True

        score = 1.0
        if score < self.confidence_threshold:
            return [], True

        return (
            [
                DraftCall(
                    tool_id=tool.id,
                    arguments=args or _args_template(tool),
                    score=score,
                    backend="tier1_llm",
                    latency_ms=latency,
                )
            ],
            True,
        )

    def _tier1_complete(self, prompt: str) -> str:
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a tool-call predictor. Reply with ONLY a JSON object "
                        '{ "name": "<tool>", "arguments": { ... } } or {}.'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 128,
            "temperature": 0.0,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.tier1_url}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout_s = max(0.05, self.timeout_ms / 1000.0)
        try:
            with request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(f"tier1 HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"tier1 unavailable: {exc.reason}") from exc

        choices = data.get("choices") if isinstance(data, dict) else None
        if isinstance(choices, list) and choices:
            c0 = choices[0] if isinstance(choices[0], dict) else {}
            msg = c0.get("message") if isinstance(c0, dict) else None
            if isinstance(msg, dict) and msg.get("content") is not None:
                return str(msg["content"])
            if isinstance(c0, dict) and c0.get("text") is not None:
                return str(c0["text"])
        if isinstance(data, dict) and data.get("content") is not None:
            return str(data["content"])
        return ""


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

class _FakeEmbedder:
    """Deterministic bag-of-tokens embedder for offline self-test."""

    dims = 32

    def encode(self, text: str, *, normalize: bool | None = None) -> np.ndarray:
        vec = np.zeros(self.dims, dtype=np.float32)
        for tok in re.findall(r"[a-z0-9_]+", (text or "").lower()):
            vec[hash(tok) % self.dims] += 1.0
        n = float(np.linalg.norm(vec)) or 1.0
        return vec / n

    def encode_query(self, text: str, *, normalize: bool | None = None) -> np.ndarray:
        return self.encode(text)

    def encode_batch(self, texts: list[str], *, normalize: bool | None = None) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        return np.stack([self.encode(t) for t in texts])


def _build_demo_registry() -> ToolRegistry:
    reg = ToolRegistry()
    demos = [
        ToolRecord(
            id="foo.search",
            name="foo_search",
            description="Search foo catalog and return matching foo records",
            params={"query": "string"},
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "example": "foo"}},
                "required": ["query"],
                "examples": [{"query": "foo"}],
            },
            example_args={"query": "foo"},
            example_prompts=["find foo items"],
            executable=True,
        ),
        ToolRecord(
            id="foo.write",
            name="foo_write",
            description="Write a foo document into the foo store",
            params={"text": "string"},
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "example": "hello foo"}},
                "required": ["text"],
            },
            example_args={"text": "hello foo"},
            example_prompts=["write foo note"],
            executable=True,
        ),
        ToolRecord(
            id="bar.ping",
            name="bar_ping",
            description="Health ping for the bar service (unrelated to foo)",
            params={},
            input_schema={"type": "object", "properties": {}},
            example_args={},
            executable=True,
        ),
    ]
    for tool in demos:
        reg.register(tool)
    return reg


def _mock_tier1_urlopen(req: Any, timeout: float = 0):  # noqa: ARG001
    """Stand-in for urllib.request.urlopen during self-test."""
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"name": "foo_search", "arguments": {"query": "foo"}}
                    )
                }
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")

    class _Resp:
        def read(self) -> bytes:
            return body

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    return _Resp()


def main() -> None:
    from unittest.mock import patch

    registry = _build_demo_registry()
    embedder = _FakeEmbedder()

    emb = ToolCallPredictor(
        registry=registry,
        embedder=embedder,
        backend="embedding",
        n_drafts=2,
        confidence_threshold=0.55,
    )
    drafts = emb.predict("foo")
    print("embedding:", drafts)
    assert len(drafts) == 2, f"expected 2 drafts, got {len(drafts)}"
    assert drafts[0].score >= drafts[1].score, "drafts must be score-desc"
    assert all(d.score >= 0.55 for d in drafts), f"scores below threshold: {drafts}"
    assert all(d.backend == "embedding" for d in drafts)

    llm = ToolCallPredictor(
        registry=registry,
        embedder=embedder,
        backend="tier1_llm",
        tier1_url="http://tier1-mock:8080",
        n_drafts=2,
        confidence_threshold=0.55,
        timeout_ms=250,
    )
    with patch("neuroswarm_arm.runtime.router.tool_call_predictor.request.urlopen", _mock_tier1_urlopen):
        llm_drafts = llm.predict("foo")
    print("tier1_llm:", llm_drafts)
    assert llm_drafts, "tier1_llm mock should return a draft"
    assert llm_drafts[0].tool_id == "foo.search"
    assert llm_drafts[0].backend == "tier1_llm"
    print("ok")


if __name__ == "__main__":
    main()
