"""TTL cache for flag evaluations."""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class CacheEntry:
    """A cached flag evaluation result."""

    value: bool
    expires_at: float


class TTLCache:
    """Thread-safe TTL cache for flag evaluations.

    Keys are stored as (flag_key, user_id) tuples to support
    user-specific flag evaluations.
    """

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        """Initialize cache with TTL in seconds.

        Args:
            ttl_seconds: Time-to-live for cache entries. Default 30 seconds.
        """
        self._ttl = ttl_seconds
        self._cache: Dict[Tuple[str, Optional[str]], CacheEntry] = {}
        self._lock = asyncio.Lock()

    @property
    def ttl(self) -> float:
        """Return the cache TTL in seconds."""
        return self._ttl

    def _make_key(self, flag_key: str, user_id: Optional[str]) -> Tuple[str, Optional[str]]:
        """Create a cache key from flag key and user ID."""
        return (flag_key, user_id)

    async def get(self, flag_key: str, user_id: Optional[str] = None) -> Optional[bool]:
        """Get a cached value if it exists and hasn't expired.

        Args:
            flag_key: The feature flag key.
            user_id: Optional user ID for user-specific evaluations.

        Returns:
            The cached boolean value, or None if not found/expired.
        """
        key = self._make_key(flag_key, user_id)
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry.expires_at:
                # Entry expired, remove it
                del self._cache[key]
                return None
            return entry.value

    async def set(
        self, flag_key: str, value: bool, user_id: Optional[str] = None
    ) -> None:
        """Cache a flag evaluation result.

        Args:
            flag_key: The feature flag key.
            value: The evaluation result.
            user_id: Optional user ID for user-specific evaluations.
        """
        key = self._make_key(flag_key, user_id)
        expires_at = time.monotonic() + self._ttl
        async with self._lock:
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    async def invalidate(
        self, flag_key: str, user_id: Optional[str] = None
    ) -> None:
        """Remove a specific entry from the cache.

        Args:
            flag_key: The feature flag key.
            user_id: Optional user ID for user-specific evaluations.
        """
        key = self._make_key(flag_key, user_id)
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        """Clear all entries from the cache."""
        async with self._lock:
            self._cache.clear()

    async def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed.
        """
        now = time.monotonic()
        removed = 0
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if now > entry.expires_at
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
        return removed

    def get_sync(self, flag_key: str, user_id: Optional[str] = None) -> Optional[bool]:
        """Synchronous version of get() for sync wrapper.

        Note: Not thread-safe with async operations. Only use from sync context.
        """
        key = self._make_key(flag_key, user_id)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._cache[key]
            return None
        return entry.value

    def set_sync(
        self, flag_key: str, value: bool, user_id: Optional[str] = None
    ) -> None:
        """Synchronous version of set() for sync wrapper.

        Note: Not thread-safe with async operations. Only use from sync context.
        """
        key = self._make_key(flag_key, user_id)
        expires_at = time.monotonic() + self._ttl
        self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
