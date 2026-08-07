"""NSA llama.cpp backend package: HTTP client, InferenceBackend, and KV shared-memory allocator."""

from .backend import LlamaCppBackend, LlamaHttpClient
from .native_shm import (
    LlamaCppSharedMemoryAllocator,
    BufferInfo,
    create_allocator,
)

__all__ = [
    "LlamaCppBackend",
    "LlamaHttpClient",
    "LlamaCppSharedMemoryAllocator",
    "BufferInfo",
    "create_allocator",
]
