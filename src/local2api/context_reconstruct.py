from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from local2api.config import Settings


@dataclass(frozen=True)
class BackendCapabilities:
    """Backend capability profile for context budgeting."""
    max_context_tokens: int
    supports_streaming: bool = True
    model_family: str = "unknown"
    quantized_kv: bool = False


# Default capability profiles matching A3 production contract
DEFAULT_BACKEND_CAPABILITIES = {
    "local": BackendCapabilities(
        max_context_tokens=4096,  # recommended context for 14B
        model_family="qwen2.5-coder",
        quantized_kv=True,
    ),
    "cloud": BackendCapabilities(
        max_context_tokens=128000,  # typical cloud context
        model_family="cloud",
    ),
}


@dataclass(frozen=True)
class ReconstructionResult:
    """Result of context reconstruction."""
    messages: list[dict[str, Any]]
    estimated_tokens: int
    compacted: bool
    compacted_turns: int = 0


def estimate_tokens(text: str) -> int:
    """Rough token estimation using word count * 1.3 heuristic."""
    # This is a rough approximation; in production you'd use a proper tokenizer
    words = len(text.split())
    return int(words * 1.3)


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate tokens in a message."""
    content = message.get("content", "")
    if isinstance(content, str):
        return estimate_tokens(content)
    elif isinstance(content, list):
        return sum(estimate_tokens(item.get("text", "")) for item in content if isinstance(item, dict))
    return 0


def extract_hard_constraints(text: str) -> list[str]:
    """Extract hard constraints from user message."""
    constraints = []
    # Look for common constraint patterns
    patterns = [
        r"(?:do not|don't|must not|never|avoid)\s+([^.]+)",
        r"(?:must|required|ensure)\s+([^.]+)",
        r"(?:only|exclusively)\s+([^.]+)",
        r"constraint[:\s]+([^.]+)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            constraint = match.strip()
            if constraint and constraint not in constraints:
                constraints.append(constraint)
    return constraints


def extract_artifacts(text: str) -> list[dict[str, Any]]:
    """Extract file/function references from text."""
    artifacts = []
    # Match file paths (including paths with slashes)
    file_matches = re.findall(r'(?:file|path)[:\s]+([^\s]+\.(?:py|js|ts|json|md|yaml|yml|toml))', text, re.IGNORECASE)
    for match in file_matches:
        artifacts.append({"type": "file", "path": match.strip()})
    # Match function/class names
    func_matches = re.findall(r'(?:function|method|class|def)\s+([a-zA-Z_][a-zA-Z0-9_]*)', text, re.IGNORECASE)
    for match in func_matches:
        artifacts.append({"type": "function", "name": match.strip()})
    return artifacts


def extract_decisions(text: str) -> list[dict[str, Any]]:
    """Extract decisions/facts from text."""
    decisions = []
    patterns = [
        (r"(?:decided|selected|chose|will use)\s+([^.]+)", "selection"),
        (r"(?:is\s+)?blocked|failed|rejected", "blocker"),
        (r"(?:prefer|recommend|suggest)\s+([^.]+)", "preference"),
    ]
    for pattern, dtype in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                # If pattern has groups, match is tuple
                content = " ".join(m for m in match if m).strip()
            else:
                # No groups, match is the full string
                content = match.strip()
            if content:
                decisions.append({"type": dtype, "content": content})
    return decisions


def reconstruct_context(
    canonical_context: Any,  # CanonicalContext - avoiding circular import
    incoming_turn: dict[str, Any],
    token_budget: int,
    backend_name: str = "local",
) -> ReconstructionResult:
    """Reconstruct backend-ready message list from canonical context.

    This is the core reconstruction pipeline that transforms the gateway's
    canonical state into a bounded, backend-ready message sequence.

    Priority order:
    1. System instructions
    2. Task goal
    3. Hard constraints
    4. Critical decisions/facts
    5. Relevant artifacts/context
    6. Recent turns (user + assistant)
    7. Older summarized history
    """
    from local2api.context_store import CanonicalContext

    if not isinstance(canonical_context, CanonicalContext):
        # Handle dict form for flexibility
        if isinstance(canonical_context, dict):
            canonical_context = CanonicalContext.from_dict(canonical_context)
        else:
            raise TypeError(f"Expected CanonicalContext, got {type(canonical_context)}")

    # Get capability profile
    capabilities = DEFAULT_BACKEND_CAPABILITIES.get(backend_name, DEFAULT_BACKEND_CAPABILITIES["local"])
    effective_budget = min(token_budget, capabilities.max_context_tokens)

    messages = []
    total_tokens = 0

    # 1. System instructions
    for instruction in canonical_context.system_instructions:
        msg = {"role": "system", "content": instruction}
        tokens = estimate_tokens(instruction)
        if total_tokens + tokens <= effective_budget:
            messages.append(msg)
            total_tokens += tokens

    # 2. Task goal (as system message)
    if canonical_context.task_goal:
        msg = {"role": "system", "content": f"Task goal: {canonical_context.task_goal}"}
        tokens = estimate_tokens(canonical_context.task_goal)
        if total_tokens + tokens <= effective_budget:
            messages.append(msg)
            total_tokens += tokens

    # 3. Hard constraints (structured, high priority)
    if canonical_context.hard_constraints:
        constraint_text = "Hard constraints:\n" + "\n".join(f"- {c}" for c in canonical_context.hard_constraints)
        msg = {"role": "system", "content": constraint_text}
        tokens = estimate_tokens(constraint_text)
        if total_tokens + tokens <= effective_budget:
            messages.append(msg)
            total_tokens += tokens

    # 4. Critical decisions/facts
    if canonical_context.decisions:
        decision_text = "Key decisions/facts:\n" + "\n".join(
            f"- [{d.get('type', 'note')}] {d.get('content', '')}"
            for d in canonical_context.decisions[-10:]  # Last 10 decisions
        )
        msg = {"role": "system", "content": decision_text}
        tokens = estimate_tokens(decision_text)
        if total_tokens + tokens <= effective_budget:
            messages.append(msg)
            total_tokens += tokens

    # 5. Relevant artifacts
    if canonical_context.artifacts:
        artifact_text = "Relevant artifacts:\n" + "\n".join(
            f"- {a.get('type', 'artifact')}: {a.get('path') or a.get('name', '')} - {a.get('summary', '')}"
            for a in canonical_context.artifacts[-10:]
        )
        msg = {"role": "system", "content": artifact_text}
        tokens = estimate_tokens(artifact_text)
        if total_tokens + tokens <= effective_budget:
            messages.append(msg)
            total_tokens += tokens

    # 6. Recent turns (most critical for continuity)
    recent_turns = canonical_context.recent_turns
    compacted_turns = 0

    # Process from most recent backwards to fit budget
    # Build conversation messages in reverse order (newest first), then reverse at end
    conversation_messages = []

    for turn in reversed(recent_turns):
        if total_tokens >= effective_budget:
            compacted_turns += 1
            continue

        # Assistant turn first (more recent in conversation flow)
        assistant_content = turn.get("assistant", "")
        if assistant_content:
            msg = {"role": "assistant", "content": assistant_content}
            tokens = estimate_tokens(assistant_content)
            if total_tokens + tokens <= effective_budget:
                conversation_messages.insert(0, msg)
                total_tokens += tokens
            else:
                compacted_turns += 1
                continue

        # User turn
        user_content = turn.get("user", "")
        if user_content:
            msg = {"role": "user", "content": user_content}
            tokens = estimate_tokens(user_content)
            if total_tokens + tokens <= effective_budget:
                conversation_messages.insert(0, msg)
                total_tokens += tokens
            else:
                compacted_turns += 1
                continue

    # Add conversation messages to main messages
    messages.extend(conversation_messages)

    # 7. Add incoming turn
    incoming_content = incoming_turn.get("content", "")
    incoming_role = incoming_turn.get("role", "user")
    incoming_msg = {"role": incoming_role, "content": incoming_content}
    incoming_tokens = estimate_tokens(incoming_content)

    if total_tokens + incoming_tokens <= effective_budget:
        messages.append(incoming_msg)
        total_tokens += incoming_tokens
    else:
        # If even incoming turn doesn't fit, truncate oldest non-system messages
        non_system_idx = next((i for i, m in enumerate(messages) if m["role"] != "system"), None)
        while non_system_idx is not None and total_tokens + incoming_tokens > effective_budget:
            removed = messages.pop(non_system_idx)
            total_tokens -= estimate_message_tokens(removed)
            compacted_turns += 1
            non_system_idx = next((i for i, m in enumerate(messages) if m["role"] != "system"), None)

        if total_tokens + incoming_tokens <= effective_budget:
            messages.append(incoming_msg)
            total_tokens += incoming_tokens
        else:
            # Emergency: truncate incoming content
            truncated = incoming_content[:int(len(incoming_content) * 0.5)]
            incoming_msg = {"role": incoming_role, "content": truncated + " [TRUNCATED]"}
            messages.append(incoming_msg)
            total_tokens = sum(estimate_message_tokens(m) for m in messages)
            compacted_turns += 1

    # Reorder: system messages first, then conversation history
    system_msgs = [m for m in messages if m["role"] == "system"]
    conversation_msgs = [m for m in messages if m["role"] != "system"]
    final_messages = system_msgs + conversation_msgs

    return ReconstructionResult(
        messages=final_messages,
        estimated_tokens=total_tokens,
        compacted=compacted_turns > 0,
        compacted_turns=compacted_turns,
    )


def update_canonical_context(
    canonical_context: Any,
    user_message: dict[str, Any],
    assistant_response: Optional[dict[str, Any]] = None,
    backend_used: str = "local",
    routing_decision: Optional[dict[str, Any]] = None,
) -> Any:
    """Update canonical context with new turn.

    This is called after a successful backend response to persist the turn
    and update derived state (constraints, decisions, facts, artifacts).
    """
    from local2api.context_store import CanonicalContext

    if not isinstance(canonical_context, CanonicalContext):
        if isinstance(canonical_context, dict):
            canonical_context = CanonicalContext.from_dict(canonical_context)
        else:
            raise TypeError(f"Expected CanonicalContext, got {type(canonical_context)}")

    user_content = user_message.get("content", "")
    user_role = user_message.get("role", "user")

    # Add turn to recent history
    turn = {
        "turn_id": str(uuid.uuid4()),
        "user": user_content if user_role == "user" else "",
        "assistant": "",
        "timestamp": time.time(),
        "backend": backend_used,
    }

    # Update from incoming message
    canonical_context.hard_constraints.extend(extract_hard_constraints(user_content))
    # Deduplicate
    canonical_context.hard_constraints = list(dict.fromkeys(canonical_context.hard_constraints))

    canonical_context.artifacts.extend(extract_artifacts(user_content))
    canonical_context.artifacts = list({f"{a['type']}:{a.get('path','')}:{a.get('name','')}": a for a in canonical_context.artifacts}.values())

    canonical_context.decisions.extend(extract_decisions(user_content))

    # Update task goal if not set
    if not canonical_context.task_goal and user_role == "user":
        # Use first substantial user message as task goal
        if len(user_content) > 20:
            canonical_context.task_goal = user_content[:200]

    if assistant_response:
        assistant_content = assistant_response.get("content", "")
        turn["assistant"] = assistant_content

        # Extract from assistant response too
        canonical_context.hard_constraints.extend(extract_hard_constraints(assistant_content))
        canonical_context.hard_constraints = list(dict.fromkeys(canonical_context.hard_constraints))

        canonical_context.known_facts.extend(
            {"fact": f, "source": "assistant"} for f in extract_artifacts(assistant_content)
        )

    canonical_context.recent_turns.append(turn)
    # Keep last 20 turns in memory (older ones would be summarized in full impl)
    if len(canonical_context.recent_turns) > 20:
        canonical_context.recent_turns = canonical_context.recent_turns[-20:]

    # Record backend history
    if routing_decision:
        canonical_context.backend_history.append({
            "turn_id": turn["turn_id"],
            "backend": backend_used,
            "reason": routing_decision.get("reason", ""),
            "fallback_mode": routing_decision.get("fallback_mode", "none"),
        })

    return canonical_context


# Import at bottom to avoid circular import issues
import uuid
import time
from typing import Optional