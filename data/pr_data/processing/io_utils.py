"""I/O helpers for reading OpenHarmony PR crawler outputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Iterator


def read_jsonl(path: Path) -> Iterator[Dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def read_json(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_jsonl(path: Path, records: Iterable[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
