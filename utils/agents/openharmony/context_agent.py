"""PR-level context extraction agent."""
from __future__ import annotations

from pathlib import Path

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentArtifact, AgentBlackboard, BaseAgent


class ContextAgent(BaseAgent):
    """Extracts PR-level context for downstream agents."""

    def __init__(self, blackboard: AgentBlackboard, rules_path: Path | None = None) -> None:
        super().__init__("context", blackboard)
        self.load_rules(rules_path)

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        project_context = self.blackboard.pull("project_context")
        payload = {
            "pr_number": pr_sample.pr_number,
            "metadata": pr_sample.metadata,
            "files": [diff_file.to_dict(include_lines=False) for diff_file in pr_sample.diff_files],
            "project_context": project_context.payload if project_context else None,
        }
        artifact = AgentArtifact(name=self.name, payload=payload)
        self.blackboard.push(self.name, artifact)
        return artifact
