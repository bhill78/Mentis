// ONE QUIET CHAT DEVELOPMENT SERVER, TWO BRAINS (Mark 2, development only).
//
// Enabled by Q2_BRAINS=1 on `vite` (dev). The dev server's /api and
// /fluid/api are answered from one of two Mentis servers:
//
//   dev     Q2_DEV_API     the disposable development Brain; writes allowed,
//                          with Mentis's own authorization as always
//   dayday  Q2_DAYDAY_API  DAY-TO-DAY, STRICTLY READ-ONLY: every request that
//                          is not GET/HEAD/OPTIONS is refused here (403) and
//                          never forwarded, and so is every GET known to write
//                          (`/api/capacity` records a reading)
//
// WHICH BRAIN A REQUEST GOES TO IS THE PAGE'S, NEVER GUESSED. A page sends its
// Brain on every fetch (`X-Q2-Brain`, quiet2/live.ts); what cannot carry a
// header (an <img>) uses the cookie the page was opened with. A request that
// names no Brain at all goes to the development Brain, never to DAY-TO-DAY.
// The choice is made only by the reader, through GET/POST /__q2/brain, and
// the page reloads on it, so no draft or pending write crosses Brains.
import http from 'node:http'

const COOKIE = 'q2-brain'
const READS = new Set(['GET', 'HEAD', 'OPTIONS'])
/** GETs that write on the Mentis server: refused where writing is not allowed. */
const WRITING_GETS = [/^\/api\/capacity(\/|\?|$)/]

export default function quietBrains(env) {
  const brains = {
    dev: { label: 'Development Brain', target: env.Q2_DEV_API ?? 'http://127.0.0.1:8790', readOnly: false },
    dayday: { label: 'DAY-TO-DAY', target: env.Q2_DAYDAY_API ?? 'http://127.0.0.1:8760', readOnly: true },
  }
  const cookieOf = (req) => /(?:^|;\s*)q2-brain=(dev|dayday)/.exec(req.headers.cookie ?? '')?.[1]
  const brainOf = (req) => {
    const named = req.headers['x-q2-brain']
    if (named === 'dev' || named === 'dayday') return named
    return cookieOf(req) ?? 'dev'
  }
  const json = (res, status, body, headers = {}) => {
    res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...headers })
    res.end(JSON.stringify(body))
  }
  return {
    name: 'quiet-brains',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? '/'
        /* the reader's choice of Brain */
        if (url.startsWith('/__q2/brain')) {
          if (req.method === 'POST') {
            /* only this dev server's own page may choose: same origin, JSON */
            const own = `http://${req.headers.host}`
            if (req.headers.origin !== own || !(req.headers['content-type'] ?? '').includes('application/json'))
              return json(res, 403, { error: 'the Brain is chosen from this page only' })
            let body = ''
            req.on('data', (c) => { body += c })
            req.on('end', () => {
              let want
              try { want = JSON.parse(body || '{}').brain } catch { want = undefined }
              if (!(want in brains)) return json(res, 400, { error: `no such Brain: ${String(want)}` })
              json(res, 200, { brain: want, ...brains[want], target: undefined },
                { 'Set-Cookie': `${COOKIE}=${want}; Path=/; SameSite=Strict` })
            })
            return
          }
          const brain = cookieOf(req) ?? 'dev'
          return json(res, 200, {
            brain, label: brains[brain].label, readOnly: brains[brain].readOnly,
            choices: Object.entries(brains).map(([k, b]) => ({ brain: k, label: b.label, readOnly: b.readOnly })),
          })
        }
        if (!url.startsWith('/api/') && url !== '/api' && !url.startsWith('/fluid/api')) return next()
        const key = brainOf(req)
        const brain = brains[key]
        const method = (req.method ?? 'GET').toUpperCase()
        if (brain.readOnly && (!READS.has(method) || WRITING_GETS.some((r) => r.test(url))))
          return json(res, 403, { error: `read-only: ${method} ${url} was not sent to ${brain.label}`, kind: 'ReadOnlyPreview' })
        const to = new URL(brain.target)
        const headers = { ...req.headers, host: to.host }
        delete headers['x-q2-brain']
        const up = http.request({ hostname: to.hostname, port: to.port, path: url, method, headers }, (r) => {
          r.on('error', () => res.destroy())
          res.writeHead(r.statusCode ?? 502, r.headers)
          r.pipe(res)
        })
        /* a broken answer is never passed on as a whole one */
        up.on('error', (e) => { if (!res.headersSent) json(res, 502, { error: `${brain.label} could not be reached: ${e.message}` }); else res.destroy() })
        res.on('close', () => { if (!res.writableFinished) up.destroy() })
        req.pipe(up)
      })
    },
  }
}
