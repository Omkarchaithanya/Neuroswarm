#include <ggml.h>
#include <ggml-backend.h>
#include <llama.h>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>

#ifdef __linux__
#include <sys/syscall.h>
#include <linux/memfd.h>
#ifndef MFD_ALLOW_SEALING
#define MFD_ALLOW_SEALING 0x0002
#endif
#endif

#if defined(__linux__) && defined(HAVE_NUMA)
#include <numa.h>
#include <numaif.h>
#endif

struct nsa_shm_buffer {
    ggml_backend_buffer buffer;
    void* base;
    size_t size;
    int fd;
    char* name;
    bool use_memfd;
    bool own_name;
};

static const char* nsa_shm_buffer_get_name(ggml_backend_buffer_t buffer) {
    return "nsa_shm";
}

static void nsa_shm_buffer_free(ggml_backend_buffer_t buffer) {
    struct nsa_shm_buffer* buf = (struct nsa_shm_buffer*)buffer;
    if (buf->base && buf->base != MAP_FAILED) {
        munmap(buf->base, buf->size);
    }
    if (buf->fd >= 0) {
        close(buf->fd);
    }
    if (buf->own_name && buf->name) {
        shm_unlink(buf->name);
        free(buf->name);
    }
    free(buf);
}

static void* nsa_shm_buffer_get_base(ggml_backend_buffer_t buffer) {
    struct nsa_shm_buffer* buf = (struct nsa_shm_buffer*)buffer;
    return buf->base;
}

static size_t nsa_shm_buffer_get_alloc_size(ggml_backend_buffer_t buffer) {
    struct nsa_shm_buffer* buf = (struct nsa_shm_buffer*)buffer;
    return buf->size;
}

static void nsa_shm_buffer_init_tensor(ggml_backend_buffer_t buffer, struct ggml_tensor* tensor) {
    (void)buffer;
    (void)tensor;
}

static void nsa_shm_buffer_set_tensor(ggml_backend_buffer_t buffer, struct ggml_tensor* tensor, const void* data, size_t offset, size_t size) {
    struct nsa_shm_buffer* buf = (struct nsa_shm_buffer*)buffer;
    if (buf->base && offset + size <= buf->size) {
        memcpy((char*)buf->base + offset, data, size);
    }
}

static void nsa_shm_buffer_get_tensor(ggml_backend_buffer_t buffer, const struct ggml_tensor* tensor, void* data, size_t offset, size_t size) {
    struct nsa_shm_buffer* buf = (struct nsa_shm_buffer*)buffer;
    if (buf->base && offset + size <= buf->size) {
        memcpy(data, (char*)buf->base + offset, size);
    }
}

static bool nsa_shm_buffer_cpy_tensor(ggml_backend_buffer_t dst, ggml_backend_buffer_t src, const struct ggml_tensor* tensor) {
    (void)dst;
    (void)src;
    (void)tensor;
    return false;
}

static ggml_backend_buffer_t nsa_shm_alloc_buffer(ggml_backend_buffer_type_t buft, size_t size) {
    (void)buft;
    
    struct nsa_shm_buffer* buf = (struct nsa_shm_buffer*)calloc(1, sizeof(struct nsa_shm_buffer));
    if (!buf) {
        return NULL;
    }
    
    buf->size = size;
    buf->fd = -1;
    buf->name = NULL;
    buf->use_memfd = false;
    buf->own_name = false;
    
    char shm_name[256];
    const char* session_id = getenv("NSA_SESSION_ID");
    if (session_id) {
        snprintf(shm_name, sizeof(shm_name), "nsa_kv_%s", session_id);
    } else {
        snprintf(shm_name, sizeof(shm_name), "nsa_kv_%d", getpid());
    }
    
#ifdef __linux__
    int fd = syscall(SYS_memfd_create, "nsa_kv", MFD_ALLOW_SEALING);
    if (fd >= 0) {
        buf->fd = fd;
        buf->use_memfd = true;
        buf->own_name = false;
    } else {
#endif
        buf->fd = shm_open(shm_name, O_CREAT | O_RDWR, 0666);
        if (buf->fd >= 0) {
            buf->name = strdup(shm_name);
            buf->own_name = true;
            buf->use_memfd = false;
        }
#ifdef __linux__
    }
#endif
    
    if (buf->fd < 0) {
        free(buf);
        return NULL;
    }
    
    if (ftruncate(buf->fd, size) != 0) {
        close(buf->fd);
        if (buf->own_name && buf->name) {
            shm_unlink(buf->name);
            free(buf->name);
        }
        free(buf);
        return NULL;
    }
    
    void* base = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, buf->fd, 0);
    if (base == MAP_FAILED) {
        close(buf->fd);
        if (buf->own_name && buf->name) {
            shm_unlink(buf->name);
            free(buf->name);
        }
        free(buf);
        return NULL;
    }
    
    buf->base = base;
    
#if defined(__linux__) && defined(HAVE_NUMA)
    if (numa_available() >= 0) {
        int numa_node = numa_preferred();
        if (numa_node >= 0) {
            struct bitmask* nodemask = numa_allocate_nodemask();
            numa_bitmask_setbit(nodemask, numa_node);
            mbind(base, size, MPOL_PREFERRED, nodemask->maskp, nodemask->size + 1, 0);
            numa_free_nodemask(nodemask);
        }
    }
#endif
    
    static const ggml_backend_buffer_i vtable = {
        .get_name = nsa_shm_buffer_get_name,
        .free_buffer = nsa_shm_buffer_free,
        .get_base = nsa_shm_buffer_get_base,
        .get_alloc_size = nsa_shm_buffer_get_alloc_size,
        .init_tensor = nsa_shm_buffer_init_tensor,
        .set_tensor = nsa_shm_buffer_set_tensor,
        .get_tensor = nsa_shm_buffer_get_tensor,
        .cpy_tensor = nsa_shm_buffer_cpy_tensor,
    };
    
    buf->buffer.iface = &vtable;
    buf->buffer.buft = buft;
    buf->buffer.context = buf;
    buf->buffer.size = size;
    buf->buffer.usage = GGML_BACKEND_BUFFER_USAGE_ANY;
    
    return &buf->buffer;
}

ggml_backend_buffer_type_t nsa_shm_buffer_type() {
    static ggml_backend_buffer_type_t buft = NULL;
    if (!buft) {
        buft = ggml_backend_buffer_type_new(&nsa_shm_alloc_buffer, NULL, NULL, "nsa_shm");
    }
    return buft;
}

extern "C" {

int nsa_shm_create(const char* name, size_t size, int* out_fd, void** out_base) {
    if (!name || !out_fd || !out_base) {
        return -1;
    }
    
    int fd = shm_open(name, O_CREAT | O_RDWR, 0666);
    if (fd < 0) {
        return -errno;
    }
    
    if (ftruncate(fd, size) != 0) {
        int err = errno;
        close(fd);
        shm_unlink(name);
        return -err;
    }
    
    void* base = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (base == MAP_FAILED) {
        int err = errno;
        close(fd);
        shm_unlink(name);
        return -err;
    }
    
#if defined(__linux__) && defined(HAVE_NUMA)
    if (numa_available() >= 0) {
        int numa_node = numa_preferred();
        if (numa_node >= 0) {
            struct bitmask* nodemask = numa_allocate_nodemask();
            numa_bitmask_setbit(nodemask, numa_node);
            mbind(base, size, MPOL_PREFERRED, nodemask->maskp, nodemask->size + 1, 0);
            numa_free_nodemask(nodemask);
        }
    }
#endif
    
    *out_fd = fd;
    *out_base = base;
    return 0;
}

int nsa_shm_open(const char* name, size_t* out_size, int* out_fd, void** out_base) {
    if (!name || !out_size || !out_fd || !out_base) {
        return -1;
    }
    
    int fd = shm_open(name, O_RDWR, 0666);
    if (fd < 0) {
        return -errno;
    }
    
    struct stat st;
    if (fstat(fd, &st) != 0) {
        int err = errno;
        close(fd);
        return -err;
    }
    
    size_t size = st.st_size;
    void* base = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (base == MAP_FAILED) {
        int err = errno;
        close(fd);
        return -err;
    }
    
    *out_size = size;
    *out_fd = fd;
    *out_base = base;
    return 0;
}

int nsa_shm_close(int fd, void* base, size_t size, bool unlink, const char* name) {
    if (base && base != MAP_FAILED) {
        munmap(base, size);
    }
    if (fd >= 0) {
        close(fd);
    }
    if (unlink && name) {
        shm_unlink(name);
    }
    return 0;
}

int nsa_shm_attach_fd(int pid, int fd) {
    char path[256];
    snprintf(path, sizeof(path), "/proc/%d/fd/%d", pid, fd);
    return 0;
}

} // extern "C"