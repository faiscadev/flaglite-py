"""Tests for FlagLite client."""

import os
import pytest
import httpx
import respx
from unittest.mock import patch

from flaglite import (
    FlagLite,
    FlagLiteError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    ConfigurationError,
)


# Test constants
TEST_API_KEY = "ffl_env_test_key_12345"
TEST_BASE_URL = "https://api.flaglite.dev/v1/"


@pytest.fixture
def api_key_env():
    """Set up environment with API key."""
    with patch.dict(os.environ, {"FLAGLITE_API_KEY": TEST_API_KEY}):
        yield


@pytest.fixture
def no_api_key_env():
    """Set up environment without API key."""
    env = os.environ.copy()
    env.pop("FLAGLITE_API_KEY", None)
    with patch.dict(os.environ, env, clear=True):
        yield


class TestClientInit:
    """Test client initialization."""

    def test_init_with_api_key(self):
        """Client initializes with explicit API key."""
        client = FlagLite(api_key=TEST_API_KEY)
        assert client._api_key == TEST_API_KEY
        client.close_sync()

    def test_init_from_env(self, api_key_env):
        """Client reads API key from environment."""
        client = FlagLite()
        assert client._api_key == TEST_API_KEY
        client.close_sync()

    def test_init_without_api_key_raises(self, no_api_key_env):
        """Client raises ConfigurationError without API key."""
        with pytest.raises(ConfigurationError) as exc_info:
            FlagLite()
        assert "API key required" in str(exc_info.value)

    def test_init_with_custom_base_url(self):
        """Client accepts custom base URL."""
        client = FlagLite(api_key=TEST_API_KEY, base_url="https://custom.api.dev/v1")
        assert "custom.api.dev" in client._base_url
        client.close_sync()

    def test_init_with_custom_cache_ttl(self):
        """Client accepts custom cache TTL."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=60.0)
        assert client.cache_ttl == 60.0
        client.close_sync()

    def test_init_with_disabled_cache(self):
        """Client can disable caching."""
        client = FlagLite(api_key=TEST_API_KEY, disable_cache=True)
        assert client.cache_ttl == 0.0
        assert client._cache is None
        client.close_sync()

    def test_init_with_zero_ttl_disables_cache(self):
        """Setting cache_ttl=0 disables caching."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=0)
        assert client._cache is None
        client.close_sync()


class TestAsyncEnabled:
    """Test async enabled() method."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=0)
        yield client
        # Clean up synchronously since we're in a fixture
        if client._sync_client:
            client._sync_client.close()

    @respx.mock
    async def test_enabled_returns_true(self, client):
        """enabled() returns True when flag is enabled."""
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            return_value=httpx.Response(200, json={"key": "test-flag", "enabled": True})
        )
        
        result = await client.enabled("test-flag")
        assert result is True
        await client.close()

    @respx.mock
    async def test_enabled_returns_false(self, client):
        """enabled() returns False when flag is disabled."""
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            return_value=httpx.Response(200, json={"key": "test-flag", "enabled": False})
        )
        
        result = await client.enabled("test-flag")
        assert result is False
        await client.close()

    @respx.mock
    async def test_enabled_with_user_id(self, client):
        """enabled() passes user_id as query parameter."""
        route = respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            return_value=httpx.Response(200, json={"key": "test-flag", "enabled": True})
        )
        
        result = await client.enabled("test-flag", user_id="user-123")
        assert result is True
        
        # Verify user_id was passed
        assert "user_id=user-123" in str(route.calls[0].request.url)
        await client.close()

    @respx.mock
    async def test_enabled_404_returns_false(self, client):
        """enabled() returns False when flag not found (fail closed)."""
        respx.get(f"{TEST_BASE_URL}flags/nonexistent").mock(
            return_value=httpx.Response(404, json={"key": "nonexistent", "enabled": False})
        )
        
        result = await client.enabled("nonexistent")
        assert result is False
        await client.close()

    @respx.mock
    async def test_enabled_401_returns_default(self, client):
        """enabled() returns default on auth error."""
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        
        result = await client.enabled("test-flag")
        assert result is False  # Default
        
        result = await client.enabled("test-flag", default=True)
        assert result is True  # Custom default
        await client.close()

    @respx.mock
    async def test_enabled_429_returns_default(self, client):
        """enabled() returns default on rate limit."""
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            return_value=httpx.Response(
                429,
                json={"error": "rate_limited"},
                headers={"Retry-After": "60"},
            )
        )
        
        result = await client.enabled("test-flag")
        assert result is False
        await client.close()

    @respx.mock
    async def test_enabled_network_error_returns_default(self, client):
        """enabled() returns default on network error."""
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(side_effect=httpx.ConnectError("Connection failed"))
        
        result = await client.enabled("test-flag")
        assert result is False
        await client.close()

    @respx.mock
    async def test_enabled_timeout_returns_default(self, client):
        """enabled() returns default on timeout."""
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(side_effect=httpx.TimeoutException("Timeout"))
        
        result = await client.enabled("test-flag")
        assert result is False
        await client.close()


class TestCaching:
    """Test caching behavior."""

    @respx.mock
    async def test_cache_hit(self):
        """Second call uses cached value."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=30.0)
        
        route = respx.get(f"{TEST_BASE_URL}flags/cached-flag").mock(
            return_value=httpx.Response(200, json={"key": "cached-flag", "enabled": True})
        )
        
        # First call - hits API
        result1 = await client.enabled("cached-flag")
        assert result1 is True
        assert len(route.calls) == 1
        
        # Second call - uses cache
        result2 = await client.enabled("cached-flag")
        assert result2 is True
        assert len(route.calls) == 1  # No additional API call
        
        await client.close()

    @respx.mock
    async def test_cache_per_user(self):
        """Different users have separate cache entries."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=30.0)
        
        route = respx.get(f"{TEST_BASE_URL}flags/user-flag").mock(
            return_value=httpx.Response(200, json={"key": "user-flag", "enabled": True})
        )
        
        # Call for user-1
        await client.enabled("user-flag", user_id="user-1")
        assert len(route.calls) == 1
        
        # Call for user-2 - should hit API
        await client.enabled("user-flag", user_id="user-2")
        assert len(route.calls) == 2
        
        # Call for user-1 again - should use cache
        await client.enabled("user-flag", user_id="user-1")
        assert len(route.calls) == 2
        
        await client.close()

    @respx.mock
    async def test_invalidate_cache(self):
        """invalidate_cache() removes entry."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=30.0)
        
        route = respx.get(f"{TEST_BASE_URL}flags/invalidate-flag").mock(
            return_value=httpx.Response(200, json={"key": "invalidate-flag", "enabled": True})
        )
        
        # First call
        await client.enabled("invalidate-flag")
        assert len(route.calls) == 1
        
        # Invalidate
        await client.invalidate_cache("invalidate-flag")
        
        # Second call - should hit API again
        await client.enabled("invalidate-flag")
        assert len(route.calls) == 2
        
        await client.close()

    @respx.mock
    async def test_clear_cache(self):
        """clear_cache() removes all entries."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=30.0)
        
        route1 = respx.get(f"{TEST_BASE_URL}flags/flag-1").mock(
            return_value=httpx.Response(200, json={"key": "flag-1", "enabled": True})
        )
        route2 = respx.get(f"{TEST_BASE_URL}flags/flag-2").mock(
            return_value=httpx.Response(200, json={"key": "flag-2", "enabled": True})
        )
        
        # Cache both flags
        await client.enabled("flag-1")
        await client.enabled("flag-2")
        assert len(route1.calls) == 1
        assert len(route2.calls) == 1
        
        # Clear cache
        await client.clear_cache()
        
        # Both should hit API again
        await client.enabled("flag-1")
        await client.enabled("flag-2")
        assert len(route1.calls) == 2
        assert len(route2.calls) == 2
        
        await client.close()


class TestSyncEnabled:
    """Test synchronous enabled_sync() method."""

    @respx.mock
    def test_enabled_sync_returns_true(self):
        """enabled_sync() returns True when flag is enabled."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=0)
        
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            return_value=httpx.Response(200, json={"key": "test-flag", "enabled": True})
        )
        
        result = client.enabled_sync("test-flag")
        assert result is True
        client.close_sync()

    @respx.mock
    def test_enabled_sync_returns_false(self):
        """enabled_sync() returns False when flag is disabled."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=0)
        
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            return_value=httpx.Response(200, json={"key": "test-flag", "enabled": False})
        )
        
        result = client.enabled_sync("test-flag")
        assert result is False
        client.close_sync()

    @respx.mock
    def test_enabled_sync_with_user_id(self):
        """enabled_sync() passes user_id as query parameter."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=0)
        
        route = respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            return_value=httpx.Response(200, json={"key": "test-flag", "enabled": True})
        )
        
        result = client.enabled_sync("test-flag", user_id="user-456")
        assert result is True
        assert "user_id=user-456" in str(route.calls[0].request.url)
        client.close_sync()

    @respx.mock
    def test_enabled_sync_error_returns_default(self):
        """enabled_sync() returns default on error."""
        client = FlagLite(api_key=TEST_API_KEY, cache_ttl=0)
        
        respx.get(f"{TEST_BASE_URL}flags/test-flag").mock(
            side_effect=httpx.ConnectError("Connection failed")
        )
        
        result = client.enabled_sync("test-flag")
        assert result is False
        
        result = client.enabled_sync("test-flag", default=True)
        assert result is True
        client.close_sync()


class TestContextManager:
    """Test context manager support."""

    @respx.mock
    async def test_async_context_manager(self):
        """Client works as async context manager."""
        respx.get(f"{TEST_BASE_URL}flags/ctx-flag").mock(
            return_value=httpx.Response(200, json={"key": "ctx-flag", "enabled": True})
        )
        
        async with FlagLite(api_key=TEST_API_KEY) as flags:
            result = await flags.enabled("ctx-flag")
            assert result is True

    @respx.mock
    def test_sync_context_manager(self):
        """Client works as sync context manager."""
        respx.get(f"{TEST_BASE_URL}flags/ctx-flag").mock(
            return_value=httpx.Response(200, json={"key": "ctx-flag", "enabled": True})
        )
        
        with FlagLite(api_key=TEST_API_KEY) as flags:
            result = flags.enabled_sync("ctx-flag")
            assert result is True


class TestExceptions:
    """Test exception classes."""

    def test_flaglite_error(self):
        """FlagLiteError has message and status_code."""
        error = FlagLiteError("Test error", status_code=500)
        assert error.message == "Test error"
        assert error.status_code == 500
        assert str(error) == "Test error"

    def test_authentication_error(self):
        """AuthenticationError is a FlagLiteError."""
        error = AuthenticationError("Invalid key", status_code=401)
        assert isinstance(error, FlagLiteError)
        assert error.status_code == 401

    def test_rate_limit_error(self):
        """RateLimitError includes retry_after."""
        error = RateLimitError("Too many requests", retry_after=60)
        assert error.retry_after == 60
        assert error.status_code == 429

    def test_network_error(self):
        """NetworkError is a FlagLiteError."""
        error = NetworkError("Connection failed")
        assert isinstance(error, FlagLiteError)

    def test_configuration_error(self):
        """ConfigurationError is a FlagLiteError."""
        error = ConfigurationError("Missing API key")
        assert isinstance(error, FlagLiteError)
