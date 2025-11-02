"""Command line entrypoint to validate数据处理流程."""
from __future__ import annotations

import argparse
from pathlib import Path

from .dataset_builder import PRReviewDatasetBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build PRReviewSample instances from raw crawler outputs.")
    parser.add_argument("--repo", required=True, help="Repository name, e.g., OpenHarmony.")
    parser.add_argument("--data-root", type=Path, required=True, help="Root directory that stores crawler结果")
    parser.add_argument("--pr-issue", type=Path, required=True, help="Path to get_pr&issue.py 的输出JSONL")
    parser.add_argument("--pr-commit", type=Path, required=True, help="Path to get_pr&commit.py 的输出JSONL")
    parser.add_argument(
        "--code-refinement",
        type=Path,
        required=True,
        help="Path to get_code_refinement_data.py 的输出JSONL",
    )
    args = parser.parse_args()

    builder = PRReviewDatasetBuilder(repo=args.repo, data_root=args.data_root)
    samples = builder.load_samples(
        pr_issue_file=args.pr_issue,
        pr_commit_file=args.pr_commit,
        code_refinement_file=args.code_refinement,
    )
    print(f"Loaded {len(samples)} PRReviewSample objects for repo {args.repo}.")
    total_hunks = sum(len(diff_file.hunks) for sample in samples for diff_file in sample.diff_files)
    print(f"Aggregated {total_hunks} diff hunks across dataset.")


if __name__ == "__main__":
    main()
