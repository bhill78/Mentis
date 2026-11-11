/* Quiet's one composer, mounted through the existing dock seam.
 *
 * REUSED, NOT REBUILT (round 4, track A). Typing `@`, `#` or `/` opens the
 * Mentis composer's own palettes -- the same trigger engine
 * (`composer/trigger.ts`), the same panel (`fluid/composer/Float.tsx`), the
 * same rows (`Palette.tsx`, `SlashPalette.tsx`), the same reading of what a
 * pick means (`fluid/composer/choose.ts`, moved out of Fluid's composer for
 * this and called by it unchanged). Nothing about the palettes is written
 * twice; what is Quiet's own here is the compact row of controls, the ground
 * it is painted on, and the draft record it writes to.
 *
 * THE TEXT IS THE INTERFACE. There is no mode: whether a trigger is open is
 * re-derived from (text, caret) on every keystroke, so a paste, an undo or a
 * click into an old mention can never leave a palette believing something the
 * text no longer says. The `@` and `#` buttons TYPE THE SIGIL, exactly as
 * Fluid's do, so the button and the keystroke are one path.
 *
 * ADDRESSING IS `@` NOW. The native "Ask someone to work…" <select> is gone --
 * it could offer only this conversation's names, only one at a time, and
 * nothing else. The posting-action choice (Ask Mentis / Post only) stays,
 * presented quietly: it is a decision about what sending MEANS, which no
 * amount of addressing answers.
 *
 * Runtime/model/effort, Persona, authority and consent choices continue to be
 * made by the shared `Settings` component, opened from the addressee's chip.
 * The drafts record, the settling keys, `bodyOf` and `ACTION_WHY` are all
 * unchanged. */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { post, type Id, type Turn } from '../../api'
import { ACTION_WHY, bodyOf, emptyDraft, shiftMarks, type Addressee } from '../../composer/draft'
import { useCapacity, useExecution } from '../../composer/execution'
import { completeTrigger, triggerAt, type Trigger } from '../../composer/trigger'
import { LATER, addressed, choosePick, retextualise, retexted, topicAttached, workMarked } from '../../fluid/composer/choose'
import { Float } from '../../fluid/composer/Float'
import Palette, { type Pick } from '../../fluid/composer/Palette'
import Settings from '../../fluid/composer/Settings'
import SlashPalette from '../../fluid/composer/SlashPalette'
import { useAddressable } from '../../fluid/composer/useAddressable'
import { useWorkflows } from '../../fluid/composer/useWorkflows'
import { tokenOf, whereOf } from '../../fluid/composer/words'
import { enforcementNote } from '../../fluid/composer/execmode'
import { attachWorkflow, dropToken, type WorkflowRow } from '../../fluid/composer/workflows'
import { getJson, refreshPeopleAndTopics, usePeopleAndTopics, type Person } from '../../fluid/conversation/facts'
import { Layer } from '../../fluid/frame/layer'
import type { Draft, SetDraft } from '../contract'
import { message, settlingKey, submissionKey, type PostingAction } from '../model'
import { newDraft } from './drafts'
import './composer.css'

/** The draft, as Fluid's `bodyOf` reads one. The four palette fields are
 *  optional on a Quiet draft (contract.ts says why), and absent means empty. */
const fluidDraft = (d: Draft) => ({
  ...emptyDraft(),
  text: d.text,
  to: d.to ?? [],
  topics: d.topics ?? [],
  marks: d.marks ?? [],
  ...(d.use ? { use: d.use } : {}),
  /* `record-only` is the one posting action Quiet offers that `bodyOf` has to
     be told: Ask Mentis is its own fallback, and `ask-participant` is read off
     whoever was marked for work, never chosen separately. */
  action: d.action === 'record-only' ? ('record-only' as const) : undefined,
})

/** THE SAME BODY FLUID'S OWN COMPOSER WOULD SEND for this draft.
 *
 *  `bodyOf` reads `to` and decides `ask-participant` for itself (`record-only`,
 *  chosen explicitly, still dominates -- the same rule Fluid reads), so the
 *  dispatch array it returns carries each addressee's runtime, model and
 *  effort exactly as Fluid's cascade set them, and `topics`, `marks` and
 *  `use` travel exactly as Fluid sends them too.
 *
 *  THE ADDRESSED TOPIC IS STILL SENT EXPLICITLY, first: filing under the topic
 *  being read is the page's fact about where this post goes, and a `#` pick is
 *  the writer's own, so both are kept and neither is sent twice. */
export function draftBody(d: Draft, author: Id, conversation: Id, topic: Id | null,
  reply: Turn | null, op: string) {
  const picked = d.topics ?? []
  const topics = topic ? [topic, ...picked.filter((t) => t !== topic)] : picked
  const body = bodyOf(fluidDraft(d), author, topics)
  /* A REPLY IS ADDRESSED TO WHOEVER WROTE WHAT IT ANSWERS, unless the draft
     names somebody itself -- an explicit `@` is the writer overriding that --
     or they are answering themselves. Fluid's rule, and with nobody addressed
     it is `postingBody`'s own, field for field. */
  if (reply && !body.addressed_to.length && reply.author !== author) body.addressed_to = [reply.author]
  return { ...body, conversation, ...(reply ? { replies_to: reply.id } : {}), op }
}

/** One addressee marked for work, as the body goes out. Kept for the callers
 *  and the suites that name it; `draftBody` is what the composer sends. */
export function dispatchBody(text: string, to: Addressee, action: PostingAction, author: Id,
  conversation: Id, topic: Id | null, reply: Turn | null, op: string) {
  return draftBody({ text, action, op, to: [to] }, author, conversation, topic, reply, op)
}

/** NOTHING PICKED is the empty shape, and a draft in it submits under exactly
 *  the key it always did (`submissionKey` alone) -- so an ordinary Ask Mentis
 *  post is unchanged, down to its operation key. */
const NOTHING = JSON.stringify([[], [], [], null])
const picksOf = (d: Draft) => JSON.stringify([d.to ?? [], d.topics ?? [], d.marks ?? [], d.use ?? null])

export default function Composer({ conversation, topic, me, reply, draft, setDraft, onPosted }: {
  conversation: Id; topic: Id | null; me: Id | null; reply: Turn | null
  draft: Draft; setDraft: SetDraft; onPosted: (id: Id) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submitting = useRef(false)
  const active = useRef(true)
  const latestOp = useRef(draft.op)
  latestOp.current = draft.op
  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [])

  const to = draft.to ?? []
  const topics = draft.topics ?? []
  /** Any edit by the reader mints a new operation key, as it always has: a
   *  draft that has become a different message is a different submission. */
  const write = (next: Draft) => setDraft({ ...next, op: crypto.randomUUID() })
  /** The draft as `choose.ts`'s transforms take one, with the four fields
   *  present. Written back whole, so nothing else in it is disturbed. */
  const composing = () => ({ ...draft, to, topics, marks: draft.marks ?? [] })

  /* WHAT THE CARET IS INSIDE, re-derived, never held. */
  const [trigger, setTrigger] = useState<Trigger | null>(null)
  /** which addressee's shared Settings panel is open, by participant */
  const [opened, setOpened] = useState<Id | null>(null)
  const [creating, setCreating] = useState(false)
  const box = useRef<HTMLTextAreaElement>(null)
  const pending = useRef<[number, number] | null>(null)
  const paletteKeys = useRef<((e: React.KeyboardEvent) => boolean) | null>(null)
  /** what a palette already answered, so a landed token does not reopen it */
  const answered = useRef<{ start: number; name: string; exact?: boolean } | null>(null)
  const settingsButton = useRef<HTMLButtonElement | null>(null)
  const closeSettings = () => { setOpened(null); settingsButton.current?.focus() }
  useEffect(() => { setOpened(null); setTrigger(null); answered.current = null }, [conversation, topic, reply?.id])

  /* The conversation's people and Topics, and everybody else the record holds
     -- asked only once a palette is reachable, never on every mount (the same
     discipline execution.ts states for runtimes and capacity, below).
     WHATEVER THE DRAFT NAMES COUNTS: a Topic attached by `#` is held as its
     id, and the chip says its NAME, so dropping this read the moment the
     palette closed left the chip saying `under #ent-...`. */
  const wantWho = !!trigger || !!opened || to.length > 0 || topics.length > 0
  const facts = usePeopleAndTopics(wantWho ? conversation : null, false)
  const declared = facts.data?.participants ?? []
  const everyone = useAddressable(trigger?.sigil === '@' ? trigger.query : '')
  /* The established Workflows the `/` palette offers, read again as it opens. */
  const workflows = useWorkflows(trigger?.sigil === '/')
  /* WHO IS IN THIS CONVERSATION, most recently involved first. Quiet's stream
     is paged rather than held in a store, so the order the read gives is the
     order shown; the palette ranks by what is typed, as it does in Fluid. */
  const here: Person[] = useMemo(() => declared, [declared])

  const wantRuntimes = !!opened || trigger?.sigil === '@'
  const ex = useExecution(wantRuntimes)
  const cap = useCapacity(wantRuntimes)

  /* -- the text, the trigger and where a pick lands ----------------------- */
  useLayoutEffect(() => {
    if (pending.current && box.current) {
      const [s, e] = pending.current
      pending.current = null
      box.current.setSelectionRange(s, e)
      box.current.focus()
    }
  })
  const look = (text: string, caret: number) => {
    const t = triggerAt(text, caret)
    if (!t) { answered.current = null; setTrigger(null); return }
    const a = answered.current
    const q = t.query.toLowerCase(), n = a ? a.name.toLowerCase() : ''
    setTrigger(a !== null && a.start === t.start && (a.exact ? q === n : q.startsWith(n)) ? null : t)
  }
  const reprobe = (e: React.SyntheticEvent<HTMLTextAreaElement>) =>
    look(e.currentTarget.value, e.currentTarget.selectionStart)
  /* The @ and # buttons TYPE THE SIGIL, so there is one palette and one
     grammar: at the caret while writing, at the end when the field was not in
     use, never jammed inside the word before it. */
  const openSigil = (sigil: '@' | '#') => {
    const el = box.current
    const at = el && document.activeElement === el ? el.selectionStart : draft.text.length
    const before = draft.text.slice(0, at)
    const ins = (before && !/\s$/.test(before) ? ' ' : '') + sigil
    const text = before + ins + draft.text.slice(at)
    const caret = at + ins.length
    answered.current = null
    write({ ...draft, text })
    pending.current = [caret, caret]
    look(text, caret)
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
    write(addressed(composing(), out.text, next))
    land(t, out, next.alias)
  }
  const attachTopic = (t: Trigger, id: Id, name: string) => {
    const out = complete(t, name)
    if (!out) { setTrigger(null); return }
    write(topicAttached(composing(), t, out.text, id, name))
    land(t, out, name)
  }
  const markWork = (t: Trigger, id: Id, said: string, kind: 'conversation' | 'turn' | 'acquired') => {
    const out = complete(t, said)
    if (!out) { setTrigger(null); return }
    write(workMarked(composing(), t, out.text, id, said, kind))
    land(t, out, said)
  }
  /* A NAME FROM ELSEWHERE IS BROUGHT IN, and a Topic created, through the same
     seams Fluid's composer uses, so the palette's people and Topics are read
     again after either. Quiet always writes into a conversation that exists,
     so `LATER` never arises here -- it is reachable only from a conversation
     not made yet, which Quiet has no page for. */
  const bringIn = async (into: Id, alias: string, op?: string) => {
    const got = await getJson<{ participant: Id; alias: string; created: boolean }>(
      `/api/conversations/${encodeURIComponent(into)}/participants`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(op ? { alias, author: me, op } : { alias }) })
    refreshPeopleAndTopics(into)
    return got
  }
  const createTopic = async (into: Id, name: string, op?: string) => {
    const r = await getJson<{ topic: Id; name: string }>(
      `/api/conversations/${encodeURIComponent(into)}/topics`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, author: me, ...(op ? { op } : {}) }) })
    refreshPeopleAndTopics(into)
    return r
  }
  const choose = (p: Pick) => choosePick(p, {
    trigger, writing: conversation, me, creating, setCreating,
    setErr: setError, setTrigger, address, attachTopic, markWork, bringIn, createTopic,
  })
  /* A WORKFLOW PICKED FROM `/`: the token goes, and the Workflow is named for
     this request exactly as "Use…" names it (`draft.use`), shown by the same
     chip. Picking one already attached leaves it as it is.
     DROPPING THE TOKEN IS AN EDIT like any other, so it goes through Fluid's
     own `retexted`: everything after the token moves back by its length, and a
     `#` reference authored earlier in the line moves with it instead of being
     left pointing at the wrong characters and posted as plain text. */
  const pickWorkflow = (w: WorkflowRow) => {
    const t = trigger
    const out = t && draft.text.slice(t.start, t.end) === '/' + t.query ? dropToken(draft.text, t) : null
    const next = attachWorkflow(fluidDraft(draft), w)
    write({ ...(out ? retexted(composing(), out.text) : draft), use: next.use })
    if (out) pending.current = [out.caret, out.caret]
    answered.current = null
    setTrigger(null)
    box.current?.focus()
  }
  const dismiss = (t: Trigger) => {
    answered.current = { start: t.start, name: t.query, exact: true }
    setTrigger(null)
  }

  /* -- sending ------------------------------------------------------------ */
  const send = async () => {
    if (!me || !draft.text.trim() || submitting.current) return
    submitting.current = true
    setBusy(true)
    setError(null)
    /* The same submission asks with the key it already used (`settlingKey`).
       WHAT ONE SUBMISSION IS now includes what was picked: the same words to a
       different person, or under a different topic, is a different message and
       must not settle against the one before it. With nothing picked the key
       is exactly `submissionKey`'s, as it always was. */
    const plain = submissionKey(draft.text, draft.action, reply)
    const picks = picksOf(draft)
    const submission = picks === NOTHING ? plain : JSON.stringify([plain, picks])
    const candidate = draft.sent && draft.sent.submission !== submission && draft.sent.op === draft.op
      ? crypto.randomUUID() : draft.op
    const op = settlingKey(submission, candidate, draft.sent)
    try {
      const result = await post<{ post: Id }>('/fluid/api/posts',
        draftBody(draft, me, conversation, topic, reply, op))
      setDraft(newDraft(), draft.op)
      setOpened(null)
      setTrigger(null)
      if (active.current && latestOp.current === draft.op) onPosted(result.post)
    } catch (e) {
      // Remember what was asked, so typing these words away and back asks
      // once. Guarded on this draft's key: a newer draft is the reader's.
      setDraft({ ...draft, sent: { submission, op } }, draft.op)
      if (active.current) setError(message(e))
    }
    finally { submitting.current = false; if (active.current) setBusy(false) }
  }
  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = Math.min(el.scrollHeight, 320) + 'px'
  }, [draft.text])

  /* HOW MUCH ROOM THE DOCK IS TAKING, told to the page. Below 900px the dock
     is held to the viewport's lower edge rather than sitting in the reading
     column's flow (layout.css says why), so nothing in the flow reserves its
     height: without this the end of the stream would sit under it with no way
     to scroll it clear. The dock's measured height is what is published, so a
     chips row, a topic or the settings panel each reserve exactly what they
     added, and nothing is reserved while no composer is mounted. */
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const dock = panel.current?.closest<HTMLElement>('.qc-dock')
    const root = panel.current?.closest<HTMLElement>('.qc')
    if (!dock || !root) return
    const measure = () =>
      root.style.setProperty('--qc-dock-height', `${dock.getBoundingClientRect().height}px`)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(dock)
    return () => { observer.disconnect(); root.style.removeProperty('--qc-dock-height') }
  }, [])

  const working = to.filter((a) => a.dispatch)
  const sendLabel = busy ? 'Sending…' : draft.action === 'record-only' ? 'Post ↑'
    : working.length === 1 ? `Ask ${working[0].alias} ↑`
      : working.length > 1 ? `Ask ${working.length} people ↑` : 'Ask Mentis ↑'
  const whyAction = draft.action === 'record-only' ? 'record-only' : working.length ? 'ask-participant' : 'ask-mentis'
  const who = opened ? to.find((a) => a.participant === opened) : undefined
  const topicName = (id: Id) => facts.data?.topics.find((t) => t.id === id)?.name
    ?? (id.startsWith(LATER.topic) ? id.slice(LATER.topic.length) : id)
  const anything = !!draft.text || to.length > 0 || topics.length > 0 || !!draft.use
  /* A PLAIN DIV, NOT A FORM. `Settings.tsx` draws its own buttons with no
     `type="button"` -- it is Fluid's own, always opened in a Float outside
     any form, where a bare <button> submitting nothing is harmless. Wrapping
     it in a <form> here would make every one of its buttons a submit button
     by the HTML default, firing `send()` the moment a runtime was picked
     (found while testing the cascade: clicking "claude" posted the draft on
     the spot). Sending is one explicit click or Ctrl/⌘ Enter, never implicit. */
  return <div ref={panel} className={'qc-composer' + (anything ? ' qc-composer-writing' : '')}>
    {/* The palettes are drawn in the frame's layer (fluid/composer/Float.tsx),
        which Quiet mounts here: the dock's own box scrolls and caps its
        height, so a panel inside it would be clipped by its own composer. */}
    <Layer />
    <label htmlFor="qc-compose">{reply ? `Replying to #${reply.number} · ${reply.author_alias}` : 'Continue the conversation'}</label>
    {/* Readable, not only a `title` tooltip nobody opened -- same text, kept
        off-screen so a sighted reader keeps the compact row the owner asked
        for, and a screen reader still gets it. */}
    <p className="qc-sr-only" aria-label="what each way of sending does">
      Ask Mentis — {ACTION_WHY['ask-mentis']} Ask someone — {ACTION_WHY['ask-participant']} Post only — {ACTION_WHY['record-only']}
      {' '}Type @ to address somebody, # to refer to a topic or a post, / for a Workflow.
    </p>
    {(to.length > 0 || topics.length > 0 || !!draft.use) && (
      <div className="qc-compose-chips">
        {to.map((a) => (
          <span key={a.participant} className={'qc-compose-to' + (a.dispatch ? ' qc-working' : '')}>
            <button type="button"
              aria-expanded={opened === a.participant} aria-controls="qc-compose-settings"
              title={a.dispatch ? 'Will be asked to work: open to choose runtime, model, effort, permission and execution'
                : 'Only addressed: open to ask them to work'}
              onClick={(e) => {
                settingsButton.current = e.currentTarget
                setOpened(opened === a.participant ? null : a.participant)
              }}>
              <span>{a.alias} ▾</span><small>{tokenOf(a, declared, undefined, undefined, ex.data)}</small>
            </button>
            <button type="button" aria-label={`remove ${a.alias}`}
              onClick={() => { write({ ...draft, to: to.filter((x) => x.participant !== a.participant) }); setOpened(null) }}>×</button>
          </span>
        ))}
        {to.filter((a) => a.dispatch).map((a) => {
          /* where it matters, how Permission is enforced (the server's words) */
          const note = enforcementNote(a, whereOf(a, declared).runtime, ex.data)
          return note ? <p key={'en' + a.participant} className="qc-compose-note">{a.alias}: {note}</p> : null
        })}
        {topics.map((t) => (
          <span key={t} className="qc-compose-topic">
            <span>under #{topicName(t)}</span>
            <button type="button" aria-label={`not under ${topicName(t)}`}
              onClick={() => write({ ...draft, topics: topics.filter((x) => x !== t) })}>×</button>
          </span>
        ))}
        {(draft.use?.governed ?? []).map((g) => (
          <span key={g} className="qc-compose-use" data-use={g}>
            <span>{draft.action === 'record-only' ? 'not sent (record only): ' : 'uses '}{draft.use?.said?.[g] ?? g}</span>
            <button type="button" aria-label={`stop using ${draft.use?.said?.[g] ?? g}`} onClick={() => {
              const rest = (draft.use?.governed ?? []).filter((x) => x !== g)
              write({ ...draft, use: rest.length ? { ...draft.use!, governed: rest } : undefined })
            }}>×</button>
          </span>
        ))}
      </div>
    )}
    {/* The placeholder is unchanged: `@` and `#` are offered by the two
        buttons in the row below, by the line above for a screen reader, and by
        the palette that opens the moment either is typed -- not by crowding
        the one line Quiet rests on. */}
    <textarea ref={box} id="qc-compose" placeholder={reply ? 'Write a reply…' : 'A thought, a question, a next step…'}
      value={draft.text} disabled={busy}
      onChange={(e) => {
        const v = e.target.value
        /* Marks are MOVED by the edit and dropped where it went through them
           (`shiftMarks`), and a name deleted from the sentence is no longer
           addressed by it (`retextualise`): Fluid's own two rules. */
        write({ ...draft, text: v, to: retextualise(v, to), marks: shiftMarks(draft.marks ?? [], draft.text, v) })
        look(v, e.target.selectionStart)
      }}
      onSelect={reprobe} onClick={reprobe}
      onKeyDown={(e) => {
        if (trigger && paletteKeys.current && paletteKeys.current(e)) { e.preventDefault(); return }
        if (e.nativeEvent.isComposing) return
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void send(); return }
        if (e.key === 'Escape' && trigger) { e.stopPropagation(); dismiss(trigger) }
      }} />
    <div className="qc-compose-actions"><span className="qc-compose-hint">Ctrl / ⌘ Enter</span>
      <button type="button" className={'qc-compose-sigil' + (trigger?.sigil === '@' ? ' on' : '')} disabled={busy}
        aria-label="address" aria-pressed={trigger?.sigil === '@'} title="Address somebody (or type @)"
        onMouseDown={(e) => e.preventDefault()} onClick={() => openSigil('@')}>@</button>
      <button type="button" className={'qc-compose-sigil' + (trigger?.sigil === '#' ? ' on' : '')} disabled={busy}
        aria-label="reference" aria-pressed={trigger?.sigil === '#'} title="Refer to a topic, a post or a conversation (or type #)"
        onMouseDown={(e) => e.preventDefault()} onClick={() => openSigil('#')}>#</button>
      <select aria-label="Posting action" className="qc-compose-what" value={draft.action} disabled={busy} title={ACTION_WHY[draft.action]}
        onChange={(e) => write({ ...draft, action: e.target.value as PostingAction })}>
        <option value="ask-mentis">Ask Mentis</option><option value="record-only">Post only</option>
      </select><button type="button" className="qc-compose-send" title={ACTION_WHY[whyAction]}
        disabled={busy || !me || !draft.text.trim()} onClick={() => void send()}>{sendLabel}</button></div>
    {who && (
      <section id="qc-compose-settings" className="qc-compose-settings" aria-label="Participant settings"
        onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); closeSettings() } }}>
        <div className="qc-compose-settings-head"><span>Participant settings</span>
          <button type="button" aria-label="Close participant settings" onClick={closeSettings}>×</button>
        </div>
        <Settings who={who} declared={declared} execution={ex} capacity={cap}
          onChange={(next) => write({ ...draft, to: to.map((a) => (a.participant === next.participant ? next : a)) })} />
      </section>
    )}
    {trigger?.sigil === '/' && (
      <Float at={box.current} width={380} label="slash commands" className="qc-float" keepOpenOn={box.current}
        onClose={() => dismiss(trigger)}>
        <SlashPalette query={trigger.query} workflows={workflows} onWorkflow={pickWorkflow}
          /* The timer and form helpers are Fluid's own dialogs and insert a
             rich block Quiet's reader shows as source; Workflows are what this
             palette offers here, so a command row says so rather than
             inserting something unreadable. */
          onSelect={() => setError('Timer and form blocks are written in Fluid; here / offers the established Workflows.')}
          onDismiss={() => { dismiss(trigger); box.current?.focus() }}
          bind={(h) => { paletteKeys.current = h }} />
      </Float>
    )}
    {trigger && trigger.sigil !== '/' && (
      <Float at={box.current} width={380} className="qc-float" keepOpenOn={box.current}
        label={trigger.sigil === '@' ? 'address someone' : 'refer to something'}
        onClose={() => dismiss(trigger)}>
        <Palette sigil={trigger.sigil} query={trigger.query} conversation={conversation} here={here}
          everyone={everyone.data} me={me} topics={facts.data?.topics ?? []} execution={ex} capacity={cap}
          onChoose={(p) => void choose(p)} canCreate={!!me} creating={creating}
          onDismiss={() => { dismiss(trigger); box.current?.focus() }}
          bind={(h) => { paletteKeys.current = h }} />
      </Float>
    )}
    {!me && <p className="qc-muted">The author must be available before posting.</p>}
    {error && <p role="alert" className="qc-error">{error} Your draft is still here.</p>}
  </div>
}
