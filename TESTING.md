# Testing Guide

## Unit Tests

Run all unit tests (default):
```bash
uv run pytest
# or
./check.sh
```

All unit tests use mock implementations (InMemorySIPClient, MockGPIO) and don't require real hardware or SIP servers.

## Integration Tests

### Docker-based Integration Tests

Integration tests use Docker to run a SIPp server for testing.

**Prerequisites**:
- Docker
- docker-compose

**Run integration tests**:
```bash
./run_integration_tests.sh
```

Or manually:
```bash
# Start SIPp test server
docker-compose -f docker-compose.test.yml up -d

# Run tests
uv run pytest tests/test_sip_integration.py -v -m integration

# Stop server
docker-compose -f docker-compose.test.yml down
```

### Real SIP Provider Tests

Test against your actual SIP provider (e.g., voip.ms):

1. Create a `.env.test` file (NOT committed to git):
```bash
SIP_SERVER=vancouver.voip.ms
SIP_PORT=5060
SIP_USERNAME=123456_test
SIP_PASSWORD=your_password_here
SIP_DID=+15551234567
```

2. Run real provider tests:
```bash
source .env.test
uv run python -m tests.manual.test_real_sip
```

**Note**: These tests will make actual SIP calls and may incur charges from your provider.

## Test Organization

```
tests/
├── test_*.py              # Unit tests (fast, no external deps)
├── test_sip_integration.py # Docker integration tests
└── manual/
    └── test_real_sip.py    # Manual tests with real SIP provider
```

## Continuous Integration

GitHub Actions / CI should run:
```bash
# Unit tests only (fast)
uv run pytest -m 'not integration'

# Integration tests (requires Docker)
./run_integration_tests.sh
```

Real SIP provider tests should be run manually during development.
