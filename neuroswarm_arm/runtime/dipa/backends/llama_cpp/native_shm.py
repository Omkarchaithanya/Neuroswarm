"""NSA KV Shared Memory Allocator Python Wrapper."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class BufferInfo:
    name: str
    fd: int
    size: int
    base_addr: int
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fd": self.fd,
            "size": self.size,
            "base_addr": self.base_addr,
        }


class LlamaCppSharedMemoryAllocator:
    """
    Manages shared memory buffers for llama.cpp KV cache.
    
    Uses POSIX shared memory (shm_open) or memfd_create + mmap
    for zero-copy KV cache sharing between processes.
    """
    
    def __init__(self, session_id: str, size_bytes: int) -> None:
        self.session_id = session_id
        self.size_bytes = size_bytes
        self._shm_name = f"nsa_kv_{session_id}"
        self._buffer: Optional[object] = None  # SharedMemoryBuffer from C++ module
        self._module: Optional[object] = None
        
    def _ensure_module(self) -> None:
        """Lazy-load the C++ extension module."""
        if self._module is None:
            try:
                import kv_shm_allocator
                self._module = kv_shm_allocator
            except ImportError as e:
                raise RuntimeError(
                    "kv_shm_allocator C++ extension not built. "
                    "Run: pip install -e neuroswarm_arm/native/kv_shm_allocator"
                ) from e
    
    def allocate(self) -> str:
        """
        Create a new shared memory buffer for KV cache.
        
        Returns:
            The shared memory name (e.g., "nsa_kv_session123")
        """
        self._ensure_module()
        
        if self._buffer is not None:
            self._buffer.detach()
            
        self._buffer = self._module.SharedMemoryBuffer()
        success = self._buffer.create(self._shm_name, self.size_bytes)
        if not success:
            raise RuntimeError(f"Failed to create shared memory: {self._shm_name}")
            
        return self._shm_name
    
    def open_existing(self) -> str:
        """
        Open an existing shared memory buffer.
        
        Returns:
            The shared memory name
        """
        self._ensure_module()
        
        if self._buffer is not None:
            self._buffer.detach()
            
        self._buffer = self._module.SharedMemoryBuffer()
        success = self._buffer.open(self._shm_name)
        if not success:
            raise RuntimeError(f"Failed to open shared memory: {self._shm_name}")
            
        return self._shm_name
    
    def attach_to_process(self, pid: int) -> bool:
        """
        Pass the file descriptor to a child process.
        
        Uses /proc/{pid}/fd/{fd} to make the fd available to llama-server.
        
        Args:
            pid: Target process ID
            
        Returns:
            True if attachment succeeded
        """
        if self._buffer is None:
            return False
            
        return self._buffer.attach(pid)
    
    def get_buffer_info(self) -> BufferInfo:
        """
        Get buffer metadata.
        
        Returns:
            BufferInfo with name, fd, size, base_addr
        """
        if self._buffer is None:
            raise RuntimeError("No buffer allocated. Call allocate() first.")
            
        return BufferInfo(
            name=self._buffer.name(),
            fd=self._buffer.fd(),
            size=self._buffer.size(),
            base_addr=int(self._buffer.base_addr()) if self._buffer.base_addr() else 0,
        )
    
    def register_with_llama(self, llama_ctx_ptr: int) -> bool:
        """
        Register the shared memory buffer with a llama.cpp context.
        
        Args:
            llama_ctx_ptr: Pointer to llama_context (cast to int)
            
        Returns:
            True if registration succeeded
        """
        self._ensure_module()
        
        if self._buffer is None:
            return False
            
        return self._module.register_with_llama(llama_ctx_ptr, self._buffer)
    
    def close(self) -> None:
        """Release the shared memory buffer."""
        if self._buffer is not None:
            self._buffer.detach()
            self._buffer = None
    
    def __enter__(self) -> LlamaCppSharedMemoryAllocator:
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
    
    def __del__(self) -> None:
        self.close()


def create_allocator(session_id: str, size_bytes: int) -> LlamaCppSharedMemoryAllocator:
    """Factory function to create a shared memory allocator."""
    return LlamaCppSharedMemoryAllocator(session_id, size_bytes)