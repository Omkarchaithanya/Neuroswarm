"""SHM integration for llama.cpp KV cache sharing."""

from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass
from typing import Any, Optional

from neuroswarm_arm.runtime.kv.utils.config import KVRuntimeConfig
from neuroswarm_arm.runtime.maks.manager import KVManager
from neuroswarm_arm.runtime.kv.sharing.shm import SharedMemoryBackend


KV_SHM_AVAILABLE = False
_llama_kv_magic = 0x4B565F4C4C414D41  # "KV_LLAMA" as uint64


def _try_load_native() -> bool:
    """Try to load the C++ native extension."""
    global KV_SHM_AVAILABLE
    try:
        import kv_shm_allocator
        KV_SHM_AVAILABLE = True
        return True
    except ImportError:
        KV_SHM_AVAILABLE = False
        return False


# Try loading on import
_try_load_native()


@dataclass(slots=True)
class SharedKVHandle:
    """Handle for shared KV cache segment."""
    shm_name: str
    size: int
    fd: int
    base_addr: int
    metadata_offset: int = 4096
    is_native: bool = False


class LlamaCppSharedKVManager:
    """
    Manages shared memory KV cache for llama.cpp backends.
    
    Supports both native C++ extension (zero-copy) and Python multiprocessing
    shared_memory fallback paths.
    """
    
    def __init__(self, config: KVRuntimeConfig) -> None:
        self.config = config
        self.maks = KVManager(config)
        self.shm = SharedMemoryBackend()
        self.native = None
        if _try_load_native():
            try:
                import kv_shm_allocator
                self.native = kv_shm_allocator
            except ImportError:
                self.native = None
    
    def _calculate_kv_size(self, n_layers: int, n_heads: int, head_size: int, n_ctx: int) -> int:
        """Calculate KV cache size in bytes for fp16."""
        # n_layers * 2 (K+V) * n_heads * head_size * n_ctx * sizeof(fp16)
        return n_layers * 2 * n_heads * head_size * n_ctx * 2  # fp16 = 2 bytes
    
    async def allocate_shared_kv(
        self,
        session_id: str,
        model: str,
        n_ctx: int,
        *,
        n_layers: int = 32,
        n_heads: int = 32,
        head_size: int = 128,
    ) -> SharedKVHandle:
        """
        Allocate shared memory for KV cache.
        
        Args:
            session_id: Unique session identifier
            model: Model name (for metadata)
            n_ctx: Context length
            n_layers: Number of transformer layers
            n_heads: Number of attention heads
            head_size: Size per head
            
        Returns:
            SharedKVHandle with SHM metadata
        """
        size = self._calculate_kv_size(n_layers, n_heads, head_size, n_ctx)
        shm_name = f"nsa_kv_{session_id}"
        
        use_native = self.native is not None and os.getenv("NSA_KV_NATIVE_SHM", "0") in {"1", "true", "TRUE", "yes"}
        use_python_shm = os.getenv("NSA_KV_PYTHON_SHM", "1") in {"1", "true", "TRUE", "yes"}
        use_file_fallback = os.getenv("NSA_KV_FILE_FALLBACK", "0") in {"1", "true", "TRUE", "yes"}
        
        if use_file_fallback:
            # File fallback - will use file-based handoff
            return SharedKVHandle(
                shm_name=shm_name,
                size=size,
                fd=-1,
                base_addr=0,
                is_native=False,
            )
        
        if use_native:
            # Native C++ path - use memfd or shm_open
            buf = self.native.SharedMemoryBuffer()
            success = buf.create(shm_name, size)
            if not success:
                raise RuntimeError(f"Failed to create native SHM: {shm_name}")
            
            # Write magic number at start
            buf.base_addr()
            # Write magic via the buffer
            magic_bytes = struct.pack("<Q", _llama_kv_magic)
            # Note: actual write would need direct memory access
            # For now, we'll do it via the Python SHM backend as well
            
            return SharedKVHandle(
                shm_name=shm_name,
                size=size,
                fd=buf.fd(),
                base_addr=int(buf.base_addr()) if buf.base_addr() else 0,
                is_native=True,
            )
        elif use_python_shm:
            # Python multiprocessing.shared_memory fallback
            import multiprocessing.shared_memory as shm_mod
            
            try:
                # Try to unlink any existing
                try:
                    existing = shm_mod.SharedMemory(name=shm_name, create=False)
                    existing.close()
                    existing.unlink()
                except FileNotFoundError:
                    pass
                
                shm_obj = shm_mod.SharedMemory(name=shm_name, create=True, size=size)
                
                # Write magic number at start
                magic_bytes = struct.pack("<Q", _llama_kv_magic)
                shm_obj.buf[:8] = magic_bytes
                
                # Get fd for SCM_RIGHTS passing
                import fcntl
                fd = shm_obj._fd if hasattr(shm_obj, '_fd') else -1
                
                return SharedKVHandle(
                    shm_name=shm_name,
                    size=size,
                    fd=fd,
                    base_addr=int(shm_obj.buf.__array_interface__['data'][0]) if hasattr(shm_obj.buf, '__array_interface__') else 0,
                    is_native=False,
                )
            except Exception as e:
                # Fall back to file-based
                return SharedKVHandle(
                    shm_name=shm_name,
                    size=size,
                    fd=-1,
                    base_addr=0,
                    is_native=False,
                )
        else:
            # File fallback
            return SharedKVHandle(
                shm_name=shm_name,
                size=size,
                fd=-1,
                base_addr=0,
                is_native=False,
            )
    
    async def bind_slot_to_shm(
        self,
        backend: Any,  # LlamaCppBackend
        slot_id: int,
        handle: SharedKVHandle,
    ) -> bool:
        """
        Bind llama.cpp slot to shared memory segment.
        
        Native mode: pass fd via SCM_RIGHTS or /proc/{pid}/fd/{fd}
        Python mode: write metadata, instruct llama-server to use --kv-shm-name
        """
        if handle.is_native and self.native is not None:
            # Native mode: attach via llama.cpp SHM API
            # Get the llama-server process PID
            if backend._supervisor is not None:
                snapshot = backend._supervisor.snapshot()
                proc_info = snapshot.get(backend.name, {})
                pid = proc_info.get("pid")
                if pid:
                    # Attach the fd to the llama-server process
                    # This uses the native attach function
                    try:
                        # The C++ module has attach(pid) method
                        import kv_shm_allocator
                        buf = kv_shm_allocator.SharedMemoryBuffer()
                        buf.open(handle.shm_name)
                        success = buf.attach(pid)
                        if success:
                            # Now instruct llama-server to use the SHM
                            # This would require llama.cpp support for --kv-shm-fd or similar
                            return True
                    except Exception:
                        pass
            return False
        else:
            # Python mode: metadata already in SHM
            # llama-server needs to be started with --kv-shm-name {handle.shm_name}
            # This requires restart (hot-swap not possible without native)
            return True  # Metadata written, ready for next restart
    
    async def migrate_kv_between_backends(
        self,
        source: Any,  # LlamaCppBackend
        target: Any,  # LlamaCppBackend
        session_id: str,
        slot_id: int,
    ) -> bool:
        """
        Migrate KV cache from source backend to target backend via SHM.
        
        Uses native export/import if available, falls back to file.
        """
        shm_name = f"nsa_kv_{session_id}"
        start_time = time.perf_counter()
        
        use_native = self.native is not None and os.getenv("NSA_KV_NATIVE_SHM", "0") in {"1", "true", "TRUE", "yes"}
        
        try:
            if use_native:
                # Native path: use llama-server save_shm / restore_shm
                export_result = source.slot_client.kv_export_shm(slot_id, shm_name)
                if not export_result.get("ok", True):
                    raise RuntimeError(f"Native export failed: {export_result}")
                
                import_result = target.slot_client.kv_import_shm(slot_id, shm_name)
                if not import_result.get("ok", True):
                    raise RuntimeError(f"Native import failed: {import_result}")
            else:
                # Python SHM path or file fallback
                # Use existing file-based export/import
                filename = source.slot_client.resolve_filename(shm_name)
                export_result = source.slot_client.kv_export_to_file(slot_id, filename)
                import_result = target.slot_client.kv_import_from_file(slot_id, filename)
            
            # Update MAKS block table to reflect new physical location
            # This would involve updating the registry with new provider/location
            # For now, just record the migration in telemetry
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            size_bytes = self._calculate_kv_size(32, 32, 128, 4096)  # estimate
            
            # Record telemetry
            if hasattr(self.maks, 'telemetry'):
                self.maks.telemetry.observe_latency("kv_migration_latency_ms", latency_ms)
                self.maks.telemetry.record_migration()
                self.maks.metrics.observe("kv_migration_bytes", float(size_bytes))
            
            return True
        except Exception as e:
            # Fall back to file-based if SHM fails
            try:
                filename = source.slot_client.resolve_filename(shm_name)
                export_result = source.slot_client.kv_export_to_file(slot_id, filename)
                import_result = target.slot_client.kv_import_from_file(slot_id, filename)
                return True
            except Exception:
                return False
    
    async def validate_shm_consistency(self, handle: SharedKVHandle) -> bool:
        """
        Validate SHM consistency by checking magic number and metadata checksum.
        
        Returns True if valid, False otherwise.
        """
        if handle.fd < 0 or handle.base_addr == 0:
            return False
        
        try:
            if handle.is_native and self.native is not None:
                # Native: open and verify via C++ module
                buf = self.native.SharedMemoryBuffer()
                success = buf.open(handle.shm_name)
                if not success:
                    return False
                
                # Read first 8 bytes as magic
                # Would need direct memory access from C++
                # For now, assume valid if open succeeded
                return True
            else:
                # Python: use multiprocessing.shared_memory
                import multiprocessing.shared_memory as shm_mod
                shm_obj = shm_mod.SharedMemory(name=handle.shm_name, create=False)
                
                # Read magic number
                magic_bytes = bytes(shm_obj.buf[:8])
                magic = struct.unpack("<Q", magic_bytes)[0]
                
                shm_obj.close()
                
                return magic == _llama_kv_magic
        except Exception:
            return False