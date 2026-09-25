---
name: tdd-workflow
description: TDD workflow for RippleTrace. Use when writing new features, fixing bugs, or refactoring code.
---

# TDD Workflow — RippleTrace

## When to Activate

- Writing new features or functionality
- Fixing bugs or issues
- Refactoring existing code
- Adding API endpoints
- Creating new components

## Test Runner

This project uses:
- **Backend**: pytest (Python)
- **Frontend**: No test framework yet — add Vitest for React component tests

## Backend TDD (pytest)

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=term-missing

# Run specific test
pytest tests/test_extraction.py -v
```

### Test File Convention
```
backend/
├── tests/
│   ├── test_extraction.py
│   ├── test_ingestion.py
│   └── test_graph.py
```

### Pattern
```python
import pytest
from extraction import extract_policies

def test_extract_policies_returns_list():
    result = extract_policies("sample text")
    assert isinstance(result, list)

def test_extract_policies_empty_input():
    result = extract_policies("")
    assert result == []
```

## Frontend TDD (add Vitest)

```bash
# Add Vitest
npm install -D vitest @testing-library/react @testing-library/jest-dom

# Run tests
npx vitest
```

## TDD Cycle (MANDATORY)

```
RED → GREEN → REFACTOR → REPEAT
```

1. **RED**: Write a failing test FIRST
2. **GREEN**: Write minimal code to pass
3. **REFACTOR**: Improve code while keeping tests green
4. **REPEAT**: Continue until feature complete

## Coverage Requirements

| Code Type | Minimum |
|-----------|---------|
| Standard code | 80% |
| Security-critical code | 100% |

## Test Types to Include

- **Unit Tests**: Individual functions
- **Edge Cases**: Empty, null, max values
- **Error Conditions**: Invalid inputs, network failures
- **Integration Tests**: API endpoints, database operations
