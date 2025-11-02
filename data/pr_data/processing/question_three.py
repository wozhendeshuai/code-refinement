"""Data preparation utilities for 研究问题三：行级缺陷定位."""
from __future__ import annotations

from typing import Dict, Iterable

from .structures import PRReviewSample


def prepare_inputs(
    pr_sample: PRReviewSample,
    target_hunks: Iterable[Dict[str, object]],
) -> Dict[str, object]:
    """Build结构化输入供行级定位使用."""

    return {
        "repo": pr_sample.repo,
        "pr_number": pr_sample.pr_number,
        "target_hunks": list(target_hunks),
        "line_expanded_diff": [diff_file.to_dict(include_lines=True) for diff_file in pr_sample.diff_files],
    }
