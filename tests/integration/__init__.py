"""Integration tests for pythermacell library.

These tests use real API credentials from .env file and make actual API calls.
They are marked with @pytest.mark.integration and skipped by default.

To run integration tests:
    pytest tests/integration -v -m integration

Environment variables required in .env:
    THERMACELL_USERNAME: Account email
    THERMACELL_PASSWORD: Account password
    THERMACELL_API_BASE_URL: API base URL (optional, defaults to production)
"""
