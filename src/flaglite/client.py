"""FlagLite SDK client implementation."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional
from urllib.parse import urlencode, urljoin

import httpx

from .cache import TTLCache
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    FlagLiteError,
    NetworkError,
    RateLimitError,
)

logger = logging.getLogger("flaglite")

DEFAULT_BASE_URL = "https://api.flaglite.dev/v1"
DEFAULT_CACHE_TTL = 30.0  # 30 seconds
DEFAULT_TIMEOUT = 5.0  # 5 seconds


class FlagLite:
    """FlagLite feature flag client.

    A lightweight, production-ready client for the FlagLite feature flag service.
    Supports both async and sync usage patterns with built-in caching.

    Example:
        ```python
        from flaglite import FlagLite

        # Async usage
        flags = FlagLite()  # Auto-init from FLAGLITE_API_KEY env var

        if await flags.enabled('new-checkout'):
            show_new_checkout()

        # With user ID for percentage rollouts
        if await flags.enabled('new-checkout', user_id='user-123'):
            show_new_checkout()

        # Sync usage
        if flags.enabled_sync('new-checkout'):
            show_new_checkout()
        ```
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        timeout: float = DEFAULT_TIMEOUT,
        disable_cache: bool = False,
    ) -> None:
        """Initialize the FlagLite client.

        Args:
            api_key: FlagLite environment API key. If not provided, reads from
                FLAGLITE_API_KEY environment variable.
            base_url: API base URL. Defaults to https://api.flaglite.dev/v1.
                Can also be set via FLAGLITE_BASE_URL env var.
            cache_ttl: Cache time-to-live in seconds. Default 30 seconds.
                Set to 0 or use disable_cache=True to disable caching.
            timeout: HTTP request timeout in seconds. Default 5 seconds.
            disable_cache: If True, disable caching entirely.

        Raises:
            ConfigurationError: If no API key is provided or found in environment.
        """
        # Resolve API key
        self._api_key = api_key or os.environ.get("FLAGLITE_API_KEY")
        if not self._api_key:
            raise ConfigurationError(
                "API key required. Pass api_key parameter or set FLAGLITE_API_KEY environment variable."
            )

        # Resolve base URL
        self._base_url = (
            base_url
            or os.environ.get("FLAGLITE_BASE_URL")
            or DEFAULT_BASE_URL
        )
        if not self._base_url.endswith("/"):
            self._base_url += "/"

        self._timeout = timeout

        # Initialize cache
        self._cache_enabled = not disable_cache and cache_ttl > 0
        self._cache = TTLCache(ttl_seconds=cache_ttl) if self._cache_enabled else None

        # HTTP clients (lazy initialized)
        self._async_client: Optional[httpx.AsyncClient] = None
        self._sync_client: Optional[httpx.Client] = None

    @property
    def cache_ttl(self) -> float:
        """Return the cache TTL in seconds, or 0 if caching is disabled."""
        return self._cache.ttl if self._cache else 0.0

    def _get_headers(self) -> dict[str, str]:
        """Return headers for API requests."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "flaglite-python/1.0.0",
        }

    def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._get_headers(),
                timeout=self._timeout,
            )
        return self._async_client

    def _get_sync_client(self) -> httpx.Client:
        """Get or create the sync HTTP client."""
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self._base_url,
                headers=self._get_headers(),
                timeout=self._timeout,
            )
        return self._sync_client

    async def close(self) -> None:
        """Close the HTTP clients and release resources.

        Should be called when you're done using the client, especially in
        long-running applications.
        """
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

    def close_sync(self) -> None:
        """Synchronous version of close()."""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
        # Note: Can't close async client from sync context safely
        # It will be garbage collected

    async def __aenter__(self) -> FlagLite:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()

    def __enter__(self) -> FlagLite:
        """Sync context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Sync context manager exit."""
        self.close_sync()

    async def enabled(
        self,
        flag_key: str,
        user_id: Optional[str] = None,
        default: bool = False,
    ) -> bool:
        """Check if a feature flag is enabled.

        This is the primary method for checking feature flags. Results are cached
        according to the cache_ttl setting.

        Args:
            flag_key: The unique flag key (e.g., 'new-checkout').
            user_id: Optional user ID for consistent percentage rollouts.
                When provided, the same user always gets the same result
                for a given flag (sticky bucketing).
            default: Value to return on error. Defaults to False (fail closed).

        Returns:
            True if the flag is enabled, False otherwise.

        Note:
            This method never raises exceptions. On any error (network, auth, etc.),
            it returns the default value and logs the error.
        """
        # Check cache first
        if self._cache:
            cached = await self._cache.get(flag_key, user_id)
            if cached is not None:
                logger.debug(f"Cache hit for flag '{flag_key}' (user={user_id})")
                return cached

        # Make API request
        try:
            result = await self._evaluate_flag(flag_key, user_id)

            # Cache the result
            if self._cache:
                await self._cache.set(flag_key, result, user_id)

            return result

        except FlagLiteError as e:
            logger.warning(f"FlagLite error evaluating '{flag_key}': {e.message}")
            return default
        except Exception as e:
            logger.warning(f"Unexpected error evaluating flag '{flag_key}': {e}")
            return default

    async def _evaluate_flag(
        self, flag_key: str, user_id: Optional[str] = None
    ) -> bool:
        """Make the actual API request to evaluate a flag.

        Args:
            flag_key: The flag key to evaluate.
            user_id: Optional user ID for percentage rollouts.

        Returns:
            The flag evaluation result.

        Raises:
            AuthenticationError: If the API key is invalid.
            RateLimitError: If rate limit is exceeded.
            NetworkError: If a network error occurs.
            FlagLiteError: For other API errors.
        """
        client = self._get_async_client()

        # Build URL with query params
        url = f"flags/{flag_key}"
        if user_id:
            url = f"{url}?{urlencode({'user_id': user_id})}"

        try:
            response = await client.get(url)
        except httpx.TimeoutException as e:
            raise NetworkError(f"Request timed out: {e}") from e
        except httpx.NetworkError as e:
            raise NetworkError(f"Network error: {e}") from e
        except httpx.HTTPError as e:
            raise NetworkError(f"HTTP error: {e}") from e

        # Handle response
        if response.status_code == 200:
            data = response.json()
            return bool(data.get("enabled", False))

        if response.status_code == 401:
            raise AuthenticationError(
                "Invalid API key", status_code=response.status_code
            )

        if response.status_code == 404:
            # Flag not found - per spec, return enabled: false
            return False

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                "Rate limit exceeded",
                retry_after=int(retry_after) if retry_after else None,
                status_code=429,
            )

        # Other errors
        try:
            error_data = response.json()
            message = error_data.get("message", f"HTTP {response.status_code}")
        except Exception:
            message = f"HTTP {response.status_code}"

        raise FlagLiteError(message, status_code=response.status_code)

    def enabled_sync(
        self,
        flag_key: str,
        user_id: Optional[str] = None,
        default: bool = False,
    ) -> bool:
        """Synchronous version of enabled().

        Use this method in synchronous code paths. Internally creates an event
        loop if needed, or uses httpx sync client for efficiency.

        Args:
            flag_key: The unique flag key.
            user_id: Optional user ID for consistent percentage rollouts.
            default: Value to return on error. Defaults to False.

        Returns:
            True if the flag is enabled, False otherwise.
        """
        # Check cache first (sync version)
        if self._cache:
            cached = self._cache.get_sync(flag_key, user_id)
            if cached is not None:
                logger.debug(f"Cache hit for flag '{flag_key}' (user={user_id})")
                return cached

        # Make sync API request
        try:
            result = self._evaluate_flag_sync(flag_key, user_id)

            # Cache the result (sync version)
            if self._cache:
                self._cache.set_sync(flag_key, result, user_id)

            return result

        except FlagLiteError as e:
            logger.warning(f"FlagLite error evaluating '{flag_key}': {e.message}")
            return default
        except Exception as e:
            logger.warning(f"Unexpected error evaluating flag '{flag_key}': {e}")
            return default

    def _evaluate_flag_sync(
        self, flag_key: str, user_id: Optional[str] = None
    ) -> bool:
        """Synchronous version of _evaluate_flag().

        Args:
            flag_key: The flag key to evaluate.
            user_id: Optional user ID for percentage rollouts.

        Returns:
            The flag evaluation result.

        Raises:
            AuthenticationError: If the API key is invalid.
            RateLimitError: If rate limit is exceeded.
            NetworkError: If a network error occurs.
            FlagLiteError: For other API errors.
        """
        client = self._get_sync_client()

        # Build URL with query params
        url = f"flags/{flag_key}"
        if user_id:
            url = f"{url}?{urlencode({'user_id': user_id})}"

        try:
            response = client.get(url)
        except httpx.TimeoutException as e:
            raise NetworkError(f"Request timed out: {e}") from e
        except httpx.NetworkError as e:
            raise NetworkError(f"Network error: {e}") from e
        except httpx.HTTPError as e:
            raise NetworkError(f"HTTP error: {e}") from e

        # Handle response
        if response.status_code == 200:
            data = response.json()
            return bool(data.get("enabled", False))

        if response.status_code == 401:
            raise AuthenticationError(
                "Invalid API key", status_code=response.status_code
            )

        if response.status_code == 404:
            # Flag not found - per spec, return enabled: false
            return False

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                "Rate limit exceeded",
                retry_after=int(retry_after) if retry_after else None,
                status_code=429,
            )

        # Other errors
        try:
            error_data = response.json()
            message = error_data.get("message", f"HTTP {response.status_code}")
        except Exception:
            message = f"HTTP {response.status_code}"

        raise FlagLiteError(message, status_code=response.status_code)

    async def invalidate_cache(
        self, flag_key: str, user_id: Optional[str] = None
    ) -> None:
        """Invalidate a cached flag value.

        Args:
            flag_key: The flag key to invalidate.
            user_id: Optional user ID to invalidate a specific user's cache.
        """
        if self._cache:
            await self._cache.invalidate(flag_key, user_id)

    async def clear_cache(self) -> None:
        """Clear the entire flag cache."""
        if self._cache:
            await self._cache.clear()
