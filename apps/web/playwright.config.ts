import { defineConfig } from '@playwright/test';

// The dev server points its API base at a distinct host that does not exist, so every API
// call is intercepted by page.route in the tests and never collides with a page route. Auth
// is forced dark (empty Cognito vars, set here so they win over any local .env.local): the
// suite exercises the open app surfaces, not the login gate. Setting the vars empty means Next
// does not load them from .env, so a developer's local auth config never turns the gate on
// under test.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  use: { baseURL: 'http://localhost:3100' },
  webServer: {
    command: 'npm run dev -- --port 3100',
    url: 'http://localhost:3100',
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_API_BASE: 'http://localhost:9999',
      NEXT_PUBLIC_COGNITO_USER_POOL_ID: '',
      NEXT_PUBLIC_COGNITO_CLIENT_ID: '',
    },
  },
});
