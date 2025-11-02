"""Project-level context agent."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentArtifact, AgentBlackboard, BaseAgent


class ProjectContextAgent(BaseAgent):
    """Collects project级上下文 before reviewing a PR."""

    def __init__(self, blackboard: AgentBlackboard, rules_path: Path | None = None) -> None:
        super().__init__("project_context", blackboard)
        self.load_rules(rules_path)

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        related_files: List[Dict[str, Any]] = []
        for diff_file in pr_sample.diff_files:
            related_files.append(
                {
                    "file_path": diff_file.file_path,
                    "historical_comments": diff_file.historical_comments,
                    "recent_commits": pr_sample.commit_history.get(diff_file.file_path, []),
                }
            )
        payload = {
            "pr_number": pr_sample.pr_number,
            "project": pr_sample.repo,
            "related_files": related_files,
            "pr_title": pr_sample.metadata.get("title"),
            "pr_body": pr_sample.metadata.get("body"),
        }
        artifact = AgentArtifact(name=self.name, payload=payload)
        self.blackboard.push(self.name, artifact)
        return artifact
