#!/bin/bash
# Run integration tests with Docker SIPp server

set -e

echo "Starting SIPp test server..."
docker compose -f docker-compose.test.yml up -d

# Wait for SIPp to be ready
echo "Waiting for SIPp server to start..."
sleep 3

echo "Running integration tests..."
uv run pytest tests/test_sip_integration.py -v "$@"

echo "Stopping SIPp test server..."
docker compose -f docker-compose.test.yml down

echo "Integration tests complete!"
