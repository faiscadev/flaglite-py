"""Tests for TTL cache."""

import time
import pytest
from unittest.mock import patch

from flaglite.cache import TTLCache


class TestTTLCache:
    """Test TTLCache implementation."""

    @pytest.fixture
    def cache(self):
        """Create a test cache with 1 second TTL."""
        return TTLCache(ttl_seconds=1.0)

    async def test_get_set_basic(self, cache):
        """Basic get/set works."""
        await cache.set("flag-1", True)
        result = await cache.get("flag-1")
        assert result is True

    async def test_get_miss_returns_none(self, cache):
        """Get on missing key returns None."""
        result = await cache.get("nonexistent")
        assert result is None

    async def test_set_false_value(self, cache):
        """Can cache False values."""
        await cache.set("flag-false", False)
        result = await cache.get("flag-false")
        assert result is False

    async def test_user_id_creates_separate_entries(self, cache):
        """Different user_ids create separate cache entries."""
        await cache.set("flag-1", True, user_id="user-1")
        await cache.set("flag-1", False, user_id="user-2")
        await cache.set("flag-1", True)  # No user_id

        assert await cache.get("flag-1", user_id="user-1") is True
        assert await cache.get("flag-1", user_id="user-2") is False
        assert await cache.get("flag-1") is True

    async def test_expiry(self, cache):
        """Entries expire after TTL."""
        # Use a very short TTL cache
        short_cache = TTLCache(ttl_seconds=0.1)
        await short_cache.set("expiring", True)
        
        # Should be available immediately
        assert await short_cache.get("expiring") is True
        
        # Wait for expiry
        time.sleep(0.15)
        
        # Should be expired
        assert await short_cache.get("expiring") is None

    async def test_invalidate(self, cache):
        """Invalidate removes specific entry."""
        await cache.set("flag-1", True)
        await cache.set("flag-2", True)
        
        await cache.invalidate("flag-1")
        
        assert await cache.get("flag-1") is None
        assert await cache.get("flag-2") is True

    async def test_invalidate_with_user_id(self, cache):
        """Invalidate with user_id only removes that entry."""
        await cache.set("flag-1", True, user_id="user-1")
        await cache.set("flag-1", True, user_id="user-2")
        
        await cache.invalidate("flag-1", user_id="user-1")
        
        assert await cache.get("flag-1", user_id="user-1") is None
        assert await cache.get("flag-1", user_id="user-2") is True

    async def test_clear(self, cache):
        """Clear removes all entries."""
        await cache.set("flag-1", True)
        await cache.set("flag-2", True, user_id="user-1")
        await cache.set("flag-3", False)
        
        await cache.clear()
        
        assert await cache.get("flag-1") is None
        assert await cache.get("flag-2", user_id="user-1") is None
        assert await cache.get("flag-3") is None

    async def test_cleanup_expired(self):
        """cleanup_expired removes expired entries."""
        cache = TTLCache(ttl_seconds=0.1)
        
        await cache.set("short", True)
        time.sleep(0.15)
        await cache.set("long", True)
        
        removed = await cache.cleanup_expired()
        assert removed == 1
        
        assert await cache.get("short") is None
        assert await cache.get("long") is True

    def test_ttl_property(self, cache):
        """TTL property returns configured value."""
        assert cache.ttl == 1.0

    def test_get_sync(self, cache):
        """Sync get works."""
        # Set via async first (for simplicity)
        cache._cache[("flag-sync", None)] = type(
            "Entry", (), {"value": True, "expires_at": time.monotonic() + 10}
        )()
        
        result = cache.get_sync("flag-sync")
        assert result is True

    def test_set_sync(self, cache):
        """Sync set works."""
        cache.set_sync("flag-sync", True)
        result = cache.get_sync("flag-sync")
        assert result is True

    def test_get_sync_expired(self, cache):
        """Sync get returns None for expired."""
        cache.set_sync("expiring", True)
        # Manually expire
        cache._cache[("expiring", None)].expires_at = time.monotonic() - 1
        
        result = cache.get_sync("expiring")
        assert result is None

    def test_get_sync_with_user_id(self, cache):
        """Sync get with user_id works."""
        cache.set_sync("flag-1", True, user_id="user-1")
        cache.set_sync("flag-1", False, user_id="user-2")
        
        assert cache.get_sync("flag-1", user_id="user-1") is True
        assert cache.get_sync("flag-1", user_id="user-2") is False
