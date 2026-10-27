/* Objects round (B5/B6, the kind registry): the link reader and the kind
   registry, held in Node against the UI source.

     * experimental/links.ts's copies of prose.tsx's `safeHref`, `readable`,
       `URL_TOKEN`, `TRAILING` and `MD_LINK` are prose.tsx's, character for
       character (they are copied, not moved, so production's built files do
       not change);
     * `parseHttp`, which the server's engine runs without a `URL`, never
       accepts what the browser's parser reads differently: for every URL it
       accepts, `URL` agrees on the scheme and host and `safeHref` follows it;
     * `youtubeOf` never names a video prose.tsx's `youtubeId` would not, and
       names every one it would in the corpus below;
     * `linksOf` finds exactly the links the block reader's own reading
       (`placedIn` + `readable`) finds, in the same order, with the same
       words -- over the texts below and, when FLUID_LINKS_CORPUS names a
       file of texts (a copy of the owner's Brain), over every one of those;
     * `kindOf` answers each kind of object as the chip, the Show menu, the
       list and the drawing each used to, and links and videos as new kinds.
   Run by tests/test_fluid_objects_links.py. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import * as prose from '../src/prose'
import { placedIn } from '../src/blocks'
import * as links from '../src/experimental/links'
import { kindOf } from '../src/experimental/objectkinds'
import { digest, linkKey, objectsOfPost } from '../src/experimental/postobjects'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }

/* -- the copies are prose.tsx's ----------------------------------------------- */
const src = readFileSync(fileURLToPath(new URL('../src/prose.tsx', import.meta.url)), 'utf8')
eq(links.safeHref.toString(), prose.safeHref.toString(), 'safeHref is prose.tsx\'s')
eq(links.readable.toString(), prose.readable.toString(), 'readable is prose.tsx\'s')
for (const [name, re] of [['URL_TOKEN', links.URL_TOKEN], ['TRAILING', links.TRAILING], ['MD_LINK', links.MD_LINK]] as const)
  eq(src.split(/\r?\n/).includes(`const ${name} = ${re.toString()}`), true, `${name} is prose.tsx's`)

/* -- parseHttp accepts nothing the browser reads otherwise ------------------------ */
const URLS = [
  'https://www.youtube.com/watch?v=8-89awEEF0g', 'http://youtu.be/8-89awEEF0g', 'https://youtu.be/8-89awEEF0g?t=42',
  'https://www.youtube.com/shorts/8-89awEEF0g', 'https://m.youtube.com/watch?feature=x&v=8-89awEEF0g',
  'https://www.youtube.com/watch?v=AAAAAAAAAAA&v=BBBBBBBBBBB', 'https://www.youtube.com/embed/8-89awEEF0g',
  'https://www.youtube.com/live/8-89awEEF0g', 'https://music.youtube.com/watch?v=8-89awEEF0g',
  'https://www.youtube.com/watch?v=8-89awEEF0', 'https://www.youtube.com/watch?v=8-89awEEF0gX',
  'https://www.youtube.com/@pbsspacetime', 'https://www.youtube.com/playlist?list=PLtiOgIRVt405CaxXjFiPRn8rai-aRZzxV',
  'https://youtube.com@evil.com/watch?v=8-89awEEF0g', 'https://youtube.com.evil.com/watch?v=8-89awEEF0g',
  'https://evil.com/x?u=https://youtube.com/watch?v=8-89awEEF0g', 'https://WWW.YouTube.COM/watch?v=8-89awEEF0g',
  'https://www.youtube.com:443/watch?v=8-89awEEF0g', 'https://www.youtube.com/watch?v=%38-89awEEF0g',
  'https://www.youtube.com/watch?v=8-89awEEF0g#t=1', 'https://www.youtube.com/x/../watch?v=8-89awEEF0g',
  'https://example.com', 'https://example.com/', 'http://127.0.0.1:8760/api/x', 'https://[::1]/x', 'http://localhost/a?b=c',
  'https://a.b.c.d.example.co.uk/path/to/thing.html?x=1&y=2#frag', 'https://example.com:99999/x', 'https://exa mple.com',
  'https://user:pw@example.com/', 'https://exämple.com/', 'https://example.com/ä', 'http:/example.com', 'https:example.com',
  'https://', 'https://.', 'https://-a.com', 'https://a-.com', 'https://1.2.3', 'https://256.1.1.1', 'https://010.0.0.1',
  'https://0x7f.1/', 'https://1.2.3.4/', 'https://example.com./', 'https://a.0x10/', 'https://example.com\\x',
  'javascript:alert(1)', 'mailto:a@b.c', 'ftp://example.com',
]
let accepted = 0, videos = 0
for (const raw of URLS) {
  const u = links.parseHttp(raw)
  const classic = prose.youtubeId(raw)
  const mine = u ? links.youtubeOf(u) : null
  if (mine !== null) { videos++; eq(mine, classic, `${raw}: the video is Classic's`) }
  if (classic !== null && u && !/\/\.\.?\//.test(raw)) eq(mine, classic, `${raw}: Classic's video is found`)
  if (!u) continue
  accepted++
  let b: URL | null = null
  try { b = new URL(raw) } catch { b = null }
  assert.ok(b, `${raw}: accepted, so the browser parses it`)
  eq(b!.protocol.replace(':', ''), u.scheme, `${raw}: the scheme agrees`)
  eq(b!.hostname, u.host, `${raw}: the host agrees`)
  assert.ok(prose.safeHref(raw), `${raw}: accepted, so a reader can follow it`)
  checks++
}
assert.ok(accepted >= 20 && videos >= 8, `the corpus exercises both sides (${accepted} accepted, ${videos} videos)`)

/* -- linksOf reads what the block reader reads ----------------------------------- */
/** The same reading through the block reader itself: what links.ts's
 *  `linksOf` would be if it could ask production's chunk for `placedIn`. */
function reference(text: string) {
  const out: { url: string; label: string | null; video: string | null }[] = []
  const at = new Map<string, number>()
  const words = (s: string) => s.replace(/(\*\*|__|\*|_|`)(.+?)\1/g, '$2').replace(/\s+/g, ' ').trim()
  for (const p of placedIn(text)) for (const raw of links.readable(p.block)) {
    const t = raw.replace(/`[^`]*`/g, ' ')
    const found: { url: string; label: string | null }[] = []
    const rest = t.replace(new RegExp(links.MD_LINK.source, 'g'), (_a, label: string, target: string) => {
      found.push({ url: target, label: words(label) || null }); return ' '
    })
    for (const m of rest.matchAll(new RegExp(links.URL_TOKEN.source, 'g'))) found.push({ url: m[0].replace(links.TRAILING, ''), label: null })
    for (const f of found) {
      const u = links.parseHttp(f.url)
      if (!u) continue
      const prior = at.get(f.url)
      const m = { url: f.url, label: f.label, video: links.youtubeOf(u) }
      if (prior === undefined) { at.set(f.url, out.length); out.push(m) }
      else if (f.label !== null && out[prior].label === null) out[prior] = m
    }
  }
  return out
}
const TEXTS = [
  'Here are five:\n\n1. **[One | NOVA](https://www.youtube.com/watch?v=8-89awEEF0g)** — a.\n2. [Two](https://youtu.be/VAKnhanjXVI)\n- **[Channel](https://www.youtube.com/@pbsspacetime)**',
  'Bare https://example.com/a/b. then (https://example.com/c) and `https://code.example/x`.',
  '```\nhttps://in.a.fence/x\n```\nafter https://after.example/',
  '~~~~md\n```\nhttps://still.fenced/\n```\n~~~~\nhttps://out.example/',
  '> quoted [words](https://q.example/) and\n> more https://q2.example/',
  '| a | b |\n|---|---|\n| https://cell.example/x | [l](https://cell2.example/) |',
  '# Heading https://h.example/\ntext https://example.com and again [labelled](https://example.com)',
  'https://youtube.com@evil.com/watch?v=8-89awEEF0g https://user:pw@x.example/',
  '    indented https://indented.example/ is prose here',
  'no links at all',
]
const corpus = process.env.FLUID_LINKS_CORPUS ? JSON.parse(readFileSync(process.env.FLUID_LINKS_CORPUS, 'utf8')) as string[] : []
let texts = 0, found = 0
const differ: string[] = []
for (const t of [...TEXTS, ...corpus]) {
  const mine = links.linksOf(t).map((m) => ({ url: m.url, label: m.label, video: m.video }))
  const ref = reference(t)
  texts++
  found += mine.length
  try { eq(mine, ref, 'linksOf reads as the block reader') } catch { differ.push(t.slice(0, 160)) }
}
if (differ.length) throw new Error(`linksOf differs from the block reader on ${differ.length} of ${texts} texts:\n` + differ.slice(0, 5).join('\n---\n'))

/* -- the kind registry ------------------------------------------------------------- */
const K = (o: Record<string, unknown>) => kindOf({ kind: 'media', type: 'attachment', parent: null, ...o } as never)
const row = (o: Record<string, unknown>) => { const k = K(o); return [k.word, k.chip, k.family, k.filter, k.doc] }
eq(row({ kind: 'post-text', type: 'text' }), ['text', null, 'text', 'text', null], 'post text')
eq(row({ kind: 'block', type: 'chart' }), ['chart', 'chart', 'section', 'chart', null], 'a chart')
eq(row({ kind: 'block', type: 'markdown' }), ['doc', 'doc', 'section', 'other', null], 'a markdown block: the chip\'s doc')
eq(row({ kind: 'block', type: 'pad', parent: 'x' }), ['note', null, 'section', 'other', null], 'a nested pad: no chip')
eq(row({ kind: 'figure', type: 'figure' }), ['image', 'image', 'media', 'image', null], 'a placed figure')
eq(row({ title: 'a.png' }), ['image', 'image', 'media', 'image', null], 'a .png with no type: an image, as the chip said')
eq(row({ title: 'notes.md', media_type: 'text/markdown' }), ['doc', 'doc', 'file', 'file', 'markdown'], 'markdown')
eq(row({ title: 'run.py' }), ['doc', 'doc', 'file', 'file', 'plain'], 'code')
eq(row({ title: 'page.html', media_type: 'text/html' }), ['file', 'file', 'file', 'file', null], 'html is opened, not read')
eq(row({ title: 'a.mp4', media_type: 'video/mp4' }), ['video', 'file', 'media', 'video', null], 'a video file')
eq(row({ title: 'pack.zip', media_type: 'application/zip', type: 'returned' }).slice(0, 4), ['file', 'file', 'file', 'file'], 'a returned zip')
eq(K({ title: 'pack.zip', type: 'returned' }).source, 'returned', 'returned by a run')
eq([K({ title: 'x.pdf' }).badge, K({ title: 'x.pdf' }).tone, K({ title: 'x.csv' }).tone, K({ title: 'x' }).badge], ['PDF', 'pdf', 'data', 'FILE'], 'badges')
eq(row({ kind: 'link', type: 'video', link: { video: 'abcdefghijk' } }), ['video', 'video', 'media', 'video', null], 'a video link')
eq(row({ kind: 'link', type: 'link', link: { video: null } }), ['link', 'link', 'link', 'link', null], 'a link')

/* objectsOfPost puts `is` on everything, and links last, keyed by their URL */
const objs = objectsOfPost({ id: 'ent-p', parts: [{ type: 'text', text: TEXTS[0] }] })
eq(objs.every((o) => o.is && o.is.word), true, 'every object says what it is')
eq(objs.filter((o) => o.kind === 'link').map((o) => [o.key, o.type, o.title]), [
  ['ent-p:link:https://www.youtube.com/watch?v=8-89awEEF0g', 'video', 'One | NOVA'],
  ['ent-p:link:https://youtu.be/VAKnhanjXVI', 'video', 'Two'],
  ['ent-p:link:https://www.youtube.com/@pbsspacetime', 'link', 'Channel'],
], 'links: keyed by URL, videos told apart, titled by their words')

/* A link's address always fits the server's cap (300): a URL that fits keeps
   its key; a longer one is its start and a digest of the whole. */
const root = 'ent-0123456789ab'
const room = 300 - `live:${root}:${root}:link:`.length
const fit = 'https://example.com/' + 'a'.repeat(room - 20)
eq(linkKey(root, fit), `${root}:link:${fit}`, 'a URL that fits keeps the key it had')
const long = 'https://example.com/' + 'x'.repeat(1980)
const k1 = linkKey(root, long), k2 = linkKey(root, long.slice(0, -1) + 'y')
eq([long.length, `live:${root}:${k1}`.length <= 300, `live:${root}:${k2}`.length <= 300], [2000, true, true], 'a 2,000-character URL fits')
eq([k1 === linkKey(root, long), k1 !== k2, k1.startsWith(`${root}:link:https://example.com/xxx`)], [true, true, true], 'stable, told apart, still readable')
eq(/[\uD800-\uDBFF]…/.test(linkKey(root, 'https://e.com/' + '\u{1F600}'.repeat(400))), false, 'never half a surrogate pair')
eq([digest('a') !== digest('b'), /^[0-9a-f]{16}$/.test(digest(long))], [true, true], 'a 16-digit digest')

console.log(`links: ${texts} texts (${corpus.length} from the corpus), ${found} links; ${checks} checks passed`)
