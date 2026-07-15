# Origin: NEXUS Extension
"""NEXUS knowledge compiler pipeline. Official OKF validate runs first when require_official=True."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from nexus_okf import __version__
from nexus_okf.compiler.artifact_gen import write_graph, write_ontology
from nexus_okf.compiler.artifact_gen.bundle import write_bundle
from nexus_okf.compiler.artifact_gen.indexes import generate_indexes
from nexus_okf.compiler.artifact_gen.signer import sign_manifest
from nexus_okf.compiler.cache import BuildCache
from nexus_okf.compiler.diagnostics import Diagnostics
from nexus_okf.compiler.graph_builder import build_graph
from nexus_okf.compiler.incremental import compute_dirty
from nexus_okf.compiler.manifest import write_manifest
from nexus_okf.compiler.normalizer import normalize_document
from nexus_okf.compiler.ontology_check import check_ontology, load_ontology
from nexus_okf.compiler.optimizer import optimize_graph
from nexus_okf.compiler.parser import discover_markdown, parse_file
from nexus_okf.compiler.resolver import build_alias_map
from nexus_okf.compiler.validator import validate_bundle
from nexus_okf.internal.mmap_json import dump_json
from nexus_okf.official.validate import validate_bundle as validate_official


@dataclass
class BuildResult:
    ok: bool
    artifact_dir: Path
    docs_count: int
    elapsed_s: float
    diagnostics: Diagnostics
    dirty_count: int = 0
    incremental: bool = False
    artifacts: dict[str, Path] = field(default_factory=dict)
    official_ok: bool = True
    official_report: dict[str, Any] = field(default_factory=dict)


def compile_bundle(
    source_root: Path,
    artifact_root: Path | None = None,
    *,
    strict: bool = True,
    incremental: bool = True,
    sign: bool = False,
    private_key_pem: bytes | None = None,
    ontology_path: Path | None = None,
    require_official: bool = True,
) -> BuildResult:
    t0 = perf_counter()
    source_root = Path(source_root).resolve()
    artifact_root = Path(artifact_root or (source_root / ".okf" / "artifacts")).resolve()
    cache_root = artifact_root.parent / "cache"
    diag = Diagnostics()
    artifact_root.mkdir(parents=True, exist_ok=True)

    official_report = validate_official(source_root)
    official_dict = official_report.to_dict()
    if require_official and not official_report.ok:
        for item in official_report.items:
            if item.severity == "error":
                diag.error(f"OFFICIAL_{item.code}", item.message, item.path)
        dump_json(artifact_root / "official_diagnostics.json", official_dict)
        return BuildResult(
            ok=False,
            artifact_dir=artifact_root,
            docs_count=0,
            elapsed_s=perf_counter() - t0,
            diagnostics=diag,
            official_ok=False,
            official_report=official_dict,
            artifacts={"official_diagnostics": artifact_root / "official_diagnostics.json"},
        )

    paths = discover_markdown(source_root)
    cache = BuildCache(cache_root)
    dirty = (
        compute_dirty(paths, source_root, cache, __version__)
        if incremental
        else {p.relative_to(source_root).as_posix() for p in paths}
    )

    docs = []
    for path in paths:
        rel = path.relative_to(source_root).as_posix()
        raw_bytes = path.read_bytes()
        digest = cache.key(rel, raw_bytes, "1.0", __version__)
        try:
            if incremental and cache.has_doc(rel, digest):
                cached = cache.load_doc(rel)
                if cached is not None:
                    docs.append(cached)
                    continue
            doc = normalize_document(parse_file(path, source_root))
            docs.append(doc)
            if incremental:
                cache.store_doc(rel, doc, digest)
            else:
                cache.put(rel, digest)
        except Exception as exc:  # noqa: BLE001
            diag.error("PARSE", str(exc), rel)

    alias_map = build_alias_map(docs)
    ontology = load_ontology(ontology_path)
    check_ontology(docs, ontology, diag)
    graph = optimize_graph(build_graph(docs, alias_map), docs)
    validate_bundle(docs, graph, alias_map, diag, strict=strict)

    artifacts: dict[str, Path] = {}
    artifacts["graph"] = write_graph(artifact_root, graph)
    artifacts["ontology"] = write_ontology(artifact_root, ontology)
    artifacts.update(generate_indexes(artifact_root, docs, graph, alias_map))
    dump_json(artifact_root / "diagnostics.json", diag.to_dict())
    dump_json(artifact_root / "official_diagnostics.json", official_dict)
    artifacts["diagnostics"] = artifact_root / "diagnostics.json"
    artifacts["official_diagnostics"] = artifact_root / "official_diagnostics.json"

    manifest = write_manifest(
        artifact_root,
        docs_count=len(docs),
        compiler_version=__version__,
        artifact_paths={k: v for k, v in artifacts.items()},
        diagnostics=diag.to_dict(),
    )
    artifacts["knowledge_manifest"] = manifest
    if sign:
        sign_manifest(manifest, private_key_pem)

    bundle_path = write_bundle(artifact_root)
    artifacts["runtime_bundle"] = bundle_path
    write_manifest(
        artifact_root,
        docs_count=len(docs),
        compiler_version=__version__,
        artifact_paths={k: v for k, v in artifacts.items()},
        diagnostics=diag.to_dict(),
    )
    if sign:
        sign_manifest(manifest, private_key_pem)

    cache.save()
    ok = (diag.ok if strict else True) and (official_report.ok if require_official else True)
    return BuildResult(
        ok=ok,
        artifact_dir=artifact_root,
        docs_count=len(docs),
        elapsed_s=perf_counter() - t0,
        diagnostics=diag,
        dirty_count=len(dirty),
        incremental=incremental,
        artifacts=artifacts,
        official_ok=official_report.ok,
        official_report=official_dict,
    )
