"""Diff parser utilities for expanding hunks to line-level structures."""
from __future__ import annotations

from typing import List, Optional, Tuple

from .structures import DiffHunk, DiffLine


class DiffParser:
    """Utility to expand unified diff text into structured hunks."""

    @staticmethod
    def parse(patch_text: str) -> List[DiffHunk]:
        if not patch_text:
            return []
        hunks: List[DiffHunk] = []
        lines = patch_text.splitlines()
        idx = 0
        current_hunk: Optional[DiffHunk] = None
        old_line = 0
        new_line = 0

        while idx < len(lines):
            line = lines[idx]
            if line.startswith("@@"):
                header = line
                try:
                    header_body = header.split("@@")[1].strip()
                except IndexError:
                    idx += 1
                    continue
                parts = header_body.split()
                if len(parts) < 2:
                    idx += 1
                    continue
                old_span = parts[0][1:]
                new_span = parts[1][1:]
                old_start, old_count = DiffParser._parse_span(old_span)
                new_start, new_count = DiffParser._parse_span(new_span)
                old_line = old_start
                new_line = new_start
                current_hunk = DiffHunk(
                    header=header,
                    old_start=old_start,
                    old_end=old_start + max(old_count - 1, 0),
                    new_start=new_start,
                    new_end=new_start + max(new_count - 1, 0),
                    lines=[],
                )
                hunks.append(current_hunk)
            else:
                if current_hunk is None:
                    idx += 1
                    continue
                prefix = line[:1]
                content = line[1:] if len(line) > 1 else ""
                if prefix == "+":
                    current_hunk.lines.append(
                        DiffLine(status="added", content=content, old_line_no=None, new_line_no=new_line)
                    )
                    new_line += 1
                elif prefix == "-":
                    current_hunk.lines.append(
                        DiffLine(status="removed", content=content, old_line_no=old_line, new_line_no=None)
                    )
                    old_line += 1
                else:
                    text = line[1:] if line.startswith(" ") else line
                    current_hunk.lines.append(
                        DiffLine(status="context", content=text, old_line_no=old_line, new_line_no=new_line)
                    )
                    old_line += 1
                    new_line += 1
            idx += 1
        return hunks

    @staticmethod
    def _parse_span(span: str) -> Tuple[int, int]:
        if "," in span:
            start_str, count_str = span.split(",", maxsplit=1)
            return int(start_str), int(count_str)
        start = int(span)
        return start, 1
