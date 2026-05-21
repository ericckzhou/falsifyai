"""Exception types raised by the execution layer."""


class ExecutionError(Exception):
    """Raised when a model call fails for any reason.

    Wraps underlying provider errors (timeout, rate-limit, auth, malformed
    response, etc.) so callers do not need to import provider-specific
    exception types. The original exception is chained via ``__cause__``.
    """
