"""Dataset builder for OpenHarmony PR review tasks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .diff_parser import DiffParser
from .io_utils import read_jsonl
from .structures import DiffFile, PRReviewSample


@dataclass
class PRReviewDatasetBuilder:
    """Builds :class:`PRReviewSample` objects from crawler outputs."""

    repo: str
    data_root: Path

    def load_samples(
        self,
        *,
        pr_issue_file: Path,
        pr_commit_file: Path,
        code_refinement_file: Path,
    ) -> List[PRReviewSample]:
        pr_metadata_map = {entry["number"]: entry for entry in read_jsonl(pr_issue_file)}
        commit_map = {entry["number"]: entry for entry in read_jsonl(pr_commit_file)}
        refinement_entries = list(read_jsonl(code_refinement_file))
        samples: List[PRReviewSample] = []
        for entry in refinement_entries:
            pr_number = entry.get("pr_number")
            if pr_number is None:
                continue
            metadata_entry = pr_metadata_map.get(pr_number, {})
            commit_entry = commit_map.get(pr_number, {})
            diff_files = self._build_diff_files(entry)
            sample = PRReviewSample(
                repo=self.repo,
                pr_number=pr_number,
                metadata=self._extract_metadata(metadata_entry),
                diff_files=diff_files,
                comments=self._extract_comments(entry, commit_entry),
                commit_history=self._extract_commit_history(commit_entry),
            )
            samples.append(sample)
        return samples

    # Internal helpers -------------------------------------------------
    def _build_diff_files(self, entry: Dict[str, object]) -> List[DiffFile]:
        diff_files: List[DiffFile] = []
        before_file = entry.get("before_file") or {}
        after_file = entry.get("after_file") or {}
        diff_comment = entry.get("diff_comment") or {}
        seen_paths = set()
        for file_blob in before_file.get("files", []) + after_file.get("files", []):
            filename = file_blob.get("filename")
            patch_text = file_blob.get("patch")
            if not filename or not patch_text or filename in seen_paths:
                continue
            seen_paths.add(filename)
            hunks = DiffParser.parse(patch_text)
            diff_files.append(
                DiffFile(
                    file_path=filename,
                    hunks=hunks,
                    historical_comments=diff_comment.get("comments", []),
                )
            )
        return diff_files

    def _extract_metadata(self, metadata_entry: Dict[str, object]) -> Dict[str, object]:
        fields = [
            "number",
            "title",
            "body",
            "state",
            "created_at",
            "merged_at",
            "user",
            "labels_name_list",
            "assignees_name_list",
        ]
        return {field: metadata_entry.get(field) for field in fields}

    def _extract_comments(
        self, refinement_entry: Dict[str, object], commit_entry: Dict[str, object]
    ) -> List[Dict[str, object]]:
        comments: List[Dict[str, object]] = []
        diff_comment = refinement_entry.get("diff_comment")
        if diff_comment:
            comments.extend(diff_comment.get("comments", []))
        comments.extend(commit_entry.get("diff_comments", []))
        return comments

    def _extract_commit_history(self, commit_entry: Dict[str, object]) -> Dict[str, List[Dict[str, object]]]:
        history: Dict[str, List[Dict[str, object]]] = {}
        for commit in commit_entry.get("pr_commits", []):
            for file_obj in commit.get("files", []):
                filename = file_obj.get("filename")
                if not filename:
                    continue
                history.setdefault(filename, []).append(
                    {
                        "sha": commit.get("sha"),
                        "date": commit.get("commit", {}).get("author", {}).get("date"),
                        "changes": file_obj.get("changes"),
                    }
                )
        return history
