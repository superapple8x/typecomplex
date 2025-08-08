from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import logging

try:
    import openai  # type: ignore
except Exception:  # pragma: no cover
    openai = None  # type: ignore


@dataclass
class DeepSeekError(Exception):
    code: str
    message: str
    status: Optional[int] = None
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        status_part = f" (status={self.status})" if self.status is not None else ""
        return f"{self.code}{status_part}: {self.message}"


# Map exceptions to normalized error codes aligned with specs
# Codes: invalid_api_key, quota_exceeded, rate_limited, bad_request, server_error, network_error, timeout

def normalize_exception(error: Exception) -> DeepSeekError:
    """Convert provider/client exceptions into DeepSeekError with normalized code."""
    # Fallbacks if openai is unavailable
    if openai is None:
        logging.debug("openai module not available; using generic normalization")
        return DeepSeekError(code="server_error", message=str(error))

    # Specific OpenAI SDK errors (v1+)
    if isinstance(error, Exception):
        # Authentication
        if hasattr(openai, "AuthenticationError") and isinstance(error, openai.AuthenticationError):
            return DeepSeekError(code="invalid_api_key", message="Authentication failed", status=getattr(error, "status_code", 401))
        # Rate limiting
        if hasattr(openai, "RateLimitError") and isinstance(error, openai.RateLimitError):
            return DeepSeekError(code="rate_limited", message="Too many requests", status=429)
        # Bad request / validation
        if hasattr(openai, "BadRequestError") and isinstance(error, openai.BadRequestError):
            return DeepSeekError(code="bad_request", message="Bad request", status=400)
        # Quota/billing sometimes reported as Permission/RateLimit variants; best-effort map
        if hasattr(openai, "PermissionDeniedError") and isinstance(error, openai.PermissionDeniedError):  # type: ignore[attr-defined]
            return DeepSeekError(code="quota_exceeded", message="Quota exceeded or permission denied", status=403)
        # Timeouts / connection
        if hasattr(openai, "APITimeoutError") and isinstance(error, openai.APITimeoutError):
            return DeepSeekError(code="timeout", message="Request timed out", status=None)
        if hasattr(openai, "APIConnectionError") and isinstance(error, openai.APIConnectionError):
            return DeepSeekError(code="network_error", message="Network connection error", status=None)
        # Server errors
        if hasattr(openai, "InternalServerError") and isinstance(error, openai.InternalServerError):
            return DeepSeekError(code="server_error", message="Server error", status=500)
        if hasattr(openai, "APIStatusError") and isinstance(error, openai.APIStatusError):
            status_code = getattr(error, "status_code", None)
            code = "server_error" if (status_code and 500 <= status_code <= 599) else "bad_request"
            return DeepSeekError(code=code, message="HTTP status error", status=status_code)
        if hasattr(openai, "APIError") and isinstance(error, openai.APIError):
            return DeepSeekError(code="server_error", message="API error", status=getattr(error, "status_code", None))

    # Generic fallback
    return DeepSeekError(code="server_error", message=str(error))
