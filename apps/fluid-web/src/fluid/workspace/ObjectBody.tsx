/* One object's content, drawn by the shared renderers as its post draws it
 * (moved from Shell.tsx, F1). `big` is the detail's and a page's rendering.
 *
 * A DOCUMENT IS ITS TEXT (F6 fix round): an attached Markdown or text file is
 * drawn as the demo draws "follow-ups.md" -- its words, a Markdown file through
 * the same Markdown renderer, a plain one as it is written -- in the card
 * (clipped, faded) and in full in the detail. Any other file keeps a file card
 * that opens it.
 *
 * OBJECTS ROUND. What an object is comes from the kind registry
 * (experimental/objectkinds.ts), never decided here again. A FILE is drawn as
 * Classic draws one (surfaces/TurnMedia.tsx `FileCard`, B3): its extension
 * badge in its tone, its name, what it is and its size (asked of
 * `?describe=1` once it is drawn), Open, and Download. A LINK (B6) is where
 * it goes and its domain (its words are its title, shown over it once), and
 * opens in a new tab; nothing is fetched. A
 * YOUTUBE LINK (B5) is Classic's video card (surfaces/VideoPreviews.tsx):
 * a plate drawn from CSS, and the player loaded only when it is pressed. */

import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { Prose } from '../../prose'
import { RenderableBlock, turnPartScope } from '../../experimental/renderable'
import { namesFor } from '../../experimental/objects'
import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import { kindOf } from '../../experimental/objectkinds'
import { safeHref } from '../../experimental/links'
import type { PostObjectEntry } from '../store'
import { usePost } from './hooks'

/* -- documents' words, read once per artifact and shared by every card -----
   ONLY WHAT IS DRAWN CROSSES THE WIRE: `/fluid/api/document` sends the first
   256 KB and says whether there was more (`/api/artifacts/<ref>` sends the
   whole file). WHAT IS NO LONGER SHOWN IS LET GO: a document no card or
   detail draws is kept for a while (the IDLE most recent) and then dropped,
   and a read nobody is waiting for any more is stopped. */

type Doc = { text: string; cut: boolean } | { error: string }
const IDLE = 8
const docs = new Map<string, Doc>()
const reading = new Map<string, AbortController>()
const holders = new Map<string, number>()
const idle: string[] = []
const heard = new Set<() => void>()
const tell = () => heard.forEach((fn) => fn())

function readDoc(ref: string) {
  if (docs.has(ref) || reading.has(ref)) return
  const stop = new AbortController()
  reading.set(ref, stop)
  fluidFetch('/fluid/api/document?ref=' + encodeURIComponent(ref), { headers: { ...CLIENT_HEADERS }, signal: stop.signal })
    .then(async (r) => {
      const body = await r.json().catch(() => null)
      if (!r.ok || !body || typeof body.text !== 'string') throw new Error(body?.why ?? body?.error ?? (r.statusText || String(r.status)))
      if (reading.get(ref) === stop) docs.set(ref, { text: body.text, cut: !!body.cut })
    })
    .catch((e: Error) => { if (reading.get(ref) === stop && !stop.signal.aborted) docs.set(ref, { error: e.message }) })
    .finally(() => { if (reading.get(ref) === stop) reading.delete(ref); tell() })
}
/** A card or a detail draws `ref` while it is mounted. */
function hold(ref: string) {
  holders.set(ref, (holders.get(ref) ?? 0) + 1)
  const at = idle.indexOf(ref)
  if (at >= 0) idle.splice(at, 1)
  readDoc(ref)
  return () => {
    const n = (holders.get(ref) ?? 1) - 1
    if (n > 0) { holders.set(ref, n); return }
    holders.delete(ref)
    reading.get(ref)?.abort()
    reading.delete(ref)
    if (docs.has(ref)) idle.push(ref)
    while (idle.length > IDLE) docs.delete(idle.shift()!)
  }
}
const useDoc = (ref: string) =>
  useSyncExternalStore((fn) => { heard.add(fn); return () => { heard.delete(fn) } }, () => docs.get(ref))

function DocText({ docRef, url, scope, title, big, plain }: { docRef: string; url: string; scope: string; title: string; big?: boolean; plain?: boolean }) {
  useEffect(() => hold(docRef), [docRef])
  const doc = useDoc(docRef)
  if (!doc) return <div className="wk-doc wk-doc-wait" aria-busy="true" />
  if ('error' in doc) return <FileCard url={url} title={title} why={`Could not read it here (${doc.error}).`} />
  const body = (
    <div className="wk-doc turn-body">
      {plain ? <pre className="wk-plain">{doc.text}</pre> : <Prose src={doc.text} scope={scope} />}
      {doc.cut && big && <p className="wk-quiet">This document is longer than Fluid draws; open the file for the rest.</p>}
    </div>
  )
  return big ? body : <div className="wk-dclip">{body}</div>
}

/* -- a file, as Classic draws one (B3) ------------------------------------------ */

/** What the server says stands behind a ref (`?describe=1`): asked once per
 *  ref while a card shows it, and kept for the page. */
type About = { size?: number | null; state?: string; treatment?: { view?: string; content_type?: string } }
const abouts = new Map<string, About | 'asking' | 'failed'>()
const aboutHeard = new Set<() => void>()
function ask(url: string) {
  if (abouts.has(url)) return
  abouts.set(url, 'asking')
  fluidFetch(url + '?describe=1', { headers: { ...CLIENT_HEADERS } })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((d: About) => { abouts.set(url, d) }, () => { abouts.set(url, 'failed') })
    .finally(() => aboutHeard.forEach((fn) => fn()))
}
function useAbout(url: string): About | null {
  useEffect(() => ask(url), [url])
  const got = useSyncExternalStore((fn) => { aboutHeard.add(fn); return () => { aboutHeard.delete(fn) } }, () => abouts.get(url))
  return got && typeof got === 'object' ? got : null
}
const sizeWords = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB` : `${(n / 1048576).toFixed(1)} MB`
/** What a held artifact's state says when it has no bytes to give. */
const STATE_WORDS: Record<string, string> = {
  purged: 'purged', 'not-held': 'not held', unknown: 'not found', 'held-but-missing': 'missing', 'held-but-corrupt': 'damaged',
}

function FileCard({ url, title, why, o }: { url: string; title: string; why?: string; o?: PostObjectEntry }) {
  const about = useAbout(url)
  const is = o ? kindOf(o) : null
  const badge = is?.badge ?? (/\.([a-z0-9]{1,5})$/i.exec(title)?.[1]?.toUpperCase() ?? 'FILE')
  const tone = is?.tone ?? 'txt'
  const state = about?.state && about.state !== 'held' ? STATE_WORDS[about.state] ?? about.state : null
  const sub = why ?? [is?.word ?? 'file', state ?? (about?.size != null ? sizeWords(about.size) : null)].filter(Boolean).join(' · ')
  const stop = (e: React.MouseEvent) => e.stopPropagation()
  return (
    <div className="wk-filecard" data-tone={tone}>
      <span className={'wk-fbadge wk-tone-' + tone} aria-hidden="true">{badge}</span>
      <span className="wk-ftext">
        <span className="wk-filename" title={title}>{title}</span>
        <span className="wk-fsub">{sub}</span>
      </span>
      <span className="wk-facts">
        <a className="wk-file" href={url} target="_blank" rel="noreferrer" title={`open ${title}`} aria-label={`Open ${title}`} onClick={stop}>Open</a>
        {!state && (
          <a className="wk-file wk-fdown" href={url} download={title} title={`download ${title}`} aria-label={`Download ${title}`} onClick={stop}>{'↓'}</a>
        )}
      </span>
    </div>
  )
}

/* -- a link (B6) and a video link (B5) ------------------------------------------ */

/** A link: where it goes, its domain, and the way out. The href is the
 *  browser's own reading of the URL (`safeHref`), never the string. Its
 *  words are its title, which every card, detail and page already shows
 *  over it, so they are not said twice. */
function LinkBody({ o }: { o: PostObjectEntry }) {
  const l = o.link!
  const href = safeHref(l.url)
  const words = l.url.replace(/^https?:\/\//i, '').replace(/^www\./i, '')
  return (
    <div className="wk-link" data-domain={l.domain}>
      <span className="wk-lglyph" aria-hidden="true">
        <svg viewBox="0 0 16 16" width="16" height="16"><path d="M6.5 9.5l3-3M7 4.5l1.2-1.2a2.6 2.6 0 0 1 3.7 3.7L10.7 8.2M9 11.5l-1.2 1.2a2.6 2.6 0 0 1-3.7-3.7L5.3 7.8" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
      </span>
      <span className="wk-ltext">
        <span className="wk-lwords">{words}</span>
        <span className="wk-ldomain">{l.domain}</span>
      </span>
      {href
        ? <a className="wk-file" href={href} target="_blank" rel="noreferrer noopener" title={`open ${l.url} in a new tab`}
            aria-label={`Open ${words} (${l.domain}) in a new tab`} onClick={(e) => e.stopPropagation()}>{'Open ↗'}</a>
        : <span className="wk-quiet" title="not a link: only http and https addresses are followed">not followed</span>}
    </div>
  )
}

/* NOTHING LEAVES THIS MACHINE UNTIL SOMEBODY PRESSES PLAY (Classic's
   surfaces/VideoPreviews.tsx, whose reasons are its own): the plate is drawn
   from CSS, no thumbnail is asked of Google, and the player comes from
   youtube-nocookie.com only on that press, with no referrer and Classic's
   sandbox. A plate that is only a picture of the object (a gallery plate)
   is not pressed: it opens the object. */
function VideoBody({ o, still }: { o: PostObjectEntry; still?: boolean }) {
  const l = o.link!
  const [playing, setPlaying] = useState(false)
  const said = l.label ?? l.url
  const href = safeHref(l.url)
  return (
    <figure className="wk-video" onClick={(e) => { if (playing) e.stopPropagation() }}>
      {playing ? (
        <iframe className="wk-vframe" title={said}
          src={`https://www.youtube-nocookie.com/embed/${l.video}?autoplay=1`}
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowFullScreen
          referrerPolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-presentation allow-popups" />
      ) : still ? (
        <span className="wk-vplate"><span className="wk-vplay" aria-hidden="true">{'▶'}</span><span className="wk-vid">{l.video}</span></span>
      ) : (
        <button className="wk-vplate" data-act="play" title="load the player and play it here" aria-label={`play ${said}`}
          onClick={(e) => { e.stopPropagation(); setPlaying(true) }}>
          <span className="wk-vplay" aria-hidden="true">{'▶'}</span>
          <span className="wk-vid">{l.video}</span>
        </button>
      )}
      {!still && (
        <figcaption className="wk-vcap">
          {/* Its title is the card's, the detail's or the page's own, over
              it; the caption is only the way to YouTube. */}
          <a href={href ?? undefined} target="_blank" rel="noreferrer noopener" title="open on YouTube" onClick={(e) => e.stopPropagation()}>
            {'Watch on YouTube ↗'}
          </a>
        </figcaption>
      )}
    </figure>
  )
}

/** `big` is the detail's and a page's rendering. `size` (stream C, present/)
 *  is the size the space it was given allows: a chart or a table is drawn
 *  at it, and only a large table is drawn unclipped. */
export default function ObjectBody({ o, big, size, still }: {
  o: PostObjectEntry; big?: boolean; size?: 'compact' | 'medium' | 'large'
  /** drawn as a picture of itself (a gallery plate): nothing in it is pressed */
  still?: boolean
}) {
  const post = usePost(o.post)
  const text = o.part !== null ? post?.parts[o.part]?.text : undefined
  const scope = turnPartScope(o.post, o.part ?? 0)
  const names = useMemo(() => (typeof text === 'string' ? namesFor(text, scope) : undefined), [text, scope])
  const drawn = size ?? (big ? 'large' : 'compact')
  if (o.kind === 'block' && o.block) {
    const block = <RenderableBlock block={o.block} blockKey={o.key} where={o.parent ?? scope} names={names} size={drawn} />
    /* A wide table is clipped in its card, with a fade, as the demo's is. */
    return o.type === 'table' && drawn !== 'large' ? <div className="wk-tclip">{block}</div> : block
  }
  if (o.kind === 'post-text') {
    const words = typeof text === 'string' && o.line !== null && o.end !== null
      ? text.replace(/\r\n?/g, '\n').split('\n').slice(o.line - 1, o.end).join('\n').trim() : ''
    return words ? <div className="wk-doc"><Prose src={words} scope={scope} /></div> : null
  }
  if (o.kind === 'link' && o.link) return o.link.video ? <VideoBody o={o} still={still} /> : <LinkBody o={o} />
  const url = o.artifact?.url ?? (o.ref ? `/api/artifacts/${o.ref}` : null)
  if (!url) return null
  const is = kindOf(o)
  if (is.word === 'image') return <figure className="wk-img"><img src={url} alt={o.title ?? ''} loading="lazy" /></figure>
  const doc = is.doc
  const ref = o.artifact?.ref ?? o.ref
  if (doc && ref) return <DocText docRef={ref} url={url} scope={`${scope}:doc:${o.key}`} title={o.title ?? 'document'} big={big || drawn === 'large'} plain={doc === 'plain'} />
  return <FileCard url={url} title={o.title ?? 'file'} o={o} />
}
