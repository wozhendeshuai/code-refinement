"""Data preparation utilities for 研究问题二：评审意见生成."""
from __future__ import annotations

from typing import Dict, Iterable

from .structures import PRReviewSample


def prepare_inputs(
    pr_sample: PRReviewSample,
    need_review_decisions: Iterable[Dict[str, object]],
) -> Dict[str, object]:
    """Assemble上下文供问题二模型使用."""

    decisions = [decision for decision in need_review_decisions if decision.get("need_review")]
    return {
        "repo": pr_sample.repo,
        "pr_number": pr_sample.pr_number,
        "need_review_hunks": decisions,
        "comments": pr_sample.comments,
        "diff_files": [diff_file.to_dict(include_lines=True) for diff_file in pr_sample.diff_files],
    }
