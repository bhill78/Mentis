/* THE WORKSPACE, WHERE A CONVERSATION'S COLUMN GOES (Shell.tsx). Its name, what it
 * holds in the curated order, and the one composer a request starts from. Beside
 * it is the ordinary Fluid workspace: its layout, floats and Magnets are the same
 * Holder's (workspace/place.ts) under the `wsp-` key, so nothing here draws a window.
 *
 * WHERE A REQUEST GOES is the owner's rule (opr-4c31fe3cf0e8): this workspace's own
 * Conversation unless somebody names another. Selecting objects says what it may
 * read, never where it goes, and with none selected the door takes all of them. */

import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { useList } from '../conversation/hooks'
import Composer, { type WorkspaceAsking } from '../Composer'
import { store, type Id } from '../store'
import { kindOf as isOf } from '../../experimental/objectkinds'
import { dropped, carries, floatIt } from '../workspace/keep'
import { useArr, workspace } from '../workspace/place'
import { forgetSurface } from '../surface/viewState'
import { magnetAppOps } from '../surface/magnet/client'
import { classNow, useNarrow } from '../frame/narrow'
import * as nav from '../nav'
import { magnetZones, magnetIdOf } from '../surface/magnet/model'
import type { MagnetId } from '../surface/magnet/types'
import {
  OBJECT_KINDS, destinationHeld, destinationOf, destinationOptions, destinationValue, sendRequest, workspaceRequest, WorkspaceRefusal,
  type ObjectId, type RequestAnswer, type WorkspaceId,
} from './client'
import { chosenBy, placeMagnet, refusalWords, workspaceDoors } from './doors'
import ObjectRows, { kindWord, type RowActs } from './ObjectRows'
import { add, moved, openWorkspace, remove, rename, reorder, useWorkspace } from './state'
import './workspaces.css'

export const WORKSPACE_UNNAMED = 'Untitled workspace'
/** How far down the launcher's first row of discs reaches, in the page's terms. */
const DISC_ROW = 96

export default function WorkspaceColumn({ id, width }: { id: WorkspaceId; width: 'wide' | 'narrow' | 'rail' }) {
  const held = useWorkspace(id)
  const s = useSyncExternalStore(nav.subscribe, nav.snapshot)
  const m = held.manifest
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  useEffect(() => { void openWorkspace(id) }, [id])

  const run = async (act: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true)
    setNote(null)
    try { await act() } catch { /* it is `held.refusal`, drawn below */ } finally { setBusy(false) }
  }

  /* -- its name -- */
  const [naming, setNaming] = useState<string | null>(null)
  const saveName = () => {
    const name = naming?.trim()
    setNaming(null)
    if (name !== undefined && m && name !== m.name) void run(() => rename(id, name))
  }

  /* -- which objects a request reads: none selected is the whole workspace -- */
  const [selected, setSelected] = useState<ReadonlySet<ObjectId>>(() => new Set())
  const [named, setNamed] = useState('')
  const objects = m?.objects ?? []
  /* In the curated order. Removing one leaves the selection with it. */
  const chosen = useMemo(() => objects.filter((o) => selected.has(o.id)).map((o) => o.id), [objects, selected])
  /* Removing a destination leaves the choice with it too, for good: what is shown and
     what is sent stay one, and adding it back doesn't quietly name it again. */
  const destination = destinationHeld(named, objects)
  if (named !== destination) setNamed(destination)

  /* -- what the layout draws, read from the one Holder -- */
  const arr = useArr()
  const drawn = useMemo(() => new Set(workspace.key === id ? magnetZones(arr).map(magnetIdOf).filter(Boolean) : []), [arr, id])
  /* A new disc goes in the launcher's row at the page's corner, over this column.
     Its name and first row keep clear of it while one is there; moved away, or at a
     narrow width where discs are stacked, nothing is reserved. */
  const narrow = useNarrow()
  const discsOver = !narrow && !!arr.focus?.floats?.some((f) => f.min && f.y < DISC_ROW && f.x < nav.drawnConvPx(s))
  const names = useList()

  const acts: RowActs = {
    selected,
    busy,
    toggle: (oid) => setSelected((was) => { const next = new Set(was); if (!next.delete(oid)) next.add(oid); return next }),
    move: (oid, by) => void run(() => reorder(id, moved(objects.map((o) => o.id), oid, by))),
    drop: (from, onto) => {
      const order = objects.map((o) => o.id)
      void run(() => reorder(id, moved(order, from, order.indexOf(onto) - order.indexOf(from))))
    },
    remove: (oid) => {
      const o = objects.find((x) => x.id === oid)
      void run(async () => {
        await remove(id, oid)
        /* Out of the list, out of the layout: the definition and every other
           workspace's list of it stay as they are. */
        if (o?.kind === 'magnet' && drawn.has(o.ref as MagnetId)) await undraw(o.ref as MagnetId, o.ref)
      })
    },
    known: (o) => {
      if (o.kind === 'magnet') return arr.magnets?.[o.ref] ? zoneName(o.ref) : null
      if (o.kind === 'conversation' || o.kind === 'chat') return (names ?? []).find((c) => c.id === o.ref)?.name ?? store.conversations.get(o.ref)?.name ?? null
      return null
    },
    open: (o) => {
      const go = workspaceDoors()
      if (o.kind === 'magnet') {
        const mag = o.ref as MagnetId
        return drawn.has(mag)
          ? { label: 'Show', run: () => magnetAppOps.reveal(mag) }
          : { label: 'Draw here', run: () => void run(async () => {
            try { await placeMagnet(id, mag, acts.known(o) ?? o.ref) } catch (e) { setNote(`It isn’t drawn: ${refusalWords(e)}`) }
          }) }
      }
      if (o.kind === 'conversation' || o.kind === 'chat') return { label: 'Open', run: () => go.openConversation(o.ref) }
      if (o.ref.startsWith('live:')) return { label: 'Float', run: (el) => { void store.loadObject(o.ref).catch(() => {}); floatIt(o.ref, el) } }
      if (o.ref.startsWith('ent-')) return { label: 'Read', run: () => void readPost(o.ref) }
      return null
    },
  }
  const zoneName = (mag: string) => magnetZones(arr).find((z) => magnetIdOf(z) === mag)?.name ?? null
  const undraw = async (mag: MagnetId, name: string) => {
    const cls = classNow()
    try {
      await workspace.patchShared({ op: 'remove', id: mag }, cls === 'wide' ? undefined : { scope: cls })
      await workspace.forgetMagnet(mag)
      forgetSurface(mag)
    } catch (e) {
      setNote(`Taken out of the list, but ${name} is still drawn: ${refusalWords(e)}`)
    }
  }
  const readPost = async (post: Id) => {
    try {
      await store.loadPosts([post])
      const home = store.posts.get(post)?.home
      if (home) workspaceDoors().openPost(home, post)
      else setNote('That post can’t be opened from here.')
    } catch (e) { setNote(refusalWords(e)) }
  }

  /* -- adding: a Conversation or anything by its reference, or a drop -- */
  const [adding, setAdding] = useState(false)
  const [kind, setKind] = useState<string>('conversation')
  const [ref, setRef] = useState('')
  const addIt = (k: string, r: string) => void run(async () => {
    const me = await store.loadMe()
    const got = await add(id, chosenBy(me, k, r))
    if (k === 'magnet' && got.changed !== false) {
      try { await placeMagnet(id, r as MagnetId, r) } catch (e) { setNote(`Added, but it isn’t drawn yet: ${refusalWords(e)}`) }
    }
  })
  const [over, setOver] = useState(false)
  const onDrop = (e: React.DragEvent) => {
    setOver(false)
    const got = dropped(e)
    if (!got) return
    e.preventDefault()
    if ('post' in got) { addIt('evidence', got.post); return }
    /* What a card is, from what this tab holds of it; a reference, whatever it is. */
    const family = (() => { const o = store.objects.get(got.item.address); return o && 'object' in o ? isOf(o.object).family : null })()
    addIt(family === 'file' ? 'file' : family === 'media' ? 'image' : 'evidence', got.item.address)
  }

  /* -- a request from here -- */
  const [asked, setAsked] = useState<RequestAnswer | null>(null)
  const asking: WorkspaceAsking = {
    where: `workspace:${id}`,
    key: JSON.stringify([chosen, destination]),
    heading: <>Asking from <b>{m?.name || WORKSPACE_UNNAMED}</b></>,
    send: async (post, op) => {
      setAsked(null)
      try {
        const got = await sendRequest(workspaceRequest(post, id, op, { objects: chosen, destination: destinationOf(destination) }))
        setAsked(got)
        void store.posted(got.post, got.route.conversation, null)
        /* its own Conversation may have just been made */
        void openWorkspace(id)
        return got
      } catch (e) {
        if (e instanceof WorkspaceRefusal && (e.refusal === 'missing' || e.refusal === 'gone' || e.refusal === 'unreadable')) void openWorkspace(id)
        throw e
      }
    },
  }

  const name = m?.name || WORKSPACE_UNNAMED
  const shell = (body: React.ReactNode) => (
    <div className="fq-mount fq-col">
      <section className={'fx-conv fx-panel fx-' + width + ' wo-column' + (over ? ' wo-over' : '')} data-discs-over={discsOver ? '' : undefined} id="conv" aria-label={`workspace ${name}`} data-workspace={id}
        onDragOver={(e) => { if (carries(e)) { e.preventDefault(); setOver(true) } }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(false) }}
        onDrop={onDrop}>
        {body}
      </section>
    </div>
  )
  const refusal = held.refusal
  if (!m) {
    return shell(refusal
      ? <p className="wo-refusal" role="alert" data-refusal={refusal.refusal}>{refusal.message}</p>
      : <p className="fx-none fx-faint" aria-busy="true">Reading this workspace…</p>)
  }
  return shell(
    <>
      <header className="wo-head">
        {naming !== null ? (
          <form onSubmit={(e) => { e.preventDefault(); saveName() }}>
            <input autoFocus aria-label="workspace name" value={naming} placeholder={WORKSPACE_UNNAMED} onChange={(e) => setNaming(e.target.value)}
              onBlur={saveName} onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); setNaming(null) } }} />
          </form>
        ) : (
          <button className="wo-title" title="Rename this workspace" aria-label={`rename ${name}`} disabled={busy} onClick={() => setNaming(m.name)}>{name}</button>
        )}
        <span className="fx-faint wo-count">{objects.length} {objects.length === 1 ? 'object' : 'objects'}</span>
        {m.conversation && <button className="fx-ctl wo-own" title="This workspace's own Conversation, where its requests and results go" onClick={() => workspaceDoors().openConversation(m.conversation!)}>Its Conversation</button>}
      </header>
      {refusal && <p className="wo-refusal" role="alert" data-refusal={refusal.refusal}>{refusal.message}</p>}
      {held.replayed && <p className="wo-note" role="status" data-replayed>Already done: this was answered from the first time, and nothing was written again.</p>}
      {note && <p className="wo-note" role="status">{note}</p>}
      <div className="wo-body fx-conv-scroll">
        {objects.length
          ? <ObjectRows objects={objects} acts={acts} />
          : <p className="fx-none fx-faint wo-empty">Blank. Add a Conversation or a reference, or drag a post or an object here.</p>}
        {adding ? (
          <form className="wo-add" onSubmit={(e) => { e.preventDefault(); const r = ref.trim(); if (r) { addIt(kind, r); setRef('') } }}>
            <select aria-label="what kind of object" value={kind} onChange={(e) => setKind(e.target.value)}>
              {OBJECT_KINDS.map((k) => <option key={k} value={k}>{kindWord(k)}</option>)}
            </select>
            <input aria-label="its reference" list={kind === 'conversation' ? 'wo-conversations' : undefined} placeholder={kind === 'magnet' ? 'mag-…' : kind === 'conversation' ? 'ent-…' : 'its reference'}
              value={ref} onChange={(e) => setRef(e.target.value)} />
            <datalist id="wo-conversations">{(names ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</datalist>
            <button className="fx-ctl" type="submit" disabled={busy || !ref.trim()}>Add</button>
            <button className="fx-ctl" type="button" onClick={() => setAdding(false)}>Done</button>
          </form>
        ) : <button className="fx-ctl wo-add-open" onClick={() => setAdding(true)}>Add…</button>}
      </div>
      <div className="wo-ask" data-selection={chosen.length ? 'objects' : 'whole'}>
        {/* Under the composer: it closes when focus leaves it, and what is above it would
            move between a press and its release, losing the click. */}
        <Composer conversation={null} asking={asking} replyTo={null} onClearReply={() => {}} />
        <div className="wo-ask-line">
          <span data-reads>{chosen.length ? `Reads ${chosen.length} of ${objects.length} selected` : `Reads the whole workspace (${objects.length})`}</span>
          {chosen.length > 0 && <button className="fx-ctl" onClick={() => setSelected(new Set())}>Whole workspace</button>}
          <label>Result in{' '}
            <select aria-label="where its result goes" value={destination} onChange={(e) => setNamed(e.target.value)}>
              <option value="">this workspace’s Conversation</option>
              {destinationOptions(objects).map((o) => <option key={o.id} value={destinationValue(o)}>{kindWord(o.kind)} {acts.known(o) ?? o.ref}</option>)}
            </select>
          </label>
        </div>
        {asked && (
          <p className="wo-note" role="status" data-asked={asked.post} data-replayed={asked.replayed ? '' : undefined}>
            {asked.replayed ? 'Already asked: this is the first request’s answer, with the selection it was first asked with. Nothing was sent again. ' : 'Asked. '}
            <button className="fx-ctl" onClick={() => workspaceDoors().openPost(asked.route.conversation, asked.post)}>Read it</button>
          </p>
        )}
      </div>
    </>,
  )
}
