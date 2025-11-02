"""Orchestrator coordinating all OpenHarmony review agents."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentBlackboard, AgentArtifact
from .context_agent import ContextAgent
from .fix_generator_agent import FixGeneratorAgent
from .line_locator_agent import LineLocatorAgent
from .need_review_agent import NeedReviewAgent
from .project_context_agent import ProjectContextAgent
from .reflector_agent import ReflectorAgent
from .review_comment_agent import ReviewCommentAgent


class OpenHarmonyReviewOrchestrator:
    """Manager orchestrating all agents for a PR review."""

    def __init__(
        self,
        *,
        blackboard: AgentBlackboard | None = None,
        project_context_agent: ProjectContextAgent | None = None,
        context_agent: ContextAgent | None = None,
        need_review_agent: NeedReviewAgent | None = None,
        review_comment_agent: ReviewCommentAgent | None = None,
        line_locator_agent: LineLocatorAgent | None = None,
        fix_generator_agent: FixGeneratorAgent | None = None,
        reflector_agent: ReflectorAgent | None = None,
    ) -> None:
        self.blackboard = blackboard or AgentBlackboard()
        self.project_context_agent = project_context_agent or ProjectContextAgent(self.blackboard)
        self.context_agent = context_agent or ContextAgent(self.blackboard)
        self.need_review_agent = need_review_agent or NeedReviewAgent(self.blackboard)
        self.review_comment_agent = review_comment_agent or ReviewCommentAgent(self.blackboard)
        self.line_locator_agent = line_locator_agent or LineLocatorAgent(self.blackboard)
        self.fix_generator_agent = fix_generator_agent or FixGeneratorAgent(self.blackboard)
        self.reflector_agent = reflector_agent

    def run(self, pr_sample: PRReviewSample, *, enable_fix_generation: bool = True) -> Dict[str, Any]:
        self.project_context_agent.run(pr_sample)
        self.context_agent.run(pr_sample)
        need_review_artifact = self.need_review_agent.run(pr_sample)
        review_artifact = self.review_comment_agent.run(pr_sample)
        locator_artifact = self.line_locator_agent.run(pr_sample)
        fix_artifact: Optional[AgentArtifact] = None
        if enable_fix_generation:
            fix_artifact = self.fix_generator_agent.run(pr_sample)
        results = {
            "need_review": need_review_artifact.payload,
            "review_comments": review_artifact.payload,
            "issues": locator_artifact.payload,
            "fixes": fix_artifact.payload if fix_artifact else {"fixes": []},
        }
        return results

    def reflect(self, successful_samples: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not self.reflector_agent:
            return None
        return self.reflector_agent.run(list(successful_samples))
