/* DRAG TO LINK (Fluid final W4; fluid-arrange DROP.md, the owner's
 * decisions of 2026-10-28).
 *
 * An object or a post dragged through the workspace means a different thing
 * on each destination, and each says which while it is over it:
 *
 *   section space    place it for display -- arrangement only, nothing is
 *                    written (workspace/keep.tsx, unchanged; not here)
 *   a post / reply   link it to that record: a REPLY to it (`replies_to`)
 *                    carrying the reference, after an explicit confirmation
 *   a conversation   its column, header or switcher row: Include in... for
 *                    a whole post (`conversation.include`); for an object,
 *                    Include its post, or Post a reference here
 *   a composer       a reference chip in the draft, durable only on Send
 *                    (Composer.tsx)
 *
 * DURABLE LINKING IS NEVER A SIDE EFFECT. While dragging, the target under
 * the pointer shows a soft tint and a caption chip ("Link to #5 · reply"),
 * no outline; letting go opens a small opaque confirmation at the drop point
 * in the owner's words, naming what is linked and where the original
 * remains, with Cancel. Esc during the drag is the browser's own cancel;
 * Esc in the confirmation closes it. Nothing is written until a choice is
 * pressed, and then through the ordinary doors: `POST /fluid/api/posts` and
 * the members command. Refusals are the server's words, shown as they come. */

import { useEffect, useLayoutEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import * as nav from '../nav'
import { newOp, store, type Id } from '../store'
import { DRAG, POST, dropped } from '../workspace/keep'
import { dragSnapshot } from '../focus/drag'
import { Sheet } from '../frame/Sheet'
import { personOf } from '../identity/people'
import {
  agentLine, captionOf, confirmWords, linkReplyBody, objectRefPart, referencePostBody, refusalOf, turnRefPart,
  type Dragged, type LinkTarget, type ObjectRefPart, type Words,
} from '../render/objectRef'
import '../render/objectref.css'

/* -- what is over what ------------------------------------------------------ */

interface Hover { key: string; caption: string; x: number; y: number }
interface Asking {
  target: LinkTarget
  dragged: Dragged
  x: number
  y: number
  /** said before anything is asked: the drop cannot mean anything here */
  refused?: string
  /** the server's answer, when it refused */
  error?: string
  busy?: boolean
}

let hover: Hover | null = null
let asking: Asking | null = null
let host: object | null = null
const heard = new Set<() => void>()
const emit = () => heard.forEach((fn) => fn())
const sub = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }
const setHover = (h: Hover | null) => {
  if (h?.key === hover?.key && h?.x === hover?.x && h?.y === hover?.y) return
  hover = h
  if (typeof document !== 'undefined') document.body.classList.toggle('ld-linking', !!h)
  emit()
}
const setAsking = (a: Asking | null) => { asking = a; emit() }
const useHover = () => useSyncExternalStore(sub, () => hover)
const useAsking = () => useSyncExternalStore(sub, () => asking)
if (typeof document !== 'undefined') {
  /* a drag ended anywhere, or cancelled with Esc: nothing is lit */
  document.addEventListener('dragend', () => setHover(null))
  window.addEventListener('drop', () => setHover(null), true)
}

/** Whether a drag carries something a link can be made to. */
const linkable = (e: React.DragEvent) => e.dataTransfer.types.includes(DRAG) || e.dataTransfer.types.includes(POST)
/** An edge pad of the conversation column docks, as it always did. */
const docking = () => { const t = dragSnapshot()?.target; return !!t && t.where !== 'center' }
export const keyOf = (t: LinkTarget) => (t.kind === 'post' ? 'post:' + t.post.id : 'conv:' + t.conversation)

/** What a drag let go carries, as a reference: an object (its part, from
 *  the object as the store reads it) or a whole post. Null when what it
 *  names cannot be read. */
export async function draggedOf(e: { item: { address: string } } | { post: Id }): Promise<Dragged | null> {
  if ('post' in e) {
    if (!store.posts.has(e.post)) await store.loadPosts([e.post]).catch(() => {})
    const p = store.posts.get(e.post)
    return p ? { kind: 'post', post: p } : null
  }
  const address = e.item.address
  if (!address.startsWith('live:') && !address.startsWith('exact:')) return null
  if (!store.objects.has(address)) await store.loadObject(address).catch(() => {})
  const st = store.objects.get(address)
  if (!st || !('object' in st)) return null
  const o = st.object
  if (!store.posts.has(o.post)) await store.loadPosts([o.post]).catch(() => {})
  return { kind: 'object', part: objectRefPart(o, store.posts.get(o.post)) }
}

/** The drop-target props for one post, reply or conversation: spread them
 *  on its element and add `className` to its own. */
export function useLinkDrop(target: LinkTarget | null): {
  className: string
  props: Pick<React.HTMLAttributes<HTMLElement>, 'onDragOver' | 'onDragLeave' | 'onDrop'> & { 'data-drop-caption'?: string }
} {
  const h = useHover()
  const key = target ? keyOf(target) : ''
  const over = !!target && h?.key === key
  return useMemo(() => {
    if (!target) return { className: '', props: {} }
    const caption = captionOf(target)
    return {
      className: over ? ' ld-over' : '',
      props: {
        ...(over ? { 'data-drop-caption': caption } : {}),
        onDragOver: (e: React.DragEvent<HTMLElement>) => {
          /* a composer, or a post inside this conversation, took it first */
          if (e.defaultPrevented || !linkable(e) || docking()) return
          e.preventDefault()
          e.dataTransfer.dropEffect = 'copy'
          setHover({ key, caption, x: e.clientX, y: e.clientY })
        },
        onDragLeave: (e: React.DragEvent<HTMLElement>) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null) && hover?.key === key) setHover(null)
        },
        onDrop: (e: React.DragEvent<HTMLElement>) => {
          if (e.defaultPrevented || !linkable(e) || docking()) return
          const got = dropped(e)
          if (!got) return
          e.preventDefault()
          setHover(null)
          const x = e.clientX, y = e.clientY
          void draggedOf(got).then((d) => {
            if (!d) { nav.toast({ text: 'Not linked: what was dragged could not be read.' }); return }
            setAsking({ target, dragged: d, x, y, refused: refusalOf(d, target) ?? undefined })
          })
        },
      },
    }
  }, [target, key, over])
}

/* -- the confirmation -------------------------------------------------------- */

/** Whether a participant is an agent: something declared it runs somewhere. */
const isAgent = (id: Id) => { const p = personOf(id); return !!p && (!!p.default_runtime || !!p.runtime || (!!p.runtime_mode && p.runtime_mode !== 'undeclared')) }

const said = (w: Words) => w.map((x, i) => (typeof x === 'string' ? <span key={i}>{x}</span> : <b key={i}>{x.b}</b>))

async function sendPost(body: Record<string, unknown>): Promise<{ post: Id }> {
  const res = await fluidFetch('/fluid/api/posts', {
    method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const got = await res.json().catch(() => null)
  if (!res.ok || !got || got.error) throw new Error(got?.error ?? res.statusText)
  return got
}

const refOf = (d: Dragged, here: Id | null) => (d.kind === 'object' ? d.part : turnRefPart(d.post, here, d.post.home))
const whereShown = (t: Extract<LinkTarget, { kind: 'post' }>) => t.here ?? t.post.home

/** Write what the reader chose. One choice, one write. */
async function choose(a: Asking, what: 'link' | 'link-ask' | 'include' | 'reference') {
  setAsking({ ...a, busy: true, error: undefined })
  try {
    const me = await store.loadMe()
    const t = a.target, d = a.dragged
    if (t.kind === 'post') {
      const into = whereShown(t)
      if (!into) throw new Error('that post is in no conversation')
      const got = await sendPost(linkReplyBody(refOf(d, into), t.post, me, into, newOp(), what === 'link-ask'))
      void store.posted(got.post, into, t.post.id)
      nav.toast({ text: `Linked one new reply to ${t.post.number != null ? '#' + t.post.number : 'the post'}. ${d.kind === 'object' ? 'The original stays where it is.' : 'Nothing is copied.'}` })
    } else if (what === 'include') {
      const post = d.kind === 'object' ? d.part.ref : d.post.id
      const got = await store.modifyMembers(t.conversation, me, [post])
      if (got.refused.length) throw new Error(String(got.refused[0].error ?? 'it was refused'))
      nav.toast({ text: `Included its post in ${t.name}. Nothing is moved or copied.` })
    } else if (d.kind === 'object') {
      const got = await sendPost(referencePostBody(d.part, me, t.conversation, newOp()))
      void store.posted(got.post, t.conversation, null)
      nav.toast({ text: `Posted one reference in ${t.name}. Nothing is copied.` })
    }
    setAsking(null)
  } catch (e) {
    setAsking({ ...a, busy: false, error: (e as Error).message })
  }
}

/** The legend near the pointer while a drop would link, and the
 *  confirmation once it is let go. Mounted once, by the workspace. */
export function LinkDropHost() {
  /* ONE HOST DRAWS, wherever several are mounted (the workspace and Home) */
  const me = useMemo(() => ({}), [])
  useEffect(() => {
    if (!host) { host = me; emit() }
    return () => { if (host === me) { host = null; emit() } }
  }, [me])
  const drawing = useSyncExternalStore(sub, () => host === me)
  const h = useHover()
  const a = useAsking()
  /* the drop point, as an element the confirmation is anchored under */
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const x = a?.x, y = a?.y, open = !!a
  useLayoutEffect(() => {
    if (!open || !drawing || x == null || y == null) { setAnchor(null); return }
    const el = document.createElement('span')
    el.className = 'ld-at'
    el.style.cssText = `position:fixed;left:${x}px;top:${y}px;width:1px;height:1px;pointer-events:none`
    document.body.appendChild(el)
    setAnchor(el)
    return () => { el.remove() }
  }, [x, y, open, drawing])
  if (!drawing) return null
  return (
    <>
      {h && (
        <div className="ld-legend" role="status" aria-live="polite"
          style={{ left: Math.min(window.innerWidth - 220, h.x + 14), top: Math.min(window.innerHeight - 40, h.y + 16) }}>
          {h.caption}
        </div>
      )}
      {a && anchor && (
        <Sheet anchor={anchor} onClose={() => setAsking(null)} label="confirm the link" role="dialog" className="ld-confirm">
          <Confirm a={a} />
        </Sheet>
      )}
    </>
  )
}

function Confirm({ a }: { a: Asking }) {
  const t = a.target, d = a.dragged
  if (a.refused) {
    return (
      <>
        <p className="ld-refused">{a.refused}</p>
        <div className="ld-actions"><button onClick={() => setAsking(null)}>Close</button></div>
      </>
    )
  }
  const hereName = t.kind === 'post' ? (() => { const w = whereShown(t); return w ? store.conversations.get(w)?.name ?? null : null })() : null
  const author = t.kind === 'post' ? t.post.author : null
  const agent = t.kind === 'post' && author && author !== store.me && isAgent(author) ? t.post.author_name : null
  const homeHere = t.kind === 'conversation' && d.kind === 'object' && d.part.about.home === t.conversation
  return (
    <>
      <p>{said(confirmWords(d, t, hereName))}</p>
      {agent && d.kind === 'object' && <p className="ld-agent">Link and ask: {agentLine(agent, d.part as ObjectRefPart)}</p>}
      {a.error && <p className="ld-refused" role="alert">Not done: {a.error}</p>}
      <div className="ld-actions">
        {t.kind === 'post' && <button className="go" disabled={a.busy} onClick={() => void choose(a, 'link')}>Link</button>}
        {t.kind === 'post' && agent && (
          <button disabled={a.busy} title={`Link, and ask ${agent} to work on it`} onClick={() => void choose(a, 'link-ask')}>Link and ask {agent}</button>
        )}
        {t.kind === 'conversation' && !homeHere && (
          <button className={d.kind === 'post' ? 'go' : ''} disabled={a.busy} onClick={() => void choose(a, 'include')}>
            {d.kind === 'object' ? 'Include its post' : `Include in ${t.name}`}
          </button>
        )}
        {t.kind === 'conversation' && d.kind === 'object' && (
          <button className="go" disabled={a.busy} onClick={() => void choose(a, 'reference')}>Post a reference here</button>
        )}
        <button disabled={a.busy} onClick={() => setAsking(null)}>Cancel</button>
      </div>
    </>
  )
}

/* -- for tests ------------------------------------------------------------- */
export const _state = { hover: () => hover, asking: () => asking, setAsking, setHover }
