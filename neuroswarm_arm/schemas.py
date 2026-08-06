from __future__ import annotations

from time import time
from uuid import uuid4

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str
    tool_calls: list[dict] | None = None


class ChatRequest(BaseModel):
    model: str = "cascade"
    messages: list[Message]
    max_tokens: int = 1024
    temperature: float = 0.2
    agent_role: str = "tool_call"
    session_id: str | None = None
    agent_id: str = "default"
    stream: bool = False
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None


class ToolDef(BaseModel):
    id: str
    name: str
    description: str
    params: dict[str, str] = Field(default_factory=dict)
    endpoint: str | None = None
    auth: str | None = None


class PlanState(BaseModel):
    tool_confidence_top1: float = 0.0
    kv_pressure: float = 0.0
    kv_hit_rate: float = 0.0
    kv_storage_tier: int = 1
    kv_migration_latency_ms: float = 0.0
    memory_pressure: float = 0.0
    slo_remaining_ms: float = 4000.0
    self_consistency_score: float = 0.0
    cascade_tier_used: int = 1
    cost_so_far_usd: float = 0.0
    session_id: str = ""


class ChatChoice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: str = "stop"


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid4().hex[:24]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time()))
    model: str
    tier_used: int
    content: str
    choices: list[ChatChoice] = Field(default_factory=list)
    usage: ChatUsage = Field(default_factory=ChatUsage)
    tool_schemas_used: list[str] = Field(default_factory=list)
    thinking_token_cap: int
    metrics: dict[str, float | str] = Field(default_factory=dict)
    # Dual output: ExecutionResult fields above + optional RuntimeCostReport payload
    runtime_cost_report: dict[str, object] | None = None
    # OpenAI-style tool_calls emitted by cascade (empty = no tool call).
    tool_calls: list[dict[str, object]] = Field(default_factory=list)
    # Speculative tool-call engine (arxiv 2512.15834) annotations — defaults keep call sites intact.
    speculative_hit: bool = False
    speculative_latency_saved_ms: float = 0.0
