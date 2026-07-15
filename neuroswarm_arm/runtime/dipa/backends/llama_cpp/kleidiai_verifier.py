"""KleidiAI verifier — require CPU_KLEIDIAI in llama.cpp load logs."""

from __future__ import annotations

import re
from dataclasses import dataclass


KLEIDIAI_PATTERN = re.compile(
    r"load_tensors:\s*CPU_KLEIDIAI\s+model\s+buffer\s+size",
    re.IGNORECASE,
)


@dataclass(slots=True)
class KleidiaiVerifyResult:
    ok: bool
    matched_line: str = ""
    require: bool = False
    message: str = ""


class KleidiaiVerifier:
    """Scrape llama-server logs for KleidiAI activation evidence."""

    def __init__(self, *, require: bool = False) -> None:
        self.require = require
        self._buffer: list[str] = []
        self._matched: str = ""

    def feed(self, line: str) -> bool:
        text = line.rstrip("\n")
        self._buffer.append(text)
        if len(self._buffer) > 5000:
            self._buffer = self._buffer[-2500:]
        if KLEIDIAI_PATTERN.search(text):
            self._matched = text
            return True
        return False

    def feed_many(self, text: str) -> bool:
        ok = False
        for line in text.splitlines():
            if self.feed(line):
                ok = True
        return ok

    def result(self) -> KleidiaiVerifyResult:
        if self._matched:
            return KleidiaiVerifyResult(
                ok=True,
                matched_line=self._matched,
                require=self.require,
                message="KleidiAI active",
            )
        if self.require:
            return KleidiaiVerifyResult(
                ok=False,
                require=True,
                message="CPU_KLEIDIAI not observed in model load logs",
            )
        return KleidiaiVerifyResult(
            ok=True,
            require=False,
            message="KleidiAI not verified (NSA_REQUIRE_KLEIDIAI unset)",
        )

    def assert_ready(self) -> None:
        res = self.result()
        if self.require and not res.ok:
            raise RuntimeError(res.message)
