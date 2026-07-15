"""Cognitive Memory Runtime exceptions."""

from __future__ import annotations


class MemoryError(Exception):
    """Base memory runtime error."""


class MemoryValidationError(MemoryError):
    """Schema or input validation failure."""


class MemoryProviderError(MemoryError):
    """Provider backend failure."""


class MemoryNotFoundError(MemoryError):
    """Requested memory id missing."""


class MemoryNamespaceError(MemoryError):
    """Invalid or unauthorized namespace."""


class MemoryCircuitOpenError(MemoryProviderError):
    """Circuit breaker open — provider unavailable."""


class MemoryConfigError(MemoryError):
    """Invalid runtime configuration."""
