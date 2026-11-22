/* The Magnet additions' disposable fixture access path: read-only EXCEPT two
 * exact, identity-gated writes.
 *
 *   node tools/quiet-magnet-additions-preview.mjs --front http://127.0.0.1:8952
 *     --port 8953 --dist apps/fluid-web/dist --log .preview/<root>/traffic.jsonl
 *     --manifest .preview/<root>/manifest.json
 *
 * WHAT MAKES THIS A FIXTURE, AND WHAT DOES NOT. A loopback port is not a
 * fixture gate and is never treated as one. Before it listens at all, this
 * process reads a COMPLETED synthetic fixture manifest that lies inside its
 * own checkout, and then asks the server it is about to forward to who it is:
 * `/api/brain?identity=1` and `/api/server` must BOTH answer the manifest's
 * corpus id, and `/api/server`'s absolute corpus path must be the manifest's
 * own `primary` Brain directory. Any doubt and it refuses to start. The same
 * check is made again, against the live server, before EVERY mutation is
 * forwarded. The full corpus@instance must also match the intended instance
 * pinned when this synthetic fixture was seeded. That binding goes on the
 * write, so a changed recipient refuses it even after verification completes.
 * Everything fails closed: an error anywhere in the gate is a refusal.
 *
 * WHAT MAY BE WRITTEN, exactly and by raw path:
 *   POST /fluid/api/posts                            into the manifest's one
 *     existing Magnet Conversation C, record-only plain text or a reply whose
 *     parent the SERVER says lives in C. No ask, dispatch, addressing,
 *     attachment, parts, topics or choice.
 *   POST /fluid/api/arrangements/<A>/magnets          one new Magnet in the
 *     manifest's one arrangement A, from a single Conversation source among
 *     the fixture's own A/B/C, with supported seed options only.
 * Both need a stable operation key, so a retry is the same operation.
 *
 * Everything else is refused before forwarding: every other method and path,
 * `/api/capacity`, percent-encoded aliases of an allowed path, a body that is
 * not JSON or is over the limit, a Host or Origin that is not this fixture's
 * own, and a request without the interface's own client header. Credentials,
 * cookies, worker grants and method-override headers are refused or stripped;
 * the page's `X-Mentis-Brain` binding is preserved and must name this fixture.
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
/** This fixture's own manifest format. The read-only trial's fixture is not one. */
export const FORMAT = 'quiet-magnet-additions-disposable-fixture-v1'
/** A fixture write is a short JSON object; anything larger is refused unread. */
export const MAX_BODY = 16 * 1024
export const MAX_TEXT = 4000
export const BRAIN_HEADER = 'x-mentis-brain'
export const CLIENT_HEADER = 'x-mentis-client'
/** Never forwarded: authority the browser holds, and anything that could turn a
 *  read into a write after this process decided it was a read. */
export const STRIPPED = ['authorization', 'proxy-authorization', 'cookie',
  'x-mentis-worker', 'x-q2-brain', 'x-http-method-override',
  'x-method-override', 'x-forwarded-for', 'x-forwarded-host',
  'x-forwarded-proto', 'x-real-ip', 'via', 'forwarded']
const SUPPORTED_TYPES = ['post', 'file', 'image', 'attachment']
const RENDERERS = ['disc', 'ring', 'cards', 'list', 'gallery']

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)
const sameFile = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase()
const inside = (p) => path.resolve(p).startsWith(REPO + path.sep)

// -- the fixture ------------------------------------------------------------

/** A completed synthetic fixture inside this checkout, or a thrown refusal.
 *  `root` is the manifest's own directory: the Brain it names is `primary`
 *  under it, never a path the manifest is free to spell for itself. */
export function fixtureOf(manifest, root) {
  if (!inside(root)) throw new Error('a fixture lives inside this checkout, never elsewhere')
  if (!isObject(manifest) || manifest.format !== FORMAT)
    throw new Error(`not a ${FORMAT} manifest`)
  if (manifest.setup_closed !== true)
    throw new Error('the fixture setup has not completed; writes are never offered to a half-seeded fixture')
  const primary = path.resolve(root, 'primary')
  if (!inside(primary)) throw new Error('the fixture Brain is outside this checkout')
  const live = ['\\mentis\\mark-iv\\', '/mentis/mark-iv/', '\\appdata\\', '/appdata/',
    '\\programdata\\', '/programdata/']
  if (live.some((bit) => primary.toLowerCase().includes(bit)))
    throw new Error('that is an installed or live Brain path, never a fixture')
  const p = manifest.primary
  const w = manifest.writes_allowed
  if (!isObject(p) || !isObject(w)) throw new Error('the manifest names no fixture identity or allowed writes')
  const need = (v, what) => {
    if (typeof v !== 'string' || !v.trim()) throw new Error(`the manifest names no ${what}`)
    return v
  }
  const corpusId = need(p.corpus_id, 'corpus id')
  const instance = need(p.instance, 'fixture instance; seed a fresh fixture')
  if (!/^[0-9a-f]{16}$/.test(instance)) throw new Error('invalid fixture instance')
  const C = need(w.conversation, 'Conversation to write into')
  const A = need(w.arrangement, 'arrangement to create in')
  if (C !== p.C || A !== p.arrangement_key)
    throw new Error('the allowed writes name something the seeded fixture does not')
  const sources = Array.isArray(w.magnet_sources) ? w.magnet_sources.filter((s) => typeof s === 'string') : []
  const people = Array.isArray(w.participants) ? w.participants.filter((s) => typeof s === 'string') : []
  if (!sources.length || !people.length)
    throw new Error('the manifest names no allowed sources or participants')
  if (!fs.existsSync(path.join(primary, 'corpus.db')))
    throw new Error('no fixture Brain at the manifest\'s own primary directory')
  return { root: path.resolve(root), primary, corpusId, binding: `${corpusId}@${instance}`, A, C, B: p.B,
    sources, participants: people, manifest }
}

export function readFixture(manifestPath) {
  const file = path.resolve(manifestPath)
  if (!inside(file)) throw new Error('the fixture manifest must be inside this checkout')
  return fixtureOf(JSON.parse(fs.readFileSync(file, 'utf8')), path.dirname(file))
}

// -- what is asked for ------------------------------------------------------

/** The read rule the read-only trial used, kept exactly: safe methods, and
 *  never capacity. Capacity reads a runtime catalogue, which a fixture has no
 *  business asking for. */
export const readOnlyRequest = (method, url) => {
  let pathname
  try { pathname = decodeURIComponent(new URL(url, 'http://fixture').pathname) } catch { return false }
  return ['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase()) && !/^\/api\/capacity(?:\/|$)/.test(pathname)
}

/** The RAW path, with no decoding anywhere: an allowed write is matched by
 *  exact string, so `%2F`, `%63` and `.`/`..` segments alias nothing. */
export function rawPath(url) {
  const q = url.indexOf('?')
  return q === -1 ? url : url.slice(0, q)
}

export const canonicalPath = (p) =>
  typeof p === 'string' && p.startsWith('/') && !p.includes('%') && !p.includes('\\') &&
  !p.includes('//') && !p.split('/').includes('.') && !p.split('/').includes('..')

/** What this request is, decided before anything is read of its body.
 *  One of: ui, read, post, magnet, or refuse (with status and error). */
export function classify(method, url, fixture) {
  const m = (method || 'GET').toUpperCase()
  const p = rawPath(url || '/')
  if (!canonicalPath(p))
    return { kind: 'refuse', status: 400, error: `the fixture answers canonical paths only: ${p}` }
  const api = /^\/(api|fluid\/api)(?:\/|$)/.test(p)
  if (m === 'POST' && p === '/fluid/api/posts') return { kind: 'post', path: p }
  if (m === 'POST' && p === `/fluid/api/arrangements/${fixture.A}/magnets`) return { kind: 'magnet', path: p }
  if (!readOnlyRequest(m, url))
    return { kind: 'refuse', status: 403,
      error: `this fixture forwards only its two allowed writes: ${m} ${p} was not forwarded` }
  return { kind: api ? 'read' : 'ui', path: p }
}

// -- what may be written ----------------------------------------------------

const onlyKeys = (body, allowed, what) => {
  const extra = Object.keys(body).filter((k) => !allowed.includes(k))
  return extra.length ? `${what} takes only ${allowed.join(', ')}; not ${extra.join(', ')}` : null
}

/** A record-only post, or a reply, into the fixture's one Conversation.
 *  Returns null, or the refusal in words. The reply PARENT is not checked
 *  here: the server is asked where it lives (`replyParentRefusal`). */
export function postRefusal(body, fixture) {
  if (!isObject(body)) return 'the body is a JSON object'
  const extra = onlyKeys(body, ['conversation', 'author', 'text', 'replies_to', 'action', 'op'], 'a fixture post')
  if (extra) return extra
  if (body.conversation !== fixture.C)
    return 'this fixture writes posts only into the Magnet\'s own Conversation'
  if (body.action !== undefined && body.action !== 'record-only')
    return 'a fixture post is record-only: it never asks for work and never dispatches'
  if (typeof body.author !== 'string' || !fixture.participants.includes(body.author))
    return 'the author is one of the fixture\'s own participants'
  if (typeof body.text !== 'string' || !body.text.trim()) return 'a post says something: "text"'
  if (body.text.length > MAX_TEXT) return `a fixture post is at most ${MAX_TEXT} characters`
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(body.text))
    return 'a fixture post is plain text'
  if (body.replies_to !== undefined && (typeof body.replies_to !== 'string' || !body.replies_to.trim()))
    return 'replies_to names one post'
  if (typeof body.op !== 'string' || !body.op.trim())
    return 'a fixture write carries a stable operation key: "op"'
  return null
}

/** One new Magnet in the fixture's one arrangement, from one of its own
 *  Conversations, with the seed options this fixture supports. */
export function magnetRefusal(body, fixture) {
  if (!isObject(body)) return 'the body is a JSON object'
  const extra = onlyKeys(body, ['seed', 'attach', 'op'], 'a fixture magnet.create')
  if (extra) return extra
  if (typeof body.op !== 'string' || !body.op.trim())
    return 'a fixture write carries a stable operation key: "op"'
  const seed = body.seed
  if (!isObject(seed)) return 'seed: a configuration'
  const seedExtra = onlyKeys(seed, ['sources', 'selection', 'collection', 'synthesis',
    'notifications', 'presentation'], 'a fixture seed')
  if (seedExtra) return seedExtra
  if (!Array.isArray(seed.sources) || seed.sources.length !== 1)
    return 'seed.sources: exactly one source in this fixture'
  const s = seed.sources[0]
  if (!isObject(s) || s.kind !== 'conversation')
    return 'seed.sources[0]: a Conversation source in this fixture'
  const sExtra = onlyKeys(s, ['kind', 'conversation'], 'a fixture source')
  if (sExtra) return sExtra
  if (!fixture.sources.includes(s.conversation))
    return 'seed.sources[0].conversation: one of this fixture\'s own Conversations'
  const sel = seed.selection
  if (!isObject(sel)) return 'seed.selection: what this Magnet collects'
  const selExtra = onlyKeys(sel, ['informationTypes', 'dates'], 'a fixture selection')
  if (selExtra) return selExtra
  if (!Array.isArray(sel.informationTypes) || !sel.informationTypes.length ||
      sel.informationTypes.some((t) => !SUPPORTED_TYPES.includes(t)) ||
      new Set(sel.informationTypes).size !== sel.informationTypes.length)
    return `seed.selection.informationTypes: each of ${SUPPORTED_TYPES.join(', ')} at most once`
  if (sel.dates !== undefined) {
    if (!isObject(sel.dates)) return 'seed.selection.dates: a date range'
    const dExtra = onlyKeys(sel.dates, ['after', 'before'], 'a fixture date range')
    if (dExtra) return dExtra
    for (const k of ['after', 'before'])
      if (sel.dates[k] !== undefined &&
          (typeof sel.dates[k] !== 'string' || Number.isNaN(Date.parse(sel.dates[k]))))
        return `seed.selection.dates.${k}: an ISO 8601 date`
  }
  if (!isObject(seed.collection) || seed.collection.mode !== 'one-time' ||
      onlyKeys(seed.collection, ['mode'], 'a fixture collection'))
    return 'seed.collection: {"mode": "one-time"} in this fixture; nothing scheduled or continuous runs here'
  if (!isObject(seed.synthesis) || seed.synthesis.mode !== 'manual' ||
      onlyKeys(seed.synthesis, ['mode'], 'a fixture synthesis'))
    return 'seed.synthesis: {"mode": "manual"} in this fixture; no synthesis runs here'
  const n = seed.notifications
  if (!isObject(n) || onlyKeys(n, ['newItems', 'changes', 'failures'], 'fixture notifications') ||
      ['newItems', 'changes', 'failures'].some((k) => n[k] !== false))
    return 'seed.notifications: newItems, changes and failures are all false in this fixture'
  const pr = seed.presentation
  if (!isObject(pr) || onlyKeys(pr, ['renderer'], 'a fixture presentation') ||
      !RENDERERS.includes(pr.renderer))
    return `seed.presentation.renderer: one of ${RENDERERS.join(', ')}`
  const attach = body.attach
  if (!isObject(attach)) return 'attach: where the Magnet is placed'
  const aExtra = onlyKeys(attach, ['zone'], 'a fixture attach')
  if (aExtra) return aExtra
  const zone = attach.zone
  if (!isObject(zone) || zone.type !== 'zone' || zone.show !== 'magnet')
    return 'attach.zone: {"type": "zone", "show": "magnet", "name": "..."}'
  const zExtra = onlyKeys(zone, ['type', 'show', 'name'], 'a fixture zone')
  if (zExtra) return zExtra
  if (typeof zone.name !== 'string' || !zone.name.trim() || zone.name.length > 80)
    return 'attach.zone.name: a name of up to 80 characters'
  return null
}

// -- what is forwarded ------------------------------------------------------

/** The headers one forwarded request carries. The browser's authority and
 *  anything that could re-aim the request are dropped; the page's Brain
 *  binding is kept, because the server behind this checks it for itself. */
export function forwardHeaders(incoming, { host, write }) {
  const headers = { ...incoming, host, [CLIENT_HEADER]: '1' }
  for (const name of STRIPPED) delete headers[name]
  delete headers.origin
  delete headers.referer
  delete headers['content-length']
  delete headers['transfer-encoding']
  if (write) headers['content-type'] = 'application/json'
  return headers
}

// -- asking the server ------------------------------------------------------

export function ask(target, { method = 'GET', path: p, headers = {}, body = null, timeout = 10000 }) {
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: target.hostname, port: target.port, path: p, method,
      headers: { host: target.host, [CLIENT_HEADER]: '1', ...headers } }, (answer) => {
      const chunks = []
      let size = 0
      answer.on('data', (c) => { size += c.length; if (size <= MAX_BODY * 8) chunks.push(c) })
      answer.on('end', () => {
        let parsed = null
        try { parsed = JSON.parse(Buffer.concat(chunks).toString('utf8')) } catch { parsed = null }
        resolve({ status: answer.statusCode ?? 0, body: parsed })
      })
    })
    req.setTimeout(timeout, () => req.destroy(new Error(`${method} ${p} did not answer in time`)))
    req.on('error', reject)
    if (body) req.write(body)
    req.end()
  })
}

/** WHO THE SERVER BEING FORWARDED TO ACTUALLY IS, asked of the server itself.
 *  Both identity reads must name the manifest's corpus, and the server's own
 *  absolute corpus path must be the manifest's `primary` directory. Anything
 *  else throws, and every caller treats a throw as a refusal. The separate
 *  instance read must match the LOCALLY PINNED intended binding, never just
 *  the corpus id of an otherwise unverified copied Brain. */
export async function verifyUpstream(target, fixture) {
  if (typeof fixture.binding !== 'string' || !fixture.binding.startsWith(`${fixture.corpusId}@`) ||
      !/^[0-9a-f]{16}$/.test(fixture.binding.slice(fixture.corpusId.length + 1)))
    throw new Error('the fixture has no pinned instance; seed a fresh fixture')
  const identity = await ask(target, { path: '/api/brain?identity=1' })
  if (identity.status !== 200 || !isObject(identity.body))
    throw new Error(`the server did not answer its identity (${identity.status})`)
  if (identity.body.corpus_id !== fixture.corpusId)
    throw new Error('the server serves another Brain than this fixture')
  if (typeof identity.body.corpus_path !== 'string' || !path.isAbsolute(identity.body.corpus_path) ||
      !sameFile(identity.body.corpus_path, fixture.primary))
    throw new Error('the server serves another directory than this fixture\'s Brain')
  const server = await ask(target, { path: '/api/server' })
  if (server.status !== 200 || !isObject(server.body))
    throw new Error(`the server did not say what it is (${server.status})`)
  if (server.body.corpus_id !== fixture.corpusId)
    throw new Error('/api/server names another Brain than this fixture')
  if (typeof server.body.corpus !== 'string' || !path.isAbsolute(server.body.corpus) ||
      !sameFile(server.body.corpus, fixture.primary))
    throw new Error('/api/server names another corpus directory than this fixture\'s Brain')
  const bound = await ask(target, { path: '/fluid/api/needs-you/brain' })
  const brain = bound.body?.brain
  if (bound.status !== 200 || !isObject(brain) || brain.corpus_id !== fixture.corpusId ||
      typeof brain.instance !== 'string' || `${brain.corpus_id}@${brain.instance}` !== fixture.binding)
    throw new Error('the server did not confirm the intended fixture instance')
  return { corpus_id: fixture.corpusId, corpus: path.resolve(server.body.corpus),
    binding: fixture.binding,
    checked_at: new Date().toISOString() }
}

/** The SERVER decides where a reply's parent lives, not the request and not a
 *  list this process keeps. Returns null, or the refusal in words. */
export async function replyParentRefusal(target, fixture, parent) {
  const answer = await ask(target, { path: `/fluid/api/posts?ids=${encodeURIComponent(parent)}` })
  if (answer.status !== 200 || !isObject(answer.body) || !Array.isArray(answer.body.posts))
    return 'the server could not say where that post lives, so the reply was not forwarded'
  const post = answer.body.posts[0]
  if (!isObject(post) || post.error) return 'that is not a post in this fixture'
  if (post.home !== fixture.C)
    return 'a reply in this fixture answers a post in the Magnet\'s own Conversation'
  return null
}

// -- the access path --------------------------------------------------------

export function createPreview({ front, dist, log, fixture, port }) {
  const target = new URL(front)
  if (target.protocol !== 'http:' || target.hostname !== '127.0.0.1' || !target.port || target.pathname !== '/')
    throw new Error('front must be an explicit http://127.0.0.1:<port> fixture address')
  if (!fixture || !fixture.corpusId) throw new Error('a verified fixture is required before serving')
  const root = path.resolve(dist)
  if (!fs.existsSync(path.join(root, 'index.html')))
    throw new Error('build the candidate first: dist/index.html missing')
  const here = new Set([`127.0.0.1:${port}`, `localhost:${port}`, `[::1]:${port}`])
  const origins = new Set([`http://127.0.0.1:${port}`, `http://localhost:${port}`])
  const append = (line) => {
    if (log) fs.appendFileSync(log, JSON.stringify({ at: new Date().toISOString(), ...line }) + '\n')
  }
  const json = (res, status, body) => {
    res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
    res.end(JSON.stringify(body))
  }
  const refuse = (res, status, method, url, error, kind = 'FixtureRefused') => {
    append({ method, url, forwarded: false, status, error })
    json(res, status, { kind, error })
  }

  const server = http.createServer((req, res) => {
    const url = req.url ?? '/'
    const method = (req.method ?? 'GET').toUpperCase()
    // A PAGE ON A REBOUND NAME IS NOT THIS FIXTURE'S PAGE. The server behind
    // this makes the same check for itself; this one is about what reaches it.
    if (!here.has(String(req.headers.host ?? '').toLowerCase()))
      return refuse(res, 421, method, url, `Host ${req.headers.host} is not this fixture's own address`)
    const what = classify(method, url, fixture)
    if (what.kind === 'refuse') return refuse(res, what.status, method, url, what.error)
    const origin = req.headers.origin
    if (origin !== undefined && !origins.has(String(origin).toLowerCase()))
      return refuse(res, 403, method, url, `Origin ${origin} is not this fixture's own page`)
    if (url.startsWith('/__q2/brain')) {
      append({ method, url, forwarded: false, status: 200, kind: 'brain' })
      return json(res, 200, {
        brain: 'dev', label: 'Disposable Magnet additions fixture', readOnly: true,
        choices: [{ brain: 'dev', label: 'Disposable Magnet additions fixture', readOnly: true }],
      })
    }
    if (rawPath(url) === '/__q2/magnet-capabilities') return capabilities(req, res, method, url)
    if (what.kind === 'post' || what.kind === 'magnet') return mutate(req, res, what, method, url)
    if (what.kind === 'read') return forwardRead(req, res, method, url)
    return serveFile(res, method, url)
  })

  /** The capability the mini Conversation and Magnet creation ask for. It is
   *  answered ONLY while the server's identity is confirmed now, so a page
   *  whose server was replaced is told nothing it could write with. */
  async function capabilities(req, res, method, url) {
    if (method !== 'GET' && method !== 'HEAD')
      return refuse(res, 405, method, url, 'the capability is read')
    try {
      await verifyUpstream(target, fixture)
    } catch (error) {
      return refuse(res, 503, method, url, `the fixture identity is not confirmed: ${error.message}`,
        'FixtureIdentityUnconfirmed')
    }
    append({ method, url, forwarded: false, status: 200, kind: 'capability' })
    return json(res, 200, { fixture: true, corpus_id: fixture.corpusId,
      conversations: [fixture.C], arrangements: [fixture.A] })
  }

  const headersFor = (req, { write }) =>
    forwardHeaders(req.headers, { host: target.host, write })

  function forwardRead(req, res, method, url) {
    const headers = headersFor(req, { write: false })
    const up = http.request({ hostname: target.hostname, port: target.port, path: url, method, headers },
      (answer) => {
        append({ method, url, forwarded: true, status: answer.statusCode })
        const out = { ...answer.headers }
        delete out['set-cookie']
        res.writeHead(answer.statusCode ?? 502, out)
        answer.pipe(res)
      })
    up.on('error', (error) => {
      if (!res.headersSent) json(res, 502, { error: error.message }); else res.destroy()
    })
    res.on('close', () => { if (!res.writableFinished) up.destroy() })
    req.pipe(up)
  }

  /** ONE ALLOWED WRITE. Every check below runs before a byte reaches the
   *  server: framing, size, the interface's own headers, the fixture binding,
   *  the body, the reply's home -- and the server's identity, asked again now
   *  rather than trusted from start-up. */
  async function mutate(req, res, what, method, url) {
    if (req.headers['transfer-encoding'])
      return refuse(res, 501, method, url, 'a fixture write is framed by its Content-Length')
    if (req.headers['x-mentis-worker'])
      return refuse(res, 403, method, url, 'a worker grant authorises /api/worker and nothing else')
    if (req.headers[CLIENT_HEADER] !== '1')
      return refuse(res, 403, method, url, `a fixture write comes from this interface: missing ${CLIENT_HEADER}`)
    if (req.headers.origin === undefined)
      return refuse(res, 403, method, url, 'a fixture write names the page it came from: missing Origin')
    const ctype = String(req.headers['content-type'] ?? '').split(';')[0].trim().toLowerCase()
    if (ctype !== 'application/json')
      return refuse(res, 415, method, url, 'a fixture write is Content-Type: application/json')
    const bound = req.headers[BRAIN_HEADER]
    if (typeof bound !== 'string' || bound.split('@')[0] !== fixture.corpusId)
      return refuse(res, 409, method, url,
        'this page is not bound to this fixture Brain; reload it', 'BrainNotThisFixture')
    const declared = Number(req.headers['content-length'])
    if (!Number.isInteger(declared) || declared <= 0 || declared > MAX_BODY)
      return refuse(res, 413, method, url, `a fixture write is 1..${MAX_BODY} bytes with a Content-Length`)
    let raw
    try {
      raw = await readBody(req, declared)
    } catch (error) {
      return refuse(res, 400, method, url, error.message)
    }
    let body
    try {
      body = JSON.parse(raw.toString('utf8'))
    } catch (error) {
      return refuse(res, 400, method, url, `the body is not JSON: ${error.message}`)
    }
    const refusal = what.kind === 'post' ? postRefusal(body, fixture) : magnetRefusal(body, fixture)
    if (refusal) return refuse(res, 422, method, url, refusal)
    let verified
    try {
      verified = await verifyUpstream(target, fixture)
    } catch (error) {
      return refuse(res, 503, method, url,
        `nothing was written: the fixture identity is not confirmed (${error.message})`,
        'FixtureIdentityUnconfirmed')
    }
    if (bound !== verified.binding)
      return refuse(res, 409, method, url,
        'this page is not bound to the verified fixture instance; reload it', 'BrainNotThisFixture')
    if (what.kind === 'post' && body.replies_to) {
      let parent
      try {
        parent = await replyParentRefusal(target, fixture, body.replies_to)
      } catch (error) {
        return refuse(res, 502, method, url, `the reply's parent could not be checked: ${error.message}`)
      }
      if (parent) return refuse(res, 422, method, url, parent)
    }
    // FORWARDED AS THIS PROCESS UNDERSTOOD IT, not as it arrived: the body is
    // re-encoded from what was checked, with the action said out loud.
    const forwarded = what.kind === 'post'
      ? JSON.stringify({ ...body, action: 'record-only' })
      : JSON.stringify(body)
    const headers = { ...headersFor(req, { write: true }),
      [BRAIN_HEADER]: verified.binding,
      'content-length': String(Buffer.byteLength(forwarded)) }
    const up = http.request({ hostname: target.hostname, port: target.port, path: what.path,
      method: 'POST', headers }, (answer) => {
      append({ method, url, forwarded: true, status: answer.statusCode, write: what.kind, op: body.op })
      const out = { ...answer.headers }
      delete out['set-cookie']
      res.writeHead(answer.statusCode ?? 502, out)
      answer.pipe(res)
    })
    up.on('error', (error) => {
      if (!res.headersSent) json(res, 502, { error: error.message }); else res.destroy()
    })
    res.on('close', () => { if (!res.writableFinished) up.destroy() })
    up.end(forwarded)
  }

  function serveFile(res, method, url) {
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
  }

  return server
}

function readBody(req, declared) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let size = 0
    req.on('data', (chunk) => {
      size += chunk.length
      if (size > declared || size > MAX_BODY) {
        reject(new Error('the body is longer than it declared'))
        req.destroy()
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => {
      if (size !== declared) reject(new Error('the body is shorter than it declared'))
      else resolve(Buffer.concat(chunks))
    })
    req.on('error', reject)
  })
}

/** Validate, verify the server's identity, and only then listen. Nothing is
 *  restarted and nothing is retried: a failure here is a refusal to start. */
export async function startPreview({ front, port, dist, log, manifest }) {
  const fixture = readFixture(manifest)
  const identity = await verifyUpstream(new URL(front), fixture)
  const server = createPreview({ front, dist, log, fixture, port })
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(Number(port), '127.0.0.1', resolve)
  })
  return { server, fixture, identity }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = Object.fromEntries(Array.from({ length: (process.argv.length - 2) / 2 },
    (_, i) => [process.argv[2 + i * 2].replace(/^--/, ''), process.argv[3 + i * 2]]))
  if (!args.front || !args.port || !args.dist || !args.log || !args.manifest)
    throw new Error('explicit --front --port --dist --log --manifest required')
  fs.mkdirSync(path.dirname(path.resolve(args.log)), { recursive: true })
  const { identity } = await startPreview(args)
  console.log(JSON.stringify({ preview: `http://127.0.0.1:${args.port}`, fixture: identity }))
}
