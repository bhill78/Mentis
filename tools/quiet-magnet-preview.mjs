/* A disposable, one-Brain, built candidate preview. Its access path refuses
 * writes BEFORE forwarding. There is no production/default target or Brain
 * switching; setup is a separate Python command and is over before this runs.
 * node tools/quiet-magnet-preview.mjs --port 8913 --front http://127.0.0.1:8912
 *   --dist apps/fluid-web/dist --log .preview/quiet-magnet/traffic.jsonl
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const readOnlyRequest = (method, url) => {
  let pathname
  try { pathname = decodeURIComponent(new URL(url, 'http://fixture').pathname) } catch { return false }
  return ['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase()) && !/^\/api\/capacity(?:\/|$)/.test(pathname)
}

export function createPreview({ front, dist, log }) {
  const target = new URL(front)
  if (target.protocol !== 'http:' || target.hostname !== '127.0.0.1' || !target.port || target.pathname !== '/')
    throw new Error('front must be an explicit http://127.0.0.1:<port> fixture address')
  const root = path.resolve(dist)
  if (!fs.existsSync(path.join(root, 'index.html'))) throw new Error('build the candidate first: dist/index.html missing')
  const append = (line) => { if (log) fs.appendFileSync(log, JSON.stringify({ at: new Date().toISOString(), ...line }) + '\n') }
  const json = (res, status, body) => { res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(body)) }
  return http.createServer((req, res) => {
    const url = req.url ?? '/', method = (req.method ?? 'GET').toUpperCase()
    if (!readOnlyRequest(method, url)) {
      append({ method, url, forwarded: false, status: 403 })
      return json(res, 403, { kind: 'ReadOnlyPreview', error: `read-only fixture: ${method} ${url} was not forwarded` })
    }
    if (url.startsWith('/__q2/brain')) return json(res, 200, {
      brain: 'dev', label: 'Disposable Magnet fixture', readOnly: true,
      choices: [{ brain: 'dev', label: 'Disposable Magnet fixture', readOnly: true }],
    })
    if (/^\/(api|fluid\/api)(?:[/?]|$)/.test(url)) {
      const headers = { ...req.headers, host: target.host, 'x-mentis-client': '1' }
      delete headers['x-q2-brain']
      // No authority or cookie is borrowed from the browser running the owner’s
      // real Brain; a synthetic fixture needs none for its ordinary reads.
      delete headers.authorization
      delete headers.cookie
      const up = http.request({ hostname: target.hostname, port: target.port, path: url, method, headers }, (answer) => {
        append({ method, url, forwarded: true, status: answer.statusCode })
        res.writeHead(answer.statusCode ?? 502, answer.headers)
        answer.pipe(res)
      })
      up.on('error', (error) => { if (!res.headersSent) json(res, 502, { error: error.message }); else res.destroy() })
      res.on('close', () => { if (!res.writableFinished) up.destroy() })
      req.pipe(up)
      return
    }
    let pathname
    try { pathname = decodeURIComponent(new URL(url, 'http://fixture').pathname) } catch { return json(res, 400, { error: 'bad path' }) }
    const relative = pathname === '/' || pathname === '/quiet2' || pathname === '/fluid' ? 'index.html' : pathname.replace(/^\/+/, '')
    const file = path.resolve(root, relative)
    if (!file.startsWith(root + path.sep)) return json(res, 403, { error: 'outside candidate build' })
    let stat
    try { stat = fs.statSync(file) } catch { return json(res, 404, { error: 'not in candidate build' }) }
    if (!stat.isFile()) return json(res, 404, { error: 'not a built file' })
    const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.json': 'application/json', '.wasm': 'application/wasm' }[path.extname(file)] ?? 'application/octet-stream'
    res.writeHead(200, { 'Content-Type': mime, 'Cache-Control': 'no-store' })
    if (method === 'HEAD') res.end(); else fs.createReadStream(file).pipe(res)
  })
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = Object.fromEntries(Array.from({ length: (process.argv.length - 2) / 2 }, (_, i) => [process.argv[2 + i * 2].replace(/^--/, ''), process.argv[3 + i * 2]]))
  if (!args.front || !args.port || !args.dist || !args.log) throw new Error('explicit --front --port --dist --log required')
  fs.mkdirSync(path.dirname(path.resolve(args.log)), { recursive: true })
  createPreview(args).listen(Number(args.port), '127.0.0.1', () => console.log(`read-only fixture preview http://127.0.0.1:${args.port}`))
}
