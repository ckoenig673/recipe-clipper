import { defineConfig, devices } from '@playwright/test';

/**
 * Deterministic browser checks for GitHub-hosted runners.
 *
 * Keep this configuration separate from playwright.config.ts. The default
 * configuration is the local, live-system suite and may exercise Recipe
 * Clipper's backend, Ollama, OCR, Whisper, and external recipe websites.
 * This CI configuration intentionally selects only specs that mock every API
 * boundary with Playwright routes.
 */
export default defineConfig({
  testDir: './frontend/tests',
  testMatch: [
    'auth-gate-mobile.spec.ts',
    'bulk-recipe-selection.spec.ts',
    'cookbook-grid-wrap.spec.ts'
  ],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: 'list',
  outputDir: 'test-results/ci-playwright',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry'
  },
  webServer: {
    command: 'python -m http.server 4173 --bind 127.0.0.1 --directory frontend',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
    timeout: 30_000
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ]
});
