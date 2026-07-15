"""Router exception hierarchy."""

from __future__ import annotations


class RouterError(Exception):
    """Base router error."""


class ToolNotFoundError(RouterError):
    def __init__(self, tool_id: str) -> None:
        super().__init__(f"tool not found: {tool_id}")
        self.tool_id = tool_id


class ToolValidationError(RouterError):
    pass


class EmbeddingError(RouterError):
    pass


class IndexError_(RouterError):
    """Vector index failure (named to avoid shadowing builtins.IndexError)."""


class SnapshotError(RouterError):
    pass


class BackendUnavailableError(RouterError):
    pass


class RegistrySyncError(RouterError):
    pass
