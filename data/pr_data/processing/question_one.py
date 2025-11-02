"""Data preparation utilities for 研究问题一：代码片段评审必要性判断."""
from __future__ import annotations

from typing import Dict

from .structures import PRReviewSample


def prepare_inputs(pr_sample: PRReviewSample) -> Dict[str, object]:
    """Return the minimal fields required for 问题一."""

    return {
        "repo": pr_sample.repo,
        "pr_number": pr_sample.pr_number,
        "metadata": pr_sample.metadata,
        "diff_files": [diff_file.to_dict(include_lines=False) for diff_file in pr_sample.diff_files],
    }
