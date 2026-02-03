"""FlagLite SDK exceptions."""

from typing import Optional


class FlagLiteError(Exception):
    """Base exception for FlagLite SDK errors."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthenticationError(FlagLiteError):
    """Raised when API key is invalid or missing."""

    pass


class RateLimitError(FlagLiteError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        status_code: int = 429,
    ) -> None:
        super().__init__(message, status_code)
        self.retry_after = retry_after


class NetworkError(FlagLiteError):
    """Raised when a network error occurs."""

    pass


class ConfigurationError(FlagLiteError):
    """Raised when SDK is misconfigured."""

    pass
