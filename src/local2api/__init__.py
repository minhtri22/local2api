__version__ = "0.0.1"

# Core modules
from local2api.config import Settings
from local2api.context_store import ContextStore, CanonicalContext
from local2api.context_reconstruct import reconstruct_context, update_canonical_context
from local2api.routing.router import RuleRouter
from local2api.routing.types import RoutingDecision
from local2api.errors import BackendUnavailable, BackendError, UnsafeFallback
from local2api.backends.http import HTTPBackendAdapter
from local2api.backends.base import BackendAdapter

__all__ = [
    "Settings",
    "ContextStore",
    "CanonicalContext",
    "reconstruct_context",
    "update_canonical_context",
    "RuleRouter",
    "RoutingDecision",
    "BackendUnavailable",
    "BackendError",
    "UnsafeFallback",
    "HTTPBackendAdapter",
    "BackendAdapter",
]
