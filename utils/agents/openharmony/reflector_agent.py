"""Agent负责自我优化与规则更新."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

from .base import AgentArtifact, AgentBlackboard, BaseAgent


class ReflectorAgent(BaseAgent):
    """Learns from历史评审样本并写回规则."""

    def __init__(self, blackboard: AgentBlackboard, rules_output_path: Path) -> None:
        super().__init__("reflector", blackboard)
        self.rules_output_path = rules_output_path
        self.load_rules(rules_output_path if rules_output_path.exists() else None)

    def run(self, successful_samples: Iterable[Dict[str, Any]]) -> AgentArtifact:
        aggregated_patterns: Dict[str, Any] = {
            "long_line_threshold": 100,
            "frequent_issue_types": {},
        }
        for sample in successful_samples:
            issue_type = sample.get("issue_type")
            if not issue_type:
                continue
            aggregated_patterns["frequent_issue_types"].setdefault(issue_type, 0)
            aggregated_patterns["frequent_issue_types"][issue_type] += 1
        try:
            import json

            with self.rules_output_path.open("w", encoding="utf-8") as handle:
                json.dump(aggregated_patterns, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass
        artifact = AgentArtifact(name=self.name, payload=aggregated_patterns)
        self.blackboard.push(self.name, artifact)
        return artifact
