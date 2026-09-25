---
name: frontend-patterns
description: React/Vite frontend patterns for RippleTrace. Use when building or reviewing React components.
---

# Frontend Patterns — RippleTrace

## Stack

- React 18.3
- Vite 6
- Tailwind CSS 3.4
- @xyflow/react (React Flow) for knowledge graph
- lucide-react for icons

## Component Patterns

### Composition
```jsx
<Card>
  <CardHeader>Title</CardHeader>
  <CardBody>Content</CardBody>
</Card>
```

### Custom Hooks
```jsx
function useGraphData(overviewUrl) {
  const [data, setData] = useState({ nodes: [], edges: [] })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(overviewUrl)
      .then(r => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }, [overviewUrl])

  return { data, loading }
}
```

### Memoization
```jsx
const sortedNodes = useMemo(() => {
  return [...nodes].sort((a, b) => a.label.localeCompare(b.label))
}, [nodes])

const handleClick = useCallback((node) => {
  onNodeClick(node)
}, [onNodeClick])
```

## React Flow Patterns

### Node Types
```jsx
const nodeTypes = {
  Document: DocumentNode,
  Chunk: ChunkNode,
  PolicyElement: PolicyNode,
}
```

### Custom Node
```jsx
function PolicyNode({ data }) {
  return (
    <div className="px-4 py-2 rounded-lg shadow-md bg-white border">
      <div className="text-sm font-medium">{data.label}</div>
    </div>
  )
}
```

## Error Boundaries
```jsx
class ErrorBoundary extends React.Component {
  state = { hasError: false }

  static getDerivedStateFromError(error) {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) {
      return <div className="p-4 text-red-600">Something went wrong.</div>
    }
    return this.props.children
  }
}
```

## Accessibility

- Use semantic HTML (`<nav>`, `<main>`, `<header>`)
- Add `aria-label` to icon buttons
- Ensure keyboard navigation works
- Use `data-testid` for testing selectors

## Responsive Design

- Use Tailwind responsive utilities (`sm:`, `md:`, `lg:`)
- Mobile-first approach
- Test at 320px, 768px, 1024px, 1440px
