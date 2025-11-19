# Authentication Guide

This document explains how to use the `AuthenticationHandler` for managing authentication with the Thermacell API, including session injection and reauthentication handling.

## Table of Contents
- [Basic Usage](#basic-usage)
- [Session Injection](#session-injection)
- [Reauthentication Handling](#reauthentication-handling)
- [Session Update Callbacks](#session-update-callbacks)
- [Best Practices](#best-practices)

## Basic Usage

### Standalone Usage (Handler Owns Session)

When you don't provide a session, the handler creates and manages its own:

```python
from pythermacell import AuthenticationHandler

async def main():
    # Handler creates and owns the session
    async with AuthenticationHandler(
        username="user@example.com",
        password="your_password"
    ) as auth:
        # Authenticate manually
        await auth.authenticate()

        # Use the tokens
        print(f"Access Token: {auth.access_token}")
        print(f"User ID: {auth.user_id}")

    # Session is automatically closed when exiting the context
```

## Session Injection

### Why Inject a Session?

When using pythermacell as part of a larger application (like Home Assistant), you may want to:
- Reuse an existing aiohttp session
- Manage connection pooling centrally
- Control session lifecycle independently

### Important: No Automatic Authentication

**When you inject a session, the handler does NOT automatically authenticate.** This design allows you to:
- Control when authentication occurs
- Handle credentials securely
- Implement custom authentication flows

```python
from aiohttp import ClientSession
from pythermacell import AuthenticationHandler

async def main():
    # Application manages its own session
    async with ClientSession() as session:
        auth = AuthenticationHandler(
            username="user@example.com",
            password="your_password",
            session=session  # Injected session
        )

        # No authentication has occurred yet!
        assert auth.access_token is None

        # You must authenticate manually
        await auth.authenticate()

        # Now you have tokens
        print(f"Access Token: {auth.access_token}")
```

## Reauthentication Handling

### Smart Reauthentication (Recommended)

The handler provides smart methods that automatically determine when reauthentication is needed, reducing unnecessary API calls:

```python
auth = AuthenticationHandler(
    username="user@example.com",
    password="your_password",
    session=session,
    auth_lifetime_seconds=14400  # 4 hours (default)
)

# Recommended: Use ensure_authenticated() before API calls
# Only reauthenticates if tokens are missing or expired
await auth.ensure_authenticated()

# Make your API call - tokens are guaranteed valid
headers = {"Authorization": auth.access_token}
```

**Key Features:**
- `ensure_authenticated()` checks token validity before authenticating
- Reduces API overhead by skipping unnecessary reauthentication
- Default 4-hour token lifetime (conservative estimate)
- Multiple calls to `ensure_authenticated()` only authenticate once

### Handling API Errors (401/403)

When an API call returns 401 (Unauthorized) or 403 (Forbidden), use the built-in retry handler:

```python
from pythermacell.exceptions import AuthenticationError

# Make API call
response = await session.get(url, headers={"Authorization": auth.access_token})

# Check if we should retry authentication
if auth.should_retry_on_status(response.status):
    try:
        # Automatically reauthenticate
        await auth.handle_auth_retry(response.status)

        # Retry the API call with new token
        response = await session.get(url, headers={"Authorization": auth.access_token})
    except AuthenticationError as e:
        # Reauthentication failed - credentials are invalid
        print(f"Persistent auth failure: {e}")
        raise
```

**Alternative: Manual approach**

You can also handle retries manually using `force_reauthenticate()`:

```python
try:
    # Make API call
    response = await session.get(url, headers={"Authorization": auth.access_token})

    if response.status in (401, 403):
        # Token is invalid - force reauthentication
        await auth.force_reauthenticate()

        # Retry the API call
        response = await session.get(url, headers={"Authorization": auth.access_token})

except Exception as e:
    print(f"API call failed: {e}")
```

### Manual Token Refresh

You can manually trigger reauthentication at any time:

```python
# Force reauthentication (even if tokens appear valid)
await auth.force_reauthenticate()

# Or clear state and reauthenticate manually
auth.clear_authentication()
await auth.authenticate()
```

### Advanced: Using the Force Parameter

The `authenticate()` method accepts a `force` parameter:

```python
# Smart authentication - skip if tokens are valid
await auth.authenticate(force=False)  # Same as ensure_authenticated()

# Force authentication - always reauthenticate
await auth.authenticate(force=True)   # Same as force_reauthenticate()
```

### Checking Authentication State

```python
# Check if currently authenticated
if auth.is_authenticated():
    print("Currently authenticated")
else:
    print("Not authenticated")

# Check if reauthentication is needed
if auth.needs_reauthentication():
    await auth.authenticate()

# Get last authentication timestamp
if auth.last_authenticated_at:
    print(f"Last authenticated at: {auth.last_authenticated_at}")
```

## Session Update Callbacks

### Why Use Callbacks?

When using an injected session, your application needs to know when tokens are updated. The callback mechanism allows you to:
- Synchronize token state across your application
- Update stored credentials
- Trigger dependent operations

### Implementing a Callback

```python
class MyApplication:
    def __init__(self):
        self.access_token = None
        self.user_id = None
        self.session = None

    def handle_session_update(self, handler: AuthenticationHandler) -> None:
        """Called when authentication succeeds."""
        # Store updated tokens
        self.access_token = handler.access_token
        self.user_id = handler.user_id

        # Perform any additional actions
        print(f"Session updated for user: {handler.user_id}")
        self.save_credentials()

    async def initialize(self):
        self.session = ClientSession()

        self.auth = AuthenticationHandler(
            username="user@example.com",
            password="password",
            session=self.session,
            on_session_updated=self.handle_session_update
        )

        # Initial authentication
        await self.auth.authenticate()
        # Callback was invoked, tokens are synchronized

    async def api_call(self):
        # Check if reauthentication needed
        if self.auth.needs_reauthentication():
            await self.auth.authenticate()
            # Callback automatically updates self.access_token

        # Use the current access token
        headers = {"Authorization": self.access_token}
        # ... make API call
```

### Callback Behavior

The callback is invoked:
- ✅ After successful authentication
- ✅ After successful reauthentication
- ❌ NOT on authentication failures
- ❌ NOT during initialization

```python
callback_count = 0

def track_updates(handler: AuthenticationHandler) -> None:
    global callback_count
    callback_count += 1
    print(f"Update #{callback_count}: {handler.access_token}")

auth = AuthenticationHandler(
    username="user@example.com",
    password="password",
    session=session,
    on_session_updated=track_updates
)

# First authentication
await auth.authenticate()  # Callback invoked, count = 1

# Reauthentication
await auth.authenticate()  # Callback invoked, count = 2

# Failed authentication (wrong password)
try:
    await auth.authenticate()
except AuthenticationError:
    pass  # Callback NOT invoked, count still = 2
```

## Best Practices

### 1. Handle Authentication Errors Gracefully

```python
from pythermacell.exceptions import (
    AuthenticationError,
    ThermacellConnectionError,
    ThermacellTimeoutError
)

async def safe_authenticate(auth: AuthenticationHandler) -> bool:
    try:
        await auth.authenticate()
        return True
    except AuthenticationError as e:
        print(f"Invalid credentials: {e}")
        return False
    except ThermacellTimeoutError as e:
        print(f"Request timed out: {e}")
        return False
    except ThermacellConnectionError as e:
        print(f"Connection failed: {e}")
        return False
```

### 2. Use Smart Authentication Methods

Use `ensure_authenticated()` for efficient, automatic reauthentication:

```python
async def make_api_request(auth: AuthenticationHandler):
    # Smart reauthentication - only authenticates if needed
    await auth.ensure_authenticated()

    # Now make your API call with fresh tokens
    # ...
```

For handling API errors, use `handle_auth_retry()`:

```python
from pythermacell.exceptions import AuthenticationError

async def make_api_request_with_retry(auth: AuthenticationHandler, url: str):
    await auth.ensure_authenticated()

    response = await session.get(url, headers={"Authorization": auth.access_token})

    # Automatically retry on 401/403
    if auth.should_retry_on_status(response.status):
        try:
            await auth.handle_auth_retry(response.status)
            response = await session.get(url, headers={"Authorization": auth.access_token})
        except AuthenticationError:
            # Credentials are invalid - cannot recover
            raise

    return response
```

### 3. Secure Credential Storage

Never hardcode credentials. Use environment variables or secure storage:

```python
import os
from pythermacell import AuthenticationHandler

auth = AuthenticationHandler(
    username=os.getenv("THERMACELL_USERNAME"),
    password=os.getenv("THERMACELL_PASSWORD"),
    session=session
)
```

### 4. Configure Auth Lifetime Appropriately

Set `auth_lifetime_seconds` based on your API's token lifetime. The default is 4 hours (14400 seconds):

```python
# Default: 4 hour lifetime (recommended)
auth = AuthenticationHandler(
    username="user@example.com",
    password="password",
    auth_lifetime_seconds=14400  # 4 hours (default)
)

# Conservative: 1 hour lifetime (more frequent reauthentication)
auth = AuthenticationHandler(
    username="user@example.com",
    password="password",
    auth_lifetime_seconds=3600  # 1 hour
)

# Extended: 8 hour lifetime (fewer reauthentication calls)
auth = AuthenticationHandler(
    username="user@example.com",
    password="password",
    auth_lifetime_seconds=28800  # 8 hours
)
```

**Note:** Use `force_reauthenticate()` after 401 errors to handle server-side token invalidation regardless of the configured lifetime.

### 5. Thread Safety

The handler uses an internal lock for thread-safe authentication:

```python
# Safe to call from multiple asyncio tasks
async def task1():
    await auth.authenticate()

async def task2():
    await auth.authenticate()

# Both tasks can safely authenticate concurrently
await asyncio.gather(task1(), task2())
```

## Complete Example

Here's a complete example showing all concepts together:

```python
import asyncio
import os
from aiohttp import ClientSession
from pythermacell import AuthenticationHandler
from pythermacell.exceptions import AuthenticationError

class ThermacellApp:
    def __init__(self):
        self.session = None
        self.auth = None
        self.access_token = None
        self.user_id = None

    def on_auth_updated(self, handler: AuthenticationHandler) -> None:
        """Callback when authentication succeeds."""
        self.access_token = handler.access_token
        self.user_id = handler.user_id
        print(f"✓ Authentication updated for user: {self.user_id}")

    async def initialize(self):
        """Initialize the application."""
        self.session = ClientSession()

        self.auth = AuthenticationHandler(
            username=os.getenv("THERMACELL_USERNAME"),
            password=os.getenv("THERMACELL_PASSWORD"),
            session=self.session,
            on_session_updated=self.on_auth_updated,
            auth_lifetime_seconds=3600
        )

        # Initial authentication
        try:
            await self.auth.authenticate()
            print(f"✓ Initialized successfully")
        except AuthenticationError as e:
            print(f"✗ Authentication failed: {e}")
            raise

    async def make_api_call(self):
        """Example API call with smart reauthentication."""
        # Smart reauthentication - only authenticates if needed
        await self.auth.ensure_authenticated()

        # Use self.access_token for API requests
        headers = {"Authorization": self.access_token}
        # ... make your API call
        print(f"Making API call with token: {self.access_token[:20]}...")

    async def make_api_call_with_retry(self, url: str):
        """Example API call with automatic 401/403 retry handling."""
        await self.auth.ensure_authenticated()

        async with self.session.get(url, headers={"Authorization": self.access_token}) as response:
            # Check if we should retry authentication
            if self.auth.should_retry_on_status(response.status):
                print(f"⟳ Received status {response.status}, attempting reauthentication...")

                try:
                    await self.auth.handle_auth_retry(response.status)

                    # Retry the request with new token
                    async with self.session.get(url, headers={"Authorization": self.access_token}) as retry_response:
                        return await retry_response.json()

                except AuthenticationError as e:
                    print(f"✗ Reauthentication failed: {e}")
                    raise

            return await response.json()

    async def cleanup(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()

async def main():
    app = ThermacellApp()

    try:
        await app.initialize()

        # Make some API calls
        await app.make_api_call()

        # Simulate time passing (in real app, this would be hours later)
        # await asyncio.sleep(3700)  # Just over 1 hour

        # Next API call will automatically reauthenticate
        await app.make_api_call()

    finally:
        await app.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
```

## API Reference

### AuthenticationHandler

#### Constructor Parameters

- `username` (str): User's email address
- `password` (str): User's password
- `base_url` (str, optional): API base URL (default: "https://api.iot.thermacell.com")
- `session` (ClientSession, optional): Injected aiohttp session (default: None)
- `on_session_updated` (Callable, optional): Callback for authentication updates (default: None)
- `auth_lifetime_seconds` (int, optional): Token lifetime in seconds (default: 14400 = 4 hours)

#### Public Attributes

- `access_token` (str | None): Current JWT access token
- `user_id` (str | None): Extracted user ID from ID token
- `last_authenticated_at` (datetime | None): Timestamp of last successful authentication

#### Public Methods

- `async authenticate(*, force: bool = False) -> bool`: Authenticate with the API
  - `force=False` (default): Skip authentication if tokens are valid (smart mode)
  - `force=True`: Always authenticate, even if tokens appear valid
- `async ensure_authenticated() -> None`: **Recommended method** - Only reauthenticates if necessary
- `async force_reauthenticate() -> bool`: Force reauthentication (useful after 401 errors)
- `should_retry_on_status(status_code: int) -> bool`: Check if a status code (401/403) should trigger retry
- `async handle_auth_retry(status_code: int) -> None`: Handle automatic retry for 401/403 errors
  - Raises `AuthenticationError` if reauthentication fails
- `is_authenticated() -> bool`: Check if currently authenticated
- `needs_reauthentication() -> bool`: Check if reauthentication may be needed based on timestamp
- `clear_authentication() -> None`: Clear all authentication state
