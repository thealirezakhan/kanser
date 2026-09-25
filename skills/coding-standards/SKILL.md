---
name: coding-standards
description: Coding conventions for RippleTrace. Python backend + React/Vite frontend.
---

# Coding Standards — RippleTrace

## Python Backend

### Style
- Follow PEP 8
- Use type hints on all public functions
- Use `snake_case` for functions/variables, `PascalCase` for classes
- Max function length: 50 lines
- Max file length: 400 lines

### Immutability
```python
# BAD: Mutation
def update_config(config, key, value):
    config[key] = value
    return config

# GOOD: Return new dict
def update_config(config, key, value):
    return {**config, key: value}
```

### Error Handling
```python
# BAD
async def get_data():
    return await fetch_something()

# GOOD
async def get_data():
    try:
        return await fetch_something()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch data: %s", e)
        raise DataFetchError("Unable to retrieve data") from e
```

### FastAPI Patterns
- Use Pydantic models for request/response
- Use dependency injection for database connections
- Return proper HTTP status codes
- Use `async def` for I/O-bound routes

## React/Vite Frontend

### Style
- Use functional components only
- Use `camelCase` for variables/functions, `PascalCase` for components
- Max component length: 200 lines
- One component per file

### Component Pattern
```jsx
// GOOD: Functional component with clear props
function GraphView({ graphData, filters, onNodeClick }) {
  // hooks first
  // handlers
  // render
}
```

### Immutability
```javascript
// BAD
items.push(newItem)

// GOOD
const newItems = [...items, newItem]
```

### State Updates
```javascript
// BAD
setCount(count + 1)

// GOOD
setCount(prev => prev + 1)
```

## File Organization

```
rippletrace/
├── backend/
│   ├── main.py          # FastAPI app
│   ├── db.py            # Database connections
│   ├── ingestion.py     # Document ingestion
│   ├── extraction.py    # Policy extraction
│   ├── graph.py         # Graph operations
│   ├── propagation.py   # Impact simulation
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── components/
│   └── package.json
```

## Comments

- Explain WHY, not WHAT
- Use JSDoc for public JavaScript functions
- Use docstrings for public Python functions
- No TODO without ticket reference
