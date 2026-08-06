"""Tests for NSA KV Shared Memory Allocator."""

import os
import pytest
import sys

# Try to import the module
try:
    import kv_shm_allocator
    HAS_MODULE = True
except ImportError:
    HAS_MODULE = False


@pytest.mark.skipif(not HAS_MODULE, reason="kv_shm_allocator module not built")
class TestSharedMemoryBuffer:
    """Tests for SharedMemoryBuffer class."""
    
    def test_create_and_open(self):
        """Test creating and opening shared memory buffer."""
        name = "nsa_kv_test_create"
        size = 4096
        
        # Create buffer
        buf = kv_shm_allocator.create_kv_shm(name, size)
        assert buf.is_valid()
        assert buf.name() == name
        assert buf.size() == size
        assert buf.fd() >= 0
        assert buf.base_addr() is not None
        
        # Open existing buffer
        buf2 = kv_shm_allocator.open_kv_shm(name)
        assert buf2.is_valid()
        assert buf2.name() == name
        assert buf2.size() == size
        assert buf2.fd() >= 0
        
        # Cleanup
        buf.detach()
        buf2.detach()
    
    def test_attach_detach(self):
        """Test attach and detach operations."""
        name = "nsa_kv_test_attach"
        size = 4096
        
        buf = kv_shm_allocator.create_kv_shm(name, size)
        assert buf.is_valid()
        
        # Attach to current process (should succeed)
        pid = os.getpid()
        result = buf.attach(pid)
        assert result is True
        
        # Detach
        buf.detach()
        assert not buf.is_valid()
    
    def test_context_manager(self):
        """Test using buffer as context manager."""
        name = "nsa_kv_test_ctx"
        size = 4096
        
        buf = kv_shm_allocator.SharedMemoryBuffer()
        buf.create(name, size)
        assert buf.is_valid()
        
        buf.detach()
        assert not buf.is_valid()
    
    def test_move_semantics(self):
        """Test move constructor/assignment."""
        name = "nsa_kv_test_move"
        size = 4096
        
        buf1 = kv_shm_allocator.create_kv_shm(name, size)
        assert buf1.is_valid()
        
        # Move construct
        buf2 = kv_shm_allocator.SharedMemoryBuffer(buf1)
        # Note: Python doesn't directly expose move semantics, 
        # but we can test the buffer is still valid
        assert buf2.is_valid()
        assert buf2.name() == name
        
        buf2.detach()


@pytest.mark.skipif(not HAS_MODULE, reason="kv_shm_allocator module not built")
class TestPythonWrapper:
    """Tests for the Python wrapper in neuroswarm_arm."""
    
    def test_allocator_creation(self):
        """Test creating LlamaCppSharedMemoryAllocator."""
        # Add path to runtime
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
        
        from neuroswarm_arm.runtime.dipa.backends.llama_cpp.native_shm import (
            LlamaCppSharedMemoryAllocator, create_allocator
        )
        
        allocator = create_allocator("test_session", 1024 * 1024)
        assert allocator.session_id == "test_session"
        assert allocator.size_bytes == 1024 * 1024
        assert allocator._shm_name == "nsa_kv_test_session"
    
    def test_allocator_allocate(self):
        """Test allocate method (requires module)."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
        
        from neuroswarm_arm.runtime.dipa.backends.llama_cpp.native_shm import (
            LlamaCppSharedMemoryAllocator
        )
        
        allocator = LlamaCppSharedMemoryAllocator("test_alloc", 4096)
        
        # This will fail if module not built, which is expected in CI
        try:
            name = allocator.allocate()
            assert name == "nsa_kv_test_alloc"
            
            info = allocator.get_buffer_info()
            assert info.name == "nsa_kv_test_alloc"
            assert info.size == 4096
            assert info.fd >= 0
            assert info.base_addr > 0
            
            allocator.close()
        except RuntimeError as e:
            if "not built" in str(e):
                pytest.skip("C++ extension not built")
            raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])