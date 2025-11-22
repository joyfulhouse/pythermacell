# Testing Guide

## Environment Setup

### Credentials Configuration

The project uses environment variables to store sensitive testing credentials. These are loaded from a `.env` file which is **excluded from version control** for security.

#### Quick Setup

1. **Copy the example file**:
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your credentials**:
   ```bash
   # Open in your preferred editor
   nano .env
   # or
   code .env
   ```

3. **Add your credentials**:
   ```ini
   THERMACELL_USERNAME=your_email@example.com
   THERMACELL_PASSWORD=your_password
   ```

#### Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `THERMACELL_API_BASE_URL` | Yes | API base URL | `https://api.iot.thermacell.com` |
| `THERMACELL_API_VERSION` | Yes | API version | `v1` |
| `THERMACELL_USERNAME` | Yes | Thermacell account email | - |
| `THERMACELL_PASSWORD` | Yes | Thermacell account password | - |
| `THERMACELL_TEST_NODE_ID` | No | Specific device ID for testing | Auto-discovered |
| `THERMACELL_OAUTH_URL` | No | OAuth base URL (future use) | - |
| `THERMACELL_CLIENT_ID` | No | OAuth client ID (future use) | - |

#### Security Notes

⚠️ **Important**: The `.env` file contains sensitive credentials and is automatically excluded from git via `.gitignore`.

**Never commit**:
- `.env` - Your actual credentials
- Any file containing real passwords or API keys

**Safe to commit**:
- `.env.example` - Template with placeholder values
- This documentation

---

## Running Tests

### Unit Tests

```bash
# Run all unit tests
pytest tests/

# Run with coverage
pytest tests/ --cov=pythermacell --cov-report=term-missing

# Run specific test file
pytest tests/test_client.py -v
```

### Integration Tests

Integration tests make **real API calls** to the Thermacell API using credentials from `.env`.

```bash
# Run integration tests (requires .env with credentials)
pytest tests/integration/ -v

# Run specific integration test
pytest tests/integration/test_real_api.py::test_authentication -v
```

**Prerequisites**:
1. Valid `.env` file with working credentials
2. Active internet connection
3. At least one Thermacell LIV device associated with account

### Manual Testing

For manual testing and exploration:

```bash
# Python interactive session with auto-loaded credentials
python tests/manual/interactive_test.py
```

Example session:
```python
>>> from pythermacell import ThermacellClient
>>> import asyncio
>>> import os

>>> # Credentials auto-loaded from .env
>>> username = os.getenv("THERMACELL_USERNAME")
>>> password = os.getenv("THERMACELL_PASSWORD")

>>> async def test():
...     async with ThermacellClient(username, password) as client:
...         devices = await client.get_devices()
...         print(f"Found {len(devices)} devices")
...         for device in devices:
...             print(f"- {device.name} ({device.node_id})")

>>> asyncio.run(test())
```

---

## Test Structure

```
tests/
├── __init__.py
├── test_client.py              # Unit tests for client
├── test_auth.py                # Unit tests for authentication
├── test_devices.py             # Unit tests for device management
├── conftest.py                 # Pytest fixtures and configuration
│
├── integration/                # Real API integration tests
│   ├── __init__.py
│   ├── test_real_api.py       # Complete API integration tests
│   ├── test_ota_updates.py    # OTA update workflow tests
│   └── test_automation.py     # Automation tests (when implemented)
│
└── manual/                     # Manual testing scripts
    ├── interactive_test.py    # Interactive Python session
    ├── discover_devices.py    # Device discovery script
    └── test_ota_check.py      # Test OTA availability check
```

---

## Loading Environment Variables

### In Python Code

```python
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Access variables
username = os.getenv("THERMACELL_USERNAME")
password = os.getenv("THERMACELL_PASSWORD")
base_url = os.getenv("THERMACELL_API_BASE_URL", "https://api.iot.thermacell.com")
```

### In Tests

Use pytest fixtures (defined in `conftest.py`):

```python
def test_authentication(api_credentials):
    """Test authentication with real credentials."""
    username, password = api_credentials
    # ... test code
```

### Example conftest.py

```python
import os
import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@pytest.fixture
def api_credentials():
    """Load API credentials from environment."""
    username = os.getenv("THERMACELL_USERNAME")
    password = os.getenv("THERMACELL_PASSWORD")

    if not username or not password:
        pytest.skip("THERMACELL_USERNAME and THERMACELL_PASSWORD required in .env")

    return username, password

@pytest.fixture
def api_base_url():
    """Load API base URL from environment."""
    return os.getenv("THERMACELL_API_BASE_URL", "https://api.iot.thermacell.com")

@pytest.fixture
def test_node_id():
    """Load test node ID from environment (optional)."""
    return os.getenv("THERMACELL_TEST_NODE_ID")
```

---

## Integration Test Examples

### Example: Test Authentication

```python
import pytest
from pythermacell import ThermacellClient

@pytest.mark.asyncio
async def test_authentication(api_credentials, api_base_url):
    """Test authentication with real API."""
    username, password = api_credentials

    async with ThermacellClient(username, password, base_url=api_base_url) as client:
        # This implicitly tests authentication
        devices = await client.get_devices()
        assert isinstance(devices, list)
```

### Example: Test Device Discovery

```python
@pytest.mark.asyncio
async def test_device_discovery(api_credentials, api_base_url):
    """Test discovering devices."""
    username, password = api_credentials

    async with ThermacellClient(username, password, base_url=api_base_url) as client:
        devices = await client.get_devices()

        assert len(devices) > 0, "No devices found in account"

        for device in devices:
            assert device.node_id
            assert device.name
            print(f"Found device: {device.name} ({device.node_id})")
```

### Example: Test OTA Check

```python
@pytest.mark.asyncio
async def test_ota_update_check(api_credentials, api_base_url, test_node_id):
    """Test checking for firmware updates."""
    if not test_node_id:
        pytest.skip("THERMACELL_TEST_NODE_ID required")

    username, password = api_credentials

    async with ThermacellClient(username, password, base_url=api_base_url) as client:
        update_info = await client.check_firmware_update(test_node_id)

        assert "ota_available" in update_info
        assert isinstance(update_info["ota_available"], bool)

        if update_info["ota_available"]:
            assert "fw_version" in update_info
            assert "ota_job_id" in update_info
            print(f"Update available: {update_info['fw_version']}")
        else:
            print("No update available - device is up to date")
```

---

## CI/CD Configuration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -e .
        pip install pytest pytest-asyncio pytest-cov python-dotenv

    - name: Run unit tests
      run: pytest tests/ --ignore=tests/integration -v --cov

    - name: Run integration tests (if credentials available)
      env:
        THERMACELL_USERNAME: ${{ secrets.THERMACELL_USERNAME }}
        THERMACELL_PASSWORD: ${{ secrets.THERMACELL_PASSWORD }}
      run: |
        if [ -n "$THERMACELL_USERNAME" ]; then
          pytest tests/integration/ -v
        else
          echo "Skipping integration tests - no credentials"
        fi
```

**GitHub Secrets Setup**:
1. Go to repository Settings → Secrets and variables → Actions
2. Add secrets:
   - `THERMACELL_USERNAME`
   - `THERMACELL_PASSWORD`

---

## Troubleshooting

### `.env` file not found

**Error**: `FileNotFoundError: .env file not found`

**Solution**:
```bash
cp .env.example .env
# Edit .env with your credentials
```

### Credentials not loading

**Error**: `THERMACELL_USERNAME not set`

**Solution**:
1. Verify `.env` file exists in project root
2. Check variable names match exactly (case-sensitive)
3. Ensure `python-dotenv` is installed: `pip install python-dotenv`
4. Call `load_dotenv()` before accessing variables

### Integration tests failing

**Error**: `401 Unauthorized` or `Authentication failed`

**Solution**:
1. Verify credentials are correct in `.env`
2. Test login at https://rainmaker.espressif.com/
3. Check if account has 2FA enabled (not currently supported)
4. Verify API base URL is correct

### No devices found

**Error**: `assert len(devices) > 0` fails

**Solution**:
1. Ensure at least one device is set up in your account
2. Log in to mobile app to verify device is visible
3. Check device is powered on and connected
4. Verify device is associated with the test account

---

## Best Practices

### Security
- ✅ **Never commit** `.env` files
- ✅ Use `.env.example` for documentation
- ✅ Use GitHub Secrets for CI/CD
- ✅ Rotate credentials periodically
- ❌ **Never hardcode** credentials in code

### Testing
- ✅ Write unit tests for all client methods
- ✅ Use integration tests for critical workflows
- ✅ Mock external API calls in unit tests
- ✅ Use fixtures for common setup
- ❌ Don't run integration tests in parallel (may hit rate limits)

### Documentation
- ✅ Document required environment variables
- ✅ Provide working examples
- ✅ Include troubleshooting section
- ✅ Keep `.env.example` up to date

---

## Dependencies

Required packages for testing:

```bash
pip install pytest pytest-asyncio pytest-cov python-dotenv aiohttp
```

Or install all dev dependencies:

```bash
pip install -e ".[dev]"
```

---

**Last Updated**: 2025-11-17
**Status**: Ready for testing
