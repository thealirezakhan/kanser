---
name: verification-loop
description: Verification system for RippleTrace. Use before committing or creating PRs.
---

# Verification Loop — RippleTrace

## Verification Phases

### Phase 1: Backend Checks
```bash
# Type check
cd backend && python -m py_compile *.py

# Lint
ruff check backend/

# Tests
cd backend && pytest -v
```

### Phase 2: Frontend Checks
```bash
cd frontend

# Build
npm run build

# (Add lint/test when configured)
```

### Phase 3: Security Scan
```bash
# Check for hardcoded secrets
grep -rn "api_key\|password\|secret" --include="*.py" --include="*.js" --include="*.jsx" . 2>/dev/null

# Check for console.log
grep -rn "console.log" frontend/src/ 2>/dev/null
```

### Phase 4: Docker Build
```bash
docker compose build
```

## Verification Report

```
VERIFICATION REPORT
==================

Backend Lint:    [PASS/FAIL]
Backend Tests:   [PASS/FAIL]
Frontend Build:  [PASS/FAIL]
Security Scan:   [PASS/FAIL]
Docker Build:    [PASS/FAIL]

Overall: [READY/NOT READY]
```

## Continuous Mode

Run verification after:
- Completing each function
- Finishing a component
- Before moving to next task

---

**TIP**: Create checkpoints at natural breakpoints.
