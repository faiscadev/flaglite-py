# FlagLite Python SDK

A lightweight, production-ready Python client for the [FlagLite](https://flaglite.dev) feature flag service.

[![PyPI version](https://badge.fury.io/py/flaglite.svg)](https://badge.fury.io/py/flaglite)
[![Python versions](https://img.shields.io/pypi/pyversions/flaglite.svg)](https://pypi.org/project/flaglite/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- ✅ **Simple API** - One method to check flags: `enabled()`
- ✅ **Async/Await** - Native asyncio support
- ✅ **Sync Support** - Use `enabled_sync()` in synchronous code
- ✅ **Built-in Caching** - 30-second TTL cache (configurable)
- ✅ **Fail Closed** - Returns `False` on errors by default
- ✅ **Type Hints** - Full type annotations for IDE support
- ✅ **Percentage Rollouts** - Sticky bucketing with user IDs
- ✅ **Production Ready** - Comprehensive error handling

## Installation

```bash
pip install flaglite
```

## Quick Start

### 1. Set your API key

```bash
export FLAGLITE_API_KEY=ffl_env_your_api_key_here
```

### 2. Check feature flags

```python
from flaglite import FlagLite

flags = FlagLite()  # Auto-init from FLAGLITE_API_KEY env var

# Async usage
if await flags.enabled('new-checkout'):
    show_new_checkout()
else:
    show_old_checkout()
```

### 3. Percentage rollouts with user IDs

```python
# User-specific evaluation for consistent rollouts
if await flags.enabled('new-checkout', user_id='user-123'):
    # Same user always gets the same result (sticky bucketing)
    show_new_checkout()
```

## Usage Examples

### Async/Await (Recommended)

```python
import asyncio
from flaglite import FlagLite

async def main():
    flags = FlagLite()

    # Simple feature check
    if await flags.enabled('dark-mode'):
        enable_dark_mode()

    # With user ID for percentage rollouts
    if await flags.enabled('new-dashboard', user_id=current_user.id):
        render_new_dashboard()

    # Don't forget to close when done
    await flags.close()

asyncio.run(main())
```

### Context Manager

```python
async def main():
    async with FlagLite() as flags:
        if await flags.enabled('feature-x'):
            do_something()
    # Client is automatically closed
```

### Synchronous Usage

```python
from flaglite import FlagLite

flags = FlagLite()

# Use enabled_sync() in synchronous code
if flags.enabled_sync('new-checkout'):
    show_new_checkout()

# Clean up
flags.close_sync()
```

### FastAPI Example

```python
from fastapi import FastAPI, Depends
from flaglite import FlagLite

app = FastAPI()

# Create a shared client instance
flags = FlagLite()

@app.on_event("shutdown")
async def shutdown():
    await flags.close()

@app.get("/checkout")
async def checkout(user_id: str):
    if await flags.enabled('new-checkout', user_id=user_id):
        return {"version": "new"}
    return {"version": "legacy"}
```

### Django Example

```python
# settings.py
from flaglite import FlagLite
FEATURE_FLAGS = FlagLite()

# views.py
from django.conf import settings

def my_view(request):
    if settings.FEATURE_FLAGS.enabled_sync('new-feature'):
        return render(request, 'new_template.html')
    return render(request, 'old_template.html')
```

## Configuration

### Constructor Options

```python
flags = FlagLite(
    api_key="ffl_env_...",   # Optional: defaults to FLAGLITE_API_KEY env var
    base_url="https://...",   # Optional: defaults to FLAGLITE_BASE_URL or production
    cache_ttl=30.0,           # Cache TTL in seconds (default: 30)
    timeout=5.0,              # HTTP timeout in seconds (default: 5)
    disable_cache=False,      # Set True to disable caching
)
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `FLAGLITE_API_KEY` | Your environment API key (required if not passed to constructor) |
| `FLAGLITE_BASE_URL` | API base URL (optional, for self-hosted) |

### Cache Management

```python
# Invalidate a specific flag
await flags.invalidate_cache('my-flag')

# Invalidate a specific user's flag
await flags.invalidate_cache('my-flag', user_id='user-123')

# Clear entire cache
await flags.clear_cache()
```

## Error Handling

The SDK is designed to **fail closed** - it returns `False` on any error by default. This ensures your application continues working even if the flag service is unavailable.

```python
# Errors are logged but don't raise exceptions
result = await flags.enabled('my-flag')  # Returns False on error

# Override default value
result = await flags.enabled('my-flag', default=True)  # Returns True on error
```

### Exceptions (for direct API access)

If you need to handle errors explicitly, you can catch these exceptions:

```python
from flaglite import (
    FlagLiteError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    ConfigurationError,
)
```

## API Reference

### FlagLite

#### `async enabled(flag_key: str, user_id: str | None = None, default: bool = False) -> bool`

Check if a feature flag is enabled.

- **flag_key**: The unique flag key (e.g., 'new-checkout')
- **user_id**: Optional user ID for consistent percentage rollouts
- **default**: Value to return on error (default: False)
- **Returns**: True if enabled, False otherwise

#### `enabled_sync(flag_key: str, user_id: str | None = None, default: bool = False) -> bool`

Synchronous version of `enabled()`.

#### `async close() -> None`

Close HTTP clients and release resources.

#### `close_sync() -> None`

Synchronous version of `close()`.

#### `async invalidate_cache(flag_key: str, user_id: str | None = None) -> None`

Remove a specific entry from the cache.

#### `async clear_cache() -> None`

Clear the entire flag cache.

## Requirements

- Python 3.9+
- httpx 0.24+

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- Documentation: https://docs.flaglite.dev/sdks/python
- Issues: https://github.com/faiscadev/flaglite-py/issues
- Email: support@flaglite.dev
