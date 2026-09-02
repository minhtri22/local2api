from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from local2api.errors import BackendUnavailable


class FakeBackend:
    def __init__(self, name: str, status: int = 200, fail: bool = False) -> None:
        self.name = name
        self.status = status
        self.fail = fail
        self.calls: list[dict] = []

    async def request(self, body: dict) -> httpx.Response:
        self.calls.append(body)
        if self.fail:
            raise BackendUnavailable(f"{self.name} is down")
        payload = {
            "id": f"fake-{self.name}",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": self.name}}],
        }
        return httpx.Response(self.status, json=payload)

    async def _stream(self, body: dict) -> AsyncIterator[bytes]:
        self.calls.append(body)
        if self.fail:
            raise BackendUnavailable(f"{self.name} is down")
        chunk = {"choices": [{"delta": {"content": self.name}}]}
        yield f"data: {json.dumps(chunk)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    def stream(self, body: dict) -> AsyncIterator[bytes]:
        return self._stream(body)

    async def health(self) -> bool:
        return not self.fail
