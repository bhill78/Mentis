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
  /* A READ-ONLY PREVIEW (MENTIS_READONLY=1): the dev UI may read a live Brain
     through its own API, and nothing else. Every request that is not a read
     is answered here, 403, and never forwarded -- the Brain sees reads only.
     The page is told too (VITE_MENTIS_READONLY), so it offers no writing. */
  const readOnly = process.env.MENTIS_READONLY === '1'
  const guard = readOnly
    ? { configure: (proxy: { on: (e: 'proxyReq', fn: (pr: { destroy: () => void }, req: { method?: string; url?: string }, res: { writeHead: (n: number, h: Record<string, string>) => void; end: (b: string) => void }) => void) => void }) => {
        proxy.on('proxyReq', (pr, req, res) => {
          if (['GET', 'HEAD', 'OPTIONS'].includes((req.method ?? 'GET').toUpperCase())) return
          pr.destroy()
          res.writeHead(403, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: `read-only preview: ${req.method} ${req.url} was not sent`, kind: 'ReadOnlyPreview' }))
        })
      } }
    : {}
  return {
    plugins: [react(), buildIdentity(), renderCheck()],
    define: readOnly ? { 'import.meta.env.VITE_MENTIS_READONLY': JSON.stringify('1') } : {},
    server: {
      port: 5173,
      ...(target ? { proxy: { '/api': { target, changeOrigin: true, ...guard }, '/fluid/api': { target, changeOrigin: true, ...guard } } } : {}),
    },
    build: { outDir: 'dist', emptyOutDir: true },
  }
})
