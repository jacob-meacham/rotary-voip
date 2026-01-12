#!/bin/bash
# Run all quality checks for the rotary phone project

# Track if any check fails
exit_code=0

echo "Running Black formatter check..."
if ! uv run black --check src tests; then
    exit_code=1
fi

echo -e "\nRunning mypy type checker..."
if ! uv run mypy src/rotary_phone; then
    exit_code=1
fi

echo -e "\nRunning pylint..."
if ! uv run pylint src/rotary_phone; then
    exit_code=1
fi

echo -e "\nRunning pytest..."
if ! uv run pytest; then
    exit_code=1
fi

if [ $exit_code -eq 0 ]; then
    echo -e "\n✅ All checks passed!"
else
    echo -e "\n❌ Some checks failed!"
fi

exit $exit_code
