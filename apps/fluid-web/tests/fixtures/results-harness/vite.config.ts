/* The harness's own build, separate from the application's: it builds this
 * directory alone into dist/results-harness (ignored by Git), so the chooser
 * can be driven in a browser without the app, a server or a Brain.
 *
 *   npx vite build --config tests/fixtures/results-harness/vite.config.ts
 */
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  base: './',
  plugins: [react()],
  build: {
    outDir: fileURLToPath(new URL('../../../dist/results-harness/', import.meta.url)),
    emptyOutDir: true,
  },
})
