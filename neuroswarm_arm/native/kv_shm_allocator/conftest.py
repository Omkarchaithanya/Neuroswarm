"""Pytest configuration for kv_shm_allocator tests."""

import pytest
import sys
import os

# Add the native directory to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'native', 'kv_shm_allocator'))

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )