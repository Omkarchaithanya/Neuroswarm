cmake_minimum_required(VERSION 3.20)
project(nsa_kv_shm_allocator LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Find pybind11
find_package(pybind11 REQUIRED)

# Find llama.cpp headers
set(LLAMA_CPP_INCLUDE_DIR "" CACHE PATH "Path to llama.cpp include directory")
set(GGML_INCLUDE_DIR "" CACHE PATH "Path to ggml include directory")

if(LLAMA_CPP_INCLUDE_DIR)
    include_directories(${LLAMA_CPP_INCLUDE_DIR})
endif()

if(GGML_INCLUDE_DIR)
    include_directories(${GGML_INCLUDE_DIR})
else()
    # Default search paths
    find_path(GGML_INCLUDE_DIR ggml.h
        PATHS /usr/local/include /usr/include /opt/homebrew/include
        PATH_SUFFIXES ggml
    )
    if(GGML_INCLUDE_DIR)
        include_directories(${GGML_INCLUDE_DIR})
    endif()
endif()

# Check for numa.h
find_path(NUMA_INCLUDE_DIR numa.h
    PATHS /usr/include /usr/local/include
)
if(NUMA_INCLUDE_DIR)
    include_directories(${NUMA_INCLUDE_DIR})
    add_compile_definitions(HAVE_NUMA=1)
    find_library(NUMA_LIB numa
        PATHS /usr/lib /usr/local/lib
    )
endif()

# Find rt library for shm_open
find_library(RT_LIB rt)

# Source files
set(SOURCES
    kv_shm_allocator.cpp
    bindings.cpp
)

# Create the pybind11 module
pybind11_add_module(kv_shm_allocator ${SOURCES})

# Link libraries
target_link_libraries(kv_shm_allocator PRIVATE
    ${RT_LIB}
    ${NUMA_LIB}
    pybind11::module
)

# Compile options
target_compile_options(kv_shm_allocator PRIVATE
    -Wall -Wextra -Wpedantic
    -O3
    -fPIC
)

# Install target
install(TARGETS kv_shm_allocator
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)