"""FlagLite Python SDK.

A lightweight, production-ready Python client for the FlagLite feature flag service.

Example:
    ```python
    from flaglite import FlagLite

    flags = FlagLite()  # Auto-init from FLAGLITE_API_KEY env var

    # Async usage
    if await flags.enabled('new-checkout'):
        show_new_checkout()

    # With user ID for percentage rollouts
    if await flags.enabled('new-checkout', user_id='user-123'):
        show_new_checkout()

    # Sync usage
    if flags.enabled_sync('new-checkout'):
        show_new_checkout()

    # Auth example
    result = await FlagLite.signup('mypassword123')
    client = FlagLite(api_key=result.api_key)
    user = await client.me()
    ```
"""

from .client import FlagLite
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    FlagLiteError,
    NetworkError,
    RateLimitError,
)
from .types import (
    Environment,
    LoginResponse,
    Project,
    SignupResponse,
    User,
)

__version__ = "1.0.0"

__all__ = [
    "FlagLite",
    "FlagLiteError",
    "AuthenticationError",
    "RateLimitError",
    "NetworkError",
    "ConfigurationError",
    "User",
    "SignupResponse",
    "LoginResponse",
    "Project",
    "Environment",
    "__version__",
]
