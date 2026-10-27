import { useMemo, useState, type ReactNode } from 'react'
import {
  announceAdvance,
  useApi,
  when,
  type Id,
  type ProposedRead,
} from '../../api'
import ActDialog, { type ActItem, type ActOutcome } from './ActDialogs'
import { standingOf, standingUndeclared, standingWords } from '../standing'
import { successorReach, type SuccessorState } from './successorReach'
import './execution-sheet.css'

/* ------------------------------------------------------------------------ *
 * TWO ITEMS, SIDE BY SIDE, AND NO VERDICT.
 *
 * Compare exists because two things can both stand and both apply, and
 * Mentis has no precedence between them. It does not resolve that: it states
 * it, shows what the record holds about each, says what every available act
 * would do BEFORE anything is clicked, and leaves the choice where it
 * belongs. "Nobody is asking. Doing nothing is a legitimate answer."
 *
 * THE ACTS ARE THE SAME ACTS, AND THEY ARE PERFORMED BY THE SAME DIALOGS.
 * Supersede and dispute here are the inspector's and the Conversation's acts,
 * recorded on the same governed item; there is no Compare-local commit path
 * and there must never be one. There WAS one: this surface posted to
 * `/supersede` and `/dispute` itself, without `attributed_to`, so the route
 * fell back to the bare string "human" and the act and its `supersedes` link
 * were attributed to nobody the record knows. `ActDialog` and `standing.ts`
 * exist precisely so there is one place to get the owner's attribution right,
 * and this is now one of the places that uses them rather than a second place
 * to get it wrong.
 *
 * WHAT IT REFUSES TO SAY. It never names a winner, never merges the two
 * columns into a diff, and never reports delivery evidence it did not read.
 * Counts here are counts of delivery records: they say how often something
 * was named, never that anybody read it or followed it.
 *
 * NO KIND IS NAMED IN THIS FILE. The Kind of a replacement is the Kind of
 * what it replaces, and the route enforces that; nothing here holds a list.
 * ------------------------------------------------------------------------ */

/* ------------------------------ what the reads return ------------------------------ */

interface EntryRead {
  id: Id
  kind: string | null
  family?: string | null
  body: Record<string, unknown>
  fields: string[]
  author_alias?: string | null
  written_by?: string | null
  at?: number
  stands: boolean
  established_by: Id[]
  superseded_by: Id[]
  standing_apt?: boolean | null
  /** what is merely PROPOSED to replace this, and what it proposes to
   *  replace. This is how Compare knows which of the two is the incumbent and
   *  which is only standing for the post, from the record rather than from
   *  the fact that one of them happens not to stand. */
  proposed?: ProposedRead | null
  missing?: boolean
}

interface LinkView {
  link: Id
  reason: string | null
  by: Id
  /** WHO, IN THE NAME THEY ARE KNOWN BY. `governance.py:_link_view` adds it
   *  for exactly this line; reading `by` alone printed a raw id where every
   *  other in-situ line on the surface prints an alias. Null is the third
   *  answer — nobody was attributed — and is not an alias. */
  by_alias: string | null
  written_by: string | null
  at: number
}

interface TimelineRow {
  entry: Id
  state: string
  at?: number
  attributed_to?: Id
  written_by?: string | null
  established: LinkView[]
}

interface Conditions {
  rows: {
    entry: Id
    records: number
    executions: number
    uncounted: boolean
    why_uncounted: string | null
  }[]
  executions_with_records: number
  counts_are: string
}

interface Context {
  components: { source_id: Id | null; why: string }[]
  withheld: { source_id: Id | null; why: string }[]
}

/** The four exclusive standing words, said the way the register says them so
 *  that two surfaces cannot disagree about one item. "Ended" used to hold;
 *  "replaced before establishment" never did, and a hue would not tell them
 *  apart. */
const STATE_SAID: Record<string, string> = {
  candidate: 'proposed',
  stands: 'stands',
  ended: 'ended',
  replaced: 'replaced before establishment',
}

/** The heading over a recorded proposal, SAID PER STATE OF THE SUCCESSOR.
 *
 *  The proposal link is in the record for ever, so a heading branched on the
 *  link alone went on calling an established successor "its proposed
 *  replacement" directly above a chip reading `stands`. The four exclusive
 *  words answer it, and `null` -- the read is not back -- answers nothing
 *  about either side. */
function proposalTitle(
  state: SuccessorState | null,
  predecessorStands: boolean | null,
): string {
  switch (state) {
    case 'candidate':
      return predecessorStands
        ? 'A standing item and its proposed replacement'
        : 'An item and the replacement proposed for it'
    case 'stands':
      return 'An item and the replacement that was established'
    case 'ended':
      return 'An item and a replacement that has since ended'
    case 'replaced':
      return 'An item and a replacement that was itself replaced'
    default:
      return 'An item and what was proposed to replace it'
  }
}

/** The dispute door's own label. Disputing confers and revokes nothing, so it
 *  is offered whatever the successor's state is; what changes is what the
 *  thing being disputed may honestly be called. */
const recordedDisputeLabel = (recorded: boolean): string =>
  recorded ? 'Dispute replacement…' : 'Dispute the other…'

/** The first declared field carrying words. The Kind declares its own fields
 *  and their order; nothing here knows what any of them are called. */
function saidBy(e: EntryRead | null | undefined): string | null {
  if (!e || e.missing) return null
  const order = e.fields?.length ? e.fields : Object.keys(e.body ?? {})
  for (const f of order) {
    const v = e.body[f]
    if (typeof v === 'string' && v.trim()) return v
  }
  return null
}

/** What the item says it speaks to, where the record carries it. Read from
 *  the body, never inferred from the words. */
const aboutOf = (e: EntryRead | null | undefined): string | null => {
  const v = e?.body?.about
  return typeof v === 'string' && v.trim() ? v : null
}

/* ------------------------------------ props ------------------------------------ */

export interface CompareAsk {
  /** who asked, as this Conversation names them */
  by_alias: string
  at: number
  conversation_name?: string | null
  /** the question in the asker's own words */
  question: string
}

export interface CompareProps {
  /** the two items being read beside each other */
  left: Id
  right: Id
  /** where the comparison is being read. null is Brain scope. */
  conversation?: Id | null
  /** who the composition is computed for, when saying why each applies */
  participant?: Id | null
  /** the ask that drove this, where one did. THREE ANSWERS, NOT TWO:
   *  an ask; `null`, which is the record saying nobody asked and is what
   *  licenses the sentence at the foot; and `undefined`, which is UNKNOWN —
   *  nobody has asked the record yet — and licenses nothing. A claim that
   *  nobody is asking, made before looking, would be a claim. */
  ask?: CompareAsk | null
  /** what the reader came from, NAMED: the approved Back never says just
   *  "Back". */
  origin?: string
  onBack?: () => void
  onOpenEntry?: (entry: Id) => void
  /** trace why one side applies — the applicability investigation */
  onTrace?: (entry: Id) => void
  /** open the delivery records that name one side. No read answers "which
   *  executions named this item", so this surface offers the door and never
   *  claims to know which record is the latest. */
  onDeliveryEvidence?: (entry: Id) => void
  /** answer the driving ask without changing any material. The ask machinery
   *  is not this surface's, so the answer is handed back with the words the
   *  reader chose. */
  onAnswer?: (answer: 'Keep both' | 'Not now') => Promise<void> | void
  /** leave the ask open. Recording nothing is what this does, and the caller
   *  is told so it can close without writing anything. */
  onLeaveOpen?: () => void
  /** WHERE THE DRIVING ASK IS ANSWERED, when a reply cannot answer it: a
   *  question of a decision form (answered at its form) or an input (by Done
   *  at its block). Given, it is drawn in place of the reply answers. */
  answerHere?: ReactNode
  /** establish a proposed replacement. Establishing is not one of this
   *  surface's acts — it is the owner's act wherever it is performed — so it
   *  is handed to whoever mounted this. */
  onEstablish?: (entry: Id) => void
  /** who an act taken here is attributed to. Absent, the acts that need an
   *  attribution are not offered rather than being attributed to nobody. */
  me?: Id | null
}

/* ----------------------------------- the sheet ----------------------------------- */

export default function Compare({
  left,
  right,
  conversation = null,
  participant = null,
  ask,
  origin,
  onBack,
  onOpenEntry,
  onTrace,
  onDeliveryEvidence,
  onAnswer,
  onLeaveOpen,
  answerHere,
  onEstablish,
  me = null,
}: CompareProps) {
  const l = useApi<EntryRead>(`/api/entries/${left}`)
  const r = useApi<EntryRead>(`/api/entries/${right}`)
  const hl = useApi<{ timeline: TimelineRow[] }>(`/api/governance/history?entry=${left}`)
  const hr = useApi<{ timeline: TimelineRow[] }>(`/api/governance/history?entry=${right}`)
  const cond = useApi<Conditions>(`/api/governance/conditions?entry=${left}&entry=${right}`)

  const ctxParams = new URLSearchParams()
  if (conversation) ctxParams.set('conversation', conversation)
  if (participant) ctxParams.set('participant', participant)
  const ctx = useApi<Context>(participant ? `/api/context?${ctxParams.toString()}` : null)

  /* WHICH ACT IS OPEN, AND ON WHICH SIDE. The act itself belongs to
     `ActDialog`: it reads the Kind's declared fields, shows the old text as
     the immutable thing it is, offers the three-way choice of what a
     replacement ends, and attributes what it writes. */
  const [acting, setActing] = useState<
    { act: 'supersede'; side: 'left' | 'right' | 'both' } | { act: 'dispute' } | null
  >(null)
  /* APPROVING A PROPOSAL IS NOT ONE OF THIS SURFACE'S OWN ACTS. It is the
     owner's single act wherever it is performed, so it is performed by the
     shared dialog that states its effect -- not by a Compare-local path. */
  const [approving, setApproving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [refused, setRefused] = useState<string | null>(null)

  const subject = aboutOf(l.data) ?? aboutOf(r.data) ?? null
  const bothStand = Boolean(l.data?.stands && r.data?.stands)
  /* WHICH ONE IS ONLY PROPOSED TO REPLACE THE OTHER, FROM THE RECORD. A
     `proposes-to-supersede` link from the right to the left says exactly
     that, and it says it while the left goes on standing -- which is the
     whole distinction this view has to be able to state. */
  const proposedAgainstLeft = Boolean(
    r.data?.proposed?.predecessors.items.some((x) => x.entry === left),
  )
  /* AND WHAT CAN STILL BE SAID WHEN NOBODY RECORDED ONE. One stands, the
     other is written and nobody established it. That is weaker -- it is two
     facts about standing, not a claim that anybody put the second forward --
     so it is kept apart and never described as a proposal anybody made.
     IT IS NOT MERGED WITH `proposedAgainstLeft` ANY MORE. It was, into one
     `proposedReplacement` flag that drove the title, the lede and two button
     labels, so four sentences said "proposed replacement" over a record
     holding no such link -- and the one honest retraction sat below all four.
     Each case now says its own words. */
  const inferredOnly = Boolean(
    !proposedAgainstLeft &&
      l.data?.stands &&
      r.data &&
      !r.data.stands &&
      r.data.superseded_by.length === 0,
  )

  /* WHERE THE SUCCESSOR ACTUALLY IS, FROM THE RECORD, NOT FROM THE LINK.
     The `proposes-to-supersede` link is deliberately never withdrawn: it
     stays after the candidate is established, after it ends, after something
     else replaces it. So branching anything on the link's EXISTENCE says
     "proposed and reaches nobody" for ever -- beside chips on this same
     screen reading `stands`. `successorReach.ts` exists so two surfaces
     cannot disagree about one item; this is the surface that was disagreeing.
     Null is the fourth answer: the read is not back, and nothing is said. */
  const proposalRow =
    l.data?.proposed?.successors.items.find((x) => x.entry === right) ?? null
  const successorState: SuccessorState | null =
    proposalRow?.state ?? (r.data && !r.data.missing ? standingOf(r.data) : null)
  /* AND WHERE THE PREDECESSOR IS, read rather than assumed. `null` is a Kind
     that never declared whether standing is meaningful for its entries: no
     standing to report, which is not the same as not standing. */
  const predecessorStands: boolean | null =
    !l.data || l.data.missing || standingUndeclared(l.data) ? null : l.data.stands

  /** One side, as an act has to speak about it: the record's own words, the
   *  record's own standing word, and nothing this file made up. */
  const actable = (e: EntryRead | null | undefined): ActItem | null =>
    e && !e.missing
      ? {
          entry: e.id,
          kind: e.kind,
          text: saidBy(e) ?? 'nothing written in its declared fields',
          stands: e.stands,
          author_alias: e.author_alias ?? null,
          standing: standingWords(e),
        }
      : null
  const leftItem = actable(l.data)
  const rightItem = actable(r.data)
  /* THE CONDITIONS THE CONTROLS THEMSELVES ARE RENDERED ON, named once so
     the sentence that describes a control and the control cannot drift. */
  const supersedeLeft = !!(me && leftItem && (bothStand || l.data?.stands))
  const supersedeRight = !!(me && rightItem && r.data?.stands)
  const replaceBoth = !!(bothStand && me && leftItem && rightItem)
  /* THE ACT THE PROPOSAL OFFERS IS OFFERED WHILE THERE IS A PROPOSAL TO
     APPROVE, AND NOT AFTER. Establishing an already-established successor is
     refused by the route; offering it anyway put a dead control under five
     sentences that were false for the same reason. */
  const approvable = proposedAgainstLeft && !!me && successorState === 'candidate'
  const establishInferred = inferredOnly && successorState === 'candidate'
  const disputable = (proposedAgainstLeft || inferredOnly) && !!me && !!rightItem

  const title = bothStand
    ? `Two standing items that speak to “${subject ?? ''}”`
    : proposedAgainstLeft
      ? proposalTitle(successorState, predecessorStands)
      : inferredOnly
        ? 'One item stands and the other was never established'
        : 'Two items, side by side'

  const perform = async (run: () => Promise<unknown>) => {
    setBusy(true)
    setRefused(null)
    try {
      await run()
      setActing(null)
      // The record moved. Every reader rereads its own path; nothing is
      // pushed and no second model of anything is built.
      announceAdvance()
    } catch (e) {
      // THE ROUTE'S OWN REFUSAL, IN ITS OWN WORDS. It knows what may replace
      // what — same Kind, standing, placed where the old material applied —
      // and this never second-guesses it or paraphrases it.
      setRefused((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="xs">
      <div className="xs-head">
        <div className="xs-eyebrow">Compare</div>
        <h2>{title}</h2>
        <div className="xs-actions">
          {onBack && <button onClick={onBack}>← Back to {origin ?? 'where you came from'}</button>}
        </div>
      </div>

      {(l.error || r.error) && <p className="xs-error">API error: {l.error ?? r.error}</p>}

      {ask && (
        <div>
          <p className="xs-card-meta">
            {ask.by_alias} asked you {when(ask.at)}
            {ask.conversation_name ? ` · ${ask.conversation_name}` : ''}
          </p>
          <p className="xs-lede">{ask.question}</p>
        </div>
      )}

      <Situation
        bothStand={bothStand}
        recorded={proposedAgainstLeft}
        inferredOnly={inferredOnly}
        successorState={successorState}
        predecessorStands={predecessorStands}
        conversation={conversation}
        left={left}
        ctx={ctx.data}
        right={right}
        leftSaid={saidBy(l.data)}
      />

      <div className="xs-cards">
        <Column
          label="Left"
          entry={left}
          read={l.data}
          timeline={hl.data?.timeline}
          conditions={cond.data}
          ctx={ctx.data}
          conversation={conversation}
          onOpenEntry={onOpenEntry}
          onTrace={onTrace}
          onDeliveryEvidence={onDeliveryEvidence}
          onSupersede={
            supersedeLeft
              ? () => setActing({ act: 'supersede', side: 'left' })
              : undefined
          }
          supersedeLabel="Supersede left only…"
        />
        <Column
          label="Right"
          entry={right}
          read={r.data}
          timeline={hr.data?.timeline}
          conditions={cond.data}
          ctx={ctx.data}
          conversation={conversation}
          onOpenEntry={onOpenEntry}
          onTrace={onTrace}
          onDeliveryEvidence={onDeliveryEvidence}
          onSupersede={
            supersedeRight
              ? () => setActing({ act: 'supersede', side: 'right' })
              : undefined
          }
          supersedeLabel="Supersede right only…"
        />
      </div>

      {/* WHAT EACH CHOICE DOES, BEFORE ANYTHING IS CLICKED. This is the
          clearest statement in the whole design that an act is understood
          before it is taken, and it is quoted as approved.

          IT DESCRIBES THE CHOICES THAT ARE HERE, AND ONLY THOSE. The three
          ask-driven ones exist when an ask drove this look and not otherwise,
          so describing them unconditionally told a reader with no ask about
          three controls they could not find. Saying what a button does is
          only a kindness while the button is on the screen. */}
      <div className="xs-consequence">
        <strong>What each choice does.</strong>{' '}
        {/* AND THE OTHER TWO, GATED ON THE SAME CONDITIONS THAT RENDER THEM.
            The ask-driven sentences were gated and these two were not, so a
            reader with nothing to supersede — neither item standing, or
            nobody to attribute an act to — was told what two buttons did that
            were not on the page. It is the same defect as the one above it,
            and the rule the file already states applies to it: saying what a
            button does is only a kindness while the button is on screen. */}
        {/* ONE SENTENCE PER BUTTON, NAMING THE BUTTON THAT IS THERE. A single
            sentence gated on "either side can be superseded" named both
            sides, so a reader with one door was told about two. */}
        {supersedeLeft && (
          <>
            <em>Supersede left only</em>: you write a replacement that is established at once,
            inherits that item's placement and ends it; the other keeps standing.{' '}
          </>
        )}
        {supersedeRight && (
          <>
            <em>Supersede right only</em>: you write a replacement that is established at once,
            inherits that item's placement and ends it; the other keeps standing.{' '}
          </>
        )}
        {/* AND THE TWO THAT WERE ON THE PAGE WITH NO SENTENCE AT ALL. */}
        {approvable && (
          <>
            <em>Establish replacement</em>: one act establishes the proposed successor and records
            its supersession of every predecessor the proposal named, together or not at all.{' '}
          </>
        )}
        {establishInferred && onEstablish && (
          <>
            <em>Establish the other</em>: it is established on its own and ends nothing, because
            nothing in the record says it was put forward to replace anything.{' '}
          </>
        )}
        {disputable && (
          <>
            <em>{recordedDisputeLabel(proposedAgainstLeft).replace('…', '')}</em>: a note is
            recorded saying why you
            disagree. It confers nothing and revokes nothing: what stood still stands.{' '}
          </>
        )}
        {replaceBoth && (
          <>
            <em>Replace both with one</em>: one replacement ends both and inherits both
            placements.{' '}
          </>
        )}
        {ask && (
          <>
            <em>Answer “Keep both”</em>: both keep standing and current composition keeps including
            both; the overlap stays visible. <em>Answer “Not now”</em> records a reply and closes
            the ask without changing anything. <em>Leave open</em> records nothing and the ask stays
            owed.{' '}
          </>
        )}
        In every case past delivery records are unchanged.
      </div>

      {refused && <p className="xs-error">{refused}</p>}

      {approving && r.data && l.data && (
        <ActDialog
          act="establish"
          item={{
            entry: right,
            kind: r.data.kind,
            text: saidBy(r.data) ?? 'nothing written in its fields',
            stands: r.data.stands,
            author_alias: r.data.author_alias ?? null,
            standing: r.data.stands ? 'stands' : 'candidate',
          }}
          /* WHAT APPROVING IT ENDS, taken from the proposal itself so that a
             proposal naming several predecessors is not described as ending
             one. One confirmation establishes the successor and records its
             supersession of every one of them. */
          ends={(r.data.proposed?.predecessors.items ?? []).map((x) => ({
            entry: x.entry,
            kind: x.kind,
            text: x.summary ?? 'nothing written in its fields',
            stands: x.stands,
            standing: x.state,
          })) as ActItem[]}
          me={me}
          onCancel={() => setApproving(false)}
          onDone={(_outcome: ActOutcome) => {
            setApproving(false)
            announceAdvance()
          }}
        />
      )}

      {/* SUPERSEDING, IN THE FORM THAT CAN ACTUALLY WRITE A REPLACEMENT. This
          was a single text box asking the owner to type an entry id, which
          meant the replacement had to have been written somewhere else first
          and its id carried here by hand. The shared dialog shows the old
          words as the immutable thing they are, offers the fields the Kind
          declares, states what the act ends and what it leaves alone, and
          attributes it (I-113, I-114, I-128). */}
      {acting?.act === 'supersede' && leftItem && rightItem && (
        <ActDialog
          act="supersede"
          item={acting.side === 'right' ? rightItem : leftItem}
          /* THE OTHER SIDE IS IN PLAY ONLY WHEN THE OWNER SAID SO. Offering
             the choice of ending both from a door named "Supersede left only"
             would put a second decision inside the first one. */
          partner={acting.side === 'both' ? rightItem : null}
          endsChosen={acting.side === 'both' ? 'both' : 'this'}
          me={me}
          onCancel={() => setActing(null)}
          onDone={(_outcome: ActOutcome) => {
            setActing(null)
            announceAdvance()
          }}
        />
      )}

      {acting?.act === 'dispute' && rightItem && (
        <ActDialog
          act="dispute"
          item={rightItem}
          me={me}
          onCancel={() => setActing(null)}
          onDone={(_outcome: ActOutcome) => {
            setActing(null)
            announceAdvance()
          }}
        />
      )}

      {ask && answerHere && <div className="xs-answer-here">{answerHere}</div>}

      <div className="xs-actions">
        {replaceBoth && (
          <button onClick={() => setActing({ act: 'supersede', side: 'both' })}>
            Replace both with one…
          </button>
        )}
        {/* THE ONE-ACT APPROVAL, OFFERED ONLY WHERE THE RECORD SAYS THERE IS
            A PROPOSAL TO APPROVE. Where nothing recorded one, the door still
            opens the item so the owner can establish it as its own act --
            which ends nothing, because nothing said it would. */}
        {approvable && (
          <button onClick={() => setApproving(true)}>Establish replacement…</button>
        )}
        {establishInferred && onEstablish && (
          <button onClick={() => onEstablish(right)}>Establish the other…</button>
        )}
        {disputable && (
          <button onClick={() => setActing({ act: 'dispute' })}>
            {recordedDisputeLabel(proposedAgainstLeft)}
          </button>
        )}
        {ask && onAnswer && !answerHere && (
          <>
            <button disabled={busy} onClick={() => void perform(async () => onAnswer('Keep both'))}>
              Answer “Keep both” &amp; close
            </button>
            <button disabled={busy} onClick={() => void perform(async () => onAnswer('Not now'))}>
              Answer “Not now” &amp; close
            </button>
          </>
        )}
        {ask && onLeaveOpen && <button onClick={onLeaveOpen}>Leave open</button>}
      </div>

      {/* NOBODY IS ASKING, AND THAT IS SAID — ONCE THE RECORD HAS SAID IT. A
          surface full of acts with no ask behind it reads as an ask; a
          surface that announces nobody is asking before it has looked is
          worse, because it says so while somebody is waiting. `undefined` is
          UNKNOWN and claims neither. */}
      {ask === null && (
        <p className="xs-note">Nobody is asking. Doing nothing is a legitimate answer.</p>
      )}
    </div>
  )
}

/* ------------------------------- the situation stated ------------------------------- */

function Situation({
  bothStand,
  recorded,
  inferredOnly,
  successorState,
  predecessorStands,
  conversation,
  left,
  right,
  ctx,
  leftSaid,
}: {
  bothStand: boolean
  /** the record holds a `proposes-to-supersede` link, rather than this being
   *  read off the fact that one of the two does not stand. */
  recorded: boolean
  /** no such link, and the weaker pair of standing facts holds instead. The
   *  two are exclusive and neither borrows the other's words. */
  inferredOnly: boolean
  /** where the successor is NOW, not whether it was ever put forward. Null
   *  until the read is back, and then nothing is said. */
  successorState: SuccessorState | null
  /** and where the predecessor is. Null is a Kind with no standing declared. */
  predecessorStands: boolean | null
  conversation: Id | null
  left: Id
  right: Id
  ctx: Context | null
  leftSaid: string | null
}) {
  const inThere = conversation ? ` in ${conversation}` : ''
  const includesBoth =
    ctx !== null &&
    [left, right].every((id) => ctx.components.some((c) => c.source_id === id))

  if (bothStand) {
    return (
      <div>
        <p className="xs-note">
          Both stand, and both apply{inThere}
          {includesBoth ? ': current composition includes both' : ''}. Mentis has no precedence
          between them, and this view does not choose one.
        </p>
        {/* SAID, NOT GUESSED. How many delivery records carry BOTH is a real
            question and no read answers it: nothing selects deliveries by the
            item they name. A number here would be a number nobody counted. */}
        <p className="xs-aside">
          How many delivery records carry both is not computed here: no read answers which
          executions named an item.
        </p>
      </div>
    )
  }
  const said = leftSaid ? `“${leftSaid.slice(0, 80)}${leftSaid.length > 80 ? '…' : ''}”` : left

  if (recorded) {
    /* THE SENTENCE AND THE CHIP NOW ASK THE SAME FIELD. `successorReach` is
       the one place that turns the successor's state into words, and it is
       already what the register rows, the item legs and the inspector say. */
    if (successorState === null) {
      return <p className="xs-note">Reading what the record says about the replacement…</p>
    }
    return (
      <div>
        <p className="xs-note">
          {successorReach(successorState, said, predecessorStands)}
          {successorState === 'candidate' && predecessorStands
            ? ' Establishing it ends the standing one; past delivery records keep naming the old one.'
            : ''}
        </p>
        {/* WHAT THE PROPOSAL ITSELF IS, AND NOTHING ABOUT ITS OUTCOME. That a
            successor stands says nothing about which predecessor it ended:
            those are two facts on two relations, and `superseded_by` is the
            one that answers it. So "that proposal has ended nothing" is said
            only where it is still true -- while it is still a proposal. */}
        <p className="xs-aside">
          The record says it was proposed to replace this one.
          {successorState === 'candidate'
            ? ' That proposal has ended nothing.'
            : ' What it ended, if anything, is written on its own relation.'}
        </p>
      </div>
    )
  }
  if (inferredOnly) {
    /* ITS OWN, WEAKER WORDS. Nobody put this forward as a replacement -- the
       record holds two facts about standing and no proposal -- so the word
       "proposal" is not used and no act is described as approving one. */
    return (
      <div>
        <p className="xs-note">
          {said} stands. The other was written and nobody established it, so it reaches nobody.
        </p>
        <p className="xs-aside">
          Nothing in the record says anybody proposed it as a replacement for this one: what the
          record holds is that one stands and the other was never established.
        </p>
      </div>
    )
  }
  return <p className="xs-note">These two do not both stand.</p>
}

/* ------------------------------------ one column ------------------------------------ */

function Column({
  label,
  entry,
  read,
  timeline,
  conditions,
  ctx,
  conversation,
  onOpenEntry,
  onTrace,
  onDeliveryEvidence,
  onSupersede,
  supersedeLabel,
}: {
  label: string
  entry: Id
  read: EntryRead | null | undefined
  timeline: TimelineRow[] | undefined
  conditions: Conditions | null
  ctx: Context | null
  conversation: Id | null
  onOpenEntry?: (e: Id) => void
  onTrace?: (e: Id) => void
  onDeliveryEvidence?: (e: Id) => void
  onSupersede?: () => void
  supersedeLabel: string
}) {
  const row = useMemo(() => timeline?.find((t) => t.entry === entry), [timeline, entry])
  const est = row?.established?.[0] ?? null
  const evidence = conditions?.rows.find((c) => c.entry === entry)
  const here = conversation ? ' here' : ''

  // THREE ANSWERS, NOT TWO. In the composition, withheld with the machine's
  // own reason, or in neither — and the third is said rather than shown as a
  // blank cell.
  const inUse = ctx?.components.find((c) => c.source_id === entry)
  const held = ctx?.withheld.find((w) => w.source_id === entry)

  const standing = row?.state ? (STATE_SAID[row.state] ?? row.state) : null

  return (
    <section className="xs-card">
      <div className="xs-col-label">{label}</div>
      <div className="xs-card-head">
        <h3>{read?.kind ?? read?.family ?? 'entry'}</h3>
        {standing && <span className="xs-tag">{standing}</span>}
      </div>
      <div className="xs-card-meta mono">{entry}</div>
      <p className="xs-body-text">{saidBy(read) ?? <em>nothing written in its declared fields</em>}</p>

      <dl className="xs-dl">
        <dt>Why it applies{here}</dt>
        <dd>
          {inUse ? (
            inUse.why
          ) : held ? (
            <>withheld: {held.why}</>
          ) : ctx === null ? (
            <em>not computed: no Participant was named to compute a composition for</em>
          ) : (
            <em>current composition does not include it</em>
          )}
        </dd>

        <dt>Provenance</dt>
        <dd>
          {est ? (
            <>
              established by {est.by_alias ?? est.by ?? <em>nobody it can name</em>} {when(est.at)}
              {est.reason ? ` · ${est.reason}` : ''}
            </>
          ) : (
            <em>nobody established it</em>
          )}
          <br />
          written by {read?.author_alias ?? read?.at ?? '—'}
          {read?.written_by ? ` · ${read.written_by}` : ''}
        </dd>

        <dt>Delivery evidence{here}</dt>
        <dd>
          {!evidence ? (
            'reading the records…'
          ) : evidence.uncounted ? (
            /* ABSENT, NOT ZERO. No record names it, so nothing was counted. */
            <>none recorded: it has never crossed{here}</>
          ) : (
            <>
              {evidence.records} records
              {onDeliveryEvidence && (
                <>
                  {' · '}
                  <button className="xs-link" onClick={() => onDeliveryEvidence(entry)}>
                    open the delivery records
                  </button>
                </>
              )}
            </>
          )}
          {conditions && <p className="xs-aside">{conditions.counts_are}</p>}
        </dd>

        <dt>Speaks to</dt>
        <dd>{aboutOf(read) ? `“${aboutOf(read)}”` : <em>the record does not say</em>}</dd>
      </dl>

      <div className="xs-col-actions">
        {onSupersede && <button onClick={onSupersede}>{supersedeLabel}</button>}
        {onOpenEntry && (
          <button className="xs-link" onClick={() => onOpenEntry(entry)}>
            Inspect
          </button>
        )}
        {onTrace && (
          <button className="xs-link" onClick={() => onTrace(entry)}>
            Trace
          </button>
        )}
      </div>
    </section>
  )
}
