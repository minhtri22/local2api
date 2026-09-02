from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from local2api.errors import BackendUnavailable


class HTTPBackendAdapter:
    def __init__(self, name: str, url: str, timeout: float) -> None:
        self.name = name
        self.url = url
        self.timeout = timeout

    async def request(self, body: dict) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.post(self.url, json=body)
        except httpx.HTTPError as exc:
            raise BackendUnavailable(f"{self.name} backend unavailable: {exc}") from exc

    async def _stream(self, body: dict) -> AsyncIterator[bytes]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.url, json=body) as response:
                    if response.is_error:
                        payload = await response.aread()
                        raise BackendUnavailable(
                            f"{self.name} stream failed with HTTP {response.status_code}: {payload[:200]!r}"
                        )
                    async for chunk in response.aiter_raw():
                        if chunk:
                            yield chunk
        except httpx.HTTPError as exc:
            raise BackendUnavailable(f"{self.name} backend unavailable: {exc}") from exc

    def stream(self, body: dict) -> AsyncIterator[bytes]:
        return self._stream(body)

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 2.0)) as client:
                response = await client.get(self.url.rsplit("/v1/chat/completions", 1)[0] or "/")
                return response.status_code < 500
        except httpx.HTTPError:
            return False
