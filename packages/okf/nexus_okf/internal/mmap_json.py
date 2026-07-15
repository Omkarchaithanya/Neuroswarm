from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    data = path.read_bytes()
    try:
        import orjson

        return orjson.loads(data)
    except ImportError:
        return json.loads(data.decode("utf-8"))


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import orjson

        path.write_bytes(orjson.dumps(obj, option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2))
    except ImportError:
        path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
