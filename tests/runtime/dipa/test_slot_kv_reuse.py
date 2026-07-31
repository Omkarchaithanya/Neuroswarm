"""Tests for cross-tier slot KV save/restore (G8)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    VerifyMode,
    VerifyRequest,
)
from neuroswarm_arm.runtime.armcascade.verification.strategies import BlockVerifier
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import LlamaCppBackend
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.slot_client import (
    SlotClient,
    SlotKVError,
)
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    GenerateRequest,
    GenerateResult,
    InferenceRequest,
)
from neuroswarm_arm.runtime.slot_registry import SlotRegistry
from neuroswarm_arm.runtime.slot_router import SlotRouter


@pytest.fixture
def shared_slot_dir() -> Path:
    slot_dir = Path("work/test-slots") / uuid.uuid4().hex
    slot_dir.mkdir(parents=True, exist_ok=True)
    yield slot_dir
    shutil.rmtree(slot_dir, ignore_errors=True)


def _make_backend(
    name: str,
    slot_dir: Path,
    *,
    tier: int,
) -> LlamaCppBackend:
    LlamaCppBackend.slot_dir = slot_dir
    backend = LlamaCppBackend(name=name, base_url=f"http://127.0.0.1:808{tier}", tier=tier)
    backend._slot_router = SlotRouter(registry=SlotRegistry(total_slots=4))
    backend._client = MagicMock()
    return backend


@pytest.mark.asyncio
async def test_generate_saves_kv_when_handle_set(
    shared_slot_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "1")
    backend = _make_backend("tier1", shared_slot_dir, tier=1)
    backend._client.chat.return_value = {
        "choices": [{"message": {"content": "draft"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        "id_slot": 0,
    }
    export_calls: list[tuple[int, str]] = []
    backend._slots.kv_export = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda sid, fn: export_calls.append((sid, fn)) or {}
    )
    req = GenerateRequest(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess-a",
        kv_handle="session-a",
        id_slot=0,
    )
    ctx = ExecutionContext(
        request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
    )
    result = await backend.generate(req, ctx)
    assert result.text == "draft"
    assert len(export_calls) == 1
    assert export_calls[0][0] == 0
    assert export_calls[0][1].endswith("session-a.kv")


@pytest.mark.asyncio
async def test_verifier_missing_kv_soft_fails_then_exports(
    shared_slot_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 1 with no slot file: soft-fail import, still verify + export."""
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "1")
    verify = _make_backend("tier2", shared_slot_dir, tier=2)

    import_calls: list[str] = []
    export_calls: list[str] = []

    def _import(sid: int, fn: str) -> dict:
        import_calls.append(fn)
        raise SlotKVError(f"kv_import: slot file not found for handle {fn!r}")

    def _export(sid: int, fn: str) -> dict:
        export_calls.append(fn)
        Path(fn).write_bytes(b"verify-kv")
        return {}

    verify._slots.kv_import = _import  # type: ignore[method-assign]
    verify._slots.kv_export = _export  # type: ignore[method-assign]
    verify.generate = AsyncMock(  # type: ignore[method-assign]
        return_value=GenerateResult(
            text="hello world",
            prompt_tokens=5,
            completion_tokens=2,
            metrics={"slot_id": 0.0},
            raw={"choices": [{"message": {"content": "hello world"}}]},
        )
    )

    registry = MagicMock()
    registry.require.return_value = verify
    verifier = BlockVerifier(backend_name="tier2")
    await verifier.initialize(
        ASCRInitContext(
            registry=registry,
            config={"strategies": {"slot_kv_reuse": {"enabled": True}}},
        )
    )
    verifier.bind_execution_context(
        ExecutionContext(
            request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
        )
    )

    req = VerifyRequest(
        messages=[{"role": "user", "content": "hi"}],
        prompt_text="hi",
        mode=VerifyMode.BLOCK,
        kv_handle="missing-round1",
        id_slot=0,
        verifier_tier=2,
    )
    result = await verifier.verify(
        Proposal.from_text("hello world", strategy="draft_model", source_tier=1),
        req,
    )
    assert result.text == "hello world"
    assert len(import_calls) == 1
    assert len(export_calls) == 1
    assert Path(export_calls[0]).is_file()


@pytest.mark.asyncio
async def test_verifier_restores_before_and_saves_after_two_rounds(
    shared_slot_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "1")
    draft = _make_backend("tier1", shared_slot_dir, tier=1)
    verify = _make_backend("tier2", shared_slot_dir, tier=2)

    kv_file = shared_slot_dir / "cascade-session.kv"
    kv_file.write_bytes(b"fake-kv-state")

    import_order: list[str] = []

    def _import(sid: int, fn: str) -> dict:
        import_order.append(f"import:{sid}:{fn}")
        return {}

    def _export(sid: int, fn: str) -> dict:
        import_order.append(f"export:{sid}:{fn}")
        return {}

    verify._slots.kv_import = _import  # type: ignore[method-assign]
    verify._slots.kv_export = _export  # type: ignore[method-assign]

    gen_results = [
        GenerateResult(
            text="verified once",
            prompt_tokens=5,
            completion_tokens=3,
            metrics={"slot_id": 0.0},
            raw={"choices": [{"message": {"content": "verified once"}}]},
        ),
        GenerateResult(
            text="verified twice",
            prompt_tokens=5,
            completion_tokens=3,
            metrics={"slot_id": 0.0},
            raw={"choices": [{"message": {"content": "verified twice"}}]},
        ),
    ]
    verify.generate = AsyncMock(side_effect=gen_results)  # type: ignore[method-assign]

    registry = MagicMock()
    registry.require.return_value = verify

    verifier = BlockVerifier(backend_name="tier2")
    await verifier.initialize(
        ASCRInitContext(
            registry=registry,
            config={"strategies": {"slot_kv_reuse": {"enabled": True}}},
        )
    )
    verifier.bind_execution_context(
        ExecutionContext(
            request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
        )
    )

    draft_proposal = Proposal.from_text(
        "hello world",
        strategy="draft_model",
        source_tier=1,
    )
    req = VerifyRequest(
        messages=[{"role": "user", "content": "hi"}],
        prompt_text="hi",
        mode=VerifyMode.BLOCK,
        kv_handle="cascade-session",
        id_slot=0,
        verifier_tier=2,
    )

    await verifier.verify(draft_proposal, req)
    await verifier.verify(draft_proposal, req)

    assert len([x for x in import_order if x.startswith("import:0:")]) == 2
    assert len([x for x in import_order if x.startswith("export:0:")]) == 2


def test_invalid_kv_handle_raises_slot_kv_error(shared_slot_dir: Path) -> None:
    client = SlotClient("http://127.0.0.1:8082", slot_dir=shared_slot_dir)
    with pytest.raises(SlotKVError, match="slot file not found"):
        client.kv_import(0, "missing-handle")


@pytest.mark.asyncio
async def test_slot_context_save_then_restore(shared_slot_dir: Path) -> None:
    from neuroswarm_arm.runtime.dipa.backends.llama_cpp.slot_client import SlotContext

    source = SlotClient("http://127.0.0.1:8081", slot_dir=shared_slot_dir)
    target = SlotClient("http://127.0.0.1:8082", slot_dir=shared_slot_dir)
    source.save_slot = MagicMock(return_value={})  # type: ignore[method-assign]
    target.restore_slot = MagicMock(return_value={})  # type: ignore[method-assign]

    kv_file = shared_slot_dir / "xfer.kv"
    kv_file.write_bytes(b"x")

    async with SlotContext(
        source=source,
        target=target,
        id_slot=1,
        filename="xfer",
    ):
        source.save_slot.assert_called_once()

    target.restore_slot.assert_called_once()
    args = target.restore_slot.call_args[0]
    assert args[0] == 1
    assert str(args[1]).endswith("xfer.kv")
