---
name: backend-patterns
description: Python/FastAPI backend patterns for RippleTrace. Use when building or reviewing API routes and data access.
---

# Backend Patterns — RippleTrace

## Stack

- Python 3.x
- FastAPI
- PostgreSQL (asyncpg)
- Neo4j
- OpenAI API (via Ollama)
- Pydantic for validation

## API Design

### RESTful Endpoints
```
GET    /api/health              # Health check
GET    /api/graph/overview      # Graph overview
GET    /api/graph/doc/:id       # Document graph
GET    /api/graph/neighborhood/:id  # Policy neighborhood
POST   /api/documents/ingest    # Ingest documents
POST   /api/simulate            # Run impact simulation
```

### Response Format
```python
# Success
{"data": {...}}

# Error
{"error": {"code": "not_found", "message": "Document not found"}}
```

## Database Patterns

### Connection Pooling
```python
# asyncpg pool (already implemented in db.py)
pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=2, max_size=10)
```

### Parameterized Queries
```python
# GOOD
rows = await conn.fetch("SELECT * FROM documents WHERE id = $1", doc_id)

# BAD — SQL injection risk
rows = await conn.fetch(f"SELECT * FROM documents WHERE id = {doc_id}")
```

### Neo4j Queries
```python
# GOOD: Parameterized
result = await session.run("MATCH (n) WHERE n.id = $id RETURN n", id=node_id)

# BAD — Cypher injection
result = await session.run(f"MATCH (n) WHERE n.id = '{node_id}' RETURN n")
```

## Error Handling

```python
from fastapi import HTTPException

@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: int):
    try:
        doc = await fetch_document(doc_id)
    except Exception as e:
        logger.error("Failed to fetch document %d: %s", doc_id, e)
        raise HTTPException(status_code=504, detail="Database unavailable")
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"data": doc}
```

## Logging

```python
import logging

logger = logging.getLogger(__name__)

# GOOD
logger.info("Ingested document %s", filename)
logger.error("Extraction failed for chunk %d", chunk_id, exc_info=True)

# BAD
print("Ingested document")  # Don't use print
```

## Environment Variables

```python
import os

DATABASE_URL = os.environ["DATABASE_URL"]
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")
```
