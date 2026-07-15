"""ICheckpointManagerPort contract — coordinator metadata shape."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.checkpoint import ICheckpointManagerPort

from .conftest import fresh_manager


class _FakeExperienceStore:
    def __init__(self) -> None:
        self._snaps: dict[str, dict] = {}

    def store_snapshot(self, snapshot):
        handle = "exp://snapshot/snap_test"
        self._snaps[handle] = dict(snapshot)
        return handle

    def load_snapshot(self, handle: str):
        return self._snaps[handle]


class _FakeExperiencePort:
    def __init__(self) -> None:
        self.attached: list[tuple[str, list[str]]] = []

    def attach_checkpoint_refs(self, execution_id: str, checkpoint_ids: list[str]) -> None:
        self.attached.append((execution_id, list(checkpoint_ids)))


def test_port_runtime_checkable() -> None:
    mgr = fresh_manager()
    assert isinstance(mgr, ICheckpointManagerPort)


def test_create_restore_coordinator_metadata() -> None:
    store = _FakeExperienceStore()
    port = _FakeExperiencePort()
    mgr = fresh_manager(experience_store=store, experience_port=port)

    snap_ref = store.store_snapshot(
        {
            "execution_json": '{"execution_id":"ex_1"}',
            "completed_nodes": ["n_1", "n_2"],
            "failed_nodes": [],
            "skipped_nodes": [],
        }
    )
    metadata = {
        "execution_id": "ex_1",
        "workflow_id": "wf_1",
        "completed_nodes": ["n_1", "n_2"],
        "snapshot_ref": snap_ref,
    }
    cid = mgr.create(metadata)
    assert cid.startswith("ckpt_")
    assert port.attached == [("ex_1", [cid])]

    payload = mgr.restore(cid)
    assert payload["checkpoint_id"] == cid
    assert payload["execution_json"] == '{"execution_id":"ex_1"}'
    assert payload["completed_nodes"] == ["n_1", "n_2"]

    types = [e.type for e in mgr.events.history()]
    assert "CheckpointCreated" in types
    assert "CheckpointRestored" in types


def test_restore_metadata_only_without_experience_store() -> None:
    mgr = fresh_manager()
    cid = mgr.create(
        {
            "execution_id": "ex_2",
            "workflow_id": "wf_2",
            "completed_nodes": ["a"],
            "snapshot_ref": None,
        }
    )
    payload = mgr.restore(cid)
    assert payload["execution_id"] == "ex_2"
    assert "execution_json" not in payload


def test_latest_and_list() -> None:
    mgr = fresh_manager()
    c1 = mgr.create(
        {"execution_id": "ex_l", "workflow_id": "wf_l", "completed_nodes": ["a"]}
    )
    c2 = mgr.create(
        {"execution_id": "ex_l", "workflow_id": "wf_l", "completed_nodes": ["a", "b"]}
    )
    latest = mgr.latest(execution_id="ex_l")
    assert latest is not None
    assert latest.checkpoint_id == c2
    assert len(mgr.list_workflow("wf_l")) == 2
    assert c1 != c2
