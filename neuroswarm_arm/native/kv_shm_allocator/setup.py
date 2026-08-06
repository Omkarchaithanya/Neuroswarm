from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import pybind11
import sys
import os

class BuildExt(build_ext):
    def build_extensions(self):
        # Add pybind11 include path
        for ext in self.extensions:
            ext.include_dirs.append(pybind11.get_include())
            ext.include_dirs.append(pybind11.get_include(user=True))
            
            # Add llama.cpp include paths
            llama_include = os.environ.get('LLAMA_CPP_INCLUDE', '/usr/local/include')
            if os.path.exists(llama_include):
                ext.include_dirs.append(llama_include)
            
            # Add ggml include path
            ggml_include = os.environ.get('GGML_INCLUDE', '/usr/local/include')
            if os.path.exists(ggml_include):
                ext.include_dirs.append(ggml_include)
                
        super().build_extensions()

ext_modules = [
    Extension(
        'kv_shm_allocator',
        sources=[
            'bindings.cpp',
            'kv_shm_allocator.cpp',
        ],
        include_dirs=[
            pybind11.get_include(),
            pybind11.get_include(user=True),
        ],
        library_dirs=[],
        libraries=['rt'],
        extra_compile_args=[
            '-std=c++17',
            '-O3',
            '-fPIC',
            '-DHAVE_NUMA',
        ],
        extra_link_args=[],
        language='c++',
    ),
]

setup(
    name='kv_shm_allocator',
    version='0.1.0',
    author='NSA Team',
    description='NSA KV Shared Memory Allocator for llama.cpp',
    ext_modules=ext_modules,
    cmdclass={'build_ext': BuildExt},
    zip_safe=False,
    python_requires='>=3.8',
    install_requires=['pybind11>=2.10'],
    setup_requires=['pybind11>=2.10'],
)