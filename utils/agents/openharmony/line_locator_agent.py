"""Agent for 研究问题三：行级缺陷定位."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentArtifact, AgentBlackboard, BaseAgent


class LineLocatorAgent(BaseAgent):
    """Pinpoints problematic lines within selected hunks."""

    def __init__(self, blackboard: AgentBlackboard, rules_path: Path | None = None) -> None:
        super().__init__("line_locator", blackboard)
        self.load_rules(rules_path)

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        review_artifact = self.blackboard.pull("review_comment")
        if not review_artifact:
            raise RuntimeError("Review comments missing")
        issues: List[Dict[str, Any]] = []
        for item in review_artifact.payload.get("comments", []):
            file_obj = pr_sample.get_file(item["file_path"])
            if not file_obj:
                continue
            new_range = item["hunk_range"]["new"]
            hunk = file_obj.get_hunk_by_range(tuple(new_range))
            if not hunk:
                continue
            for line in hunk.lines:
                if line.status == "added" and len(line.content) > self.rules_cache.get("long_line_threshold", 100):
                    issue_type = "maintainability"
                    desc = "新增行过长，建议拆分提升可读性"
                    evidence = line.content[:160]
                    issues.append(
                        {
                            "pr_number": pr_sample.pr_number,
                            "file_path": file_obj.file_path,
                            "line_no": line.new_line_no,
                            "issue_type": issue_type,
                            "issue_desc": desc,
                            "evidence": evidence,
                        }
                    )
        artifact = AgentArtifact(name=self.name, payload={"issues": issues})
        self.blackboard.push(self.name, artifact)
        return artifact
