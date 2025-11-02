"""Data preparation utilities for 研究问题四：修复版本生成."""
from __future__ import annotations

from typing import Dict, Iterable

from .structures import PRReviewSample


def prepare_inputs(
    pr_sample: PRReviewSample,
    issues: Iterable[Dict[str, object]],
) -> Dict[str, object]:
    """Assemble the上下文用于修复生成."""

    return {
        "repo": pr_sample.repo,
        "pr_number": pr_sample.pr_number,
        "issues": list(issues),
        "diff_files": [diff_file.to_dict(include_lines=True) for diff_file in pr_sample.diff_files],
    }
