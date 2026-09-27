import { defineConfig } from '@playwright/test'

const baseURL = 'http://127.0.0.1:__PORT__'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: 'list',
  use: { baseURL, trace: 'retain-on-failure' },
  webServer: {
    command: 'node server.mjs',
    env: { PORT: '__PORT__' },
    url: baseURL,
    reuseExistingServer: false,
  },
})
