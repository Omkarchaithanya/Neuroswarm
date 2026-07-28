"""Unit tests for ARM MTE KV backend."""

from __future__ import annotations

import asyncio
import ctypes
from unittest.mock import MagicMock

import pytest

from neuroswarm_arm.runtime.maks.backends.mte_backend import MTEBackend
from neuroswarm_arm.runtime.maks.exceptions import KVProviderUnavailableError
from neuroswarm_arm.runtime.maks.native import mte as native_mte


@pytest.fixture
def fake_mte_region():
    buf = ctypes.create_string_buffer(4096)
    ptr = ctypes.addressof(buf)
    yield ptr, 4096, buf


@pytest.fixture
def mte_available(monkeypatch, fake_mte_region):
    ptr, size, _buf = fake_mte_region

    def _mmap(sz: int) -> tuple[int, int]:
        return ptr, size

    monkeypatch.setattr(native_mte, "AVAILABLE", True)
    monkeypatch.setattr(native_mte, "detect_mte_support", lambda: True)
    monkeypatch.setattr(native_mte, "enable_mte_sync", lambda: None)
    monkeypatch.setattr(native_mte, "install_tag_fault_handler", lambda _r: None)
    monkeypatch.setattr(native_mte, "mte_mmap", _mmap)
    monkeypatch.setattr(native_mte, "mte_munmap", lambda _a, _s: None)
    monkeypatch.setattr(native_mte, "mte_promote", lambda _a, _s: None)
    monkeypatch.setattr(native_mte, "stg_tag", lambda _p, t: native_mte.tag_share(_p, t))
    monkeypatch.setattr(MTEBackend, "AVAILABLE", True)
    return ptr, size


@pytest.fixture
def backend_mte(mte_available):
    return MTEBackend()


def test_mte_available_allocate_store_load(backend_mte):
    async def _run():
        loc = await backend_mte.allocate("kv-1", 128)
        assert loc == "future_mte://kv-1"
        await backend_mte.store("kv-1", b"hello-mte")
        data = await backend_mte.load("kv-1")
        assert data == b"hello-mte"
        st = await backend_mte.stats()
        assert st.available is True
        assert st.extra.get("regions") == 1

    asyncio.run(_run())


def test_mte_unavailable_raises(monkeypatch):
    monkeypatch.setattr(native_mte, "AVAILABLE", False)
    monkeypatch.setattr(MTEBackend, "AVAILABLE", False)
    backend = MTEBackend()

    async def _run():
        assert await backend.exists("x") is False
        st = await backend.stats()
        assert st.available is False
        for coro in (
            backend.allocate("k", 64),
            backend.store("k", b"z"),
            backend.load("k"),
            backend.delete("k"),
            backend.share("k", "agent_b"),
            backend.migrate("k", MagicMock()),
        ):
            with pytest.raises(KVProviderUnavailableError):
                await coro

    asyncio.run(_run())


def test_mte_unavailable_hwcap2_unset(monkeypatch):
    monkeypatch.setattr(native_mte, "_hwcap2_has_mte", lambda: False)
    monkeypatch.setattr(native_mte, "detect_mte_support", native_mte.detect_mte_support)
    assert native_mte.detect_mte_support() is False


def test_tag_grant_flow(backend_mte):
    async def _run():
        await backend_mte.allocate("kv-1", 256)
        await backend_mte.store("kv-1", b"shared-payload")
        token1 = await backend_mte.share("kv-1", "agent_b")
        assert token1.startswith("mte:")
        parts = token1.split(":")
        assert len(parts) == 3
        tag = int(parts[1], 16)
        assert 1 <= tag <= 15

        token2 = await backend_mte.share("kv-1", "agent_b")
        assert token2 == token1

        assert backend_mte.resolve_kv_for_consumer("agent_b") == "kv-1"
        assert backend_mte._sharing.mte_tag("kv-1", "agent_b") == tag

    asyncio.run(_run())


def test_grant_mte_revoke_clears_tag(backend_mte):
    async def _run():
        await backend_mte.allocate("kv-1", 64)
        await backend_mte.store("kv-1", b"x")
        await backend_mte.share("kv-1", "agent_b")
        assert backend_mte._sharing.mte_tag("kv-1", "agent_b") is not None
        backend_mte._sharing.revoke_all("kv-1")
        assert backend_mte._sharing.mte_tag("kv-1", "agent_b") is None

    asyncio.run(_run())


def test_feature_matrix_reflects_mte(monkeypatch):
    from neuroswarm_arm.runtime.maks.native import feature_matrix

    monkeypatch.setattr(native_mte, "AVAILABLE", False)
    assert feature_matrix()["mte"] is False
    monkeypatch.setattr(native_mte, "AVAILABLE", True)
    assert feature_matrix()["mte"] is True
