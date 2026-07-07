from __future__ import annotations

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "cascade"
    messages: list[Message]
    max_tokens: int = 1024
    temperature: float = 0.2
    agent_role: str = "tool_call"


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
    slo_remaining_ms: float = 4000.0
    self_consistency_score: float = 0.0
    cascade_tier_used: int = 1
    cost_so_far_usd: float = 0.0


class ChatResponse(BaseModel):
    model: str
    tier_used: int
    content: str
    tool_schemas_used: list[str]
    thinking_token_cap: int
    metrics: dict[str, float] = Field(default_factory=dict)

