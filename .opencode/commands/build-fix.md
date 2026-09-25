---
description: Fix build and type errors with minimal changes
agent: build-error-resolver
subtask: true
---

# Build Fix Command

Fix build and type errors with minimal changes: $ARGUMENTS

## Your Task

1. **Run type check**: `npx tsc --noEmit` (or `ruff check` / `mypy` for Python)
2. **Collect all errors**
3. **Fix errors one by one** with minimal changes
4. **Verify each fix** doesn't introduce new errors
5. **Run final check** to confirm all errors resolved

## Approach

### DO:
- PASS: Fix type errors with correct types
- PASS: Add missing imports
- PASS: Fix syntax errors
- PASS: Make minimal changes
- PASS: Preserve existing behavior
- PASS: Run type checker after each change

### DON'T:
- FAIL: Refactor code
- FAIL: Add new features
- FAIL: Change architecture
- FAIL: Use `any` type (unless absolutely necessary)
- FAIL: Add `@ts-ignore` comments
- FAIL: Change business logic

## Verification Steps

After fixes:
1. Type check passes with 0 errors
2. `npm run build` / `python -m py_compile` succeeds
3. Tests still pass

---

**IMPORTANT**: Focus on fixing errors only. No refactoring, no improvements, no architectural changes. Get the build green with minimal diff.
