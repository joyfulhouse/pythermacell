# Integration Tests

This directory contains integration tests that make real API calls to the Thermacell API.

## Prerequisites

1. **Environment Variables**: Create a `.env` file in the project root with your Thermacell credentials:

```bash
# .env
THERMACELL_USERNAME=your_email@example.com
THERMACELL_PASSWORD=your_password
THERMACELL_API_BASE_URL=https://api.iot.thermacell.com

# Optional: Specify a test device node ID
# THERMACELL_TEST_NODE_ID=your_device_node_id
```

2. **Dependencies**: Install dev dependencies including `python-dotenv`:

```bash
pip install -e ".[dev]"
```

## Running Integration Tests

### Run all integration tests:
```bash
pytest tests/integration -v -m integration
```

### Run specific test file:
```bash
pytest tests/integration/test_auth_integration.py -v
```

### Run with coverage:
```bash
pytest tests/integration -v -m integration --cov=pythermacell
```

### Skip slow tests:
```bash
pytest tests/integration -v -m "integration and not slow"
```

### Run only slow tests:
```bash
pytest tests/integration -v -m "integration and slow"
```

## Test Organization

### `test_auth_integration.py`
- Authentication with valid/invalid credentials
- Token management and refresh
- JWT token decoding
- Session callbacks
- Force reauthentication

### `test_client_integration.py`
- Device discovery
- Device state retrieval
- Session management (owned vs injected)
- Multi-device scenarios
- Concurrent operations

### `test_device_control_integration.py` (marked as slow)
- Power control (on/off)
- LED control (power, brightness, color)
- Parameter validation
- Refill cartridge reset
- State refresh after operations

### `test_resilience_integration.py`
- Circuit breaker patterns
- Exponential backoff
- Rate limiting
- Combined resilience patterns
- Error recovery

## Important Notes

### API Rate Limits
The Thermacell API may have rate limits. If you encounter 429 errors:
- Increase delays between test runs
- Use `pytest -k` to run specific tests
- Configure rate limiter settings in tests

### Device State Modification
**WARNING**: Control tests (`test_device_control_integration.py`) will modify your device state:
- Turn devices on/off
- Change LED colors and brightness
- Reset refill counters

These tests attempt to restore original state, but manual verification is recommended.

### Test Duration
- **Authentication tests**: ~10-20 seconds
- **Client tests**: ~20-30 seconds
- **Control tests**: ~60-120 seconds (marked as slow)
- **Resilience tests**: ~30-60 seconds

### Network Requirements
All integration tests require:
- Active internet connection
- Access to `api.iot.thermacell.com`
- Valid Thermacell account with at least one device

## Skipping Integration Tests

Integration tests are marked with `@pytest.mark.integration` and can be skipped:

```bash
# Run only unit tests (skip integration)
pytest tests/ -v -m "not integration"

# Run all tests including integration
pytest tests/ -v
```

## Continuous Integration

For CI/CD pipelines, integration tests should be:
1. Run on a schedule (not every commit)
2. Use dedicated test account credentials
3. Have longer timeouts configured
4. Be isolated from unit tests

Example GitHub Actions workflow:

```yaml
name: Integration Tests
on:
  schedule:
    - cron: '0 0 * * *'  # Daily
  workflow_dispatch:

jobs:
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - run: pip install -e ".[dev]"
      - run: pytest tests/integration -v -m integration
        env:
          THERMACELL_USERNAME: ${{ secrets.THERMACELL_USERNAME }}
          THERMACELL_PASSWORD: ${{ secrets.THERMACELL_PASSWORD }}
```

## Debugging

### Enable debug logging:
```bash
pytest tests/integration -v -m integration --log-cli-level=DEBUG
```

### Run specific test with verbose output:
```bash
pytest tests/integration/test_auth_integration.py::TestAuthenticationIntegration::test_authenticate_with_valid_credentials -vv
```

### Capture print statements:
```bash
pytest tests/integration -v -m integration -s
```

## Contributing

When adding new integration tests:
1. Mark with `@pytest.mark.integration`
2. Mark slow tests (>30s) with `@pytest.mark.slow`
3. Use `integration_config` fixture for credentials
4. Use `test_device` fixture for device operations
5. Clean up device state after tests
6. Add docstrings explaining what's being tested
7. Handle cases where devices aren't available (pytest.skip)

## Troubleshooting

### Authentication failures
- Verify credentials in `.env` file
- Check API base URL is correct
- Ensure account has active subscription

### Device not found
- Set `THERMACELL_TEST_NODE_ID` in `.env`
- Or ensure account has at least one device
- Tests will skip if no devices available

### Timeout errors
- Check network connection
- Increase timeout in test configuration
- API may be experiencing issues

### State inconsistency
- Wait longer between operations (increase `asyncio.sleep`)
- Run tests sequentially instead of parallel
- Manually reset device state between test runs
