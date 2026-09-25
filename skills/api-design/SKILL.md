---
name: api-design
description: REST API design patterns for RippleTrace. Use when designing or reviewing endpoints.
---

# API Design — RippleTrace

## Current API Endpoints

```
GET    /api/health                 # Health check
POST   /api/documents/ingest       # Ingest documents
POST   /api/extraction/extract     # Extract policies
GET    /api/graph/overview         # Graph overview (documents as nodes)
GET    /api/graph/doc/:doc_id      # Document sub-graph
GET    /api/graph/neighborhood/:id # Policy neighborhood
POST   /api/simulate               # Run impact simulation
```

## Conventions

### URL Structure
- Resources are plural nouns
- Use kebab-case for multi-word resources
- Use query parameters for filtering

### Status Codes
```
200 OK                    — Successful GET, PATCH
201 Created               — Successful POST (include Location header)
204 No Content            — Successful DELETE
400 Bad Request           — Validation failure
401 Unauthorized          — Missing authentication
403 Forbidden             — Authenticated but not authorized
404 Not Found             — Resource doesn't exist
422 Unprocessable Entity  — Valid JSON, bad data
429 Too Many Requests     — Rate limit exceeded
500 Internal Server Error — Unexpected failure
```

### Response Format
```python
# Success
{"data": {...}}

# Collection
{"data": [...], "meta": {"total": 100}}

# Error
{"error": {"code": "validation_error", "message": "..."}}
```

### Input Validation
```python
from pydantic import BaseModel, Field

class SimulateRequest(BaseModel):
    policy_ids: list[int] = Field(..., min_length=1)
    scenario: str = Field(..., max_length=500)
```

### Rate Limiting
- Add rate limiting before production deployment
- Use slowapi or custom middleware
- Stricter limits on expensive operations (simulation, extraction)

## Design Checklist

- [ ] Resource URL follows conventions
- [ ] Correct HTTP method used
- [ ] Appropriate status codes
- [ ] Input validated with Pydantic
- [ ] Error responses follow standard format
- [ ] Authentication required (or marked public)
- [ ] Rate limiting configured
