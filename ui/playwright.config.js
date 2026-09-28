import { defineConfig, devices } from '@playwright/test';

// The browser talks only to the UI origin (Vite preview on 4173); Vite
// proxies /api to the real Flask server on 5000.  Both servers are started
// by the global setup in e2e/global-server.js.
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-server.js',
  timeout: 30_000,
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'off'
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ]
});
