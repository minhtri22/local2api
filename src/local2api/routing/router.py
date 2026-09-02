from __future__ import annotations

from collections.abc import Iterable

from .types import RoutingDecision

LOCAL_TASK_HINTS = {
    "autocomplete",
    "complete this line",
    "rewrite",
    "proofread",
    "summarize",
    "rename variable",
    "format code",
}

CLOUD_TASK_HINTS = {
    "architecture",
    "architect",
    "multi-file",
    "repository",
    "repo-wide",
    "refactor",
    "race condition",
    "algorithm",
    "deep debug",
    "optimize system",
    "security review",
}

SAFE_LOCAL_FALLBACK_HINTS = {
    "rewrite",
    "proofread",
    "summarize",
    "autocomplete",
    "complete this line",
    "format code",
}


class RuleRouter:
    """Deterministic v0.0.1 router."""

    def __init__(self, complexity_words: int = 450) -> None:
        self.complexity_words = complexity_words

    @staticmethod
    def _text(messages: Iterable[dict]) -> str:
        chunks: list[str] = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        chunks.append(str(item.get("text", "")))
        return " ".join(chunks).lower()

    def decide(self, body: dict) -> RoutingDecision:
        requested_model = str(body.get("model", "local2api-auto")).lower()
        if requested_model in {"local", "local2api-local"}:
            return RoutingDecision("local", "explicit_model_override", "none", 1.0)
        if requested_model in {"cloud", "local2api-cloud"}:
            return RoutingDecision("cloud", "explicit_model_override", "none", 1.0)

        text = self._text(body.get("messages", []))
        word_count = len(text.split())
        cloud_hits = [hint for hint in CLOUD_TASK_HINTS if hint in text]
        local_hits = [hint for hint in LOCAL_TASK_HINTS if hint in text]

        if cloud_hits:
            fallback = "safe" if any(h in text for h in SAFE_LOCAL_FALLBACK_HINTS) else "none"
            return RoutingDecision("cloud", f"complex_task:{cloud_hits[0]}", fallback, 0.95)

        if word_count > self.complexity_words:
            return RoutingDecision("cloud", "large_context", "safe", 0.75)

        if local_hits:
            return RoutingDecision("local", f"local_task:{local_hits[0]}", "none", 0.9)

        return RoutingDecision("local", "default_low_cost", "none", 0.6)
