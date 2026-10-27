import { useMemo, useState } from 'react'
import {
  useApi,
  type AppliesRead,
  type ConditionsRead,
  type Id,
  type OwedList,
  type SinceRead,
} from '../../api'
import type { GovFilters } from '../../address'
import Register, { RegisterHeads, RegisterRow, type Row } from '../Register'
import { placedHere } from './r2Model'
import { AskCard, onePerForm, type AskRow } from './Asks'
import ActDialog, { type ActOutcome } from './ActDialogs'
import type { AppliesRow } from './InUseContext'
import './Lens.css'

/* ------------------------------------------------------------------------ *
 * THE STANDING LENS — what the record SAYS about the governed material.
 *
 * Whether it stands, on whose authority, and whether it is contested or
 * proposed. NO EXECUTIONS AND NO HISTORY: what the material does to work is
 * the other lens over this same corpus, and what actually crossed to anybody
 * is a question with its own door. Those are not omissions to be filled in
 * later; keeping them out is what makes this lens answerable.
 *
 * THREE GROUPS, AND ONLY THE FIRST IS OWED.
 *
 *   Asked of you      somebody explicitly asked, and a response is owed until
 *                     one is given.
 *   Stands here       established, and nothing has superseded it.
 *   Proposed here     folded away, reaching nobody, owing nothing.
 *
 * A PROPOSAL IS NOT AN OBLIGATION AND AN EXPLICIT ASK IS, so the two counts
 * are never added together and never rendered in one number. A proposal waits,
 * reaching nobody, for as long as it is left.
 *
 * AT BRAIN SCOPE the same corpus is read wider: the summary counts become
 * doors into the register with a facet already set, and the register itself
 * takes the page. It is not a different application; it is this lens with the
 * Conversation taken off it.
 * ------------------------------------------------------------------------ */

export interface LensStandingProps {
  /** the Conversation this lens looks through, or null for the whole corpus */
  conversation: Id | null
  conversationName?: string | null
  filters: GovFilters
  onFilters: (f: GovFilters) => void
  me: Id | null
  onOpenEntry: (entry: Id) => void
  onCompare?: (left: Id, right: Id) => void
  /** cross to the other lens over the same corpus */
  onInUse: () => void
  /** names for Conversations, so a placement is said and not idented */
  names?: Record<string, string>
  /** something was recorded; whoever holds the reads should take them again */
  onChanged?: () => void
  /** the item the inspector holds, marked on its row (I-138) */
  inspected?: Id | null
}

/** A count that is also a door. Zero renders the word `no`, because "0 asks
 *  you" reads like a tally and "no asks you" reads like an answer.
 *
 *  AND `null` IS THE THIRD ANSWER, WHICH IS NOT ZERO. Nobody counted, so no
 *  count is shown and no word standing in for one: "no asks you" said over a
 *  read that refused, or that has not come back, is the positive claim that
 *  nobody is waiting, made before looking.
 *
 *  THE SEPARATOR TRAILS THE COUNT IT FOLLOWS. The summary is a sentence and
 *  wraps as one, and a leading middot left at the start of a wrapped line
 *  reads as a bullet nobody wrote -- which is what 390px showed it doing.
 *  It is also the ONLY middot in the line: two labels carried one of their
 *  own, so "1 contested · no disputed · not standing" read as four counts. */
function Count({
  n,
  said,
  unknownSaid,
  owed,
  title,
  more,
  onGo,
}: {
  n: number | null
  said: string
  /** what to say instead of a count when nobody has counted. */
  unknownSaid?: string
  owed?: boolean
  title?: string
  /** something follows this count, so it carries the separator */
  more?: boolean
  onGo?: () => void
}) {
  const body =
    n === null ? (
      <em>{unknownSaid ?? 'not counted'}</em>
    ) : (
      <>
        <b>{n === 0 ? 'no' : n}</b> {said}
      </>
    )
  const one =
    !onGo || n === null || n === 0 ? (
      <span className={'ls-count' + (owed ? ' owed' : '')} title={title}>
        {body}
      </span>
    ) : (
      <button
        className={'ls-count ls-count-go' + (owed ? ' owed' : '')}
        title={title}
        onClick={onGo}
      >
        {body}
      </button>
    )
  return (
    <>
      {one}
      {more ? ' · ' : null}
    </>
  )
}

export default function LensStanding({
  conversation,
  conversationName,
  filters,
  onFilters,
  me,
  onOpenEntry,
  onCompare,
  onInUse,
  names = {},
  onChanged,
  inspected = null,
}: LensStandingProps) {
  const here = conversationName ?? conversation ?? 'this Conversation'
  /* WRITING AN INSTRUCTION IS AN OWNER ACT, and the dialog says what it does
     before anybody confirms it. Opened from the group heading, because that is
     where somebody reading what stands here decides something else should. */
  const [writing, setWriting] = useState(false)
  const [landed, setLanded] = useState<string | null>(null)
  const [proposedOpen, setProposedOpen] = useState(false)

  /* ONE READ OF THE CORPUS, arranged. The groups are three questions about the
     same rows, so they must not be three reads that could disagree. */
  const got = useApi<{
    error?: string
    groups: Record<string, Row[]>
    kinds: { standing_apt_unknown: { kind: string; entries: number }[] }
  }>('/api/governed?limit=500')
  const owed = useApi<OwedList>(me ? '/api/owed?participant=' + encodeURIComponent(me) : null)
  const applies = useApi<AppliesRead>('/api/governance/applies')
  const appliesBy = useMemo(() => {
    const out: Record<string, AppliesRow> = {}
    for (const r of applies.data?.rows ?? []) out[r.entry] = r as AppliesRow
    return out
  }, [applies.data])

  const all = useMemo<Row[]>(() => {
    const g = got.data?.groups
    if (!g) return []
    return [...(g.standing ?? []), ...(g.proposed ?? []), ...(g.history ?? []), ...(g.unknown ?? [])]
  }, [got.data])

  /* IN SCOPE HERE means placed here or proposed here. A Conversation is a lens
     and not a container, so nothing is moved into or out of one. */
  const inScope = useMemo(
    () =>
      conversation
        ? all.filter(
            (r) =>
              r.placed_at.some((p) => placedHere(p, conversation)) ||
              r.proposed_by.some((p) => p.conversation === conversation),
          )
        : all,
    [all, conversation],
  )
  const byName = (a: Row, b: Row) =>
    (a.summary || a.entry).localeCompare(b.summary || b.entry, undefined, { sensitivity: 'base' })
  const stands = inScope.filter((r) => r.state === 'stands').sort(byName)
  const proposed = inScope.filter((r) => r.state === 'candidate').sort(byName)
  /* CONTESTED IS ABOUT STANDING MATERIAL, and that is the register's own
     `Disputed` facet: an open challenge AND it still stands. So this count
     and that facet mean one thing and the jump between them lands where the
     reader expects. */
  const contested = inScope.filter((r) => r.disputed_by.length > 0 && r.state === 'stands')
  /* AND A CHALLENGE AGAINST SOMETHING THAT DOES NOT STAND IS STILL A
     CHALLENGE. It fell between the two: not contested, because it does not
     stand, and not visible under `proposed`, which counts every candidate
     whether anybody disputed it or not. So the header said "no contested"
     while the record held an open dispute. Counted here, apart, because
     folding it into `contested` would make the count disagree with the
     facet it jumps to. */
  const disputedNotStanding = inScope.filter(
    (r) => r.disputed_by.length > 0 && r.state !== 'stands',
  )

  /* THE ASKS THAT NAME SOMETHING HERE. An ask is what is owed; a proposal is
     not, and the two counts are never blended. */
  /* AND WHETHER THE RECORD HAS ANSWERED AT ALL. `/api/owed` answers
     `{error, owed: null}` where it cannot answer, and no read is made while
     `me` is null; `?? []` turned both into an empty list, which the summary
     then reported as "no asks you". Null here is UNKNOWN and is carried as
     such all the way to the word on the screen. */
  const asksKnown = Boolean(me) && owed.data?.owed != null
  /* ONE PER FORM, in the count and the list alike (P11). */
  const asks: AskRow[] = useMemo(
    () =>
      onePerForm((owed.data?.owed ?? [])
        .filter((o) => !conversation || o.conversation === conversation)
        .map((o) => ({
          expectation: o.expectation,
          expects: o.expects,
          turn: o.turn,
          number: o.number,
          conversation: o.conversation,
          conversation_name: o.conversation_name ?? null,
          asked_by: o.asked_by,
          asked_by_alias: o.asked_by_alias,
          because: o.because,
          options: o.options,
          at: o.at,
          form: o.form ?? null,
          question: o.question ?? null,
        }))),
    [owed.data, conversation],
  )

  const conditions = useApi<ConditionsRead>(
    inScope.length
      ? '/api/governance/conditions?' +
        inScope
          .slice(0, 60)
          .map((r) => 'entry=' + encodeURIComponent(r.entry))
          .join('&')
      : null,
  )
  const since = useApi<SinceRead>(
    me
      ? '/api/governance/since?participant=' +
        encodeURIComponent(me) +
        (conversation ? '&conversation=' + encodeURIComponent(conversation) : '')
      : null,
  )
  const fresh = useMemo(() => {
    const out = new Set<string>()
    if (!since.data?.bounded) return out
    for (const a of since.data.changed?.acts ?? []) for (const e of a.about ?? []) out.add(e)
    return out
  }, [since.data])

  /* WHAT STANDS BRAIN-WIDE AND CANNOT REACH HERE BY ITSELF. Only a placement
     reaches everybody acting somewhere; everything else needs a particular
     execution to select or name it, which is the other lens's question. */
  const elsewhere = useMemo(() => {
    if (!conversation) return { personas: 0, nameable: 0 }
    let personas = 0
    let nameable = 0
    for (const r of all) {
      if (r.state !== 'stands') continue
      if (r.placed_at.some((p) => placedHere(p, conversation))) continue
      const a = appliesBy[r.entry]
      if (!a) continue
      if (a.applies === 'by_persona') personas += 1
      else if (a.applies === 'when_named') nameable += 1
    }
    return { personas, nameable }
  }, [all, conversation, appliesBy])

  const row = (r: Row) => (
    <RegisterRow
      key={r.entry}
      r={r}
      lens="standing"
      scope={conversation}
      isNew={fresh.has(r.entry)}
      conditions={conditions.data ?? null}
      applies={appliesBy[r.entry]}
      appliesRead={applies.error ? 'failed' : applies.data ? 'answered' : 'pending'}
      names={names}
      onOpen={onOpenEntry}
      onCompare={onCompare}
      me={me}
      onChanged={() => {
        got.reload()
        onChanged?.()
      }}
      inspected={r.entry === inspected}
    />
  )

  const jump = (state: string) => onFilters({ ...filters, state })

  return (
    <section className="ls" aria-label="Standing">
      <p className="ls-lede">
        What the record says about the governed material
        {conversation ? ` that concerns ${here}` : ''}: whether it stands, on whose authority, and
        whether it is contested or proposed. No executions, no history.
      </p>

      {got.error && (
        <p className="ls-error" role="alert">
          could not read the governed material: {got.error}
        </p>
      )}
      {!got.data && !got.error && <p className="ls-faint">reading the record…</p>}

      {got.data && (
        <>
          <p className="ls-summary">
            {/* OWED AND NOT OWED, NEVER ADDED TOGETHER. */}
            <Count
              n={asksKnown ? asks.length : null}
              said={conversation ? 'asks you' : 'ask you'}
              unknownSaid={
                me
                  ? 'what asks you has not been read yet'
                  : 'nobody is named as you, so what asks you was never asked'
              }
              owed
              more
              title="Explicit requests for your decision. Proposals alone are not counted."
            />
            <Count
              n={stands.length}
              said={conversation ? 'stand here' : 'stand'}
              more
              title="established, and nothing has superseded it"
              onGo={conversation ? undefined : () => jump('standing')}
            />
            <Count
              n={contested.length}
              said="contested"
              more
              title="standing material with an open challenge, and it still stands. A dispute revokes nothing."
              onGo={conversation ? undefined : () => jump('disputed')}
            />
            <Count
              n={disputedNotStanding.length}
              said="disputed, not standing"
              more
              title="an open challenge against material that does not stand — a disputed candidate, or one that has ended. Counted apart from contested, which is about standing material."
              /* No facet holds exactly this set, and sending the reader to
                 one that holds a different set would be worse than sending
                 them nowhere. */
            />
            <Count
              n={proposed.length}
              said="proposed, not owed"
              title="written, reaching nobody. Nobody asked you about it."
              onGo={conversation ? () => setProposedOpen(true) : () => jump('proposed')}
            />
          </p>

          {/* ------------------------------------------ asked of you --- */}
          {asks.length > 0 && (
            <section className="ls-group">
              <h3>Asked of you</h3>
              <p className="ls-sub">
                {asks.length} · someone explicitly asked; a response is owed until you give one
              </p>
              {asks.map((a) => (
                <AskCard
                  key={a.form ?? a.expectation}
                  ask={a}
                  showConversation={!conversation}
                  me={me}
                  onInspect={onOpenEntry}
                  onCompare={(l, r) => r && onCompare?.(l, r)}
                  onChanged={() => {
                    owed.reload()
                    got.reload()
                    onChanged?.()
                  }}
                />
              ))}
            </section>
          )}

          {conversation ? (
            <>
              {/* --------------------------------------- stands here --- */}
              <section className="ls-group">
                <div className="ls-head">
                  <h3>Stands here</h3>
                  <button
                    className="ls-write"
                    onClick={() => setWriting(true)}
                    title="Write an Instruction for work in this Conversation. As owner it is written and established in one act."
                  >
                    + Instruction here
                  </button>
                </div>
                <p className="ls-sub">{stands.length} · established and not superseded</p>
                {stands.length === 0 ? (
                  <p className="ls-empty">
                    Nothing that concerns this Conversation stands. An empty answer.
                  </p>
                ) : (
                  /* FIVE COLUMNS ARE FIVE COLUMNS WHEREVER THEY ARE. The
                     full Register owns the heads and is mounted only at Brain
                     scope, so every list here rendered the same grid with
                     nothing naming its columns. */
                  <ul className="reg-list" data-lens="standing">
                    <RegisterHeads lens="standing" />
                    {stands.map(row)}
                  </ul>
                )}
              </section>

              {/* ------------------------------------- proposed here --- */}
              <section className="ls-group">
                <button
                  className="ls-fold"
                  aria-expanded={proposedOpen}
                  onClick={() => setProposedOpen(!proposedOpen)}
                >
                  <span className="caret" aria-hidden="true">
                    {proposedOpen ? '▾' : '▸'}
                  </span>
                  <span className="ls-fold-title">Proposed here</span>
                  <span className="ls-faint">{proposed.length}</span>
                </button>
                {proposedOpen && (
                  <div className="ls-fold-body">
                    <p className="ls-sub">
                      {proposed.length} · not governing · reaches nobody · nothing owed unless
                      someone asks
                    </p>
                    <p className="ls-note">
                      A proposal waits, reaching nobody, for as long as you leave it.
                    </p>
                    {proposed.length === 0 ? (
                      <p className="ls-empty">None.</p>
                    ) : (
                      <ul className="reg-list" data-lens="standing">
                        <RegisterHeads lens="standing" />
                        {proposed.map(row)}
                      </ul>
                    )}
                  </div>
                )}
              </section>

              {/* THE CONVERSATION/BRAIN BOUNDARY, said once and plainly.
                  Nothing is placed "in the Brain": material that stands
                  elsewhere reaches work here only through a particular
                  execution that selects or names it. */}
              <p className="ls-boundary">
                Also standing across the Brain, and able to affect work here only through a
                particular execution: {elsewhere.personas} Personas and {elsewhere.nameable} items
                that can be named. See{' '}
                <button className="ls-link" onClick={onInUse}>
                  In use
                </button>{' '}
                for how they apply.
              </p>
            </>
          ) : (
            <>
              {/* ------------- contested or proposed to change (Brain) --- */}
              {(contested.length > 0 || proposed.length > 0) && (
                <section className="ls-group">
                  <h3>Contested or proposed to change</h3>
                  <p className="ls-sub">
                    {contested.length + proposed.length} · nobody asked, so none of these is owed
                  </p>
                  {/* AN EXCERPT, AND MARKED AS ONE. Twelve rows sliced out
                      of a corpus the register below holds in full: two grids
                      that each resolve their own `max-content` and therefore
                      cannot keep one column in one place. It stops looking
                      like the ledger's first twelve rows. */}
                  <ul className="reg-list reg-list-excerpt" data-lens="standing">
                    <RegisterHeads lens="standing" />
                    {[...contested, ...proposed].slice(0, 12).map(row)}
                  </ul>
                </section>
              )}

              <Register
                lens="standing"
                conversation={null}
                filters={filters}
                onFilters={onFilters}
                onOpenEntry={onOpenEntry}
                onCompare={onCompare}
                me={me}
                names={names}
                inspected={inspected}
              />
            </>
          )}
        </>
      )}

      {landed && (
        <p className="ls-landed" role="status">
          {landed}
        </p>
      )}

      {writing && conversation && (
        <ActDialog
          act="write"
          item={null}
          me={me}
          conversation={{ id: conversation, name: conversationName ?? null }}
          onCancel={() => setWriting(false)}
          onDone={(outcome: ActOutcome) => {
            setWriting(false)
            setLanded(outcome.said)
            got.reload()
            onChanged?.()
          }}
        />
      )}
    </section>
  )
}
