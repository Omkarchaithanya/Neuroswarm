# Origin: NEXUS Extension (CLI over Official OKF + NEXUS Knowledge OS)
"""CLI for Google OKF conformance and NEXUS Knowledge OS tooling."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from nexus_okf.compiler.pipeline import compile_bundle
from nexus_okf.official.validate import validate_bundle as validate_official
from nexus_okf.runtime.kernel import build_runtime
from nexus_okf.runtime.query import OKFQuery

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="NEXUS Knowledge OS over Google Open Knowledge Format (OKF)",
)


def _default_source() -> Path:
    return Path("okf")


@app.command()
def init(path: Path = typer.Argument(Path("okf"))) -> None:
    """Initialize a Google-conformant OKF bundle (+ NEXUS okf.yaml)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "agents").mkdir(exist_ok=True)
    (path / "tools").mkdir(exist_ok=True)
    (path / "policies").mkdir(exist_ok=True)
    index = path / "index.md"
    if not index.exists():
        index.write_text(
            '---\nokf_version: "0.1"\n---\n\n# Knowledge Bundle\n\n# Concepts\n\n',
            encoding="utf-8",
        )
    log = path / "log.md"
    if not log.exists():
        from datetime import date

        today = date.today().isoformat()
        log.write_text(
            f"# Directory Update Log\n\n## {today}\n* **Initialization**: Created bundle.\n",
            encoding="utf-8",
        )
    cfg = path / "okf.yaml"
    if not cfg.exists():
        cfg.write_text(
            'name: nexus-okf\nnexus_okf_version: "1.0"\nokf_spec: "0.1"\nstrict: true\n',
            encoding="utf-8",
        )
    typer.echo(f"initialized {path}")


@app.command()
def build(
    source: Path = typer.Option(_default_source(), "--source", "-s"),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
    strict: bool = typer.Option(True, "--strict/--no-strict"),
    incremental: bool = typer.Option(True, "--incremental/--full"),
    sign: bool = typer.Option(False, "--sign"),
    require_official: bool = typer.Option(True, "--require-official/--skip-official"),
) -> None:
    result = compile_bundle(
        source,
        out,
        strict=strict,
        incremental=incremental,
        sign=sign,
        require_official=require_official,
    )
    typer.echo(
        f"build {'OK' if result.ok else 'FAIL'} docs={result.docs_count} "
        f"official={result.official_ok} dirty={result.dirty_count} "
        f"elapsed={result.elapsed_s:.3f}s out={result.artifact_dir}"
    )
    if not result.ok:
        for d in result.diagnostics.errors:
            typer.echo(f"ERROR {d.code}: {d.message} ({d.path})")
        raise typer.Exit(1)


@app.command()
def validate(
    source: Path = typer.Option(_default_source(), "--source", "-s"),
    layer: str = typer.Option(
        "official",
        "--layer",
        "-l",
        help="official | nexus | both",
    ),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
) -> None:
    """Validate bundle. Default: Google OKF §9 (official)."""
    layer = layer.lower().strip()
    failed = False

    if layer in {"official", "both"}:
        report = validate_official(source)
        typer.echo({"layer": "official", **report.to_dict()})
        if not report.ok:
            failed = True

    if layer in {"nexus", "both"}:
        result = compile_bundle(
            source,
            out,
            strict=True,
            require_official=(layer == "both"),
        )
        typer.echo(
            {
                "layer": "nexus",
                "ok": result.ok,
                "official_ok": result.official_ok,
                "diagnostics": result.diagnostics.to_dict(),
            }
        )
        if not result.ok:
            failed = True

    if layer not in {"official", "nexus", "both"}:
        typer.echo("layer must be official|nexus|both")
        raise typer.Exit(2)

    if failed:
        raise typer.Exit(1)


@app.command()
def graph(
    source: Path = typer.Option(_default_source(), "--source", "-s"),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
) -> None:
    result = compile_bundle(source, out, strict=False)
    gpath = result.artifact_dir / "graph.json"
    typer.echo(gpath.read_text(encoding="utf-8")[:4000])


@app.command()
def doctor(source: Path = typer.Option(_default_source(), "--source", "-s")) -> None:
    report = validate_official(source)
    typer.echo({"official": report.to_dict()})
    if not report.ok:
        raise typer.Exit(1)
    art = source / ".okf" / "artifacts"
    if not art.exists():
        compile_bundle(source, art)
    rt = build_runtime(art, source)
    typer.echo(f"docs={len(rt.loader.document_index)} official+runtime ready")


@app.command()
def stats(source: Path = typer.Option(_default_source(), "--source", "-s")) -> None:
    art = source / ".okf" / "artifacts"
    if not (art / "knowledge_manifest.json").exists():
        compile_bundle(source, art)
    rt = build_runtime(art, source)
    typer.echo(
        {
            "docs": len(rt.loader.document_index),
            "aliases": len(rt.loader.alias_map),
            "edges": len(rt.loader.graph.get("edges") or []),
            "metrics": rt.metrics.snapshot(),
        }
    )


@app.command()
def watch(source: Path = typer.Option(_default_source(), "--source", "-s"), interval: float = 1.0) -> None:
    from nexus_okf.watcher.fs_watcher import watch_and_rebuild

    watch_and_rebuild(source, interval=interval)


@app.command()
def bundle(source: Path = typer.Option(_default_source(), "--source", "-s")) -> None:
    result = compile_bundle(source, strict=True)
    typer.echo(result.artifacts.get("runtime_bundle"))


@app.command()
def export(
    source: Path = typer.Option(_default_source(), "--source", "-s"),
    dest: Path = typer.Option(Path("okf-export"), "--dest"),
) -> None:
    import shutil

    result = compile_bundle(source, strict=False)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(result.artifact_dir, dest / "artifacts", dirs_exist_ok=True)
    typer.echo(dest)


@app.command()
def lint(source: Path = typer.Option(_default_source(), "--source", "-s")) -> None:
    validate(source=source, layer="both")


@app.command()
def migrate(
    source: Path = typer.Option(_default_source(), "--source", "-s"),
    mode: str = typer.Option("official", "--mode", help="official | nexus"),
) -> None:
    from nexus_okf.migration.google_okf_import import migrate_official, migrate_tree

    if mode == "nexus":
        n = migrate_tree(source)
    else:
        n = migrate_official(source)
    typer.echo(f"migrated {n} files mode={mode}")


@app.command()
def serve(
    source: Path = typer.Option(_default_source(), "--source", "-s"),
    host: str = "127.0.0.1",
    port: int = 8099,
) -> None:
    import uvicorn
    from nexus_okf.server.app import create_app

    art = source / ".okf" / "artifacts"
    if not art.exists():
        compile_bundle(source, art)
    app_ = create_app(art, source)
    uvicorn.run(app_, host=host, port=port)


@app.command()
def query(
    text: str,
    source: Path = typer.Option(_default_source(), "--source", "-s"),
    agent: str = "architect",
    budget: int = 800,
) -> None:
    art = source / ".okf" / "artifacts"
    if not art.exists():
        compile_bundle(source, art)
    rt = build_runtime(art, source)
    ctx = rt.query(OKFQuery(text=text, agent_profile=agent, token_budget=budget))
    typer.echo(ctx.text)
    typer.echo(ctx.metrics)


@app.callback()
def main_callback() -> None:
    pass


def main() -> None:
    app()


if __name__ == "__main__":
    main()
