from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from local2api.context_reconstruct import (
    reconstruct_context,
    update_canonical_context,
    ReconstructionResult,
)
from local2api.context_store import ContextStore, CanonicalContext
from local2api.errors import BackendUnavailable
from local2api.config import Settings

logger = logging.getLogger("local2api")
router = APIRouter()


def _headers(backend: str, reason: str) -> dict[str, str]:
    return {
        "X-Local2API-Backend": backend,
        "X-Local2API-Route-Reason": reason,
    }


def _error(status: int, error_type: str, message: str, headers: dict[str, str] | None = None):
    return JSONResponse(
        status_code=status,
        content={"error": {"type": error_type, "message": message}},
        headers=headers or {},
    )


def _get_conversation_id(request: Request) -> Optional[str]:
    """Extract conversation ID from request body or header."""
    # Check header first (OpenAI-compatible extension)
    x_conversation_id = request.headers.get("X-Local2API-Conversation-ID")
    if x_conversation_id:
        return x_conversation_id
    # Check request body
    body = getattr(request.state, "request_body", None)
    if body and isinstance(body, dict):
        return body.get("conversation_id")
    return None


async def _load_or_create_context(
    context_store: ContextStore,
    conversation_id: Optional[str],
    request_body: dict,
) -> tuple[CanonicalContext, str, bool]:
    """Load existing context or create new one."""
    is_new = False
    if conversation_id:
        context = context_store.get_conversation(conversation_id)
        if context:
            return context, conversation_id, False
        # Conversation ID provided but not found - could create new or error
        # For backward compatibility, we'll create new with provided ID
        is_new = True
    else:
        conversation_id = str(uuid.uuid4())
        is_new = True

    # Extract initial system instructions from request if present
    system_instructions = []
    messages = request_body.get("messages", [])
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                system_instructions.append(content)

    context = context_store.create_conversation(
        conversation_id=conversation_id,
        system_instructions=system_instructions,
    )
    return context, conversation_id, is_new


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error(400, "invalid_json", "Request body must be valid JSON.")

    messages = body.get("messages")
    if not isinstance(messages, list):
        return _error(400, "invalid_request", "'messages' must be a list.")

    # Store request body for conversation ID extraction
    request.state.request_body = body

    # Get conversation ID
    conversation_id = _get_conversation_id(request)
    context_store: ContextStore = request.app.state.context_store

    # Load or create canonical context
    context, conv_id, is_new = await _load_or_create_context(context_store, conversation_id, body)

    # Get the last user message
    last_user_message = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_message = msg
            break

    if not last_user_message:
        return _error(400, "invalid_request", "No user message found.")

    # Get routing decision
    decision = request.app.state.router.decide(body)
    selected = request.app.state.backends[decision.backend]

    # Reconstruct context for backend
    reconstruction = reconstruct_context(
        canonical_context=context,
        incoming_turn=last_user_message,
        token_budget=request.app.state.settings.context_budget_tokens if hasattr(request.app.state, "settings") else 4096,
        backend_name=decision.backend,
    )

    # Build upstream body with reconstructed context
    upstream_body = dict(body)
    upstream_body["model"] = request.app.state.backend_models[decision.backend]
    upstream_body["messages"] = reconstruction.messages
    upstream_body["stream"] = body.get("stream", False)

    route_headers = _headers(decision.backend, decision.reason)
    route_headers["X-Local2API-Conversation-ID"] = conv_id
    if reconstruction.compacted:
        route_headers["X-Local2API-Context-Compacted"] = "true"
    route_headers["X-Local2API-Context-Tokens"] = str(reconstruction.estimated_tokens)

    started = time.perf_counter()

    if body.get("stream") is True:
        # For streaming, we'll persist the turn after stream completes
        # (including both user message and assistant response)
        # If stream fails, we still persist user message without assistant
        turn_persisted = False

        async def event_stream():
            nonlocal turn_persisted
            assistant_content_parts = []
            stream_completed = False
            try:
                async for chunk in selected.stream(upstream_body):
                    # Capture assistant content for context update
                    try:
                        chunk_str = chunk.decode() if isinstance(chunk, bytes) else chunk
                        for line in chunk_str.split('\n'):
                            if line.startswith('data: ') and line != 'data: [DONE]':
                                data = json.loads(line[6:])
                                delta = data.get('choices', [{}])[0].get('delta', {})
                                content = delta.get('content')
                                if content:
                                    assistant_content_parts.append(content)
                    except Exception:
                        pass  # Don't fail stream on parsing error
                    yield chunk
                    if b"data: [DONE]" in chunk or 'data: [DONE]' in chunk_str:
                        stream_completed = True
            except BackendUnavailable as exc:
                logger.warning(
                    "stream backend failure backend=%s reason=%s error=%s",
                    decision.backend,
                    decision.reason,
                    exc,
                )
                error_event = {
                    "error": {
                        "type": "backend_unavailable",
                        "message": str(exc),
                    }
                }
                yield f"data: {json.dumps(error_event)}\n\n".encode()
                yield b"data: [DONE]\n\n"
                stream_completed = False

            # Update canonical context after stream completes
            if not turn_persisted:
                if stream_completed and assistant_content_parts:
                    full_assistant = "".join(assistant_content_parts)
                    await _persist_turn(
                        context_store=context_store,
                        context=context,
                        user_message=last_user_message,
                        assistant_response={"content": full_assistant, "role": "assistant"},
                        backend_used=decision.backend,
                        routing_decision={
                            "reason": decision.reason,
                            "fallback_mode": decision.fallback_mode,
                        },
                    )
                elif not stream_completed:
                    # Stream failed - persist user message without assistant
                    await _persist_turn(
                        context_store=context_store,
                        context=context,
                        user_message=last_user_message,
                        assistant_response=None,
                        backend_used=decision.backend,
                        routing_decision={
                            "reason": decision.reason,
                            "fallback_mode": decision.fallback_mode,
                        },
                    )
                turn_persisted = True

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers=route_headers,
        )

    # Non-streaming path
    try:
        upstream = await selected.request(upstream_body)
    except BackendUnavailable as exc:
        if decision.backend == "cloud" and decision.fallback_mode == "safe":
            fallback = request.app.state.backends["local"]
            try:
                fallback_body = dict(upstream_body)
                fallback_body["model"] = request.app.state.backend_models["local"]
                upstream = await fallback.request(fallback_body)
                route_headers = _headers("local", f"fallback_from_cloud:{decision.reason}")
            except BackendUnavailable as fallback_exc:
                return _error(503, "backend_unavailable", str(fallback_exc), route_headers)
        else:
            return _error(503, "backend_unavailable", str(exc), route_headers)

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "request_complete backend=%s reason=%s status=%s latency_ms=%.1f conv=%s",
        route_headers["X-Local2API-Backend"],
        route_headers["X-Local2API-Route-Reason"],
        upstream.status_code,
        elapsed_ms,
        conv_id[:8],
    )

    # Parse response to extract assistant content
    assistant_response = None
    if upstream.status_code == 200:
        try:
            response_data = json.loads(upstream.content)
            choices = response_data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                if msg.get("role") == "assistant":
                    assistant_response = {"content": msg.get("content", ""), "role": "assistant"}
        except json.JSONDecodeError:
            pass

    # Persist turn to canonical context
    if assistant_response:
        await _persist_turn(
            context_store=context_store,
            context=context,
            user_message=last_user_message,
            assistant_response=assistant_response,
            backend_used=decision.backend,
            routing_decision={
                "reason": decision.reason,
                "fallback_mode": decision.fallback_mode,
            },
        )

    media_type = upstream.headers.get("content-type", "application/json").split(";", 1)[0]
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=media_type,
        headers=route_headers,
    )


async def _persist_turn(
    context_store: ContextStore,
    context: CanonicalContext,
    user_message: dict[str, Any],
    assistant_response: dict[str, Any],
    backend_used: str,
    routing_decision: dict[str, Any],
) -> None:
    """Persist a completed turn to the canonical context."""
    from local2api.context_reconstruct import update_canonical_context

    updated_context = update_canonical_context(
        canonical_context=context,
        user_message=user_message,
        assistant_response=assistant_response,
        backend_used=backend_used,
        routing_decision=routing_decision,
    )

    context_store.update_conversation(
        context=updated_context,
        turn_count=len(updated_context.recent_turns),
    )
