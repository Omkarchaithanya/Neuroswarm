# NSA KV Shared Memory Allocator

Custom `ggml_backend_buffer_type_t` implementation backed by POSIX shared memory (`shm_open`) or `memfd_create` + `mmap`.

## Features

- **Zero-copy KV cache sharing** between processes using shared memory
- **POSIX `shm_open`** for named shared memory segments
- **Linux `memfd_create`** with `MFD_ALLOW_SEALING` for anonymous shared memory
- **NUMA-aware allocation** using `mbind()` with `MPOL_PREFERRED`
- **Python bindings** via `pybind11` for easy integration
- **llama.cpp integration** via custom backend buffer type

## Building

### Using CMake (recommended)

```bash
mkdir build && cd build
cmake -DLLAMA_CPP_INCLUDE_DIR=/path/to/llama.cpp/include ..
make -j$(nproc)
```

### Using pip

```bash
pip install -e .
```

## Environment Variables

- `NSA_KV_SHM_ENABLED=1` - Enable shared memory KV cache backend
- `NSA_SESSION_ID` - Session identifier for shared memory naming

## C++ API

```cpp
// Get the buffer type for use with ggml
ggml_backend_buffer_type_t buft = nsa_shm_buffer_type();

// Create buffer
ggml_backend_buffer_t buffer = ggml_backend_buffer_type_alloc_buffer(buft, size);

// Use with llama.cpp
llama_model_params params = llama_model_default_params();
// ... configure params to use the buffer type
```

## Python API

```python
from kv_shm_allocator import SharedMemoryBuffer, create_kv_shm

# Create shared memory buffer
buf = create_kv_shm("nsa_kv_session123", 1024 * 1024 * 1024)  # 1GB

# Access buffer info
print(buf.name())      # "nsa_kv_session123"
print(buf.size())      # 1073741824
print(buf.fd())        # file descriptor
print(buf.base_addr()) # memory address

# Attach to another process
buf.attach(pid)

# Clean up
buf.detach()
```

## Integration with llama-server

When `NSA_KV_SHM_ENABLED=1`, the process supervisor automatically adds:
```
--kv-backend shm --kv-shm-name nsa_kv_{session_id}
```

The file descriptor is passed to the child process for zero-copy access.