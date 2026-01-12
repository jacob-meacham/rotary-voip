#!/bin/bash
# Run all quality checks for the rotary phone project

set -e  # Exit on first error

echo "Running Black formatter check..."
uv run black --check src tests

echo -e "\nRunning mypy type checker..."
uv run mypy src/rotary_phone

echo -e "\nRunning pylint..."
uv run pylint src/rotary_phone

echo -e "\nRunning pytest..."
uv run pytest

echo -e "\n✅ All checks passed!"
