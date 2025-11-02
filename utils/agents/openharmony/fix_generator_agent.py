"""Agent for 研究问题四：修复版本生成."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentArtifact, AgentBlackboard, BaseAgent


class FixGeneratorAgent(BaseAgent):
    """Produces draft fixes for detected issues."""

    def __init__(self, blackboard: AgentBlackboard, rules_path: Path | None = None) -> None:
        super().__init__("fix_generator", blackboard)
        self.load_rules(rules_path)

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        locator_artifact = self.blackboard.pull("line_locator")
        if not locator_artifact:
            raise RuntimeError("Line locator results missing")
        fixes: List[Dict[str, Any]] = []
        for issue in locator_artifact.payload.get("issues", []):
            file_obj = pr_sample.get_file(issue["file_path"])
            if not file_obj:
                continue
            target_line = file_obj.get_line_by_new_no(issue["line_no"])
            original = target_line.content if target_line else ""
            if len(original) <= self.rules_cache.get("long_line_threshold", 100):
                continue
            suggested = original[:100] + " // TODO: 拆分逻辑，遵循OpenHarmony代码规范"
            fixes.append(
                {
                    "pr_number": pr_sample.pr_number,
                    "file_path": issue["file_path"],
                    "original_lines": [original],
                    "fixed_lines": [suggested],
                    "fix_desc": issue["issue_desc"],
                    "can_auto_apply": False,
                }
            )
        artifact = AgentArtifact(name=self.name, payload={"fixes": fixes})
        self.blackboard.push(self.name, artifact)
        return artifact
