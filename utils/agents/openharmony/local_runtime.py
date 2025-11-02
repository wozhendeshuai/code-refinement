"""Local multi-GPU runtime for OpenHarmony review agents."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentArtifact, AgentBlackboard
from .context_agent import ContextAgent
from .fix_generator_agent import FixGeneratorAgent
from .line_locator_agent import LineLocatorAgent
from .need_review_agent import NeedReviewAgent
from .orchestrator import OpenHarmonyReviewOrchestrator
from .project_context_agent import ProjectContextAgent
from .reflector_agent import ReflectorAgent
from .review_comment_agent import ReviewCommentAgent


@dataclass
class LocalModelSpec:
    """Description of a locally部署的模型."""

    name: str
    device: str
    max_context: int
    priority: int = 0


class LocalModelRegistry:
    """Tracks task-to-model映射并记录调用日志."""

    def __init__(self) -> None:
        self._registry: Dict[str, LocalModelSpec] = {}
        self._invocations: List[Dict[str, Any]] = []

    def register(self, task: str, spec: LocalModelSpec) -> None:
        self._registry[task] = spec

    def resolve(self, task: str) -> LocalModelSpec:
        return self._registry.get(task, LocalModelSpec(name="heuristic", device="cpu", max_context=4096))

    def record(self, task: str, payload_size: int, extra: Optional[Dict[str, Any]] = None) -> None:
        spec = self.resolve(task)
        entry = {
            "task": task,
            "model": spec.name,
            "device": spec.device,
            "payload_size": payload_size,
            "max_context": spec.max_context,
            "priority": spec.priority,
        }
        if extra:
            entry.update(extra)
        self._invocations.append(entry)

    @property
    def invocations(self) -> List[Dict[str, Any]]:
        return list(self._invocations)


class LocalNeedReviewAgent(NeedReviewAgent):
    """NeedReviewAgent enhanced with本地模型调度记录."""

    def __init__(self, blackboard: AgentBlackboard, *, registry: LocalModelRegistry, **kwargs: Any) -> None:
        super().__init__(blackboard, **kwargs)
        self.registry = registry

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        artifact = super().run(pr_sample)
        self.registry.record("need_review", len(artifact.payload.get("decisions", [])))
        return artifact


class LocalReviewCommentAgent(ReviewCommentAgent):
    """ReviewCommentAgent with本地模型日志."""

    def __init__(self, blackboard: AgentBlackboard, *, registry: LocalModelRegistry, **kwargs: Any) -> None:
        super().__init__(blackboard, **kwargs)
        self.registry = registry

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        artifact = super().run(pr_sample)
        payload_size = sum(len(c["review_comment"]["context_snippet"]) for c in artifact.payload.get("comments", []))
        self.registry.record("review_comment", payload_size)
        return artifact


class LocalLineLocatorAgent(LineLocatorAgent):
    """LineLocatorAgent that logs GPU 分配."""

    def __init__(self, blackboard: AgentBlackboard, *, registry: LocalModelRegistry, **kwargs: Any) -> None:
        super().__init__(blackboard, **kwargs)
        self.registry = registry

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        artifact = super().run(pr_sample)
        self.registry.record("line_locator", len(artifact.payload.get("issues", [])))
        return artifact


class LocalFixGeneratorAgent(FixGeneratorAgent):
    """FixGeneratorAgent with GPU usage tracing."""

    def __init__(self, blackboard: AgentBlackboard, *, registry: LocalModelRegistry, **kwargs: Any) -> None:
        super().__init__(blackboard, **kwargs)
        self.registry = registry

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        artifact = super().run(pr_sample)
        self.registry.record("fix_generator", len(artifact.payload.get("fixes", [])))
        return artifact


class LocalOpenHarmonyPipeline:
    """Pipeline coordinating本地多 GPU 推理."""

    def __init__(
        self,
        *,
        registry: Optional[LocalModelRegistry] = None,
        blackboard: Optional[AgentBlackboard] = None,
        reflector_rules_path: Optional[Path] = None,
    ) -> None:
        self.registry = registry or LocalModelRegistry()
        self.blackboard = blackboard or AgentBlackboard()
        self._ensure_default_models()
        project_context_agent = ProjectContextAgent(self.blackboard)
        context_agent = ContextAgent(self.blackboard)
        need_review_agent = LocalNeedReviewAgent(self.blackboard, registry=self.registry)
        review_agent = LocalReviewCommentAgent(self.blackboard, registry=self.registry)
        line_agent = LocalLineLocatorAgent(self.blackboard, registry=self.registry)
        fix_agent = LocalFixGeneratorAgent(self.blackboard, registry=self.registry)
        reflector_agent = (
            ReflectorAgent(self.blackboard, reflector_rules_path)
            if reflector_rules_path
            else None
        )
        self.orchestrator = OpenHarmonyReviewOrchestrator(
            blackboard=self.blackboard,
            project_context_agent=project_context_agent,
            context_agent=context_agent,
            need_review_agent=need_review_agent,
            review_comment_agent=review_agent,
            line_locator_agent=line_agent,
            fix_generator_agent=fix_agent,
            reflector_agent=reflector_agent,
        )

    def _ensure_default_models(self) -> None:
        if self.registry.resolve("need_review").name == "heuristic":
            self.registry.register(
                "need_review",
                LocalModelSpec(name="qwen2-7b", device="cuda:1", max_context=16384, priority=1),
            )
        if self.registry.resolve("review_comment").name == "heuristic":
            self.registry.register(
                "review_comment",
                LocalModelSpec(name="qwen2-72b", device="cuda:0", max_context=32768, priority=0),
            )
        if self.registry.resolve("line_locator").name == "heuristic":
            self.registry.register(
                "line_locator",
                LocalModelSpec(name="qwen2-32b", device="cuda:2", max_context=12288, priority=2),
            )
        if self.registry.resolve("fix_generator").name == "heuristic":
            self.registry.register(
                "fix_generator",
                LocalModelSpec(name="codeqwen-7b", device="cuda:0", max_context=16384, priority=1),
            )

    def run(self, pr_sample: PRReviewSample, *, enable_fix_generation: bool = True) -> Dict[str, Any]:
        result = self.orchestrator.run(pr_sample, enable_fix_generation=enable_fix_generation)
        result["scheduler_log"] = self.registry.invocations
        return result

    def reflect(self, successful_samples: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not self.orchestrator.reflector_agent:
            return None
        samples_list = list(successful_samples)
        outcome = self.orchestrator.reflect(samples_list)
        if outcome is not None:
            self.registry.record("reflector", len(samples_list))
        return outcome
