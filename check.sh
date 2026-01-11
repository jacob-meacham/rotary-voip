#!/bin/bash
# Run all quality checks for the rotary phone project

set -e  # Exit on first error

echo "Running Black formatter check..."
uv run black --check src tests

echo -e "\nRunning mypy type checker..."
uv run mypy src tests

echo -e "\nRunning pylint..."
uv run pylint src tests

echo -e "\nRunning pytest..."
uv run pytest

echo -e "\n✅ All checks passed!"
