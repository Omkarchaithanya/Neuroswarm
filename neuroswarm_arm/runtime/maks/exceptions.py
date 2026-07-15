"""MAKS typed exceptions."""

from __future__ import annotations


class MAKSError(Exception):
    """Base MAKS error."""


class KVNotFoundError(MAKSError):
    """KV handle or payload missing."""


class KVStateError(MAKSError):
    """Illegal lifecycle transition."""


class KVProviderError(MAKSError):
    """Backend provider failure."""


class KVProviderUnavailableError(MAKSError):
    """Provider not available on this host (e.g. MTE/CXL on Axion)."""


class KVDedupCollisionError(MAKSError):
    """Hash collision detected between distinct payloads."""


class KVPinnedError(MAKSError):
    """Pinned KV cannot be evicted or destroyed."""


class KVPermissionError(MAKSError):
    """Share/access permission denied."""


class KVIdentityMismatchError(MAKSError):
    """Model/quant/RoPE/tokenizer identity mismatch — cannot share."""


class KVRegistryError(MAKSError):
    """Registry persistence failure."""


class KVBudgetExceededError(MAKSError):
    """ARMORA / config budget exceeded."""
