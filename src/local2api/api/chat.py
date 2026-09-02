from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from local2api.errors import BackendUnavailable

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


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error(400, "invalid_json", "Request body must be valid JSON.")

    messages = body.get("messages")
    if not isinstance(messages, list):
        return _error(400, "invalid_request", "'messages' must be a list.")

    decision = request.app.state.router.decide(body)
    selected = request.app.state.backends[decision.backend]
    upstream_body = dict(body)
    upstream_body["model"] = request.app.state.backend_models[decision.backend]
    route_headers = _headers(decision.backend, decision.reason)
    started = time.perf_counter()

    if body.get("stream") is True:
        async def event_stream():
            try:
                async for chunk in selected.stream(upstream_body):
                    yield chunk
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

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers=route_headers,
        )

    try:
        upstream = await selected.request(upstream_body)
    except BackendUnavailable as exc:
        if decision.backend == "cloud" and decision.fallback_mode == "safe":
            fallback = request.app.state.backends["local"]
            try:
                fallback_body = dict(body)
                fallback_body["model"] = request.app.state.backend_models["local"]
                upstream = await fallback.request(fallback_body)
                route_headers = _headers("local", f"fallback_from_cloud:{decision.reason}")
            except BackendUnavailable as fallback_exc:
                return _error(503, "backend_unavailable", str(fallback_exc), route_headers)
        else:
            return _error(503, "backend_unavailable", str(exc), route_headers)

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "request_complete backend=%s reason=%s status=%s latency_ms=%.1f",
        route_headers["X-Local2API-Backend"],
        route_headers["X-Local2API-Route-Reason"],
        upstream.status_code,
        elapsed_ms,
    )

    media_type = upstream.headers.get("content-type", "application/json").split(";", 1)[0]
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=media_type,
        headers=route_headers,
    )
