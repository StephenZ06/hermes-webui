"""Normalized failures, so every provider reports trouble the same way."""

from __future__ import annotations


class ToolError(RuntimeError):
    """``kind`` decides what happens next, never the message text."""

    #: kinds safe to retry for an idempotent capability
    RETRYABLE = {"rate_limited", "timeout", "unavailable"}

    def __init__(self, kind: str, message: str, *, retry_after: float = 0):
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


def denied(message: str) -> ToolError:
    return ToolError("denied", message)
