import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import buildIdentity from './build-identity.mjs'
import renderCheck from './render-check.mjs'

// The one Node global this file reads, declared here rather than pulling in
// Node's type declarations, which the UI does not otherwise carry.
declare const process: { env: Record<string, string | undefined> }

// Fluid is Mentis's only interface: one page, index.html, served at / and
// /fluid by the Mentis server from dist/. render-check writes
// dist/render-check.js, the Markdown readers the server runs to tell an agent
// what will not render (mentis/conversation/render_check.py).
//
// THE DEV SERVER'S BACKEND IS NAMED, NEVER ASSUMED: `vite` (dev) refuses to
// start without MENTIS_API, e.g. MENTIS_API=http://127.0.0.1:8790 npm run dev
export default defineConfig(({ command, isPreview }) => {
  const target = process.env.MENTIS_API
  if (command === 'serve' && !isPreview && !target)
    throw new Error('Set MENTIS_API to the Mentis server this dev UI should talk to (e.g. http://127.0.0.1:8790). There is no default.')
  return {
    plugins: [react(), buildIdentity(), renderCheck()],
    server: {
      port: 5173,
      ...(target ? { proxy: { '/api': { target, changeOrigin: true }, '/fluid/api': { target, changeOrigin: true } } } : {}),
    },
    build: { outDir: 'dist', emptyOutDir: true },
  }
})
