from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [
            {"id": "local2api-auto", "object": "model", "owned_by": "local2api"},
            {"id": "local", "object": "model", "owned_by": "local2api"},
            {"id": "cloud", "object": "model", "owned_by": "local2api"},
        ],
    }


@router.get("/health")
async def health(request: Request):
    results = {}
    for name, backend in request.app.state.backends.items():
        results[name] = await backend.health()
    overall = "ok" if any(results.values()) else "degraded"
    return {"status": overall, "backends": results, "version": "0.0.1"}
