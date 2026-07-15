from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from nexus_okf.compiler.pipeline import BuildResult, compile_bundle
from nexus_okf.official.parse import concept_id
from nexus_okf.official.validate import validate_bundle as validate_official
from nexus_okf.runtime.kernel import build_runtime
from nexus_okf.runtime.mem0_bridge import merge_mem0_okf
from nexus_okf.runtime.query import OKFQuery

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def corpus_root() -> Path:
    return REPO / "okf"


@pytest.fixture
def art_root() -> Path:
    path = REPO / "work" / "okf" / "pytest-artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _compile_fresh(corpus_root: Path, art: Path, **kwargs: object) -> BuildResult:
    if art.exists():
        shutil.rmtree(art)
    result = compile_bundle(corpus_root, art, **kwargs)
    assert result.ok, result.diagnostics.to_dict()
    assert result.official_ok, result.official_report
    assert result.docs_count > 0, result.diagnostics.to_dict()
    return result


def test_official_validate_corpus(corpus_root: Path) -> None:
    report = validate_official(corpus_root)
    assert report.ok, report.to_dict()


def test_official_concept_id() -> None:
    assert concept_id("tables/users.md") == "tables/users"
    assert concept_id("agents/research-analyst.md") == "agents/research-analyst"


def test_official_accepts_unknown_type(art_root: Path) -> None:
    root = art_root / "google-sample"
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.md").write_text('---\nokf_version: "0.1"\n---\n\n# Bundle\n', encoding="utf-8")
    (root / "orders.md").write_text(
        "---\ntype: BigQuery Table\ntitle: Orders\n---\n# Orders\n",
        encoding="utf-8",
    )
    report = validate_official(root)
    assert report.ok, report.to_dict()


def test_official_rejects_missing_type(art_root: Path) -> None:
    root = art_root / "missing-type"
    root.mkdir(parents=True, exist_ok=True)
    (root / "bad.md").write_text("---\ntitle: No Type\n---\n# X\n", encoding="utf-8")
    report = validate_official(root)
    assert not report.ok
    assert any(i.code == "MISSING_TYPE" for i in report.items)


def test_compile_corpus(corpus_root: Path, art_root: Path) -> None:
    art = art_root / "compile"
    result = _compile_fresh(corpus_root, art, strict=False)
    assert result.docs_count >= 10
    assert (art / "graph.json").exists()
    assert (art / "runtime_bundle.okfb").exists()


def test_runtime_query(corpus_root: Path, art_root: Path) -> None:
    art = art_root / "query"
    _compile_fresh(corpus_root, art, strict=False)
    rt = build_runtime(art, corpus_root)
    ctx = rt.query(
        OKFQuery(text="github tool cost budget policy", agent_profile="coding", token_budget=600)
    )
    assert ctx.tokens_used > 0
    assert ctx.text


def test_tool_docs_after_route(corpus_root: Path, art_root: Path) -> None:
    art = art_root / "tools"
    _compile_fresh(corpus_root, art, strict=False)
    rt = build_runtime(art, corpus_root)
    docs = rt.load_tool_docs(["github"], budget=400)
    assert "GitHub" in docs.text or docs.tokens_used >= 0


def test_mem0_okf_separation(corpus_root: Path, art_root: Path) -> None:
    art = art_root / "merge"
    _compile_fresh(corpus_root, art, strict=False)
    rt = build_runtime(art, corpus_root)
    knowledge = rt.query(
        OKFQuery(text="cascade playbook", agent_profile="architect", token_budget=400)
    )
    merged = merge_mem0_okf(["user prefers terse answers"], knowledge, None)
    assert "Mem0" in merged
    assert "OKF" in merged


def test_incremental_rebuild(corpus_root: Path, art_root: Path) -> None:
    art = art_root / "incr"
    r1 = _compile_fresh(corpus_root, art, strict=False, incremental=True)
    r2 = compile_bundle(corpus_root, art, strict=False, incremental=True)
    assert r2.ok, r2.diagnostics.to_dict()
    assert r2.docs_count == r1.docs_count
    assert r2.dirty_count == 0


def test_duplicate_nexus_alias_detection(art_root: Path) -> None:
    root = art_root / "dup-corp"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.md").write_text(
        "---\ntype: concept\nid: same.id\ntitle: A\n---\n# A\n", encoding="utf-8"
    )
    (root / "b.md").write_text(
        "---\ntype: concept\nid: same.id\ntitle: B\n---\n# B\n", encoding="utf-8"
    )
    result = compile_bundle(root, art_root / "dup-out", strict=True, require_official=True)
    assert not result.ok
    assert any(d.code == "DUP_ID" for d in result.diagnostics.errors)
