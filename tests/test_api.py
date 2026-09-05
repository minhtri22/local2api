import httpx
import pytest

from local2api.main import create_app
from tests.fakes import FakeBackend


@pytest.fixture
async def client_and_backends():
    app = create_app()
    local = FakeBackend("local")
    cloud = FakeBackend("cloud")
    app.state.backends = {"local": local, "cloud": cloud}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, local, cloud


@pytest.mark.asyncio
async def test_models_endpoint(client_and_backends):
    client, _, _ = client_and_backends
    response = await client.get("/v1/models")
    assert response.status_code == 200
    assert {m["id"] for m in response.json()["data"]} == {
        "local2api-auto", "local", "cloud"
    }


@pytest.mark.asyncio
async def test_short_chat_routes_local(client_and_backends):
    client, local, cloud = client_and_backends
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "local2api-auto", "messages": [{"role": "user", "content": "rewrite this sentence"}]},
    )
    assert response.status_code == 200
    assert response.headers["x-local2api-backend"] == "local"
    assert len(local.calls) == 1
    assert local.calls[0]["model"] == "qwen2.5-coder-14b-instruct-q4_k_m"
    assert len(cloud.calls) == 0


@pytest.mark.asyncio
async def test_complex_chat_routes_cloud(client_and_backends):
    client, local, cloud = client_and_backends
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "local2api-auto", "messages": [{"role": "user", "content": "review this repository architecture"}]},
    )
    assert response.status_code == 200
    assert response.headers["x-local2api-backend"] == "cloud"
    assert len(cloud.calls) == 1
    assert len(local.calls) == 0


@pytest.mark.asyncio
async def test_unsafe_cloud_failure_does_not_silently_fallback(client_and_backends):
    client, local, cloud = client_and_backends
    cloud.fail = True
    response = await client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "repository architecture review"}]},
    )
    assert response.status_code == 503
    assert len(local.calls) == 0


@pytest.mark.asyncio
async def test_safe_large_context_fallbacks_local(client_and_backends):
    client, local, cloud = client_and_backends
    cloud.fail = True
    long_text = "word " * 500
    response = await client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": long_text}]},
    )
    assert response.status_code == 200
    assert response.headers["x-local2api-backend"] == "local"
    assert "fallback_from_cloud" in response.headers["x-local2api-route-reason"]
    assert len(local.calls) == 1


@pytest.mark.asyncio
async def test_streaming_passthrough(client_and_backends):
    client, _, _ = client_and_backends
    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"stream": True, "messages": [{"role": "user", "content": "autocomplete"}]},
    ) as response:
        body = b"".join([chunk async for chunk in response.aiter_bytes()])
    assert response.status_code == 200
    assert b"data:" in body
    assert b"[DONE]" in body


@pytest.mark.asyncio
async def test_invalid_messages_is_400(client_and_backends):
    client, _, _ = client_and_backends
    response = await client.post("/v1/chat/completions", json={"messages": "not-a-list"})
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_upstream_non_2xx_is_preserved(client_and_backends):
    client, local, _ = client_and_backends
    local.status = 429
    response = await client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "rewrite"}]},
    )
    assert response.status_code == 429
    assert response.headers["x-local2api-backend"] == "local"


@pytest.mark.asyncio
async def test_health_reports_backends(client_and_backends):
    client, local, cloud = client_and_backends
    cloud.fail = True
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["backends"] == {"local": True, "cloud": False}
    assert response.json()["status"] == "ok"
