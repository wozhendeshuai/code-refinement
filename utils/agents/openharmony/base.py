"""Base classes shared across OpenHarmony review agents."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class AgentArtifact:
    """Container for agent outputs stored on the blackboard."""

    name: str
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentBlackboard:
    """Simple in-memory blackboard for coordinating agents."""

    def __init__(self) -> None:
        self._store: Dict[str, AgentArtifact] = {}

    def push(self, key: str, artifact: AgentArtifact) -> None:
        self._store[key] = artifact

    def pull(self, key: str) -> Optional[AgentArtifact]:
        return self._store.get(key)

    def as_dict(self) -> Dict[str, AgentArtifact]:
        return dict(self._store)


class BaseAgent:
    """Base class for all agents."""

    def __init__(self, name: str, blackboard: AgentBlackboard) -> None:
        self.name = name
        self.blackboard = blackboard
        self.rules_cache: Dict[str, Any] = {}

    def load_rules(self, rules_path: Optional[Path]) -> None:
        if not rules_path:
            return
        if rules_path.exists():
            try:
                import json

                with rules_path.open("r", encoding="utf-8") as handle:
                    self.rules_cache = json.load(handle)
            except Exception:
                self.rules_cache = {}

    def run(self, *args: Any, **kwargs: Any) -> AgentArtifact:
        raise NotImplementedError
