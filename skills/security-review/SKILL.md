---
name: security-review
description: Security review checklist for RippleTrace. Use when handling user input, secrets, API endpoints, or sensitive data.
---

# Security Review — RippleTrace

## When to Activate

- Implementing authentication or authorization
- Handling user input or file uploads
- Creating new API endpoints
- Working with secrets or credentials
- Storing or transmitting sensitive data

## Project-Specific Security

### Secrets Management
```python
# BAD: Hardcoded secrets
DATABASE_URL = "postgresql://rippletrace:rippletrace@localhost:5432/rippletrace"

# GOOD: Environment variables
import os
DATABASE_URL = os.environ["DATABASE_URL"]
```

- `.env` is in `.gitignore` — good
- `.env.example` exists for reference — good
- Never commit `.env` files

### Input Validation (FastAPI)
```python
from pydantic import BaseModel, EmailStr

class DocumentInput(BaseModel):
    filename: str
    content: str

    class Config:
        max_anystr_length = 1_000_000  # 1MB max
```

### SQL Injection Prevention
- Use parameterized queries (asyncpg supports `$1, $2` params)
- Never use f-strings in SQL

### CORS
```python
# Current: allows all origins (fine for dev, restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Neo4j Cypher Injection
- Use parameterized Cypher queries
- Never concatenate user input into queries

### API Key Exposure
- OpenAI API key must come from environment
- Never log API keys

## Security Checklist

- [ ] No hardcoded secrets
- [ ] All inputs validated with Pydantic
- [ ] SQL injection prevention (parameterized queries)
- [ ] CORS restricted in production
- [ ] Rate limiting on API endpoints
- [ ] Error messages don't leak sensitive data
- [ ] No secrets in logs
- [ ] Dependencies up to date (`pip audit`)

## Pre-Deployment Security Checklist

- [ ] CORS origins restricted
- [ ] Rate limiting enabled
- [ ] HTTPS enforced
- [ ] Security headers configured
- [ ] No sensitive data in logs
- [ ] Database credentials rotated
