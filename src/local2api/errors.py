class BackendError(RuntimeError):
    """Base exception raised when a backend cannot serve a request."""


class BackendUnavailable(BackendError):
    """Backend cannot be reached or failed before a valid response."""


class UnsafeFallback(BackendError):
    """The selected task must not silently degrade to a weaker backend."""
