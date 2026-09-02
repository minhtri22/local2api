from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BackendName = Literal["local", "cloud"]
FallbackMode = Literal["safe", "none"]


@dataclass(frozen=True)
class RoutingDecision:
    backend: BackendName
    reason: str
    fallback_mode: FallbackMode
    score: float
