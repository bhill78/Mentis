import Bounded from './Bounded'
import { useMemo, useState } from 'react'
import {
  ago,
  useApi,
  when,
  type ContextPayload,
  type DeliveriesRead,
  type DisputeRead,
  type Id,
  type ItemHistoryRead,
  type GovLinkRead,
} from '../../api'
import { SUCCESSOR_CHIP } from './successorReach'

/* ------------------------------------------------------------------------ *
 * THE ITEM INSPECTOR'S THREE LEGS, IN THE ORDER THEY ARE READ.
 *
 * Standing, then In use, then History — and History closed. The order is the
 * claim: what the record SAYS about a thing comes before what that thing DOES
 * to work, and both come before what once happened, which is asked for and
 * does not occupy the surface until it is.
 *
 * They live beside the workspace rather than inside the inspector because the
 * inspector is one shared surface reached from everywhere, and these three
 * reads are governance's own. Nothing here branches on a Kind name.
 * ------------------------------------------------------------------------ */

/** The record's own words, short enough to sit inside a line. Material is
 *  never rewritten; it is only ever shown shorter than it is. */
const clipped = (t: string, n = 56) =>
  t.replace(/\s+/g, ' ').trim().length <= n
    ? t.replace(/\s+/g, ' ').trim()
    : t.replace(/\s+/g, ' ').trim().slice(0, n - 1) + '…'

function PlacementFact({ link, onOpenEntry }: { link: GovLinkRead; onOpenEntry: (id: Id) => void }) {
  const target = useApi<{ body: Record<string, unknown>; kind: string | null }>(`/api/entries/${link.to}`)
  const name = String(target.data?.body.name ?? target.data?.kind ?? 'the recorded location')
  return <div className="ei-aside">
    Placed in <button className="ei-link" onClick={() => onOpenEntry(link.to)}>{name}</button>
    {link.reason ? ` · ${link.reason}` : ' · no placement reason recorded'}
    <p className="ei-faint">Recorded by @{(link.by_alias ?? link.by ?? 'somebody').replace(/^@/, '')} · {when(link.at)}. Placement records where it applies; it does not confer standing.</p>
    <details><summary>Placement details</summary><pre>{JSON.stringify(link, null, 2)}</pre></details>
  </div>
}

/** A fold that starts closed unless a link asked for it open. */
export function Fold({
  title,
  open: wanted,
  children,
}: {
  title: string
  open?: boolean
  children: React.ReactNode
}) {
  const [chosen, setChosen] = useState<boolean | null>(null)
  const open = chosen ?? Boolean(wanted)
  return (
    <div className={'ei-fold' + (open ? ' open' : '')}>
      <button className="ei-fold-head" aria-expanded={open} onClick={() => setChosen(!open)}>
        <span className="caret" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        {title}
      </button>
      {open && <div className="ei-fold-body">{children}</div>}
    </div>
  )
}

/* ------------------------------------------------------------- standing --- */

export interface StandingLegProps {
  entry: Id
  /** who the material is attributed to, as the record names them */
  authorAlias: string | null
  /** and who that is, durably, so the authority line is a door and not a
   *  decoration. A Participant is a durable thing with its own room. */
  authorId: Id | null
  stands: boolean
  establishedBy: Id[]
  supersededBy: Id[]
  /** the Turn this was proposed in, where the record produced one */
  fromTurn: Id | null
  /** said instead when nothing claims to have produced it */
  provenanceWhyNot: string | null
  onOpenEntry: (id: Id) => void
  onGoToTurn?: (turn: Id) => void
  onOpenParticipant?: (participant: Id) => void
  conversationName?: string | null
  /** ANSWER THE CHALLENGE WHERE IT IS READ. Offered per open dispute, and only
   *  where the caller says it may be: the material has to still stand, and no
   *  open ask may already cover it, or the owner would be shown the same
   *  decision twice. Absent means the caller cannot offer it, which is not the
   *  same as the dispute being unanswerable — so nothing is said in its place. */
  onSetAside?: (dispute: DisputeRead) => void
  /** approve a proposed successor from the leg that reports it. The same act
   *  the timeline offers and the same dialog performs it; this is simply the
   *  other place a reader meets the proposal. Absent means the caller cannot
   *  offer it, which is not the same as the proposal being unapprovable. */
  onEstablishReplacement?: (successor: Id) => void
}

/** ON WHOSE AUTHORITY, and what is open against it.
 *
 *  WRITTEN AND ESTABLISHED ARE TWO ACTS and the record keeps them apart, so
 *  this says which of the three sentences is true rather than reducing them to
 *  one "by @X". The establishing act's own reason is quoted as it was given.
 *
 *  NO EXECUTION AND NO DELIVERY DATE APPEARS HERE. Those are the two questions
 *  below, and they open only when somebody asks them.
 *
 *  THE REFUSAL IS STATED ON THE ITEM ITSELF. There is no Edit and no Delete,
 *  and saying so where somebody is looking for one is the only place it is any
 *  use at all. */
export function StandingLeg({
  entry,
  authorAlias,
  authorId,
  stands,
  establishedBy,
  supersededBy,
  fromTurn,
  provenanceWhyNot,
  onOpenEntry,
  onGoToTurn,
  onOpenParticipant,
  conversationName,
  onSetAside,
  onEstablishReplacement,
}: StandingLegProps) {
  const hist = useApi<ItemHistoryRead>(
    '/api/governance/history?entry=' + encodeURIComponent(entry),
  )
  const challenges = useApi<{ disputes: DisputeRead[] }>(
    '/api/governance/disputes?entry=' + encodeURIComponent(entry),
  )
  const step = hist.data?.timeline?.find((t) => t.entry === entry)
  const establishing = step?.established?.[0] ?? null
  const author = (authorAlias ?? '').replace(/^@/, '')
  const establisher = (establishing?.by_alias ?? '').replace(/^@/, '')
  /* THE NAME IS A DOOR. A Participant is a durable thing with its own room,
     and the authority line is where somebody most often wants to walk into
     it. Where the record gives no id, the alias stays plain text rather than
     becoming a control that goes nowhere. */
  const who = (alias: string, id: Id | null | undefined) =>
    id && onOpenParticipant ? (
      <button className="ei-link" onClick={() => onOpenParticipant(id)}>
        @{alias}
      </button>
    ) : (
      <>@{alias}</>
    )
  const authority = !establishing ? (
    author ? (
      <>Not established {'·'} written by {who(author, authorId)}</>
    ) : (
      <>Not established</>
    )
  ) : establisher && establisher !== author ? (
    <>
      Established by {who(establisher, establishing.by)} {'·'} written by{' '}
      {who(author, authorId)}
    </>
  ) : (
    <>Written and established by {who(author || establisher, authorId ?? establishing.by)}</>
  )

  /* WHAT IS MERELY PROPOSED AGAINST IT, WHICH IS NOT WHAT ENDED IT. Read from
     the step's own `proposed`, never inferred from two items being on screen:
     `superseded_by` above is the successor that actually replaced this, and
     these have replaced nothing and reach nobody. */
  const proposedSuccessors = step?.proposed?.successors.items ?? []
  const proposalsReadable = hist.data?.proposals_readable
  const open = (challenges.data?.disputes ?? []).filter((x) => x.open)
  const aside = (challenges.data?.disputes ?? []).filter((x) => !x.open)
  const neverAnswered = !stands && establishedBy.length === 0 && supersededBy.length === 0

  return (
    <>
      <p className="ei-authority">{authority}</p>
      {establishing?.reason && <blockquote className="ei-quote">{establishing.reason}</blockquote>}

      {/* THE ONE PIECE OF HISTORY THE STANDING LEG SURFACES: where it was
          proposed. Provenance rather than a timeline — one link, to one
          Turn, which is then flashed. */}
      {fromTurn ? (
        <p className="ei-aside">
          <button className="ei-link" onClick={() => onGoToTurn?.(fromTurn)}>
            Proposed in a Turn{conversationName ? ` in ${conversationName}` : ''}
          </button>
        </p>
      ) : (
        provenanceWhyNot && <p className="ei-aside ei-faint">{provenanceWhyNot}</p>
      )}

      {neverAnswered && (
        <p className="ei-aside">
          Nobody has asked you about this. It can wait as long as you like; while it waits it
          reaches nobody.
        </p>
      )}

      {supersededBy.length > 0 && (
        <p className="ei-aside">
          Ended: replaced by{' '}
          {supersededBy.map((sid, i) => (
            <span key={sid}>
              {i > 0 && ', '}
              <button className="ei-link" onClick={() => onOpenEntry(sid)}>
                its successor
              </button>
            </span>
          ))}
          .
        </p>
      )}

      {/* PROPOSED SUCCESSORS, UNDER STANDING, BECAUSE THEY BEAR ON IT AND DO
          NOT CHANGE IT. Each one is stated with the chip that says what it
          reaches, so nobody reads a proposal as a replacement.

          THE CHIP IS READ FROM THE SAME FIELD THE ACT IS OFFERED FROM. It
          used to say "reaches nobody" unconditionally, one line above a
          button that branched on `x.state` — so a successor established on
          its own, while this predecessor still stood, was announced as
          reaching nobody by the very panel whose read said it stands. */}
      <Bounded items={proposedSuccessors} label="Proposed replacements">{(x) => (
        <p className="ei-aside" key={x.link}>
          @{(x.by_alias ?? x.attributed_to ?? 'somebody').replace(/^@/, '')} proposed a
          replacement:{' '}
          <button className="ei-link" onClick={() => onOpenEntry(x.entry)}>
            {x.summary ? clipped(x.summary) : (x.kind ?? 'the candidate')}
          </button>{' '}
          <span className="ei-flag">{SUCCESSOR_CHIP[x.state]}</span>
          {x.reason ? <span className="ei-faint">{' · '}{x.reason}</span> : null}
          {onEstablishReplacement && stands && x.state === 'candidate' && (
            <>
              {' '}
              <button className="ei-link" onClick={() => onEstablishReplacement(x.entry)}>
                Establish replacement…
              </button>
            </>
          )}
        </p>
      )}</Bounded>
      {(step?.proposed?.successors.omitted ?? 0) > 0 && <p className="ei-faint">{step!.proposed!.successors.omitted} further proposed replacements were not returned by this history read. Use the related records below to inspect their links and candidates; its bounded read offers more when needed.</p>}
      {proposalsReadable === false && (
        <p className="ei-aside ei-faint">
          This record declares no relation that says one thing is proposed to replace another,
          so whether anything is proposed against this cannot be read. That is not an answer
          of none.
        </p>
      )}

      <Bounded items={open} label="Open disputes">{(x) => (
        <div className="ei-dispute" key={x.link}>
          <p className="ei-aside">
            @{(x.by_alias ?? x.by ?? 'somebody').replace(/^@/, '')} disputes this{' · '}
            <span title={when(x.at)}>{ago(x.at)}</span>
          </p>
          {x.reason && <blockquote className="ei-quote">{x.reason}</blockquote>}
          <p className="ei-aside">
            {stands ? 'It still stands. ' : ''}A dispute revokes nothing.
            {onSetAside && (
              <>
                {' '}
                <button className="ei-link" onClick={() => onSetAside(x)}>
                  Set it aside…
                </button>
              </>
            )}
          </p>
        </div>
      )}</Bounded>
      {aside.length > 0 && (
        <p className="ei-aside">
          {aside.length === 1 ? 'A challenge was' : `${aside.length} challenges were`} set aside.
          The challenge and its text stay in the record, and standing did not change.
        </p>
      )}

      <p className="ei-refusal">
        Never rewritten. Editing writes a new version and deleting writes a record that it was
        deleted — both leave this exactly as it is; superseding writes a replacement and ends this;
        disputing records a challenge and changes nothing else.
      </p>
    </>
  )
}

/* --------------------------------------------------------------- in use --- */

export interface InUseLegProps {
  entry: Id
  conversation: Id | null
  conversationName?: string | null
  stands: boolean
  /** read inside the workspace, where the doors below lead somewhere */
  governance?: boolean
  onTrace?: (entry: Id) => void
  onCompare?: (left: Id, right: Id) => void
  onPreview?: () => void
}

/** ONE SENTENCE, and the machine's own reason where it is withheld.
 *
 *  Computed from what stands, and it says so. IT IS NOT A RECORD: nothing here
 *  is evidence that any execution received anything, and the question that
 *  answers that has its own door. */
export function InUseLeg({
  entry,
  conversation,
  conversationName,
  stands,
  governance,
  onTrace,
  onCompare,
  onPreview,
}: InUseLegProps) {
  const reach = useApi<{ rows: { entry: Id; applies: string; why: string }[] }>(
    '/api/governance/applies?entry=' + encodeURIComponent(entry),
  )
  const brainReach = reach.data?.rows.find(r => r.entry === entry)
  const ctx = useApi<ContextPayload>(
    '/api/context' + (conversation ? '?conversation=' + encodeURIComponent(conversation) : ''),
  )
  const here = conversationName ?? conversation ?? 'the whole Brain'
  const component = ctx.data?.components?.find((c) => c.source_id === entry) ?? null
  const withheld = ctx.data?.withheld?.find((w) => w.source_id === entry) ?? null
  /* TWO STANDING ITEMS ON ONE SUBJECT. Surfaced, never resolved: composition
     includes both and Mentis has no precedence between them. */
  const conflict = useMemo(() => {
    for (const c of (ctx.data?.conflicts ?? []) as { about: string; components: string[] }[])
      if (c.components?.includes(entry)) return c
    return null
  }, [ctx.data, entry])

  if (ctx.error)
    return <p className="ei-aside">what it does now could not be computed: {ctx.error}</p>
  if (!ctx.data) return <p className="ei-aside ei-faint">computing from what stands…</p>

  return (
    <>
      {withheld ? (
        <p className="ei-inuse no">
          Composition {conversation ? 'here ' : ''}withholds it (
          <span className="ei-machine">{withheld.why}</span>). It reaches nobody.
        </p>
      ) : component ? (
        <p className="ei-inuse ok">
          {component.why} Under current standing, composition {conversation ? 'here ' : ''}includes
          it.
        </p>
      ) : !conversation && stands && brainReach ? (
        <p className="ei-inuse ok">{brainReach.why}.</p>
      ) : (
        <p className="ei-inuse no">
          {stands
            ? `Nothing places or selects it ${conversation ? 'here' : 'in this composition'}. It applies only to an execution that names it.`
            : 'It does not stand, so composition does not include it. It reaches nobody.'}
        </p>
      )}
      <p className="ei-aside ei-faint">
        Computed from what stands, for {here}. Not a record: it does not say what any execution
        received. For that, ask History.
      </p>

      {conflict && (
        <p className="ei-aside">
          It speaks to &ldquo;{conflict.about}&rdquo;, and so does other standing material.
          Composition includes both; there is no precedence.
          {governance && onCompare && conflict.components.length > 1 && (
            <>
              {' '}
              <button
                className="ei-link"
                onClick={() => {
                  const other = conflict.components.find((c) => c !== entry)
                  if (other) onCompare(entry, other)
                }}
              >
                Compare
              </button>
            </>
          )}
        </p>
      )}

      {governance && (onTrace || onPreview) && (
        <p className="ei-acts">
          {onTrace && (
            <button className="ei-link" onClick={() => onTrace(entry)}>
              {conversation ? 'Trace why this applies →' : 'Trace where it applies →'}
            </button>
          )}
          {onTrace && onPreview && ' · '}
          {onPreview && (
            <button className="ei-link" onClick={onPreview}>
              Preview what would compose now
            </button>
          )}
        </p>
      )}
    </>
  )
}

/* -------------------------------------------------------------- history --- */

/** Where it came from and what it replaced — one timeline, oldest first.
 *
 *  NOT ESTABLISHED IS SAID, NOT LEFT BLANK. An empty establishing list is the
 *  sentence "nobody established this", which is exactly what somebody reading
 *  a proposal needs to be told. */
/* THE TIMELINE WALKS TWO RELATIONS NOW, AND SAYS WHICH IS WHICH.
   The chain itself is `supersedes` links and always was, so every row of a
   chain longer than one was written by something that stood -- a proposed
   successor can never appear as a ROW. It used to follow from that that a
   proposal could not be shown here at all, and that was true only because the
   record held no such fact: "Mark IV has no proposed-supersession link".

   It does now. `proposes-to-supersede` says one thing is PUT FORWARD to
   replace another, carries no substrate role, and ends nothing -- so every
   row of this timeline still stands exactly as it stood, and what is proposed
   against a row is shown BESIDE that row rather than in the chain. The two
   lines are worded apart on purpose: `Supersedes` is what happened,
   `Proposed to supersede` is what somebody is asking for.

   And the act offered from a proposal is the one act that exists.
   `Establish replacement…` opens `ActDialog`'s establish path, which states
   before the click that establishing this successor ends what it was proposed
   to replace, and performs both in one confirmation. This grows no second
   path to the route. */
export function Life({
  entry,
  onOpenEntry,
  onSetAside,
  onEstablishReplacement,
}: {
  entry: Id
  onOpenEntry: (id: Id) => void
  /** answer an open challenge from the line that records it. Same act and same
   *  dialog as the Standing leg's; the timeline is simply the other place a
   *  reader meets the dispute. */
  onSetAside?: (dispute: DisputeRead) => void
  /** approve a proposed successor from the line that records it — I-57. The
   *  caller opens the establish dialog, which is where the one act lives. */
  onEstablishReplacement?: (successor: Id) => void
}) {
  const hist = useApi<ItemHistoryRead>(
    '/api/governance/history?entry=' + encodeURIComponent(entry),
  )
  if (hist.error) return <p className="ei-aside">the timeline could not be read: {hist.error}</p>
  if (!hist.data) return <p className="ei-aside ei-faint">reading the record…</p>
  const rows = hist.data.timeline ?? []
  if (rows.length === 0)
    return <p className="ei-aside">The record holds no chain through this. An empty answer.</p>
  return (
      <Bounded items={rows} label="Versions" listClass="ei-life">{(t) => (
        <li key={t.entry} className={t.entry === entry ? 'on' : ''}>
          {t.missing ? (
            <p className="ei-aside">
              An item in this chain the record cannot produce. A gap in a timeline is a fact, so it
              is shown rather than dropped.
            </p>
          ) : (
            <>
              <p className="ei-life-what">
                {t.entry === entry ? (
                  <b>this</b>
                ) : (
                  <button className="ei-link" onClick={() => onOpenEntry(t.entry)}>
                    {t.kind ?? 'entry'}
                  </button>
                )}
                {t.at ? <span className="ei-faint">{' · '}{ago(t.at)}</span> : null}
              </p>
              {(t.established ?? []).length === 0 ? (
                <p className="ei-aside">
                  Not established. It is in the record: you can address it and argue with it, and
                  it reaches no execution.
                </p>
              ) : (
                <Bounded items={(t.established ?? [])} label="Establishments">{(l) => (
                  <p className="ei-aside" key={l.link}>
                    Established by @{(l.by_alias ?? l.by ?? 'somebody').replace(/^@/, '')}
                    {' · '}
                    {ago(l.at)}
                    {l.reason ? ` · ${l.reason}` : ''}
                  </p>
                )}</Bounded>
              )}
              <Bounded items={(t.placed_at ?? [])} label="Placements">{(l) => (
                <PlacementFact key={l.link} link={l} onOpenEntry={onOpenEntry} />
              )}</Bounded>
              <Bounded items={(t.supersedes ?? [])} label="Replacements">{(l) => (
                <p className="ei-aside" key={l.link}>
                  Replaces{' '}
                  <button className="ei-link" onClick={() => onOpenEntry(l.to)}>
                    what it replaced
                  </button>
                  {l.reason ? ` · ${l.reason}` : ''}
                </p>
              )}</Bounded>
              <Bounded items={(t.disputes ?? [])} label="Disputes">{(x) => (
                <p className="ei-aside" key={x.link}>
                  Disputed by @{(x.by_alias ?? x.by ?? 'somebody').replace(/^@/, '')}
                  {' · '}
                  {x.open
                    ? 'Open. A dispute does not revoke or supersede anything.'
                    : 'Set aside. The dispute stays in the record.'}
                  {onSetAside && x.open && t.entry === entry && (
                    <>
                      {' '}
                      <button className="ei-link" onClick={() => onSetAside(x)}>
                        Set it aside…
                      </button>
                    </>
                  )}
                </p>
              )}</Bounded>
              {/* WHAT THIS ROW IS PUT FORWARD TO REPLACE. Worded apart from
                  `Supersedes` above because it is a different fact: nothing
                  here has ended, and every item named goes on standing. */}
              <Bounded items={(t.proposed?.predecessors.items ?? [])} label="Proposed predecessors">{(x) => (
                <p className="ei-aside" key={x.link}>
                  Proposed to replace{' '}
                  <button className="ei-link" onClick={() => onOpenEntry(x.entry)}>
                    {x.summary ? clipped(x.summary) : (x.kind ?? 'what it would replace')}
                  </button>
                  {x.reason ? ` · ${x.reason}` : ''}
                  {' · '}
                  <span className="ei-flag">nothing has ended</span>
                </p>
              )}</Bounded>
              {/* AND WHAT IS PUT FORWARD TO REPLACE IT. Several may be, and
                  every one the read carried is shown: the incumbent holds the
                  post while every candidate for it waits. THE READ IS BOUNDED
                  AND THE BOUND IS SAID — see below — because a list that is
                  silently cut reads as a complete one. */}
              <Bounded items={(t.proposed?.successors.items ?? [])} label="Proposed replacements">{(x) => (
                <p className="ei-aside" key={x.link}>
                  @{(x.by_alias ?? x.attributed_to ?? 'somebody').replace(/^@/, '')} proposed a
                  replacement:{' '}
                  <button className="ei-link" onClick={() => onOpenEntry(x.entry)}>
                    {x.summary ? clipped(x.summary) : (x.kind ?? 'the candidate')}
                  </button>
                  {x.reason ? ` · ${x.reason}` : ''}
                  {' · '}
                  {/* The state the read carried, not a constant: after
                      approval this same list holds the successor that ended
                      the step beside the candidates that did not, and calling
                      all of them "reaches nobody" contradicted the row. */}
                  <span className="ei-flag">{SUCCESSOR_CHIP[x.state]}</span>
                  {onEstablishReplacement && x.state === 'candidate' && (
                    <>
                      {' '}
                      <button
                        className="ei-link"
                        onClick={() => onEstablishReplacement(x.entry)}
                      >
                        Establish replacement…
                      </button>
                    </>
                  )}
                </p>
              )}</Bounded>
              {(t.proposed?.successors.omitted ?? 0) > 0 && (
                <p className="ei-aside ei-faint">
                  and {t.proposed!.successors.omitted} more proposed to replace it, not listed
                  here — {t.proposed!.successors.total} in all.
                  Use the related records below to inspect links and candidates, and load more when that read is bounded.
                </p>
              )}
              {(t.proposed?.predecessors.omitted ?? 0) > 0 && <p className="ei-faint">{t.proposed!.predecessors.omitted} proposed predecessors were not returned. Inspect this version's related records to follow their links.</p>}
              <Bounded items={(t.superseded_by ?? [])} label="Successors">{(l) => (
                <p className="ei-aside" key={l.link}>
                  Ended: replaced by{' '}
                  <button className="ei-link" onClick={() => onOpenEntry(l.from)}>
                    its successor
                  </button>
                  {l.reason ? ` · ${l.reason}` : ''}
                </p>
              )}</Bounded>
            </>
          )}
        </li>
      )}</Bounded>
  )
}


/** What executions actually received it — delivery lines only.
 *
 *  A RECORD SAYS WHAT CROSSED. It never says an execution read or followed it,
 *  and nothing here may be worded as though it did. Where no record names it,
 *  that is an answer from the records and not a guess. */
export function Received({
  entry,
  conversation,
  onOpenExecution,
}: {
  entry: Id
  conversation: Id | null
  onOpenExecution?: (execution: Id) => void
}) {
  const [limit, setLimit] = useState(50)
  const got = useApi<DeliveriesRead>(
    '/api/governance/deliveries?entry=' +
      encodeURIComponent(entry) + '&limit=' + limit +
      (conversation ? '&conversation=' + encodeURIComponent(conversation) : ''),
  )
  if (got.error)
    return <p className="ei-aside">the delivery records could not be read: {got.error}</p>
  if (!got.data) return <p className="ei-aside ei-faint">reading the records…</p>
  const rows = got.data.deliveries ?? []
  if (rows.length === 0)
    return (
      <p className="ei-aside">
        No delivery record names it. That is an answer from the records, not a guess.
      </p>
    )
  const shown = rows
  return (
    <>
      <p className="ei-aside">Delivered to {got.data.per_entry[0]?.executions ?? "an unknown number of"} runs · {got.data.total} delivery records{rows[0]?.at ? ` · last ${when(rows[0].at)}` : ""}</p><div className="ei-deliveries">
        <Bounded items={shown} label="Delivery records">{(r) => (
          <div key={r.delivery}>
            <span>
              {r.at ? <span title={when(r.at)}>{ago(r.at)}</span> : 'undated'}
            </span>
            {onOpenExecution && <button className="ei-link" onClick={() => onOpenExecution(r.execution)}>Open run</button>}
            <span className="ei-faint">
              {r.runtime ? ` · ${r.runtime}` : ''}
              {r.conversation ? ' · in a Conversation' : ' · Brain scope'}
            </span>
            <details><summary>Delivery details</summary><pre>{JSON.stringify(r, null, 2)}</pre></details>
          </div>
        )}</Bounded>
      </div>
      {got.data.omitted > 0 && <p className="ei-aside">{got.data.omitted} additional delivery records are available. <button className="ei-link" onClick={() => setLimit(limit + 50)}>Load 50 more delivery records</button></p>}
      <p className="ei-aside ei-faint">
        From delivery records only. A record says what crossed. It never says an execution read or
        followed it.
      </p>
    </>
  )
}
