import { createContext, useContext, useMemo, useRef, useState } from 'react'
import { said, shortId, useApi, when, type Act, type Conversation, type Id } from './api'
import { anchored, Floating } from './bits'
import AcquiredChip from './surfaces/sources/AcquiredChip'

/* ------------------------------------------------------------------------ *
 * INSPECTABLE REFERENCES.
 *
 * One component for every identifier this interface ever shows — entry ids,
 * operational ids, execution ids, artifact refs, topic ids. It stays quiet
 * until asked: hover or focus gives a compact human answer (what it is, whose
 * it is, when), click opens whatever the identifier stands for when there is
 * somewhere to go. Conversation never becomes an ID display.
 *
 * Identity is resolved from what the scope already fetched; only an `ent-`
 * the scope does not hold is read from /api/entries, and only on hover.
 * Nothing is invented for an identifier the record cannot explain.
 * ------------------------------------------------------------------------ */

export interface RefFact {
  /** what kind of thing it is, in a person's words */
  kind: string
  /** its human-readable identity */
  title: string
  by?: string | null
  at?: number | null
  note?: string | null
  /** where a click lands, when the reference stands for a Turn */
  turn?: Id | null
}

interface RefValue {
  lookup: (id: string) => RefFact | null
  openTurn?: (id: Id) => void
  /** where a click lands for an entry that is not a Turn of this scope */
  openEntry?: (id: Id) => void
}

const Ctx = createContext<RefValue>({ lookup: () => null })

interface EntryDetail {
  id: Id
  missing?: boolean
  kind: string | null
  author_alias: string | null
  at: number | null
  stands: boolean
  meaning: string | null
  body?: Record<string, unknown>
}

/** The scope's own answer about its identifiers. Built from what is already
 *  loaded, so a preview costs nothing in the ordinary case. */
export function RefIndex({
  conversation,
  acts,
  alias,
  openTurn,
  openEntry,
  children,
}: {
  conversation: Conversation | null
  acts: Act[]
  alias: (id: Id) => string | null
  openTurn?: (id: Id) => void
  openEntry?: (id: Id) => void
  children: React.ReactNode
}) {
  const value = useMemo<RefValue>(() => {
    const map = new Map<string, RefFact>()
    if (conversation) {
      map.set(conversation.id, { kind: 'conversation', title: conversation.name, note: conversation.about })
      for (const t of conversation.turns)
        map.set(t.id, {
          kind: 'turn',
          title: `Turn #${t.number} in ${conversation.name}`,
          by: t.author_alias,
          at: t.at,
          turn: t.id,
        })
      for (const t of conversation.topics)
        map.set(t.id, { kind: 'topic', title: t.name, note: t.about ?? `${t.turns} turns under it` })
      for (const p of conversation.participants)
        map.set(p.participant, { kind: 'participant', title: p.alias })
      for (const t of conversation.turns)
        for (const e of t.expectations)
          map.set(e.id, {
            kind: 'expectation',
            title: `a ${e.expects} owed by ${e.of_alias} to ${e.by_alias}`,
            note: e.response_present ? 'it arrived' : 'still owed',
            turn: t.id,
          })
    }
    /* A TURN THE FLOW NO LONGER CARRIES IS STILL A TURN. The index above is
       built from the Turns the Conversation sent, which was every Turn; it is
       a batch now, so an inline reference to anything older fell through to
       `shapeOf` and drew a truncated id labelled "record entry" instead of
       "Turn #12 in Saltmarsh". Each act states the number of the Turn it
       happened on, so the references those acts reach are named. */
    for (const a of acts) {
      if (a.turn && a.turn_number != null && !map.has(a.turn)) {
        map.set(a.turn, {
          kind: 'turn',
          title: conversation
            ? `Turn #${a.turn_number} in ${conversation.name}`
            : `Turn #${a.turn_number}`,
          turn: a.turn,
        })
      }
      map.set(a.id, {
        kind: 'operational act',
        title: `${alias(a.actor) ?? 'somebody'} ${said(a.act)}`,
        by: alias(a.actor),
        at: a.at,
        note: a.because,
        turn: a.turn,
      })
      if (a.execution && !map.has(a.execution))
        map.set(a.execution, {
          kind: 'execution',
          title: a.runtime ? `a ${a.runtime} run` : 'a run',
          by: alias(a.actor),
          at: a.at,
          turn: a.turn,
        })
      for (const x of a.about)
        if (!map.has(x) && x.startsWith('artifact:'))
          map.set(x, { kind: 'artifact', title: x.slice('artifact:'.length), by: alias(a.actor), at: a.at, note: a.because })
    }
    return { lookup: (id) => map.get(id) ?? null, openTurn, openEntry }
  }, [conversation, acts, alias, openTurn, openEntry])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

/** What an identifier's shape alone tells you — never more than that. */
function shapeOf(id: string): string {
  if (id.startsWith('artifact:')) return 'artifact reference'
  if (id.startsWith('exe-')) return 'execution'
  if (id.startsWith('opr-')) return 'operational record'
  if (id.startsWith('ent-')) return 'record entry'
  if (id.startsWith('adm-')) return 'Admission'
  return 'reference'
}

/** A quiet reference. Hover or focus explains it; click opens it when there
 *  is somewhere to open. */
export function Ref({
  id,
  n = 10,
  label,
  className,
}: {
  id: string | null | undefined
  n?: number
  /** show this instead of the truncated id — the reference stays inspectable */
  label?: React.ReactNode
  className?: string
}) {
  const { lookup, openTurn, openEntry } = useContext(Ctx)
  const [open, setOpen] = useState(false)
  const [pin, setPin] = useState(false)
  if (!id) return null
  /* AN ADMISSION IS EXPLAINED BY THE RECORD AS WHAT IT IS -- one
     observation of acquired source material, pinned, with its provenance and
     whether a newer one exists (U9), or an ordinary held artifact. The chip
     is drawn as acquired material only once the record says it is one. */
  if (id.startsWith('adm-'))
    return <AcquiredChip id={id} said={typeof label === 'string' ? label : undefined} />
  return (
    <RefBody
      id={id}
      n={n}
      label={label}
      className={className}
      lookup={lookup}
      openTurn={openTurn}
      openEntry={openEntry}
      open={open || pin}
      pin={pin}
      setOpen={setOpen}
      setPin={setPin}
    />
  )
}

function RefBody({
  id,
  n,
  label,
  className,
  lookup,
  openTurn,
  openEntry,
  open,
  pin,
  setOpen,
  setPin,
}: {
  id: string
  n: number
  label?: React.ReactNode
  className?: string
  lookup: (id: string) => RefFact | null
  openTurn?: (id: Id) => void
  openEntry?: (id: Id) => void
  open: boolean
  pin: boolean
  setOpen: (v: boolean) => void
  setPin: (v: boolean) => void
}) {
  const at = useRef<HTMLButtonElement | null>(null)
  const local = lookup(id)
  // Only an entry the scope does not already hold is read, and only once asked.
  const remote = useApi<EntryDetail>(open && !local && id.startsWith('ent-') ? `/api/entries/${id}` : null)
  const r = remote.data
  const fact: RefFact | null =
    local ??
    (r && !r.missing
      ? { kind: r.kind ?? 'record entry', title: r.meaning ?? r.kind ?? 'an entry in the record', by: r.author_alias, at: r.at }
      : null)

  /* AN ENTRY IS A PLACE TO GO. A Turn of this scope opens where it is read;
     any other entry opens in the inspector, which reads the record for it and
     says so plainly when the record holds nothing under that reference.
     Anything else has nowhere to go, so a click keeps its explanation open. */
  /* Only an entry this scope does not already explain: a Participant, Topic
     or Conversation of this scope is known here as what it is, and the
     inspector is not where those are read. */
  const inspectable = !!openEntry && !local && id.startsWith('ent-') && !(r && r.missing)
  const go = () => {
    if (fact?.turn && openTurn) openTurn(fact.turn)
    else if (inspectable) openEntry?.(id)
    else setPin(!pin)
  }

  return (
    <span className={'ref-wrap ' + (className ?? '')}>
      <button
        ref={at}
        className="ref"
        title={fact ? `${fact.kind} · ${fact.title}` : shapeOf(id)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.stopPropagation()
          go()
        }}
      >
        {label ?? shortId(id, n)}
      </button>
      {open && (
        <Floating>
        <span className="ref-pop" role="tooltip" style={anchored(at.current, 320)}>
          <span className="ref-kind">{fact?.kind ?? shapeOf(id)}</span>
          <span className="ref-title">{fact?.title ?? (remote.loading ? 'reading the record…' : 'nothing recorded under this identifier')}</span>
          {(fact?.by || fact?.at) && (
            <span className="ref-meta">
              {fact.by && <span>{fact.by}</span>}
              {fact.at ? <span>{when(fact.at)}</span> : null}
            </span>
          )}
          {fact?.note && <span className="ref-note">{fact.note}</span>}
          <span className="ref-id">{id}</span>
          {((fact?.turn && openTurn) || inspectable) && (
            <span className="ref-go">click to open it</span>
          )}
        </span>
        </Floating>
      )}
    </span>
  )
}
