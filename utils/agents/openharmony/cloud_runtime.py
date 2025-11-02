"""Cloud runtime pipeline for OpenHarmony review agents."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:  # pragma: no cover - optional dependency
    import requests
except Exception:  # pragma: no cover - tolerate missing dependency
    requests = None  # type: ignore

from data.pr_data.processing.structures import PRReviewSample

from .base import AgentArtifact, AgentBlackboard
from .fix_generator_agent import FixGeneratorAgent
from .line_locator_agent import LineLocatorAgent
from .need_review_agent import NeedReviewAgent
from .orchestrator import OpenHarmonyReviewOrchestrator
from .project_context_agent import ProjectContextAgent
from .reflector_agent import ReflectorAgent
from .review_comment_agent import ReviewCommentAgent
from .context_agent import ContextAgent

LOGGER = logging.getLogger(__name__)


@dataclass
class CloudCallResult:
    """Container describing a cloud inference response."""

    payload: Dict[str, Any]
    used_cloud: bool


class CloudLLMClient:
    """Minimal REST client wrapping云端 LLM 调用."""

    def __init__(
        self,
        *,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        response_field: Optional[str] = None,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.response_field = response_field

    def call_json(self, prompt: str, *, default: Dict[str, Any]) -> CloudCallResult:
        """Call the cloud endpoint, falling back to ``default`` on failure."""

        if not self.endpoint or not self.model or requests is None:
            return CloudCallResult(payload=dict(default), used_cloud=False)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "prompt": prompt}
        try:
            response = requests.post(  # type: ignore[operator]
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, str):
                data = json.loads(data)
            if self.response_field and isinstance(data, dict):
                data = data.get(self.response_field, data)
            if isinstance(data, str):
                data = json.loads(data)
            if not isinstance(data, dict):
                raise ValueError("Cloud response is not a JSON object")
            return CloudCallResult(payload=data, used_cloud=True)
        except Exception as exc:  # pragma: no cover - network errors
            LOGGER.debug("Cloud call failed, fallback to default: %s", exc)
            return CloudCallResult(payload=dict(default), used_cloud=False)


def _merge_structured(default: Dict[str, Any], update: Dict[str, Any], allowed_keys: Iterable[str]) -> Dict[str, Any]:
    """Merge ``update`` into ``default`` while keeping only allowed keys."""

    merged = dict(default)
    for key in allowed_keys:
        if key in update:
            merged[key] = update[key]
    return merged


class CloudNeedReviewAgent(NeedReviewAgent):
    """NeedReviewAgent with optional云端调用."""

    def __init__(self, blackboard: AgentBlackboard, *, llm_client: Optional[CloudLLMClient] = None, **kwargs: Any) -> None:
        super().__init__(blackboard, **kwargs)
        self.llm_client = llm_client

    @staticmethod
    def build_prompt(pr_sample: PRReviewSample, decision: Dict[str, Any]) -> str:
        file_obj = pr_sample.get_file(decision["file_path"])
        snippet = ""
        if file_obj:
            hunk = file_obj.get_hunk_by_range(tuple(decision["hunk_range"]["new"]))
            if hunk:
                snippet = hunk.render_snippet(context=3)
        metadata = pr_sample.metadata
        return (
            "任务：问题一（代码片段评审必要性判断）\n"
            f"PR 标题：{metadata.get('title', '')}\n"
            f"文件：{decision['file_path']}\n"
            f"Hunk 范围：旧 {decision['hunk_range']['old']} 新 {decision['hunk_range']['new']}\n"
            f"已有判断：{decision['need_review']}，原因：{decision['reason']}\n"
            f"代码片段：\n{snippet}\n"
            "请仅给出 JSON，对应字段 {\"need_review\": bool, \"reason\": str}."
        )

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        artifact = super().run(pr_sample)
        if not self.llm_client:
            return artifact
        updated: List[Dict[str, Any]] = []
        for decision in artifact.payload.get("decisions", []):
            prompt = self.build_prompt(pr_sample, decision)
            result = self.llm_client.call_json(prompt, default=decision)
            merged = _merge_structured(decision, result.payload, ["need_review", "reason"])
            merged.setdefault("source", "cloud" if result.used_cloud else "heuristic")
            updated.append(merged)
        artifact.payload["decisions"] = updated
        self.blackboard.push(self.name, artifact)
        return artifact


class CloudReviewCommentAgent(ReviewCommentAgent):
    """ReviewCommentAgent with云端生成能力."""

    def __init__(self, blackboard: AgentBlackboard, *, llm_client: Optional[CloudLLMClient] = None, **kwargs: Any) -> None:
        super().__init__(blackboard, **kwargs)
        self.llm_client = llm_client

    @staticmethod
    def build_prompt(pr_sample: PRReviewSample, decision: Dict[str, Any], snippet: str) -> str:
        metadata = pr_sample.metadata
        return (
            "任务：问题二（评审意见生成）\n"
            f"PR 标题：{metadata.get('title', '')}\n"
            f"文件：{decision['file_path']} Hunk：{decision['hunk_range']}\n"
            f"需要评审原因：{decision.get('reason', '')}\n"
            f"代码上下文：\n{snippet}\n"
            "请输出 JSON，对应字段 {\"summary\": str, \"rationale\": str, \"context_snippet\": str}."
        )

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        artifact = super().run(pr_sample)
        if not self.llm_client:
            return artifact
        enhanced: List[Dict[str, Any]] = []
        need_review_artifact = self.blackboard.pull("need_review")
        decisions = need_review_artifact.payload["decisions"] if need_review_artifact else []
        decision_map = {(d["file_path"], tuple(d["hunk_range"]["new"])): d for d in decisions}
        for comment in artifact.payload.get("comments", []):
            file_path = comment["file_path"]
            new_range = tuple(comment["hunk_range"]["new"])
            decision = decision_map.get((file_path, new_range), {})
            file_obj = pr_sample.get_file(file_path)
            snippet = comment["review_comment"].get("context_snippet", "")
            if file_obj:
                hunk = file_obj.get_hunk_by_range(new_range)
                if hunk:
                    snippet = hunk.render_snippet(context=3)
            prompt = self.build_prompt(pr_sample, decision, snippet)
            result = self.llm_client.call_json(prompt, default=comment["review_comment"])
            merged_comment = _merge_structured(
                comment["review_comment"],
                result.payload,
                ["summary", "rationale", "context_snippet"],
            )
            merged_comment.setdefault("source", "cloud" if result.used_cloud else "heuristic")
            enhanced.append({**comment, "review_comment": merged_comment})
        artifact.payload["comments"] = enhanced
        self.blackboard.push(self.name, artifact)
        return artifact


class CloudLineLocatorAgent(LineLocatorAgent):
    """LineLocatorAgent that can调用云端模型细化行级缺陷."""

    def __init__(self, blackboard: AgentBlackboard, *, llm_client: Optional[CloudLLMClient] = None, **kwargs: Any) -> None:
        super().__init__(blackboard, **kwargs)
        self.llm_client = llm_client

    @staticmethod
    def build_prompt(pr_sample: PRReviewSample, comment: Dict[str, Any], snippet: str) -> str:
        return (
            "任务：问题三（问题行定位）\n"
            f"PR#{pr_sample.pr_number} 文件：{comment['file_path']} 范围：{comment['hunk_range']}\n"
            f"评审意见：{comment['review_comment'].get('summary', '')}\n"
            f"上下文：\n{snippet}\n"
            "请返回 JSON 数组 issues，每个元素包含 line_no, issue_type, issue_desc, evidence。"
        )

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        artifact = super().run(pr_sample)
        if not self.llm_client:
            return artifact
        refined: List[Dict[str, Any]] = list(artifact.payload.get("issues", []))
        review_artifact = self.blackboard.pull("review_comment")
        if not review_artifact:
            return artifact
        for comment in review_artifact.payload.get("comments", []):
            file_obj = pr_sample.get_file(comment["file_path"])
            snippet = comment["review_comment"].get("context_snippet", "")
            if file_obj:
                hunk = file_obj.get_hunk_by_range(tuple(comment["hunk_range"]["new"]))
                if hunk:
                    snippet = hunk.render_snippet(context=3)
            prompt = self.build_prompt(pr_sample, comment, snippet)
            default = {"issues": []}
            result = self.llm_client.call_json(prompt, default=default)
            for issue in result.payload.get("issues", []):
                merged_issue = {
                    "pr_number": pr_sample.pr_number,
                    "file_path": comment["file_path"],
                    "line_no": issue.get("line_no"),
                    "issue_type": issue.get("issue_type", "unknown"),
                    "issue_desc": issue.get("issue_desc", ""),
                    "evidence": issue.get("evidence", snippet[:160]),
                    "source": "cloud" if result.used_cloud else "heuristic",
                }
                refined.append(merged_issue)
        artifact.payload["issues"] = refined
        self.blackboard.push(self.name, artifact)
        return artifact


class CloudFixGeneratorAgent(FixGeneratorAgent):
    """FixGeneratorAgent that delegates到云端模型提供修复草案."""

    def __init__(self, blackboard: AgentBlackboard, *, llm_client: Optional[CloudLLMClient] = None, **kwargs: Any) -> None:
        super().__init__(blackboard, **kwargs)
        self.llm_client = llm_client

    @staticmethod
    def build_prompt(pr_sample: PRReviewSample, issue: Dict[str, Any], original: str) -> str:
        return (
            "任务：问题四（修复版本生成）\n"
            f"PR#{pr_sample.pr_number} 文件：{issue['file_path']} 行：{issue.get('line_no')}\n"
            f"问题类型：{issue.get('issue_type')} 描述：{issue.get('issue_desc')}\n"
            f"原始代码：\n{original}\n"
            "请输出 JSON 字段 {\"fixed_lines\": [str], \"fix_desc\": str, \"can_auto_apply\": bool}."
        )

    def run(self, pr_sample: PRReviewSample) -> AgentArtifact:
        artifact = super().run(pr_sample)
        if not self.llm_client:
            return artifact
        heuristics_lookup: Dict[str, Dict[str, Any]] = {}
        for fix in artifact.payload.get("fixes", []):
            heuristics_lookup.setdefault(fix.get("file_path", ""), fix)
        locator_artifact = self.blackboard.pull("line_locator")
        if not locator_artifact:
            return artifact
        fixes: List[Dict[str, Any]] = []
        for issue in locator_artifact.payload.get("issues", []):
            file_obj = pr_sample.get_file(issue["file_path"])
            original_line = ""
            if file_obj:
                line_obj = file_obj.get_line_by_new_no(issue.get("line_no"))
                original_line = line_obj.content if line_obj else ""
            prompt = self.build_prompt(pr_sample, issue, original_line)
            result = self.llm_client.call_json(prompt, default={})
            merged_fix = {
                "pr_number": pr_sample.pr_number,
                "file_path": issue["file_path"],
                "original_lines": [original_line] if original_line else [],
                "fixed_lines": result.payload.get("fixed_lines")
                if isinstance(result.payload.get("fixed_lines"), list)
                else None,
                "fix_desc": result.payload.get("fix_desc", issue.get("issue_desc", "")),
                "can_auto_apply": bool(result.payload.get("can_auto_apply", False)),
                "source": "cloud" if result.used_cloud else "heuristic",
            }
            if not merged_fix["fixed_lines"]:
                fallback = heuristics_lookup.get(issue["file_path"])
                fallback_lines = fallback.get("fixed_lines") if fallback else None
                if isinstance(fallback_lines, list) and fallback_lines:
                    merged_fix["fixed_lines"] = fallback_lines
                elif original_line:
                    merged_fix["fixed_lines"] = [original_line]
                else:
                    merged_fix["fixed_lines"] = []
            fixes.append(merged_fix)
        artifact.payload["fixes"] = fixes
        self.blackboard.push(self.name, artifact)
        return artifact


class CloudOpenHarmonyPipeline:
    """High-level orchestrator for the云端 API 版本."""

    def __init__(
        self,
        *,
        llm_client: Optional[CloudLLMClient] = None,
        blackboard: Optional[AgentBlackboard] = None,
        reflector_rules_path: Optional[str] = None,
    ) -> None:
        self.blackboard = blackboard or AgentBlackboard()
        self.llm_client = llm_client
        project_context_agent = ProjectContextAgent(self.blackboard)
        context_agent = ContextAgent(self.blackboard)
        need_review_agent = CloudNeedReviewAgent(self.blackboard, llm_client=llm_client)
        review_agent = CloudReviewCommentAgent(self.blackboard, llm_client=llm_client)
        line_agent = CloudLineLocatorAgent(self.blackboard, llm_client=llm_client)
        fix_agent = CloudFixGeneratorAgent(self.blackboard, llm_client=llm_client)
        reflector_agent = (
            ReflectorAgent(self.blackboard, Path(reflector_rules_path))
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

    def run(self, pr_sample: PRReviewSample, *, enable_fix_generation: bool = True) -> Dict[str, Any]:
        return self.orchestrator.run(pr_sample, enable_fix_generation=enable_fix_generation)

    def reflect(self, successful_samples: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not self.orchestrator.reflector_agent:
            return None
        return self.orchestrator.reflect(successful_samples)
