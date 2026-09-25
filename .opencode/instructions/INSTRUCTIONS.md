# ECC - OpenCode Instructions

This document consolidates the core rules and guidelines for RippleTrace development.

## Security Guidelines (CRITICAL)

### Mandatory Security Checks

Before ANY commit:
- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] All user inputs validated
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (sanitized HTML)
- [ ] Authentication/authorization verified
- [ ] Error messages don't leak sensitive data

### Secret Management

```python
# NEVER: Hardcoded secrets
DATABASE_URL = "postgresql://..."

# ALWAYS: Environment variables
import os
DATABASE_URL = os.environ["DATABASE_URL"]
```

### Security Response Protocol

If security issue found:
1. STOP immediately
2. Use **security-reviewer** agent
3. Fix CRITICAL issues before continuing
4. Review entire codebase for similar issues

---

## Coding Style

### Immutability (CRITICAL)

**Python:**
```python
# WRONG: Mutation
def update(config, key, value):
    config[key] = value
    return config

# CORRECT: Immutability
def update(config, key, value):
    return {**config, key: value}
```

**JavaScript:**
```javascript
// WRONG: Mutation
items.push(newItem)

// CORRECT: Immutability
const newItems = [...items, newItem]
```

### File Organization

MANY SMALL FILES > FEW LARGE FILES:
- High cohesion, low coupling
- Python: 400 lines max
- React components: 200 lines max

### Error Handling

ALWAYS handle errors comprehensively:

```python
try:
    result = await risky_operation()
    return result
except SpecificError as e:
    logger.error("Operation failed: %s", e)
    raise UserFacingError("Detailed message") from e
```

### Input Validation

ALWAYS validate user input:

```python
from pydantic import BaseModel, Field

class CreateInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=2000)
```

---

## Testing Requirements

### Minimum Test Coverage: 80%

### Test-Driven Development

MANDATORY workflow:
1. Write test first (RED)
2. Run test - it should FAIL
3. Write minimal implementation (GREEN)
4. Run test - it should PASS
5. Refactor (IMPROVE)
6. Verify coverage (80%+)

---

## Git Workflow

### Commit Message Format

```
<type>: <description>

<optional body>
```

Types: feat, fix, refactor, docs, test, chore, perf

---

## Agent Orchestration

### Available Agents

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| planner | Implementation planning | Complex features |
| architect | System design | Architecture decisions |
| tdd-guide | Test-driven development | New features, bugs |
| code-reviewer | Code review | After writing code |
| security-reviewer | Security analysis | Before commits |
| build-error-resolver | Fix build errors | When build fails |
| e2e-runner | E2E testing | Critical user flows |
| refactor-cleaner | Dead code cleanup | Code maintenance |
| python-reviewer | Python code review | Python changes |
| database-reviewer | Database optimization | SQL/schema changes |

### Immediate Agent Usage

1. Complex feature requests → Use **planner** agent
2. Code just written → Use **code-reviewer** agent
3. Bug fix or new feature → Use **tdd-guide** agent
4. Architectural decision → Use **architect** agent

---

## Performance Optimization

### Model Selection Strategy

**Haiku** (fast, cheap):
- Lightweight agents, frequent invocation

**Sonnet** (best coding):
- Main development work
- Complex coding tasks

**Opus** (deepest reasoning):
- Complex architectural decisions
- Maximum reasoning requirements

---

## Common Patterns

### API Response Format

```python
# Success
{"data": {...}}

# Error
{"error": {"code": "not_found", "message": "..."}}
```

---

## OpenCode-Specific Notes

Since OpenCode does not support hooks, the following must be done manually:

### After Writing/Editing Code
- Run formatter on modified files
- Run type checker
- Check for print/console.log statements

### Before Committing
- Run security checks
- Verify no secrets in code
- Run full test suite

### Commands Available

- `/plan` - Create implementation plan
- `/tdd` - Enforce TDD workflow
- `/code-review` - Review code changes
- `/security` - Run security review
- `/build-fix` - Fix build errors
- `/e2e` - Generate E2E tests
- `/refactor-clean` - Remove dead code
- `/orchestrate` - Multi-agent workflow
- `/verify` - Run verification loop
- `/checkpoint` - Save progress
- `/learn` - Extract patterns
- `/eval` - Evaluate against criteria

---

## Success Metrics

You are successful when:
- All tests pass (80%+ coverage)
- No security vulnerabilities
- Code is readable and maintainable
- Performance is acceptable
- User requirements are met
