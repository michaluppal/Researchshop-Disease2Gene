import { resolve } from 'path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

const repoRoot = resolve(__dirname, '..')

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: resolve(repoRoot, 'app/src/main/index.ts'),
        external: ['better-sqlite3']
      }
    }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: resolve(repoRoot, 'app/src/preload/index.ts')
      }
    }
  },
  renderer: {
    root: resolve(repoRoot, 'app/src/renderer'),
    resolve: {
      alias: {
        '@': resolve(repoRoot, 'app/src/renderer')
      }
    },
    build: {
      rollupOptions: {
        input: resolve(repoRoot, 'app/src/renderer/index.html')
      }
    },
    plugins: [react()],
    css: {
      postcss: {
        plugins: [
          tailwindcss({ config: resolve(repoRoot, 'config/tailwind.config.js') }),
          autoprefixer()
        ]
      }
    }
  }
})
