---
name: e2e-testing
description: Playwright E2E testing patterns for RippleTrace. Use when writing or running browser-based tests.
---

# E2E Testing — RippleTrace

## Setup

Playwright is configured via MCP in `.opencode/opencode.json`:
```json
"playwright": {
  "type": "local",
  "command": ["npx", "@playwright/mcp@latest"],
  "enabled": true
}
```

## Test Commands

```bash
# Install Playwright
npm install -D @playwright/test

# Run all E2E tests
npx playwright test

# Run in headed mode
npx playwright test --headed

# Debug with inspector
npx playwright test --debug

# Generate test code
npx playwright codegen http://localhost:3000
```

## Page Object Model

```typescript
// pages/GraphPage.ts
import { Page, Locator } from '@playwright/test'

export class GraphPage {
  readonly page: Page
  readonly searchInput: Locator
  readonly graphCanvas: Locator

  constructor(page: Page) {
    this.page = page
    this.searchInput = page.locator('[data-testid="search-input"]')
    this.graphCanvas = page.locator('.react-flow')
  }

  async goto() {
    await this.page.goto('/')
    await this.page.waitForLoadState('networkidle')
  }
}
```

## Critical User Flows to Test

1. **Document Ingestion**: Upload → Process → Graph updated
2. **Graph Navigation**: Click node → View details → Navigate back
3. **Impact Simulation**: Select policy → Run simulation → View report
4. **Search**: Type query → See filtered results

## Best Practices

- Use `data-testid` selectors
- Wait for network idle, not arbitrary timeouts
- Each test should be independent
- Screenshot on failure
