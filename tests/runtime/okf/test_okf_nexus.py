from __future__ import annotations

from pathlib import Path

from neuroswarm_arm.runtime.okf import build_okf
from neuroswarm_arm.runtime.okf.factory import OKFConfig

REPO = Path(__file__).resolve().parents[3]


def test_nexus_okf_build_and_query() -> None:
    root = REPO / "okf"
    art = REPO / "work" / "okf" / "nexus-test-artifacts"
    rt = build_okf(OKFConfig(source_root=root, artifact_root=art, auto_build=True))
    status = rt.status()
    assert status.get("enabled") is True
    assert int(status.get("docs") or 0) >= 10
    ctx = rt.query("architecture domain HAOE DIPA", agent_profile="architect")
    assert getattr(ctx, "text", "")
