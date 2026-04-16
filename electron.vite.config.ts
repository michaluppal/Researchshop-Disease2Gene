import { resolve } from 'path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

// Sources live under app/src/{main,preload,renderer}. Configs + package.json
// stay at repo root so electron-vite + electron-builder find them in CWD.
export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: resolve(__dirname, 'app/src/main/index.ts'),
        external: ['better-sqlite3']
      }
    }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: resolve(__dirname, 'app/src/preload/index.ts')
      }
    }
  },
  renderer: {
    root: resolve(__dirname, 'app/src/renderer'),
    resolve: {
      alias: {
        '@': resolve(__dirname, 'app/src/renderer')
      }
    },
    build: {
      rollupOptions: {
        input: resolve(__dirname, 'app/src/renderer/index.html')
      }
    },
    plugins: [react()],
    css: {
      postcss: {
        plugins: [tailwindcss, autoprefixer]
      }
    }
  }
})
