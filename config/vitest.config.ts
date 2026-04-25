import { defineConfig } from 'vitest/config'
import { resolve } from 'path'

export default defineConfig({
  root: resolve(__dirname, '..'),
  test: {
    environment: 'node',
    include: ['app/**/*.test.ts', 'app/**/*.test.tsx'],
  },
})
