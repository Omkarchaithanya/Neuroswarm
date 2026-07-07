from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import zlib


@dataclass
class KVPage:
    page_id: str
    data: bytes
    compressed: bool = False


@dataclass
class KVCachePager:
    root: Path
    pages: dict[str, KVPage] = field(default_factory=dict)

    def save(self, session_id: str, payload: dict) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(payload).encode("utf-8")
        page = KVPage(page_id=session_id, data=zlib.compress(raw), compressed=True)
        self.pages[session_id] = page
        target = self.root / f"{session_id}.kvz"
        target.write_bytes(page.data)
        return target

    def load(self, session_id: str) -> dict:
        target = self.root / f"{session_id}.kvz"
        raw = zlib.decompress(target.read_bytes())
        return json.loads(raw.decode("utf-8"))

