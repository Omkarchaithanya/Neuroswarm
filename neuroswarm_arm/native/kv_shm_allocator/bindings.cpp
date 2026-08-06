#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

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

namespace py = pybind11;

class SharedMemoryBuffer {
public:
    SharedMemoryBuffer() : fd_(-1), base_(nullptr), size_(0), own_name_(false) {}
    
    ~SharedMemoryBuffer() {
        detach();
    }
    
    SharedMemoryBuffer(const SharedMemoryBuffer&) = delete;
    SharedMemoryBuffer& operator=(const SharedMemoryBuffer&) = delete;
    
    SharedMemoryBuffer(SharedMemoryBuffer&& other) noexcept
        : name_(std::move(other.name_))
        , fd_(other.fd_)
        , base_(other.base_)
        , size_(other.size_)
        , own_name_(other.own_name_) {
        other.fd_ = -1;
        other.base_ = nullptr;
        other.size_ = 0;
        other.own_name_ = false;
    }
    
    SharedMemoryBuffer& operator=(SharedMemoryBuffer&& other) noexcept {
        if (this != &other) {
            detach();
            name_ = std::move(other.name_);
            fd_ = other.fd_;
            base_ = other.base_;
            size_ = other.size_;
            own_name_ = other.own_name_;
            other.fd_ = -1;
            other.base_ = nullptr;
            other.size_ = 0;
            other.own_name_ = false;
        }
        return *this;
    }
    
    bool create(const std::string& name, size_t size) {
        if (fd_ >= 0) {
            return false;
        }
        
        name_ = name;
        size_ = size;
        
#ifdef __linux__
        fd_ = syscall(SYS_memfd_create, "nsa_kv", MFD_ALLOW_SEALING);
        if (fd_ >= 0) {
            own_name_ = false;
        } else {
#endif
            fd_ = shm_open(name_.c_str(), O_CREAT | O_RDWR, 0666);
            if (fd_ >= 0) {
                own_name_ = true;
            }
#ifdef __linux__
        }
#endif
        
        if (fd_ < 0) {
            return false;
        }
        
        if (ftruncate(fd_, size_) != 0) {
            close(fd_);
            if (own_name_) {
                shm_unlink(name_.c_str());
            }
            fd_ = -1;
            return false;
        }
        
        base_ = mmap(nullptr, size_, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
        if (base_ == MAP_FAILED) {
            close(fd_);
            if (own_name_) {
                shm_unlink(name_.c_str());
            }
            fd_ = -1;
            base_ = nullptr;
            return false;
        }
        
#if defined(__linux__) && defined(HAVE_NUMA)
        if (numa_available() >= 0) {
            int numa_node = numa_preferred();
            if (numa_node >= 0) {
                struct bitmask* nodemask = numa_allocate_nodemask();
                numa_bitmask_setbit(nodemask, numa_node);
                mbind(base_, size_, MPOL_PREFERRED, nodemask->maskp, nodemask->size + 1, 0);
                numa_free_nodemask(nodemask);
            }
        }
#endif
        
        return true;
    }
    
    bool open(const std::string& name) {
        if (fd_ >= 0) {
            return false;
        }
        
        name_ = name;
        fd_ = shm_open(name_.c_str(), O_RDWR, 0666);
        if (fd_ < 0) {
            return false;
        }
        
        struct stat st;
        if (fstat(fd_, &st) != 0) {
            close(fd_);
            fd_ = -1;
            return false;
        }
        
        size_ = st.st_size;
        base_ = mmap(nullptr, size_, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
        if (base_ == MAP_FAILED) {
            close(fd_);
            fd_ = -1;
            return false;
        }
        
        own_name_ = false;
        return true;
    }
    
    bool attach(pid_t pid) {
        if (fd_ < 0 || !base_) {
            return false;
        }
        
        char path[256];
        snprintf(path, sizeof(path), "/proc/%d/fd/%d", pid, fd_);
        
        int target_fd = open(path, O_RDWR);
        if (target_fd < 0) {
            return false;
        }
        
        close(target_fd);
        return true;
    }
    
    void detach() {
        if (base_ && base_ != MAP_FAILED) {
            munmap(base_, size_);
            base_ = nullptr;
        }
        if (fd_ >= 0) {
            close(fd_);
            fd_ = -1;
        }
        if (own_name_ && !name_.empty()) {
            shm_unlink(name_.c_str());
            own_name_ = false;
        }
        size_ = 0;
    }
    
    const std::string& name() const { return name_; }
    size_t size() const { return size_; }
    int fd() const { return fd_; }
    void* base_addr() const { return base_; }
    bool is_valid() const { return fd_ >= 0 && base_ != nullptr && base_ != MAP_FAILED; }

private:
    std::string name_;
    int fd_;
    void* base_;
    size_t size_;
    bool own_name_;
};

SharedMemoryBuffer create_kv_shm(const std::string& name, size_t size) {
    SharedMemoryBuffer buf;
    buf.create(name, size);
    return buf;
}

SharedMemoryBuffer open_kv_shm(const std::string& name) {
    SharedMemoryBuffer buf;
    buf.open(name);
    return buf;
}

bool register_with_llama(void* ctx, SharedMemoryBuffer& shm_buffer) {
    if (!ctx || !shm_buffer.is_valid()) {
        return false;
    }
    
    llama_context* llama_ctx = static_cast<llama_context*>(ctx);
    if (!llama_ctx) {
        return false;
    }
    
    return false;
}

PYBIND11_MODULE(kv_shm_allocator, m) {
    m.doc() = "NSA KV Shared Memory Allocator";
    
    py::class_<SharedMemoryBuffer>(m, "SharedMemoryBuffer")
        .def(py::init<>())
        .def("create", &SharedMemoryBuffer::create, py::arg("name"), py::arg("size"))
        .def("open", &SharedMemoryBuffer::open, py::arg("name"))
        .def("attach", &SharedMemoryBuffer::attach, py::arg("pid"))
        .def("detach", &SharedMemoryBuffer::detach)
        .def("name", &SharedMemoryBuffer::name)
        .def("size", &SharedMemoryBuffer::size)
        .def("fd", &SharedMemoryBuffer::fd)
        .def("base_addr", &SharedMemoryBuffer::base_addr)
        .def("is_valid", &SharedMemoryBuffer::is_valid);
    
    m.def("create_kv_shm", &create_kv_shm, py::arg("name"), py::arg("size"));
    m.def("open_kv_shm", &open_kv_shm, py::arg("name"));
    m.def("register_with_llama", &register_with_llama, py::arg("ctx"), py::arg("shm_buffer"));
}