"""RMF label policy — allowlist, sanitization, cardinality gates."""

from __future__ import annotations

from typing import Mapping

ALLOWED_LABELS: frozenset[str] = frozenset(
    {
        "agent_type",
        "planner",
        "backend",
        "model",
        "model_tier",
        "quantization",
        "worker",
        "thread_pool",
        "numa_node",
        "request_type",
        "streaming",
        "reasoning",
        "status",
        "outcome",
        "dim",
        "pool",
        "tier",
        "stage",
        "exporter",
        "error_class",
        "function",
        "event",
    }
)

FORBIDDEN_LABELS: frozenset[str] = frozenset(
    {
        "workflow_id",
        "request_id",
        "trace_id",
        "span_id",
        "user_id",
        "session_id",
        "prompt",
        "completion",
        "message",
        "ip",
        "email",
    }
)


def sanitize_label_value(value: str, *, max_len: int = 64) -> str:
    text = str(value)
    out = "".join(ch if ch.isalnum() or ch in "_-./" else "_" for ch in text)
    return out[:max_len] if out else "unknown"


class LabelPolicy:
    """Normalize and gate labels for scrape-time series."""

    def __init__(
        self,
        *,
        allowed: frozenset[str] | None = None,
        forbidden: frozenset[str] | None = None,
        max_series_per_metric: int = 2048,
    ) -> None:
        self.allowed = allowed or ALLOWED_LABELS
        self.forbidden = forbidden or FORBIDDEN_LABELS
        self.max_series_per_metric = max(1, int(max_series_per_metric))
        self.dropped_labels = 0
        self.cardinality_rejects = 0
        self._series_keys: dict[str, set[tuple[tuple[str, str], ...]]] = {}

    def normalize(
        self,
        labels: Mapping[str, str] | None,
        *,
        allowed_keys: tuple[str, ...] | None = None,
    ) -> dict[str, str]:
        if not labels:
            return {}
        # Metric-def label_keys override the global allowlist when provided.
        permit = set(allowed_keys) if allowed_keys is not None else set(self.allowed)
        out: dict[str, str] = {}
        for raw_k, raw_v in labels.items():
            key = str(raw_k)
            if key in self.forbidden or key not in permit:
                self.dropped_labels += 1
                continue
            out[key] = sanitize_label_value(str(raw_v))
        return out

    def admit_series(self, metric_name: str, labels: Mapping[str, str]) -> bool:
        key = tuple(sorted(labels.items()))
        bucket = self._series_keys.setdefault(metric_name, set())
        if key in bucket:
            return True
        if len(bucket) >= self.max_series_per_metric:
            self.cardinality_rejects += 1
            return False
        bucket.add(key)
        return True

    def format_labels(self, labels: Mapping[str, str]) -> str:
        if not labels:
            return ""
        parts = [f'{k}="{sanitize_label_value(v)}"' for k, v in sorted(labels.items())]
        return "{" + ",".join(parts) + "}"
