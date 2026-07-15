# Origin: Official OKF
"""Official OKF §9 conformance validator — no NEXUS rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from nexus_okf.official.parse import OfficialDocument, discover_markdown, parse_document
from nexus_okf.official.reserved import is_root_index

DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", re.M)
RECOMMENDED = ("title", "description", "resource", "tags", "timestamp")


@dataclass
class OfficialDiagnostic:
    severity: str  # error | warning
    code: str
    message: str
    path: str | None = None


@dataclass
class OfficialReport:
    ok: bool
    items: list[OfficialDiagnostic] = field(default_factory=list)

    def error(self, code: str, message: str, path: str | None = None) -> None:
        self.items.append(OfficialDiagnostic("error", code, message, path))
        self.ok = False

    def warning(self, code: str, message: str, path: str | None = None) -> None:
        self.items.append(OfficialDiagnostic("warning", code, message, path))

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "layer": "official",
            "errors": sum(1 for i in self.items if i.severity == "error"),
            "warnings": sum(1 for i in self.items if i.severity == "warning"),
            "items": [
                {"severity": i.severity, "code": i.code, "message": i.message, "path": i.path}
                for i in self.items
            ],
        }


def _validate_index(doc: OfficialDocument, report: OfficialReport) -> None:
    """SPEC §6 + §11."""
    if is_root_index(doc.rel_path):
        if doc.has_frontmatter:
            illegal = [k for k in doc.frontmatter if k != "okf_version"]
            if illegal:
                report.error(
                    "INDEX_FM",
                    f"Root index.md frontmatter may only contain okf_version; found {illegal}",
                    doc.rel_path,
                )
        # body structure soft
        if not doc.body.strip():
            report.warning("INDEX_EMPTY", "index.md body is empty", doc.rel_path)
        return

    # Nested index.md: no frontmatter
    if doc.has_frontmatter:
        report.error(
            "INDEX_FM",
            "index.md must not contain frontmatter (SPEC §6)",
            doc.rel_path,
        )


def _validate_log(doc: OfficialDocument, report: OfficialReport) -> None:
    """SPEC §7."""
    if doc.has_frontmatter:
        report.error("LOG_FM", "log.md must not contain frontmatter (SPEC §7)", doc.rel_path)
    dates = DATE_HEADING_RE.findall(doc.body)
    if dates:
        # newest first soft check
        sorted_desc = sorted(dates, reverse=True)
        if dates != sorted_desc:
            report.warning(
                "LOG_ORDER",
                "log.md date headings SHOULD be newest first (ISO YYYY-MM-DD)",
                doc.rel_path,
            )
    elif doc.body.strip() and "##" in doc.body:
        report.warning(
            "LOG_DATE",
            "log.md date headings MUST use ISO 8601 YYYY-MM-DD when present",
            doc.rel_path,
        )


def _validate_concept(doc: OfficialDocument, report: OfficialReport) -> None:
    """SPEC §4 + §9."""
    if not doc.has_frontmatter:
        report.error(
            "MISSING_FRONTMATTER",
            "Concept documents must have parseable YAML frontmatter (SPEC §9)",
            doc.rel_path,
        )
        return
    typ = doc.frontmatter.get("type")
    if typ is None or (isinstance(typ, str) and not typ.strip()):
        report.error(
            "MISSING_TYPE",
            "Frontmatter must contain a non-empty type field (SPEC §4.1 / §9)",
            doc.rel_path,
        )
    # Soft recommended fields — never fail
    for key in RECOMMENDED:
        if key not in doc.frontmatter:
            report.warning(
                "RECOMMENDED_FIELD",
                f"Recommended frontmatter field missing: {key}",
                doc.rel_path,
            )
    # Unknown types / keys: MUST NOT reject (no action)


def validate_bundle(bundle_root: Path) -> OfficialReport:
    """Run Google OKF v0.1 §9 conformance only."""
    root = Path(bundle_root).resolve()
    report = OfficialReport(ok=True)
    if not root.is_dir():
        report.error("NO_BUNDLE", f"Bundle root is not a directory: {root}")
        return report

    paths = discover_markdown(root)
    if not paths:
        report.warning("EMPTY_BUNDLE", "No markdown files found in bundle")

    for path in paths:
        try:
            doc = parse_document(path, root)
        except Exception as exc:  # noqa: BLE001
            report.error("PARSE", str(exc), path.relative_to(root).as_posix())
            continue

        if doc.reserved and path.name == "index.md":
            _validate_index(doc, report)
        elif doc.reserved and path.name == "log.md":
            _validate_log(doc, report)
        else:
            _validate_concept(doc, report)

        # Broken links: MUST NOT reject (§5.3 / §9) — optional soft warn only
        # Intentionally no error.

    return report
