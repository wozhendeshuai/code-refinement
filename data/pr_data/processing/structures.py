"""Core data structures for OpenHarmony PR review datasets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class DiffLine:
    """Represents a single line in a diff hunk."""

    status: str
    content: str
    old_line_no: Optional[int]
    new_line_no: Optional[int]

    def to_dict(self) -> Dict[str, Optional[int]]:
        return {
            "status": self.status,
            "content": self.content,
            "old_line_no": self.old_line_no,
            "new_line_no": self.new_line_no,
        }


@dataclass
class DiffHunk:
    """Represents a diff hunk with expanded line-level information."""

    header: str
    old_start: int
    old_end: int
    new_start: int
    new_end: int
    lines: List[DiffLine] = field(default_factory=list)
    has_comment: bool = False

    def to_dict(self, include_lines: bool = True) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "header": self.header,
            "old_start": self.old_start,
            "old_end": self.old_end,
            "new_start": self.new_start,
            "new_end": self.new_end,
            "has_comment": self.has_comment,
        }
        if include_lines:
            payload["lines"] = [line.to_dict() for line in self.lines]
        return payload

    def render_snippet(self, context: int = 2) -> str:
        snippet_lines: List[str] = []
        context_budget = context
        for line in self.lines:
            if line.status in {"added", "removed"}:
                snippet_lines.append(line.content)
                context_budget = context
            elif context_budget > 0:
                snippet_lines.append(line.content)
                context_budget -= 1
        return "\n".join(snippet_lines)


@dataclass
class DiffFile:
    """Represents a file diff with associated hunks and metadata."""

    file_path: str
    hunks: List[DiffHunk] = field(default_factory=list)
    historical_comments: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self, include_lines: bool = True) -> Dict[str, object]:
        return {
            "file_path": self.file_path,
            "hunks": [hunk.to_dict(include_lines=include_lines) for hunk in self.hunks],
            "historical_comments": self.historical_comments,
        }

    def get_hunk_by_range(self, new_range: Tuple[int, int]) -> Optional[DiffHunk]:
        for hunk in self.hunks:
            if hunk.new_start == new_range[0] and hunk.new_end == new_range[1]:
                return hunk
        return None

    def get_line_by_new_no(self, new_no: int) -> Optional[DiffLine]:
        for hunk in self.hunks:
            for line in hunk.lines:
                if line.new_line_no == new_no:
                    return line
        return None


@dataclass
class PRReviewSample:
    """Canonical structure for downstream research tasks."""

    repo: str
    pr_number: int
    metadata: Dict[str, object]
    diff_files: List[DiffFile]
    comments: List[Dict[str, object]] = field(default_factory=list)
    commit_history: Dict[str, List[Dict[str, object]]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "repo": self.repo,
            "pr_number": self.pr_number,
            "metadata": self.metadata,
            "diff_files": [file.to_dict() for file in self.diff_files],
            "comments": self.comments,
            "commit_history": self.commit_history,
        }

    def get_file(self, file_path: str) -> Optional[DiffFile]:
        for diff_file in self.diff_files:
            if diff_file.file_path == file_path:
                return diff_file
        return None
