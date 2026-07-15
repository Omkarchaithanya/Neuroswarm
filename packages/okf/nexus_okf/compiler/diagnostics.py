from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(slots=True)
class Diagnostic:
    severity: Severity
    code: str
    message: str
    path: str | None = None


@dataclass
class Diagnostics:
    items: list[Diagnostic] = field(default_factory=list)

    def error(self, code: str, message: str, path: str | None = None) -> None:
        self.items.append(Diagnostic(Severity.ERROR, code, message, path))

    def warning(self, code: str, message: str, path: str | None = None) -> None:
        self.items.append(Diagnostic(Severity.WARNING, code, message, path))

    def info(self, code: str, message: str, path: str | None = None) -> None:
        self.items.append(Diagnostic(Severity.INFO, code, message, path))

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == Severity.ERROR]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": len(self.errors),
            "warnings": sum(1 for d in self.items if d.severity == Severity.WARNING),
            "items": [
                {
                    "severity": d.severity.value,
                    "code": d.code,
                    "message": d.message,
                    "path": d.path,
                }
                for d in self.items
            ],
        }
