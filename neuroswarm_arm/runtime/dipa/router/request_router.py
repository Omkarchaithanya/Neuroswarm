"""Normalize chat-like payloads into :class:`InferenceRequest`."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces.types import CorrelationIds, InferenceRequest


class RequestRouter:
    """Admit external chat / OpenAI-shaped objects into DIPA's request envelope."""

    def normalize(self, obj: InferenceRequest | Mapping[str, Any] | Any) -> InferenceRequest:
        if isinstance(obj, InferenceRequest):
            return obj

        if isinstance(obj, Mapping):
            return self._from_mapping(obj)

        return self._from_object(obj)

    def _from_mapping(self, data: Mapping[str, Any]) -> InferenceRequest:
        messages = self._coerce_messages(data.get("messages"))
        ids = self._coerce_ids(data)
        baggage = dict(data.get("baggage") or {})
        return InferenceRequest(
            messages=messages,
            model=str(data.get("model", "cascade")),
            max_tokens=int(data.get("max_tokens", 1024)),
            temperature=float(data.get("temperature", 0.2)),
            agent_role=str(data.get("agent_role", data.get("role", "tool_call"))),
            session_id=str(data.get("session_id", "")),
            agent_id=str(data.get("agent_id", "default")),
            stream=bool(data.get("stream", False)),
            tool_names=list(data.get("tool_names") or data.get("tools") or []),
            tool_schemas=list(data.get("tool_schemas") or []),
            tool_confidence=float(data.get("tool_confidence") or 0.0),
            tool_high_confidence=bool(data.get("tool_high_confidence") or False),
            tool_prompt_block=str(data.get("tool_prompt_block") or ""),
            thinking_token_cap=_opt_int(data.get("thinking_token_cap")),
            system_prompt=_opt_str(data.get("system_prompt") or data.get("system")),
            latency_sla_ms=float(data.get("latency_sla_ms", 4000.0)),
            cost_budget_usd=float(data.get("cost_budget_usd", 0.01)),
            baggage=baggage,
            ids=ids,
        )

    def _from_object(self, obj: Any) -> InferenceRequest:
        get = lambda name, default=None: getattr(obj, name, default)  # noqa: E731
        messages = self._coerce_messages(get("messages"))
        # Single-prompt chat objects.
        if not messages:
            prompt = get("prompt") or get("content") or get("text") or ""
            if prompt:
                messages = [{"role": "user", "content": str(prompt)}]

        ids_raw = get("ids")
        if isinstance(ids_raw, CorrelationIds):
            ids = ids_raw
        else:
            ids = CorrelationIds(
                request_id=str(get("request_id", "") or ""),
                agent_id=str(get("agent_id", "default") or "default"),
                session_id=str(get("session_id", "") or ""),
                trace_id=str(get("trace_id", "") or ""),
                execution_id=str(get("execution_id", "") or ""),
                correlation_id=str(get("correlation_id", "") or ""),
            )

        return InferenceRequest(
            messages=messages,
            model=str(get("model", "cascade") or "cascade"),
            max_tokens=int(get("max_tokens", 1024) or 1024),
            temperature=float(get("temperature", 0.2) if get("temperature") is not None else 0.2),
            agent_role=str(get("agent_role", get("role", "tool_call")) or "tool_call"),
            session_id=str(get("session_id", "") or ""),
            agent_id=str(get("agent_id", "default") or "default"),
            stream=bool(get("stream", False)),
            tool_names=list(get("tool_names") or get("tools") or []),
            tool_schemas=list(get("tool_schemas") or []),
            tool_confidence=float(get("tool_confidence") or 0.0),
            tool_high_confidence=bool(get("tool_high_confidence") or False),
            tool_prompt_block=str(get("tool_prompt_block") or ""),
            thinking_token_cap=_opt_int(get("thinking_token_cap")),
            system_prompt=_opt_str(get("system_prompt") or get("system")),
            latency_sla_ms=float(get("latency_sla_ms", 4000.0) or 4000.0),
            cost_budget_usd=float(get("cost_budget_usd", 0.01) or 0.01),
            baggage=dict(get("baggage") or {}),
            ids=ids,
        )

    @staticmethod
    def _coerce_messages(raw: Any) -> list[dict[str, str]]:
        if not raw:
            return []
        out: list[dict[str, str]] = []
        for item in raw:
            if isinstance(item, Mapping):
                out.append(
                    {
                        "role": str(item.get("role", "user")),
                        "content": str(item.get("content", "")),
                    }
                )
            else:
                role = str(getattr(item, "role", "user"))
                content = str(getattr(item, "content", getattr(item, "text", "")))
                out.append({"role": role, "content": content})
        return out

    @staticmethod
    def _coerce_ids(data: Mapping[str, Any]) -> CorrelationIds:
        nested = data.get("ids")
        if isinstance(nested, CorrelationIds):
            return nested
        if isinstance(nested, Mapping):
            return CorrelationIds(
                request_id=str(nested.get("request_id", "")),
                agent_id=str(nested.get("agent_id", "")),
                session_id=str(nested.get("session_id", "")),
                trace_id=str(nested.get("trace_id", "")),
                execution_id=str(nested.get("execution_id", "")),
                correlation_id=str(nested.get("correlation_id", "")),
            )
        return CorrelationIds(
            request_id=str(data.get("request_id", "")),
            agent_id=str(data.get("agent_id", data.get("agent", ""))),
            session_id=str(data.get("session_id", "")),
            trace_id=str(data.get("trace_id", "")),
            execution_id=str(data.get("execution_id", "")),
            correlation_id=str(data.get("correlation_id", "")),
        )


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
