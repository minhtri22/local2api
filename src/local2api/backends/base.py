from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

import httpx


class BackendAdapter(Protocol):
    name: str

    async def request(self, body: dict) -> httpx.Response: ...

    def stream(self, body: dict) -> AsyncIterator[bytes]: ...

    async def health(self) -> bool: ...
