"""Draft-model Speculator for next tool call.

Predicts the tool the main (Tier 2/3) model will emit, using a small Tier-1
draft model + Top-K schemas from the semantic router. Read-only: never calls
MCP tools/execute — safe when ``NSA_MCP_EXECUTE=0``.

References:
  - arXiv:2512.15834 (Nichols et al., Speculative Tool Calls)
  - arXiv:2510.04371 (Ye et al., Speculative Actions)
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import LlamaHttpClient
from neuroswarm_arm.tools.registry import ToolRegistry
from neuroswarm_arm.tools.semantic_mcp_router import SemanticMCPRouter

_TOOL_TAG_RE = re.compile(
    r"<tool>\s*([A-Za-z0-9_.\-:/]+)\s*\((.*)\)\s*</tool>",
    re.DOTALL | re.IGNORECASE,
)
_MAX_HISTORY_MSGS = 6
_DEFAULT_N_PROBS = 5


@dataclass(slots=True)
class ToolPrediction:
    """Single draft tool-call hypothesis."""

    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


class ToolCallPredictor:
    """Ye-style Speculator: draft model predicts next tool_call before Actor.

    Injects only semantic-router Top-K schemas (not full registry). Forces a
    single tool_call JSON via ``response_format`` when the backend supports it,
    else system-prompt constraint. Confidence from llama.cpp ``n_probs`` /
    OpenAI ``logprobs`` (``NSA_LLAMA_N_PROBS`` / ``NSA_LLAMA_N_PROBS_DEFAULT``).

    Does **not** execute tools — independent of ``NSA_MCP_EXECUTE``.
    """

    def __init__(
        self,
        draft_client: LlamaHttpClient | Any,
        registry: ToolRegistry,
        semantic_router: SemanticMCPRouter | Any,
        threshold: float = 0.75,
        max_predictions: int = 3,
    ) -> None:
        self.draft_client = draft_client
        self.registry = registry
        self.semantic_router = semantic_router
        self.threshold = float(threshold)
        self.max_predictions = max(1, int(max_predictions))

    async def predict(self, messages: list[dict]) -> list[ToolPrediction]:
        """Return high-confidence draft tool predictions (≤ max_predictions)."""
        try:
            query = _last_user_text(messages)
            schemas = self._top_k_schemas(query)
            if not schemas:
                return []
            prompt = await self._format_tool_prompt(messages, schemas)
            raw = await self._draft_generate(prompt)
            text = _extract_content(raw)
            pred = self._parse_tool_call(text) if text else None
            if pred is None:
                # OpenAI-style tool_calls on the message object
                pred = _parse_message_tool_calls(raw)
            if pred is None:
                return []
            conf = _confidence_from_response(raw)
            if conf > 0.0:
                pred.confidence = conf
            elif pred.confidence <= 0.0:
                # llama.cpp often has NSA_LLAMA_N_PROBS=0 → no logprobs.
                # A successful parse still counts as high-confidence for dispatch.
                pred.confidence = 0.85
            if pred.confidence < self.threshold:
                return []
            return [pred][: self.max_predictions]
        except Exception:  # noqa: BLE001 — never block Actor path
            return []

    async def _format_tool_prompt(
        self, messages: list[dict], schemas: list[dict[str, Any]]
    ) -> list[dict]:
        """Build draft prompt: trimmed history + Top-K schemas only."""
        system = (
            "You are a tool-call Speculator. Output EXACTLY one tool call as JSON: "
            '{"name": "<tool_name>", "arguments": {}}. '
            "No prose, no markdown. Prefer tools from the provided Top-K schemas."
        )
        tools_msg = (
            "Top-K tool schemas (semantic router only — do not invent others):\n"
            + json.dumps(schemas, separators=(",", ":"))
        )
        trimmed = _trim_messages(messages)
        out: list[dict] = [
            {"role": "system", "content": system},
            {"role": "system", "content": tools_msg},
        ]
        for msg in trimmed:
            role = str(msg.get("role") or "user")
            content = msg.get("content")
            if content is None:
                continue
            if role == "system":
                # Already injected Speculator system — keep user/assistant only.
                continue
            out.append({"role": role, "content": str(content)})
        return out

    def _parse_tool_call(self, raw: str) -> ToolPrediction | None:
        """Parse ``<tool>name(args)</tool>`` or OpenAI-style tool_call JSON."""
        text = (raw or "").strip()
        if not text:
            return None
        # Strip common fences.
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        m = _TOOL_TAG_RE.search(text)
        if m:
            name = m.group(1).strip()
            args = _parse_args_blob(m.group(2).strip())
            if name:
                return ToolPrediction(tool_name=name, args=args, confidence=0.0)

        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            # Best-effort: find first JSON object or array in text.
            start_obj = text.find("{")
            start_arr = text.find("[")
            if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
                start, end = start_arr, text.rfind("]")
            else:
                start, end = start_obj, text.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                obj = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None

        return _prediction_from_obj(obj)

    def _top_k_schemas(self, query: str) -> list[dict[str, Any]]:
        router = self.semantic_router
        top_k = int(getattr(router, "top_k", 3) or 3)
        schemas: list[dict[str, Any]] = []
        try:
            if hasattr(router, "route_result"):
                result = router.route_result(query)
                if hasattr(router, "schemas"):
                    schemas = list(router.schemas(result) or [])
                else:
                    for scored in list(getattr(result, "tools", None) or [])[:top_k]:
                        tool = getattr(scored, "tool", scored)
                        schema = getattr(scored, "schema", None)
                        if isinstance(schema, dict) and schema:
                            schemas.append(schema)
                        elif isinstance(tool, dict):
                            schemas.append(dict(tool))
                        else:
                            schemas.append(
                                {
                                    "type": "function",
                                    "function": {
                                        "name": getattr(tool, "name", str(tool)),
                                        "description": getattr(tool, "description", ""),
                                        "parameters": {
                                            "type": "object",
                                            "properties": dict(
                                                getattr(tool, "params", {}) or {}
                                            ),
                                        },
                                    },
                                    "id": getattr(tool, "id", ""),
                                }
                            )
            elif hasattr(router, "route"):
                tools = list(router.route(query) or [])[:top_k]
                for tool in tools:
                    if hasattr(tool, "model_dump"):
                        schemas.append(tool.model_dump())
                    elif isinstance(tool, dict):
                        schemas.append(dict(tool))
                    else:
                        schemas.append({"name": getattr(tool, "name", str(tool))})
        except Exception:  # noqa: BLE001
            return []
        return schemas[:top_k]

    async def _draft_generate(self, messages: list[dict]) -> dict[str, Any]:
        top_n = _n_probs()
        extra: dict[str, Any] = {
            "response_format": {"type": "json_object"},
        }
        client = self.draft_client
        # Prefer generate_with_logits (n_probs / OpenAI logprobs).
        gen = getattr(client, "generate_with_logits", None)
        chat = getattr(client, "chat", None)
        kwargs: dict[str, Any] = {
            "max_tokens": 128,
            "temperature": 0.0,
            "extra": extra,
        }
        if gen is not None:
            if inspect.iscoroutinefunction(gen):
                return await gen(messages, top_logprobs=top_n, **kwargs)
            return await asyncio.to_thread(
                gen, messages, top_logprobs=top_n, **kwargs
            )
        if chat is not None:
            if inspect.iscoroutinefunction(chat):
                return await chat(messages, **kwargs)
            return await asyncio.to_thread(chat, messages, **kwargs)
        raise RuntimeError("draft_client missing generate_with_logits/chat")


def _n_probs() -> int:
    try:
        n = int(os.getenv("NSA_LLAMA_N_PROBS", "0") or "0")
    except ValueError:
        n = 0
    if n <= 0:
        try:
            n = int(os.getenv("NSA_LLAMA_N_PROBS_DEFAULT", str(_DEFAULT_N_PROBS)) or _DEFAULT_N_PROBS)
        except ValueError:
            n = _DEFAULT_N_PROBS
    return max(1, n)


def _last_user_text(messages: list[dict]) -> str:
    for msg in reversed(messages or []):
        if str(msg.get("role") or "") == "user":
            return str(msg.get("content") or "")
    if messages:
        return str(messages[-1].get("content") or "")
    return ""


def _trim_messages(messages: list[dict]) -> list[dict]:
    """Drop heavy history — keep last N non-system turns."""
    if not messages:
        return []
    non_system = [m for m in messages if str(m.get("role") or "") != "system"]
    return non_system[-_MAX_HISTORY_MSGS:]


def _extract_content(raw: Mapping[str, Any] | dict[str, Any] | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    choices = raw.get("choices") if isinstance(raw, Mapping) else None
    if isinstance(choices, list) and choices:
        c0 = choices[0] if isinstance(choices[0], dict) else {}
        msg = c0.get("message") if isinstance(c0, dict) else None
        if isinstance(msg, dict):
            content = msg.get("content")
            if content:
                return str(content)
        text = c0.get("text") if isinstance(c0, dict) else None
        if text:
            return str(text)
    content = raw.get("content") if isinstance(raw, Mapping) else None
    return str(content) if content else ""


def _parse_args_blob(blob: str) -> dict[str, Any]:
    blob = (blob or "").strip()
    if not blob:
        return {}
    try:
        val = json.loads(blob)
        return dict(val) if isinstance(val, dict) else {"value": val}
    except json.JSONDecodeError:
        return {"_raw": blob}


def _prediction_from_obj(obj: Any) -> ToolPrediction | None:
    # Draft models often emit a one-element JSON array: [{"name":...}].
    if isinstance(obj, list):
        if not obj:
            return None
        return _prediction_from_obj(obj[0])
    if not isinstance(obj, dict):
        return None
    # {"tool_calls": [...]}
    tcs = obj.get("tool_calls")
    if isinstance(tcs, list) and tcs:
        return _prediction_from_tool_call_entry(tcs[0])
    # {"name": ..., "arguments": ...} or {"function": {...}}
    if "function" in obj and isinstance(obj["function"], dict):
        return _prediction_from_tool_call_entry(obj)
    name = obj.get("name") or obj.get("tool_name") or obj.get("tool")
    if not name:
        return None
    args = obj.get("arguments") if "arguments" in obj else obj.get("args")
    if isinstance(args, str):
        args = _parse_args_blob(args)
    elif not isinstance(args, dict):
        args = {}
    return ToolPrediction(tool_name=str(name), args=dict(args), confidence=0.0)


def _prediction_from_tool_call_entry(entry: Any) -> ToolPrediction | None:
    if not isinstance(entry, dict):
        return None
    fn = entry.get("function") if isinstance(entry.get("function"), dict) else entry
    if not isinstance(fn, dict):
        return None
    name = fn.get("name") or entry.get("name")
    if not name:
        return None
    args = fn.get("arguments") if "arguments" in fn else fn.get("args")
    if isinstance(args, str):
        args = _parse_args_blob(args)
    elif not isinstance(args, dict):
        args = {}
    return ToolPrediction(tool_name=str(name), args=dict(args), confidence=0.0)


def _parse_message_tool_calls(raw: Mapping[str, Any] | dict[str, Any] | None) -> ToolPrediction | None:
    if not isinstance(raw, Mapping):
        return None
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    c0 = choices[0] if isinstance(choices[0], dict) else {}
    msg = c0.get("message") if isinstance(c0, dict) else None
    if not isinstance(msg, dict):
        return None
    tcs = msg.get("tool_calls")
    if isinstance(tcs, list) and tcs:
        return _prediction_from_tool_call_entry(tcs[0])
    return None


def _confidence_from_response(raw: Mapping[str, Any] | dict[str, Any] | None) -> float:
    """Geometric-mean token probability from OpenAI-style logprobs / n_probs."""
    if not isinstance(raw, Mapping):
        return 0.0
    # Explicit override for fakes / telemetry.
    if "confidence" in raw:
        try:
            return float(raw["confidence"])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return 0.0
    c0 = choices[0] if isinstance(choices[0], dict) else {}
    if not isinstance(c0, dict):
        return 0.0
    logprobs = c0.get("logprobs")
    content: list[Any] = []
    if isinstance(logprobs, dict):
        content = list(logprobs.get("content") or [])
    if not content:
        # llama.cpp completion_probabilities
        probs = c0.get("completion_probabilities") or raw.get("completion_probabilities")
        if isinstance(probs, list) and probs:
            vals = []
            for p in probs:
                if isinstance(p, dict) and "prob" in p:
                    vals.append(float(p["prob"]))
                elif isinstance(p, dict) and "logprob" in p:
                    vals.append(math.exp(float(p["logprob"])))
            if vals:
                return _geom_mean(vals)
        return 0.0
    vals: list[float] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        lp = entry.get("logprob")
        if isinstance(lp, (int, float)):
            vals.append(math.exp(float(lp)))
            continue
        top = entry.get("top_logprobs") or []
        if isinstance(top, list) and top and isinstance(top[0], dict):
            tlp = top[0].get("logprob")
            if isinstance(tlp, (int, float)):
                vals.append(math.exp(float(tlp)))
    if not vals:
        return 0.0
    return _geom_mean(vals)


def _geom_mean(vals: list[float]) -> float:
    clean = [max(1e-12, min(1.0, float(v))) for v in vals if v is not None]
    if not clean:
        return 0.0
    log_sum = sum(math.log(v) for v in clean)
    return float(math.exp(log_sum / len(clean)))
