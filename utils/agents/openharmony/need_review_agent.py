"""Agent for 研究问题一：评审必要性判断."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentArtifact, AgentBlackboard, BaseAgent


class NeedReviewAgent(BaseAgent):
    """Determines whether diff hunks need review."""

    def __init__(self, blackboard: AgentBlackboard, threshold: int = 3, rules_path: Path | None = None) -> None:
        super().__init__("need_review", blackboard)
        self.threshold = threshold
        self.load_rules(rules_path)

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        need_review_list: List[Dict[str, Any]] = []
        context_artifact = self.blackboard.pull("context")
        for diff_file in pr_sample.diff_files:
            for hunk in diff_file.hunks:
                added_lines = sum(1 for line in hunk.lines if line.status == "added")
                removed_lines = sum(1 for line in hunk.lines if line.status == "removed")
                heuristics_score = added_lines + removed_lines
                if hunk.has_comment or heuristics_score >= self.threshold:
                    decision = True
                    reason = "历史已存在评论" if hunk.has_comment else f"代码变更行数 {heuristics_score} 超过阈值 {self.threshold}"
                else:
                    decision = False
                    reason = f"代码变更行数 {heuristics_score} 未超过阈值 {self.threshold}"
                need_review_list.append(
                    {
                        "pr_number": pr_sample.pr_number,
                        "file_path": diff_file.file_path,
                        "hunk_range": {
                            "old": [hunk.old_start, hunk.old_end],
                            "new": [hunk.new_start, hunk.new_end],
                        },
                        "need_review": decision,
                        "reason": reason,
                    }
                )
        payload = {
            "pr_number": pr_sample.pr_number,
            "decisions": need_review_list,
            "context_ref": context_artifact.payload if context_artifact else None,
        }
        artifact = AgentArtifact(name=self.name, payload=payload)
        self.blackboard.push(self.name, artifact)
        return artifact
