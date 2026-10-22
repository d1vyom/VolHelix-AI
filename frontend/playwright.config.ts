import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', timeout: 30000, workers: 1,
  use: { baseURL: 'http://127.0.0.1:3107', headless: true },
  webServer: { command: 'node tests/dev-server.mjs', url: 'http://127.0.0.1:3107', reuseExistingServer: false, timeout: 120000 },
});
