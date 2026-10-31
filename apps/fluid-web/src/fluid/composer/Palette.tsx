/* THE `@` AND `#` PALETTE OF THE FLUID COMPOSER (#187 #8, #442 #4).
 *
 * The text is the interface, as in production: typing `@` offers people,
 * typing `#` offers Topics and existing work, and nothing is a mode -- the
 * composer re-derives the trigger from (text, caret) with production's
 * `triggerAt`, so a paste or a click into an old mention can never leave this
 * believing something the text no longer says. Ranking is production's
 * `score` (prefix, word start, substring), never a relevance number.
 *
 * `@`: this conversation's people first (most recently involved first), each
 * saying what the record says of them -- something running now, the runtime
 * they DECLARED -- then anybody else the record holds ("brought in"), then,
 * for a name nobody has, "Summon". Enter addresses them AND asks them to work
 * (production's one selection for the ordinary thing); → chooses where it
 * runs first, with what each runtime has left; → again, the model.
 *
 * `#`: this conversation's Topics (filing the post under one), then Topics
 * elsewhere from the Topic lookup (`/fluid/api/topics`), then existing work
 * found by production's resolver (`/api/references`), then "Create topic".
 * The Topic rows and "Create" come from the lookup alone and never wait for
 * the resolver (`hashRows`). A Topic files the post; a post or a
 * conversation is only referred to -- two facts, kept apart as production
 * keeps them. */

import { Fragment, useEffect, useRef, useState } from 'react'
import { modelSays, runnable, runningNames, type ExecutionInfo, type RuntimeCapacity } from '../../composer/execution'
import { getJson, type Person, type Topic } from '../conversation/facts'
import Meters from './Meters'
import { Who } from '../identity/Who'
import type { Id } from '../store'
import { bare, hashAsks, hashRows, hashWaits, ranked, titleOf, topicAsks, type Found, type Pick, type TopicHit } from './hashRows'

export type { Pick } from './hashRows'

/** `who`: a person, drawn as everywhere in Fluid (E2), the ring if they are working now. */
interface Row { key: string; label: string; note?: string; group?: string; pick: Pick; more?: boolean; meter?: React.ReactNode; who?: { id: Id; working: boolean } }

const SUGGEST = 6
/** The Topic lookup is a name lookup: asked sooner than the full search. */
const TOPIC_PAUSE = 100
const FULL_PAUSE = 250

function declaredSays(p: Person): string | null {
  if (p.default_runtime) return `${p.default_runtime} · their default`
  if (p.runtime_mode === 'auto') return 'runtime: Mentis picks'
  return null
}

export default function Palette({ sigil, query, conversation, here, everyone, me, topics, execution, capacity, onChoose, onDismiss, bind, canCreate, creating }: {
  sigil: '@' | '#'
  query: string
  /** null: a new conversation, not made yet */
  conversation: Id | null
  /** this conversation's participants, most recently involved first */
  here: Person[]
  /** everybody the record holds (null while being read) */
  everyone: Person[] | null
  me: Id | null
  topics: Topic[]
  execution: { data: ExecutionInfo | null; loading: boolean; error?: string | null }
  capacity: { data: { capacity: Record<string, RuntimeCapacity> } | null; loading: boolean; error?: string | null }
  onChoose: (p: Pick) => void
  onDismiss: () => void
  bind: (h: (e: React.KeyboardEvent) => boolean) => void
  canCreate: boolean
  creating: boolean
}) {
  /* The selected row BY KEY, so a row arriving above it (the full answer's
     posts land above "Create topic") never moves the selection onto it. */
  const [sel, setSel] = useState<string | null>(null)
  const [level, setLevel] = useState<'name' | 'runtime' | 'model'>('name')
  const [who, setWho] = useState<Row | null>(null)
  const [rt, setRt] = useState<string | null>(null)
  /* What the record answered, and for which words: each answer is the
     answer to its `answered` only. */
  const [full, setFull] = useState<{ found: Found[]; answered: string | null }>({ found: [], answered: null })
  const [named, setNamed] = useState<{ topics: TopicHit[]; answered: string | null }>({ topics: [], answered: null })
  const list = useRef<HTMLDivElement | null>(null)
  const q = bare(query)
  const typed = q.trim()
  const asks = sigil === '#' && hashAsks(typed)
  const asksTopics = sigil === '#' && topicAsks(typed)
  /* An answer is out while the words typed are not the words it answered --
     from the first keystroke, not from when the ask goes out -- so
     "searching" and "Nothing found" are never said together. `null` is an
     answer not yet come. */
  const found = !asks ? [] : full.answered === typed ? full.found : null
  const topicHits = !asksTopics ? [] : named.answered === typed ? named.topics : null
  const searching = found === null

  /* `#` asks for Topic names first and existing work once typing pauses, as
     production asks it; each is drawn as it comes. */
  useEffect(() => {
    if (!asksTopics) return
    let live = true
    const t = window.setTimeout(() => {
      void getJson<{ topics: TopicHit[] }>(`/fluid/api/topics?q=${encodeURIComponent(typed)}&limit=8`)
        .then((r) => { if (live) setNamed({ topics: r.topics ?? [], answered: typed }) })
        .catch(() => { if (live) setNamed({ topics: [], answered: typed }) })
    }, TOPIC_PAUSE)
    return () => { live = false; clearTimeout(t) }
  }, [asksTopics, typed])
  useEffect(() => {
    if (!asks) return
    let live = true
    const t = window.setTimeout(() => {
      void getJson<{ found: Found[] }>(`/api/references?q=${encodeURIComponent(typed)}${conversation ? `&conversation=${encodeURIComponent(conversation)}` : ''}&limit=8`)
        .then((r) => { if (live) setFull({ found: r.found ?? [], answered: typed }) })
        .catch(() => { if (live) setFull({ found: [], answered: typed }) })
    }, FULL_PAUSE)
    return () => { live = false; clearTimeout(t) }
  }, [asks, typed, conversation])
  useEffect(() => { setSel(null) }, [q, level, sigil])
  useEffect(() => { setLevel('name'); setWho(null) }, [sigil, q])

  const running = runningNames(execution.data)
  const rows: Row[] = []
  if (level === 'name' && sigil === '@') {
    const mine = here.filter((p) => p.participant !== me)
    const near = (q ? ranked(mine, (p) => bare(p.alias), q) : mine).slice(0, q ? 12 : SUGGEST)
    for (const p of near) {
      const busy = running.has(bare(p.alias).toLowerCase()) || running.has(p.alias.toLowerCase())
      const notes = [busy ? 'working now' : null, declaredSays(p)].filter(Boolean)
      rows.push({ key: p.participant, label: p.alias, note: notes.join(' · ') || 'in this conversation', group: 'In this conversation', more: true,
        who: { id: p.participant, working: busy },
        pick: { kind: 'person', participant: p.participant, alias: p.alias, dispatch: true } })
    }
    if (q) {
      const ids = new Set(mine.map((p) => p.participant))
      const others = ranked((everyone ?? []).filter((p) => !ids.has(p.participant) && p.participant !== me), (p) => bare(p.alias), q).slice(0, 5)
      for (const p of others)
        rows.push({ key: p.participant, label: p.alias, note: [conversation ? 'not here yet: brought in' : 'brought in with your first post', declaredSays(p)].filter(Boolean).join(' · '), group: 'Elsewhere in the record', more: true,
          who: { id: p.participant, working: false },
          pick: { kind: 'person', participant: p.participant, alias: p.alias, dispatch: true, joining: true } })
      const exact = [...mine, ...(everyone ?? [])].some((p) => bare(p.alias).toLowerCase() === q.toLowerCase())
      if (!exact && /^[\w.-]+$/.test(q))
        rows.push({ key: 'summon', label: `Summon @${titleOf(q)}`, note: conversation ? 'a new name, brought into this conversation' : 'a new name, brought in with your first post', group: 'New', more: true,
          pick: { kind: 'summon', alias: '@' + titleOf(q), dispatch: true } })
    }
  } else if (level === 'name') {
    rows.push(...hashRows({ q, topics, topicHits, found, conversation, canCreate, creating }))
  } else if (level === 'runtime' && who) {
    const base = who.pick as Extract<Pick, { kind: 'person' | 'summon' }>
    rows.push({ key: 'decide', label: 'Let Mentis decide', note: 'its selection picks, and says what informed it', pick: { ...base, runtime: undefined } })
    for (const r of runnable(execution.data))
      rows.push({ key: r.kind, label: r.kind, note: r.version ?? undefined, more: r.models.length > 0,
        meter: <Meters runtime={r.kind} capacity={capacity.data?.capacity?.[r.kind]} loading={capacity.loading} failed={!!capacity.error} />,
        pick: { ...base, runtime: r.kind } })
  } else if (level === 'model' && who && rt) {
    const base = who.pick as Extract<Pick, { kind: 'person' | 'summon' }>
    const r = runnable(execution.data).find((x) => x.kind === rt)
    rows.push({ key: 'any', label: `Any ${rt} model`, note: 'the runtime\'s own default', pick: { ...base, runtime: rt } })
    for (const m of r?.models ?? []) rows.push({ key: m.slug, label: m.name, note: modelSays(m, rt), pick: { ...base, runtime: rt, model: m.slug } })
  }

  const n = rows.length
  const at = Math.max(0, rows.findIndex((r) => r.key === sel))
  const cur = rows[at]
  const setAt = (f: (i: number) => number) => { if (n) setSel(rows[f(at)].key) }
  const deeper = (row: Row | undefined) => {
    if (!row?.more) return false
    if (level === 'name') { setWho(row); setLevel('runtime'); return true }
    if (level === 'runtime' && row.key !== 'decide') { setRt(row.key); setLevel('model'); return true }
    return false
  }
  bind((e) => {
    if (e.key === 'ArrowDown') { setAt((i) => (n ? (i + 1) % n : 0)); return true }
    if (e.key === 'ArrowUp') { setAt((i) => (n ? (i - 1 + n) % n : 0)); return true }
    if (e.key === 'ArrowRight' && level !== 'model') return deeper(cur)
    if (e.key === 'ArrowLeft' && level !== 'name') { setLevel(level === 'model' ? 'runtime' : 'name'); return true }
    if ((e.key === 'Enter' || e.key === 'Tab') && !e.shiftKey && cur) {
      /* While the answer that decides the first row is out, Enter waits
         rather than taking whatever row is first; once the Topic lookup has
         answered, a Topic or "Create" is taken without waiting for the full search. */
      if (level === 'name' && sigil === '#' && hashWaits(typed, topicHits, found)) return true
      onChoose(cur.pick); return true
    }
    if (e.key === 'Escape') { onDismiss(); return true }
    return false
  })
  useEffect(() => { list.current?.querySelector('.on')?.scrollIntoView({ block: 'nearest' }) }, [at])

  const head = level === 'name'
    ? (sigil === '@' ? 'Address someone: Enter asks them to work · → choose where it runs' : 'Refer to a topic, a post or a conversation')
    : level === 'runtime' ? `Where ${who?.label} works: Enter picks · → a model · ← back` : `${rt}: which model · ← back`
  return (
    <div className="fc-palette" ref={list} role="listbox" aria-label={sigil === '@' ? 'people' : 'references'}>
      <p className="fc-phead">{head}</p>
      {level !== 'name' && execution.loading && <p className="fc-pnote">asking this machine what it can run…</p>}
      {level === 'name' && sigil === '#' && searching && <p className="fc-pnote">searching the record…</p>}
      {level !== 'name' && execution.error && <p className="fc-pnote">could not ask this machine what it can run: {execution.error}</p>}
      {rows.map((r, i) => (
        <Fragment key={r.key + i}>
          {r.group && (i === 0 || rows[i - 1].group !== r.group) && <div className="fc-pgroup">{r.group}</div>}
          <div className={'fc-prow' + (i === at ? ' on' : '')} role="option" aria-selected={i === at}
            onMouseEnter={() => setSel(r.key)} onMouseDown={(e) => e.preventDefault()}>
            <button className="fc-pmain" onClick={() => onChoose(r.pick)}>
              <span className="fc-plabel">{r.who ? <Who id={r.who.id} name={r.label} show="line" size={18} live working={r.who.working || undefined} /> : r.label}</span>
              {r.note && <span className="fc-pnote-i">{r.note}</span>}
              {r.meter}
            </button>
            {r.more && level !== 'model' && (
              <button className="fc-pmore" aria-label={`${r.label}: choose ${level === 'name' ? 'where it runs' : 'a model'}`}
                title={level === 'name' ? 'Choose where it runs' : 'Choose a model'} onClick={() => deeper(r)}>›</button>
            )}
          </div>
        </Fragment>
      ))}
      {n === 0 && !searching && topicHits !== null && <p className="fc-pnote">{sigil === '@' ? (everyone === null && q ? 'looking…' : 'Nobody by that name.') : q.length < 2 ? 'Type to find topics, posts and conversations.' : 'Nothing found by that.'}</p>}
    </div>
  )
}
