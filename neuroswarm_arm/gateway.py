from __future__ import annotations

from dataclasses import dataclass

from .schemas import ChatRequest, ChatResponse
from .tools.registry import ToolRegistry
from .tools.semantic_mcp_router import SemanticMCPRouter
from .inference.cascade import CascadeRouter


@dataclass
class AgentGateway:
    registry: ToolRegistry
    semantic_router: SemanticMCPRouter
    cascade: CascadeRouter

    def handle_chat(self, req: ChatRequest) -> ChatResponse:
        selected_tools = self.semantic_router.route(req.messages[-1].content if req.messages else "")
        tool_names = [t.name for t in selected_tools]
        return self.cascade.handle(req, tool_names)

