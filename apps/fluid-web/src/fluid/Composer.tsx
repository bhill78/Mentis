/* THE FLUID COMPOSER, with every capability production's has (#187 #8,
 * #442 #4, completion stream B) in the #184 demo's presentation.
 *
 * AT REST, TWO QUIET LINES: where the post goes over "Message X...". Focused,
 * a subtle strip of tools appears -- Aa formatting, + attach, @ address,
 * # refer, Use... -- with the send control integrated at its end. Nothing in
 * the strip is the only way in: `@` and `#` typed in the text open the same
 * palette the buttons do (the buttons type the sigil, as production's do),
 * formatting has production's shortcuts, and files can be dropped or pasted.
 *
 * ONE COMPOSER PER SURFACE (#188, #448). The conversation has one; every
 * thread -- slid out, pinned, or full screen -- has its own, and each says,
 * in its one header line, exactly where its post goes. They never borrow each
 * other's target, so the line is always right.
 *
 * THE MEANING OF SENDING IS PRODUCTION'S. `actionOf` reads the draft, the
 * body is `bodyOf` of the same draft, so the button and the post cannot
 * disagree: Ask Mentis / Ask @someone / Record only, and a reply records
 * unless asked otherwise. What the button adds is who acts and where: "Ask
 * @Quill on codex" (composer/words.ts). The ▾ lists the choices with what
 * each does, so the choice is visible before it is made.
 *
 * WHERE IT GOES. `POST /fluid/api/posts`, Fluid's own command door, through
 * the same domain operation as production's. Nothing is reloaded after: the
 * store follows the change feed. */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { CLIENT_HEADERS } from '../api'
import { fluidFetch } from './http'
import { Prose } from '../prose'
import {
  attachedParts,
  bodyOf,
  emptyDraft,
  isEmpty,
  shiftMarks,
  withMark,
  withRef,
  type Action,
  type Addressee,
  type Attached,
  type Draft,
} from '../composer/draft'
import { usable } from '../composer/Use'
import { useCapacity, useExecution } from '../composer/execution'
import { completeTrigger, triggerAt, type Trigger } from '../composer/trigger'
import { continueLine } from '../composer/markdown'
import * as nav from './nav'
import { store, type Id } from './store'
import { getJson, refreshFacts, useFacts, usePeople, type Person } from './conversation/facts'
import { onAsk, posted } from './conversation/threads'
import { Float } from './composer/Float'
import Palette, { type Pick } from './composer/Palette'
import SlashPalette from './composer/SlashPalette'
import TimerDialog from './composer/TimerDialog'
import FormDialog from './composer/FormDialog'
import Settings, { usePersonaNames } from './composer/Settings'
import { MARKS } from './composer/marks'
import { dropDraft, loadDraft, saveDraft } from './composer/drafts'
import { sendWords, tokenOf } from './composer/words'
import { DRAG, POST, dropped } from './workspace/keep'
import { draggedOf } from './conversation/linkDrop'
import { ObjectRefCard } from './render/ObjectRefPart'
import { agentLine, turnRefPart, type ObjectRefPart } from './render/objectRef'

interface GovernedRow { entry: Id; kind: string; summary: string; governs?: boolean }

const newOp = () => `fluid-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
const num = (id: Id | null | undefined) => {
  const n = id ? store.posts.get(id)?.number : null
  return n != null ? `#${n}` : 'a post'
}

/** A NEW CONVERSATION NOT MADE YET (owner decision D1, #599): Home's column
 *  starts empty and unsaved, and NOTHING IS WRITTEN BEFORE THE FIRST POST
 *  (opr-eaf506149e8a). A Topic created or a name brought in before then is
 *  held in the draft (`LATER`) and said there; on the first post `create`
 *  makes the conversation (an unnamed one, #562), what was held is applied
 *  to it, and the post goes in. `made` is told once the first post is in it. */
export interface Starting {
  /** `op`: the operation key, the same on every retry of one first post */
  create: (op: string) => Promise<Id>
  made: (conversation: Id) => void
}

/* What a draft holds for the first post to apply: a Topic not created yet
   (its name), and a name not brought in yet (its alias), in the places the
   real ids go once they exist. */
const LATER = { topic: 'later-topic:', name: 'later-name:' }
const later = (id: Id) => id.startsWith(LATER.topic) || id.startsWith(LATER.name)

export default function Composer({ conversation, start, replyTo, onClearReply, thread, autoFocus, onAutoFocused }: {
  /** null: a new conversation, made by `start` when it is first needed */
  conversation: Id | null
  start?: Starting
  /** the post being replied to, wherever it lives; null for a new post */
  replyTo: Id | null
  onClearReply: () => void
  /** set on a thread's own composer: the root of the thread it writes in */
  thread?: Id
  autoFocus?: boolean
  onAutoFocused?: () => void
}) {
  const where = thread ? `thread:${conversation}:${thread}` : `conversation:${conversation ?? 'new'}`
  const conv = conversation ? store.conversations.get(conversation) : undefined
  const parent = replyTo ? store.posts.get(replyTo) : undefined
  const [draft, setDraftState] = useState<Draft>(() => loadDraft(where))
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState(false)
  const [menu, setMenu] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [me, setMe] = useState<Id | null>(store.me)
  const [trigger, setTrigger] = useState<Trigger | null>(null)
  const [opened, setOpened] = useState<Id | null>(null)
  const [floating, setFloating] = useState<null | 'format' | 'use'>(null)
  const [activeHelper, setActiveHelper] = useState<'timer' | 'form' | null>(null)
  const [dragging, setDragging] = useState<false | 'file' | 'ref'>(false)
  const [creating, setCreating] = useState(false)
  const [wantRuntimes, setWantRuntimes] = useState(false)
  const box = useRef<HTMLTextAreaElement>(null)
  const files = useRef<HTMLInputElement>(null)
  const section = useRef<HTMLElement | null>(null)
  const pending = useRef<[number, number] | null>(null)
  const paletteKeys = useRef<((e: React.KeyboardEvent) => boolean) | null>(null)
  const answered = useRef<{ start: number; name: string; exact?: boolean } | null>(null)
  const anchors = useRef<Record<string, HTMLButtonElement | null>>({})
  const useAt = useRef<HTMLButtonElement | null>(null)
  const caretAt = useRef<HTMLButtonElement | null>(null)
  const menuEdge = useRef<'first' | 'last'>('first')

  /* ONE DRAFT PER PLACE, kept for the tab (composer/drafts.ts). */
  const setDraft = (fn: Draft | ((d: Draft) => Draft)) =>
    setDraftState((d) => { const next = typeof fn === 'function' ? fn(d) : fn; saveDraft(where, next); return next })
  useEffect(() => { setDraftState(loadDraft(where)); setTrigger(null); setActiveHelper(null) }, [where])

  /* ONE OPERATION KEY PER DRAFT: a retry after a lost answer is the same post.
     Settling what the draft held (below) changes the draft without anybody
     editing it, so the draft it settled to keeps the key (opr-844677304102). */
  const op = useRef(newOp())
  const settledTo = useRef<Draft | null>(null)
  const same = (a: Draft, b: Draft | null) => a === b || (!!b && JSON.stringify(a) === JSON.stringify(b))
  useEffect(() => { if (!same(draft, settledTo.current)) op.current = newOp() }, [draft, replyTo, conversation])
  /* ONE KEY FOR WHAT THE FIRST POST APPLIES: the conversation made, each Topic
     created and each name brought in are asked under it, so a retry after an
     answer that was lost is answered with what was done, never done twice
     (opr-4d9dfcd3cb67). It is the draft's until the post is in. */
  const settling = useRef(newOp())
  useEffect(() => { settling.current = newOp() }, [where])
  /* The conversation a new one became, once made: a retry, a Topic and the
     post all go into the same one, never a second. */
  const made = useRef<Id | null>(null)
  useEffect(() => { made.current = null }, [conversation])
  const ensure = async (): Promise<Id> => {
    if (conversation) return conversation
    if (!made.current) {
      if (!start) throw new Error('nowhere to write this')
      made.current = await start.create(`${settling.current}:conversation`)
    }
    return made.current
  }

  useEffect(() => {
    void store.loadMe().then((m) => setMe(m)).catch((e: Error) => setErr(e.message))
  }, [])

  /* What this machine can run, and what each runtime has left: asked only
     once something will show it (production's rule -- it is subprocess work). */
  useEffect(() => { if ((trigger && trigger.sigil === '@') || opened) setWantRuntimes(true) }, [trigger, opened])
  const ex = useExecution(wantRuntimes)
  const cap = useCapacity(wantRuntimes)
  /* Read with the conversation's posts first (deferred), but at once as soon
     as somebody is writing here: focused, a sigil typed, or a chip opened. */
  const facts = useFacts(conversation ?? made.current, !(open || trigger || opened))
  const everyone = usePeople(!!trigger && trigger.sigil === '@' && trigger.query.length > 0)

  /* This conversation's people, most recently involved first: who wrote or
     was addressed most recently, from the posts in hand -- a fact about the
     record, never a score. */
  const here: Person[] = useMemo(() => {
    const ps = facts.data?.participants ?? []
    const coll = store.collections.get('conversation:' + conversation)
    const seen = new Map<Id, number>()
    ;(coll?.items ?? []).forEach((it, i) => {
      const p = store.posts.get(it.id)
      if (!p) return
      seen.set(p.author, i)
      for (const a of p.addressed_to ?? []) seen.set(a, i)
    })
    return [...ps].sort((a, b) => (seen.get(b.participant) ?? -1) - (seen.get(a.participant) ?? -1))
  }, [facts.data, conversation, trigger])
  const declared = facts.data?.participants ?? []
  const personaName = usePersonaNames(draft.to.some((a) => !!a.persona))

  /* A reply target named from outside opens the composer on it. A thread's
     composer always has one (the thread), so it opens only when asked for
     (`onAsk`, below) -- opening a thread never takes the caret. */
  useEffect(() => { if (replyTo && !thread) { setOpen(true); box.current?.focus() } }, [replyTo, thread])
  useEffect(() => {
    if (autoFocus) { setOpen(true); box.current?.focus(); onAutoFocused?.() }
  }, [autoFocus, onAutoFocused])
  /* A thread's composer is asked for by name (Reply, in its thread). */
  useEffect(() => (thread ? onAsk((root) => { if (root === thread) { setOpen(true); box.current?.focus() } }) : undefined), [thread])

  useLayoutEffect(() => {
    if (pending.current && box.current) {
      const [s, e] = pending.current
      pending.current = null
      box.current.setSelectionRange(s, e)
      box.current.focus()
    }
  })

  /* -- what sending means, right now: production's reading of the draft. A
        reply records unless asked otherwise; a new post asks Mentis. ------ */
  const fallback: Action = replyTo || thread ? 'record-only' : 'ask-mentis'
  const words = sendWords(draft, fallback, declared)
  const placeName = conv?.name ?? (conversation ? 'this conversation' : 'a new conversation')
  const to = draft.to.map((a) => a.alias).join(', ')
  /* A REPLY IS ADDRESSED TO WHOEVER WROTE WHAT IT ANSWERS (A5b; production's
     ThreadRail): unless the draft names somebody itself -- an explicit `@`
     is the writer overriding that, and adding the author back would
     contradict them -- or the writer is answering themselves. Said in the
     line above the box, so it is never a surprise. */
  const answering = replyTo ? store.posts.get(replyTo) : undefined
  const byDefault = !!answering && !draft.to.length && !!me && answering.author !== me ? answering : null
  const parentElsewhere = parent && parent.home && parent.home !== conversation
  const heading = thread
    ? replyTo && replyTo !== thread
      ? <>Replying to <b>{num(replyTo)}</b> in the thread of {num(thread)}</>
      : parentElsewhere
        ? <>Replying in the thread of {parent!.home_name ?? 'another conversation'} {num(thread)}, in <b>{placeName}</b></>
        : <>Replying in the thread of <b>{num(thread)}</b></>
    : parent
      ? parentElsewhere
        ? <>Replying to {parent.home_name ?? 'another conversation'} {num(replyTo)}, in <b>{placeName}</b></>
        : <>Replying to <b>{num(replyTo)}</b></>
      : <>Posting to <b>{placeName}</b></>

  /* -- the text, the trigger and the marks ------------------------------- */
  const retextualise = (text: string, list: Addressee[]) => list.filter((a) => text.includes(a.alias))
  const look = (text: string, caret: number) => {
    const t = triggerAt(text, caret)
    if (!t) { answered.current = null; setTrigger(null); return }
    const a = answered.current
    const q = t.query.toLowerCase(), n = a ? a.name.toLowerCase() : ''
    setTrigger(a !== null && a.start === t.start && (a.exact ? q === n : q.startsWith(n)) ? null : t)
  }
  const setText = (text: string, caret?: [number, number]) => {
    if (caret) pending.current = caret
    setDraft((d) => ({ ...d, text, to: retextualise(text, d.to), marks: shiftMarks(d.marks, d.text, text) }))
  }
  const onChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value
    setDraft((d) => ({ ...d, text: v, to: retextualise(v, d.to), marks: shiftMarks(d.marks, d.text, v) }))
    look(v, e.target.selectionStart)
  }
  const mark = (apply: (t: string, s: number, e: number) => { text: string; start: number; end: number }) => {
    const el = box.current
    if (!el) return
    const out = apply(draft.text, el.selectionStart, el.selectionEnd)
    setText(out.text, [out.start, out.end])
  }
  /* The @ and # buttons TYPE THE SIGIL, so there is one palette and one grammar. */
  const openSigil = (sigil: '@' | '#') => {
    const el = box.current
    /* At the caret while writing; at the end when the field was not in use
       (just back from the preview, say), never inside the first word. */
    const at = el && document.activeElement === el ? el.selectionStart : draft.text.length
    const before = draft.text.slice(0, at)
    const ins = (before && !/\s$/.test(before) ? ' ' : '') + sigil
    const text = before + ins + draft.text.slice(at)
    const caret = at + ins.length
    answered.current = null
    setDraft((d) => ({ ...d, text }))
    pending.current = [caret, caret]
    setOpen(true)
    look(text, caret)
  }
  const insertBlock = (t: Trigger | null, block: string) => {
    const el = box.current
    const at = el && document.activeElement === el ? el.selectionStart : draft.text.length
    const start = t ? t.start : at
    const end = t ? t.end : at
    const before = draft.text.slice(0, start)
    const after = draft.text.slice(end)
    const padBefore = before.length > 0 && !before.endsWith('\n') ? (before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n') : ''
    const padAfter = after.length > 0 && !after.startsWith('\n') ? (after.startsWith('\n\n') ? '' : after.startsWith('\n') ? '\n' : '\n\n') : '\n'
    const inserted = padBefore + block + padAfter
    const nextText = before + inserted + after
    const nextCaret = before.length + inserted.length
    setText(nextText, [nextCaret, nextCaret])
    setTrigger(null)
    setActiveHelper(null)
    answered.current = null
    pending.current = [nextCaret, nextCaret]
    el?.focus()
  }
  const openTimer = () => {
    setOpen(true)
    setActiveHelper('timer')
    setTrigger(null)
  }
  const complete = (t: Trigger, label: string) => {
    const written = t.sigil + label.replace(/^[@#]/, '')
    try { return completeTrigger(draft.text, t, written) } catch {
      const fresh = box.current ? triggerAt(draft.text, box.current.selectionStart) : null
      return fresh ? completeTrigger(draft.text, fresh, written) : null
    }
  }
  const land = (t: Trigger, out: { caret: number }, label: string) => {
    pending.current = [out.caret, out.caret]
    answered.current = { start: t.start, name: label.replace(/^[@#]/, '') }
    setTrigger(null)
  }
  const address = (t: Trigger, next: Addressee) => {
    const out = complete(t, next.alias)
    if (!out) { setTrigger(null); return }
    setDraft((d) => ({ ...d, text: out.text, to: [...retextualise(out.text, d.to).filter((a) => a.participant !== next.participant), next] }))
    land(t, out, next.alias)
  }
  const attachTopic = (t: Trigger, id: Id, name: string) => {
    const out = complete(t, name)
    if (!out) { setTrigger(null); return }
    const written = '#' + name.replace(/^#/, '')
    setDraft((d) => ({
      ...d, text: out.text, to: retextualise(out.text, d.to),
      topics: d.topics.includes(id) ? d.topics : [...d.topics, id],
      marks: withMark(shiftMarks(d.marks, d.text, out.text), { topic: id, text: written, start: t.start }),
    }))
    land(t, out, name)
  }
  const markWork = (t: Trigger, id: Id, said: string, kind: 'conversation' | 'turn' | 'acquired') => {
    const out = complete(t, said)
    if (!out) { setTrigger(null); return }
    const written = '#' + said.replace(/^#/, '')
    setDraft((d) => ({ ...d, text: out.text, to: retextualise(out.text, d.to),
      marks: withMark(shiftMarks(d.marks, d.text, out.text), { kind, topic: id, text: written, start: t.start }) }))
    land(t, out, said)
  }
  /* A NAME FROM ELSEWHERE IS BROUGHT IN, through the conversation's own seam
     (production's onSummon): the answer says whether it was new. */
  const bringIn = async (into: Id, alias: string, op?: string) => {
    const got = await getJson<{ participant: Id; alias: string; created: boolean }>(`/api/conversations/${encodeURIComponent(into)}/participants`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(op ? { alias, author: me, op } : { alias }),
    })
    refreshFacts(into)
    return got
  }
  const createTopic = async (into: Id, name: string, op?: string) => {
    const r = await getJson<{ topic: Id; name: string }>(`/api/conversations/${encodeURIComponent(into)}/topics`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, author: me, ...(op ? { op } : {}) }),
    })
    refreshFacts(into)
    return r
  }
  /* Not made yet: nowhere to write to, so it is held in the draft. */
  const writing = conversation ?? made.current
  const choose = async (p: Pick) => {
    const t = trigger
    if (!t) return
    setErr(null)
    try {
      if (p.kind === 'topic') return attachTopic(t, p.id, p.name)
      if (p.kind === 'ref') return markWork(t, p.id, p.label, p.refKind)
      if (p.kind === 'create') {
        if (!writing) return attachTopic(t, LATER.topic + p.name, p.name)
        if (creating || !me) return
        setCreating(true)
        try {
          const r = await createTopic(writing, p.name)
          attachTopic(t, r.topic, r.name)
        } finally { setCreating(false) }
        return
      }
      if (p.kind === 'summon' || p.joining) {
        const fresh = p.kind === 'summon'
        if (!writing)
          return address(t, { participant: LATER.name + p.alias, alias: p.alias, dispatch: p.dispatch,
            summoned: fresh, newInstance: fresh, runtime: p.runtime, model: p.model })
        const got = await bringIn(writing, p.alias)
        return address(t, { participant: got.participant, alias: got.alias, dispatch: p.dispatch,
          summoned: got.created, newInstance: got.created, runtime: p.runtime, model: p.model })
      }
      address(t, { participant: p.participant, alias: p.alias, dispatch: p.dispatch, runtime: p.runtime, model: p.model })
    } catch (e) {
      setErr((e as Error).message)
      setTrigger(null)
    }
  }

  /* -- attaching: paste, drop and the picker, one path, staged at once ------ */
  const patchAttached = (id: string, patch: Partial<Attached>) =>
    setDraft((d) => ({ ...d, attached: d.attached.map((a) => (a.id === id ? { ...a, ...patch } : a)) }))
  const attach = (list: File[]) => {
    for (const f of list) {
      const id = `att-${Math.random().toString(36).slice(2)}`
      const mime = f.type || 'application/octet-stream'
      setDraft((d) => ({ ...d, attached: [...d.attached, { id, name: f.name || 'pasted', mime, size: f.size, state: 'sending',
        preview: mime.startsWith('image/') ? URL.createObjectURL(f) : undefined }] }))
      fluidFetch('/api/artifacts', { method: 'POST', headers: { 'Content-Type': mime, 'X-Mentis-Upload': '1' }, body: f })
        .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.error ?? r.statusText); patchAttached(id, { ref: j.staged, state: 'held' }) })
        .catch((e: Error) => patchAttached(id, { state: 'failed', error: e.message }))
    }
  }
  /* Something Mentis already holds, dragged from a post: referenced, not re-sent. */
  const attachHeld = (ref: string) => {
    const id = `att-${Math.random().toString(36).slice(2)}`
    setDraft((d) => (d.attached.some((a) => a.ref === ref) ? d : { ...d, attached: [...d.attached, { id, name: ref, mime: '', size: 0, ref, state: 'sending' }] }))
    fluidFetch(`/api/artifacts/${ref}?describe=1`, { headers: { ...CLIENT_HEADERS } }).then((r) => r.json()).then((d) => {
      if (d.state !== 'held') throw new Error(`Mentis does not hold that (${d.state})`)
      patchAttached(id, { name: String(d.name ?? ref), mime: String(d.claimed_media_type ?? ''), size: Number(d.size ?? 0), state: 'held',
        preview: d.treatment?.view === 'image' ? `/api/artifacts/${ref}` : undefined })
    }).catch((e: Error) => patchAttached(id, { state: 'failed', error: e.message }))
  }
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    setOpen(true)
    /* AN OBJECT OR A POST FROM FLUID IS A REFERENCE (W4, DROP.md): a chip in
       the draft, written only when it is sent. Nothing is copied. */
    const fluid = dropped(e)
    if (fluid) {
      void draggedOf(fluid).then((d) => {
        if (!d) { setErr('what was dropped could not be read, so no reference was added'); return }
        const part = d.kind === 'object' ? d.part : turnRefPart(d.post, conversation, d.post.home)
        setDraft((x) => ({ ...x, refs: withRef(x.refs, { part: { ...part } }) }))
      })
      return
    }
    const fs = [...e.dataTransfer.files]
    if (fs.length) return attach(fs)
    const uri = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain')
    const m = /\/api\/artifacts\/(adm-[0-9a-f]+)/.exec(uri ?? '')
    if (m) { try { if (new URL(uri, location.href).origin === location.origin) attachHeld(m[1]) } catch { /* not a URL */ } }
  }

  /* -- sending ------------------------------------------------------------ */
  const sending = draft.attached.some((a) => a.state === 'sending')
  /* WHAT THE DRAFT HELD, APPLIED to the conversation now made, before the
     post goes in: each name brought in, each Topic created, and its real id
     put where the held one was. Each is kept in the draft as it is done, so
     a retry after a failure does not do it twice -- and each is asked under
     the draft's settling key, so one whose answer was lost is not done twice
     either. The draft it settles to is not an edit: the post keeps its key. */
  const settle = async (d: Draft, into: Id): Promise<Draft> => {
    let cur = d
    const swap = (apply: (x: Draft) => Draft) => {
      cur = apply(cur)
      setDraft((x) => { const next = apply(x); settledTo.current = next; return next })
    }
    for (const a of d.to.filter((x) => x.participant.startsWith(LATER.name))) {
      const got = await bringIn(into, a.alias, `${settling.current}:name:${a.alias}`)
      swap((x) => ({ ...x, to: x.to.map((y) => (y.participant === a.participant
        ? { ...y, participant: got.participant, summoned: got.created, newInstance: got.created } : y)) }))
    }
    const held = new Set([...d.topics, ...d.marks.map((m) => m.topic)].filter((id) => id.startsWith(LATER.topic)))
    for (const id of held) {
      const r = await createTopic(into, id.slice(LATER.topic.length), `${settling.current}:${id}`)
      swap((x) => ({ ...x, topics: x.topics.map((y) => (y === id ? r.topic : y)),
        marks: x.marks.map((m) => (m.topic === id ? { ...m, topic: r.topic } : m)) }))
    }
    return cur
  }
  const go = async (as?: Action) => {
    if (busy || isEmpty(draft) || !me) return
    if (sending) { setErr('still sending an attachment to Mentis'); return }
    if (draft.attached.some((a) => a.state === 'failed')) { setErr('an attachment did not reach Mentis; remove it or attach it again'); return }
    setBusy(true)
    setErr(null)
    try {
      const into = await ensure()
      const settled = await settle(draft, into)
      const d = as ? { ...settled, action: as } : settled
      const built = bodyOf(d, me, d.topics, fallback)
      const answered = replyTo ? store.posts.get(replyTo) : undefined
      if (answered && !built.addressed_to.length && answered.author !== me) built.addressed_to = [answered.author]
      const body = { ...built, conversation: into, ...(replyTo ? { replies_to: replyTo } : {}), op: op.current }
      const res = await fluidFetch('/fluid/api/posts', {
        method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      const got = await res.json().catch(() => null)
      if (!res.ok || !got || got.error) throw new Error(got?.error ?? res.statusText)
      for (const a of draft.attached) if (a.preview?.startsWith('blob:')) URL.revokeObjectURL(a.preview)
      dropDraft(where)
      settling.current = newOp()
      setDraftState(emptyDraft())
      setPreview(false)
      setMenu(false)
      onClearReply()
      if (thread) posted(thread)
      /* Written while the conversation is read around an older post: the new
         post is at its newest, so the conversation goes there and reads it. */
      const held = store.collections.get('conversation:' + into)
      const away = !thread && !replyTo && !!held && held.newer > 0
      void store.posted(got.post, into, replyTo).then(() => {
        if (away) void store.loadConversation(into).then(() =>
          nav.read(into, got.post, store.posts.get(got.post)?.number ?? null))
      })
      /* A new conversation is made now, with its first post: it goes on there. */
      if (!conversation) start?.made(into)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (trigger && paletteKeys.current && paletteKeys.current(e)) { e.preventDefault(); return }
    if (e.nativeEvent.isComposing) return
    if (e.key === 'Enter' && e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); void go('record-only'); return }
    if (e.ctrlKey || e.metaKey) {
      const m = MARKS.find((x) => x.key === e.key.toLowerCase())
      if (m) { e.preventDefault(); mark(m.apply); return }
      if (e.key === 'Enter') { e.preventDefault(); void go(); return }
    }
    if (e.key === 'Enter' && e.shiftKey) {
      const out = continueLine(draft.text, e.currentTarget.selectionStart)
      if (out) { e.preventDefault(); setText(out.text, [out.start, out.end]) }
      return
    }
    if (e.key === 'Enter') { e.preventDefault(); void go(); return }
    if (e.key === 'Escape') {
      if (trigger) setTrigger(null)
      else if (activeHelper) setActiveHelper(null)
      else if (preview) setPreview(false)
      else if (menu) setMenu(false)
      else if (floating === 'format') setFloating(null)
    }
  }
  const reprobe = (e: React.SyntheticEvent<HTMLTextAreaElement>) => look(e.currentTarget.value, e.currentTarget.selectionStart)

  const closed = !open && isEmpty(draft) && (thread ? !replyTo || replyTo === thread : !replyTo)
  const topicName = (id: Id) => (id.startsWith(LATER.topic) ? id.slice(LATER.topic.length) : facts.data?.topics.find((t) => t.id === id)?.name ?? id)
  const waiting = [...draft.to.filter((a) => later(a.participant)).map((a) => a.alias), ...draft.topics.filter(later).map((t) => '#' + topicName(t))]
  const rows = Math.min(10, Math.max(2, draft.text.split('\n').length))
  const who = opened ? draft.to.find((a) => a.participant === opened) : undefined
  return (
    <section ref={section} className={'fw-composer fx-composer' + (closed ? ' fw-quiet' : '') + (dragging ? ' fc-dragging' : '') + (dragging === 'ref' ? ' ld-over' : '') + (thread ? ' fc-thread' : '')}
      aria-label={thread ? `composer for the thread of ${num(thread)}` : 'composer'} data-where={where}
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        const next = e.relatedTarget as Node | null
        if (next && (e.currentTarget.contains(next) || (next as Element).closest?.('.fx-float'))) return
        if (opened || floating || activeHelper) return
        setOpen(false); setMenu(false)
      }}
      data-drop-caption={dragging === 'ref' ? 'Insert reference' : undefined}
      onDragOver={(e) => { e.preventDefault(); const k = e.dataTransfer.types.includes(DRAG) || e.dataTransfer.types.includes(POST) ? 'ref' : 'file'; if (dragging !== k) setDragging(k) }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false) }}
      onDrop={onDrop}>
      <header className="fw-composer-head fx-lbl">
        <span className="fw-composer-where" data-destination>{heading}{to ? <>, to {to}</> : byDefault ? (
          <span className="fc-default-to" title="A reply is addressed to whoever wrote what it answers, unless you @ somebody">, to @{byDefault.author_name.replace(/^@/, '')}</span>
        ) : null}</span>
        {thread && replyTo && replyTo !== thread && (
          <button className="fw-close" aria-label="reply to the thread instead" title="Reply to the thread itself instead" onClick={onClearReply}>×</button>
        )}
        {!thread && replyTo && <button className="fw-close" aria-label="not a reply" title="Post on its own instead" onClick={onClearReply}>×</button>}
      </header>
      {!closed && (draft.to.length > 0 || draft.topics.length > 0) && (
        <div className="fw-composer-to">
          {draft.to.map((a) => (
            <span key={a.participant} className={'fw-addressee' + (a.dispatch ? ' working' : '')}>
              <button ref={(el) => { anchors.current[a.participant] = el }} aria-expanded={opened === a.participant}
                title={a.dispatch ? 'Will be asked to work: open to choose runtime, model, effort and persona' : 'Only addressed: open to ask them to work'}
                aria-label={`${a.alias}: ${tokenOf(a, declared, personaName)}`} onClick={() => setOpened(opened === a.participant ? null : a.participant)}>
                {a.alias}<span className="fc-token"> · {tokenOf(a, declared, personaName)}</span> ▾
              </button>
              <button aria-label={`remove ${a.alias}`} onClick={() => setDraft((d) => ({ ...d, to: d.to.filter((x) => x.participant !== a.participant) }))}>×</button>
            </span>
          ))}
          {draft.topics.map((t) => (
            <span key={t} className="fw-addressee fc-topic">
              <span className="fc-under">under #{topicName(t)}</span>
              <button aria-label={`not under ${topicName(t)}`} onClick={() => setDraft((d) => ({ ...d, topics: d.topics.filter((x) => x !== t) }))}>×</button>
            </span>
          ))}
          {waiting.length > 0 && (
            <p className="fw-meta fc-later" data-later={waiting.length}>
              With your first post: {waiting.join(', ')}. Nothing is written before it.
            </p>
          )}
        </div>
      )}
      {/* ATTACHMENTS ABOVE THE WORDS, IN ONE BOUNDED ROW (#568 2.3; production's
          order, composer/Composer.tsx). Below the text area they wrapped
          without limit and pushed the place to write out of reach; now
          however many there are, they scroll sideways in one row and the
          text area stays beside Send. */}
      {draft.attached.length > 0 && !closed && (
        <div className="fw-composer-attached fc-attached" role="group" aria-label={`${draft.attached.length} attached`}>
          {(draft.attached.length > 3 || attachedParts(draft.attached).length !== draft.attached.length) && (
            <span className="fw-meta fc-att-count">
              {draft.attached.length}{attachedParts(draft.attached).length !== draft.attached.length ? ' · staging…' : ''}
            </span>
          )}
          <div className="fc-att-strip">
            {draft.attached.map((a) => (
              <span key={a.id} className={'fw-chip' + (a.state === 'failed' ? ' failed' : '')} title={a.error ?? (a.state === 'held' ? `${a.name} · held by Mentis · ${a.ref}` : `${a.name} · ${a.state}`)} data-attached={a.state}>
                {a.preview && <img src={a.preview} alt="" className="fc-thumb" />}
                <span className="fc-att-name">{a.name}</span>{a.state === 'sending' ? ' …' : a.state === 'failed' ? ' (failed)' : ''}
                <button aria-label={`remove ${a.name}`} onClick={() => setDraft((d) => ({ ...d, attached: d.attached.filter((x) => x.id !== a.id) }))}>×</button>
              </span>
            ))}
          </div>
        </div>
      )}
      {/* REFERENCES IN THE DRAFT (W4): each the original, small, saying it is
          added when you send; an agent asked to work is given each object
          the draft references, and nothing else of its post. */}
      {(draft.refs?.length ?? 0) > 0 && !closed && (
        <div className="fw-composer-attached fc-refs-wrap">
          <div className="fc-refs" role="group" aria-label={`${draft.refs!.length} ${draft.refs!.length === 1 ? 'reference' : 'references'}, added when you send`}>
            {draft.refs!.map((r, i) => {
              const remove = () => setDraft((d) => ({ ...d, refs: (d.refs ?? []).filter((_, k) => k !== i) }))
              return r.part.type === 'object'
                ? <ObjectRefCard key={`${r.part.ref}:${String(r.part.key)}`} part={r.part as unknown as ObjectRefPart} draft onRemove={remove} />
                : (
                  <span key={r.part.ref} className="or-card or-draft or-turn" title={`a reference to ${r.part.text}: added when you send`}>
                    ↗ {r.part.text}<small className="or-draft-status">added when you send</small>
                    <button type="button" className="or-remove" aria-label={`remove the reference to ${r.part.text}`} onClick={remove}>×</button>
                  </span>
                )
            })}
          </div>
          {draft.to.filter((a) => a.dispatch).slice(0, 1).flatMap((a) => (draft.refs ?? []).filter((r) => r.part.type === 'object').map((r) => (
            <p key={`${a.participant}:${r.part.ref}:${String(r.part.key)}`} className="fc-agent-line">{agentLine(a.alias, r.part as unknown as ObjectRefPart)}</p>
          )))}
        </div>
      )}
      {preview && !closed
        ? <div className="fw-composer-preview turn-body" aria-label="preview"><Prose src={draft.text || ' '} scope={`fluid-draft:${where}`} /></div>
        : (
          <textarea
            ref={box}
            className="fw-composer-field fx-in"
            rows={closed ? 1 : rows}
            placeholder={closed ? (thread ? `Reply in the thread of ${num(thread)}…` : conversation ? `Message ${placeName}…` : 'Start a new conversation…') : 'Write in Markdown… @ to address, # to refer'}
            aria-label={thread ? `write a reply in the thread of ${num(thread)}` : 'write a post'}
            value={draft.text}
            onChange={onChange}
            onSelect={reprobe}
            onClick={reprobe}
            onPaste={(e) => { const fs = [...e.clipboardData.files]; if (fs.length) { e.preventDefault(); attach(fs) } }}
            onKeyDown={onKeyDown}
          />
        )}
      {draft.use && draft.use.governed.length > 0 && !closed && (
        <div className="fw-composer-attached">
          {draft.use.governed.map((g) => (
            <span key={g} className="fw-chip" data-use={g}>
              {words.action === 'record-only' ? 'not sent (record only): ' : 'uses '}{draft.use?.said?.[g] ?? g}
              <button aria-label={`stop using ${draft.use?.said?.[g] ?? g}`} onClick={() => setDraft((d) => {
                const rest = (d.use?.governed ?? []).filter((x) => x !== g)
                return { ...d, use: rest.length ? { ...d.use!, governed: rest } : undefined }
              })}>×</button>
            </span>
          ))}
        </div>
      )}
      {dragging && <div className="fc-drop" aria-hidden="true">Drop to attach</div>}
      {/* FORMATTING IS A STRIP IN THE COMPOSER, between the words and the
          tools: drawn over them it covered the text and the "Posting to"
          line in a narrow conversation. Aa or Esc puts it away. */}
      {floating === 'format' && !closed && (
        <div className="fc-format-strip" role="group" aria-label="formatting">
          <div className="fc-format" role="toolbar" aria-label="formatting tools">
            {MARKS.map((m) => (
              <button key={m.key} aria-label={m.label} title={`${m.label} · ${m.chord}`} onMouseDown={(e) => e.preventDefault()}
                onClick={() => mark(m.apply)}>{m.glyph}</button>
            ))}
            <span className="fc-rule" />
            <button aria-pressed={preview} className={preview ? 'on' : ''} aria-label={preview ? 'Back to writing' : 'Preview'} title={preview ? 'Back to writing' : 'Preview the Markdown'}
              onMouseDown={(e) => e.preventDefault()} onClick={() => { setPreview((p) => !p); setFloating(null) }}>{preview ? '✎' : '👁'}</button>
          </div>
          <p className="fc-hint"><kbd>ctrl B</kbd> bold · <kbd>ctrl I</kbd> italic · <kbd>ctrl K</kbd> link · <kbd>@</kbd> someone · <kbd>#</kbd> a topic</p>
        </div>
      )}
      {!closed && (
        <div className="fw-composer-row">
          <div className="fw-tools" role="toolbar" aria-label="tools">
            <button className={floating === 'format' || preview ? 'on' : ''} aria-expanded={floating === 'format'} aria-label="format" title="Formatting and preview"
              onMouseDown={(e) => e.preventDefault()} onClick={() => setFloating(floating === 'format' ? null : 'format')}>Aa</button>
            <button aria-label="attach" title="Attach a file (or drop one here)" onClick={() => files.current?.click()}>+</button>
            <button className={trigger?.sigil === '@' ? 'on' : ''} aria-label="address" title="Address somebody (or type @)" onMouseDown={(e) => e.preventDefault()} onClick={() => openSigil('@')}>@</button>
            <button className={trigger?.sigil === '#' ? 'on' : ''} aria-label="reference" title="Refer to a topic, a post or a conversation (or type #)" onMouseDown={(e) => e.preventDefault()} onClick={() => openSigil('#')}>#</button>
            <button className={activeHelper === 'timer' || trigger?.sigil === '/' ? 'on' : ''} aria-label="timer" title="Insert timer: Pomodoro, Stopwatch, Timebox (or type /timer)" onMouseDown={(e) => e.preventDefault()} onClick={openTimer}>⏱</button>
            <button ref={useAt} className={floating === 'use' ? 'on' : ''} aria-expanded={floating === 'use'} aria-label="use" title="Use… name the governed material this work is done under"
              onClick={() => setFloating(floating === 'use' ? null : 'use')}>Use…</button>
            <input ref={files} type="file" multiple hidden onChange={(e) => { attach([...(e.target.files ?? [])]); e.target.value = '' }} />
          </div>
          {err && <span className="fw-error" role="status">{err}</span>}
          <div className={'fw-send' + (words.action === 'ask-participant' ? ' live' : '') + (words.action === 'record-only' ? ' fc-record' : '')} data-action={words.action}>
            <button className="fw-send-main" disabled={busy || isEmpty(draft) || !me}
              title={`${words.why} Enter sends; Alt+Enter: record only.`}
              onMouseDown={(e) => e.preventDefault()} onClick={() => void go()}>
              {busy ? 'Sending…' : words.label}
            </button>
            <button ref={caretAt} className="fw-send-caret" aria-label="Choose what sending does" title="Choose what sending does" aria-haspopup="menu" aria-expanded={menu}
              onKeyDown={(e) => {
                if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
                e.preventDefault(); menuEdge.current = e.key === 'ArrowUp' ? 'last' : 'first'; setMenu(true)
              }}
              onMouseDown={(e) => e.preventDefault()} onClick={() => { menuEdge.current = 'first'; setMenu((m) => !m) }}>▾</button>
            {/* In the frame's layer, like the composer's other panels: a
                thread's sheet clipped it, "Record only" cut off below. */}
            {menu && (
              <Float at={caretAt.current} width={360} align="end" label="ways to send" onClose={() => { setMenu(false); caretAt.current?.focus() }}>
              <SendMenu edge={menuEdge.current} opener={caretAt.current} close={() => setMenu(false)}>
                <p className="fw-meta fc-menu-head">What sending this does</p>
                <SendRow on={words.action === 'ask-mentis'} name="Ask Mentis" why="Mentis records what is owed and assigns it; you pick no runtime"
                  pick={() => { setDraft((d) => ({ ...d, action: 'ask-mentis', to: d.to.map((a) => ({ ...a, dispatch: false })) })); setMenu(false) }} />
                {draft.to.length > 0 && (() => {
                  const w = sendWords({ ...draft, action: undefined, to: draft.to.map((a, i) => (draft.to.some((x) => x.dispatch) ? a : i === 0 ? { ...a, dispatch: true } : a)) }, fallback, declared)
                  return <SendRow on={words.action === 'ask-participant'} name={w.label} why={w.why}
                    pick={() => { setDraft((d) => ({ ...d, action: undefined, to: d.to.some((a) => a.dispatch) ? d.to : d.to.map((a, i) => (i === 0 ? { ...a, dispatch: true } : a)) })); setMenu(false) }} />
                })()}
                <SendRow on={false} name="Ask someone…" why="type @ to choose who, and where their work runs"
                  pick={() => { setMenu(false); openSigil('@') }} />
                <SendRow on={words.action === 'record-only'} name="Record only" why="nobody is asked, nothing runs (Alt+Enter)"
                  pick={() => { setDraft((d) => ({ ...d, action: 'record-only' })); setMenu(false) }} />
                <p className="fw-meta">This choice is for this message only.</p>
              </SendMenu>
              </Float>
            )}
          </div>
        </div>
      )}
      {((trigger?.sigil === '/' && !activeHelper) || activeHelper) && !closed && (
        <Float at={box.current} width={380} label={activeHelper ? `${activeHelper} helper` : 'slash commands'} keepOpenOn={box.current}
          onClose={() => {
            if (trigger?.sigil === '/') {
              answered.current = { start: trigger.start, name: trigger.query, exact: true }
              setTrigger(null)
            }
            setActiveHelper(null)
          }}>
          {activeHelper === 'timer' ? (
            <TimerDialog
              query={trigger?.sigil === '/' ? trigger.query : 'timer'}
              conversation={conversation ?? made.current}
              convName={conv?.name ?? placeName}
              replyTo={replyTo}
              parent={parent}
              existingText={draft.text}
              onInsert={(block) => insertBlock(trigger?.sigil === '/' ? trigger : null, block)}
              onClose={() => {
                if (trigger?.sigil === '/') {
                  answered.current = { start: trigger.start, name: trigger.query, exact: true }
                  setTrigger(null)
                }
                setActiveHelper(null)
                box.current?.focus()
              }}
              bind={(h) => { paletteKeys.current = h }}
            />
          ) : activeHelper === 'form' ? (
            <FormDialog
              conversation={conversation ?? made.current}
              convName={conv?.name ?? placeName}
              replyTo={replyTo}
              parent={parent}
              existingText={draft.text}
              onInsert={(block) => insertBlock(trigger?.sigil === '/' ? trigger : null, block)}
              onClose={() => {
                if (trigger?.sigil === '/') {
                  answered.current = { start: trigger.start, name: trigger.query, exact: true }
                  setTrigger(null)
                }
                setActiveHelper(null)
                box.current?.focus()
              }}
              bind={(h) => { paletteKeys.current = h }}
            />
          ) : (
            <SlashPalette
              query={trigger?.query ?? ''}
              onSelect={(cmdId) => {
                if (cmdId === 'timer') setActiveHelper('timer')
                else if (cmdId === 'form') setActiveHelper('form')
              }}
              onDismiss={() => {
                if (trigger?.sigil === '/') {
                  answered.current = { start: trigger.start, name: trigger.query, exact: true }
                  setTrigger(null)
                }
                setActiveHelper(null)
                box.current?.focus()
              }}
              bind={(h) => { paletteKeys.current = h }}
            />
          )}
        </Float>
      )}
      {trigger && trigger.sigil !== '/' && !closed && (
        <Float at={box.current} width={380} label={trigger.sigil === '@' ? 'address someone' : 'refer to something'} keepOpenOn={box.current}
          onClose={() => { answered.current = { start: trigger.start, name: trigger.query, exact: true }; setTrigger(null) }}>
          <Palette sigil={trigger.sigil} query={trigger.query} conversation={conversation ?? made.current} here={here} everyone={everyone.data} me={me}
            topics={facts.data?.topics ?? []} execution={ex} capacity={cap} onChoose={(p) => void choose(p)}
            canCreate={!!me} creating={creating}
            onDismiss={() => { answered.current = { start: trigger.start, name: trigger.query, exact: true }; setTrigger(null) }}
            bind={(h) => { paletteKeys.current = h }} />
        </Float>
      )}
      {who && (
        <Float at={anchors.current[who.participant] ?? null} width={380} label={`${who.alias}: how the work runs`}
          onClose={() => { setOpened(null); box.current?.focus() }}>
          <Settings who={who} declared={declared} execution={ex} capacity={cap}
            onChange={(next) => setDraft((d) => ({ ...d, action: d.action === 'record-only' && next.dispatch ? undefined : d.action,
              to: d.to.map((a) => (a.participant === next.participant ? next : a)) }))} />
        </Float>
      )}
      {floating === 'use' && (
        <Float at={useAt.current} width={360} label="use" onClose={() => setFloating(null)}>
          <UsePanel chosen={draft.use?.governed ?? []}
            onChange={(governed, said) => setDraft((d) => ({ ...d, use: governed.length ? { governed, said: { ...d.use?.said, ...said } } : undefined }))} />
        </Float>
      )}
    </section>
  )
}

/** Roving focus; Tab resumes from the opener even though Float draws in the frame's layer. */
function SendMenu({ edge, opener, close, children }: {
  edge: 'first' | 'last'; opener: HTMLButtonElement | null; close: () => void; children: React.ReactNode
}) {
  const menu = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const rows = menu.current?.querySelectorAll<HTMLButtonElement>('[role^="menuitem"]')
    const row = edge === 'last' ? rows?.[rows.length - 1] : rows?.[0]
    if (row) { row.tabIndex = 0; row.focus() }
  }, [edge])
  return <div ref={menu} className="fw-send-menu" role="menu" aria-label="Ways to send"
    onClick={() => { if (menu.current?.contains(document.activeElement)) opener?.focus() }}
    onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) close() }}
    onKeyDown={(e) => {
      if (e.key === 'Tab') { opener?.focus(); close(); return }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return
      e.preventDefault(); e.stopPropagation()
      const rows = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('[role^="menuitem"]')]
      const at = rows.indexOf(document.activeElement as HTMLButtonElement)
      const next = e.key === 'Home' ? 0 : e.key === 'End' ? rows.length - 1
        : (at + (e.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length
      rows.forEach((r, i) => { r.tabIndex = i === next ? 0 : -1 })
      rows[next]?.focus()
    }}>{children}</div>
}

function SendRow({ on, name, why, pick }: { on: boolean; name: string; why: string; pick: () => void }) {
  return (
    <button tabIndex={-1} role="menuitemradio" aria-checked={on} className={'fw-send-row' + (on ? ' on' : '')} onClick={pick}>
      <span className="fw-send-name">{on ? '✓ ' : ''}{name}</span>
      <span className="fw-meta">{why}</span>
    </button>
  )
}

/* Use...: standing material whose Kind directs work, as production's Use...
   offers it (`usable`), named by reference on the request. */
function UsePanel({ chosen, onChange }: { chosen: Id[]; onChange: (governed: Id[], said: Record<Id, string>) => void }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<GovernedRow[] | null>(null)
  const [said, setSaid] = useState<Record<Id, string>>({})
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    void Promise.all([
      getJson<{ kinds: Parameters<typeof usable>[1] }>('/fluid/api/governance/authoring'),
      getJson<{ groups: Record<string, GovernedRow[]> }>('/fluid/api/governed?state=standing&limit=200' + (q.trim() ? '&q=' + encodeURIComponent(q.trim()) : '')),
    ])
      .then(([k, g]) => live && setRows(usable(g.groups.standing ?? [], k.kinds) as GovernedRow[]))
      .catch((e: Error) => live && setWhy(e.message))
    return () => { live = false }
  }, [q])
  return (
    <div className="fc-use">
      <input autoFocus placeholder="Use…" aria-label="find governed material" value={q} onChange={(e) => setQ(e.target.value)} />
      {why && <p className="fw-meta">{why}</p>}
      {rows && rows.length === 0 && <p className="fw-meta">No standing material directs work{q ? ' by that name' : ''}.</p>}
      <ul>
        {(rows ?? []).map((r) => {
          const on = chosen.includes(r.entry)
          return (
            <li key={r.entry}>
              <button aria-pressed={on} className={on ? 'on' : ''} onClick={() => {
                const w = { ...said, [r.entry]: r.summary }
                setSaid(w)
                onChange(on ? chosen.filter((x) => x !== r.entry) : [...chosen, r.entry], w)
              }}>{on ? '✓ ' : ''}{r.summary} <span className="fw-meta">{r.kind}</span></button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
