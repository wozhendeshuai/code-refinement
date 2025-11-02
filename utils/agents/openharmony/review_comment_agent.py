"""Agent for 研究问题二：评审意见生成."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentArtifact, AgentBlackboard, BaseAgent


class ReviewCommentAgent(BaseAgent):
    """Generates structured review comments for hunks that need review."""

    def __init__(self, blackboard: AgentBlackboard, rules_path: Path | None = None) -> None:
        super().__init__("review_comment", blackboard)
        self.load_rules(rules_path)

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        need_review_artifact = self.blackboard.pull("need_review")
        if not need_review_artifact:
            raise RuntimeError("Need review results missing")
        review_comments: List[Dict[str, Any]] = []
        for decision in need_review_artifact.payload["decisions"]:
            if not decision["need_review"]:
                continue
            file_obj = pr_sample.get_file(decision["file_path"])
            hunk = file_obj.get_hunk_by_range(tuple(decision["hunk_range"]["new"])) if file_obj else None
            context_lines = hunk.render_snippet() if hunk else ""
            review_comments.append(
                {
                    "pr_number": pr_sample.pr_number,
                    "file_path": decision["file_path"],
                    "hunk_range": decision["hunk_range"],
                    "review_comment": {
                        "summary": "建议检查此变更是否符合OpenHarmony模块规范",
                        "context_snippet": context_lines,
                        "rationale": decision["reason"],
                    },
                }
            )
        artifact = AgentArtifact(name=self.name, payload={"comments": review_comments})
        self.blackboard.push(self.name, artifact)
        return artifact
