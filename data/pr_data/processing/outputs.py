"""Utilities for persisting研究问题输出."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

from .io_utils import write_jsonl


@dataclass
class QuestionOutputPaths:
    """Manage输出文件路径."""

    root: Path

    def path_for(self, question_id: int) -> Path:
        filename = f"question_{question_id:02d}_outputs.jsonl"
        return self.root / filename

    def save_outputs(self, question_id: int, records: Iterable[Dict[str, object]]) -> None:
        write_jsonl(self.path_for(question_id), records)
