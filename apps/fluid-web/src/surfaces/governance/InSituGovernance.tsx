import { useState } from 'react'
import { shortId, type Id } from '../../api'
import {
  dispute,
  establish,
  establishReplacement,
  mayDispute,
  mayEstablish,
  revise,
  setAside,
  standingWords,
  type StandingFacts,
} from '../standing'
import { InlineForm, Landing, RecordsNothing, useAct } from './InSituForms'
import {
  useInSituIndex,
  useItem,
  type InSituIndex,
  type ItemTimeline,
  type RegisterRow,
} from './InSituRecord'
import './InSituGovernance.css'

/* ------------------------------------------------------------------------ *
 * GOVERNANCE WHERE THE WORK MET IT, AND NOWHERE ELSE.
 *
 * ONLY WHERE THE WORK MET SOMETHING. A Turn carries this when the work done
 * in it brought governed material into being. Every other Turn carries
 * nothing extra — no empty panel, no "no governance here", no affordance
 * waiting to be useful. A Conversation of ordinary Turns looks exactly as it
 * did.
 *
 * ONE MECHANISM, NOT TWO. The Turn holds a REFERENCE. Everything drawn here
 * is read from the item's own current state, and every act offered is the
 * same act the Governance workspace performs, through the same helpers and
 * the same routes. There is no Conversation-local copy of governance state
 * and no in-situ commit path — if there were, the two would eventually
 * disagree, and the record would have two answers to one question.
 *
 * WHICH MEANS IT COLLAPSES. Material that has been dealt with becomes one
 * line saying what happened and pointing onward, so a working surface does
 * not silently become a governance queue.
 *
 * NO KIND IS NAMED HERE. The Kind's own name is a word this prints; nothing
 * branches on it, and nothing here was taught the names of the Kinds we have.
 * ------------------------------------------------------------------------ */

/** "Inspect in Governance", when the workspace is wired to hear it.
 *
 *  THE SHELL OWNS THE WORKSPACE, and this package does not. A card says where
 *  it wants to go by announcing it; whatever holds the workspace listens and
 *  calls `preventDefault` to say it took it. Unhandled, the card says so
 *  rather than looking like a control that works. */
export const INSPECT_EVENT = 'mentis:inspect-in-governance'

export function announceInspect(entry: Id): boolean {
  const e = new CustomEvent<{ entry: Id }>(INSPECT_EVENT, {
    detail: { entry },
    cancelable: true,
  })
  window.dispatchEvent(e)
  return e.defaultPrevented
}

/** The same arrangement for putting two items side by side in the workspace.
 *  A card in a Turn has room for the two texts and no room for the provenance,
 *  the delivery evidence and the consequence block that Compare carries. */
export const COMPARE_EVENT = 'mentis:compare-in-governance'

export function announceCompare(left: Id, right: Id): boolean {
  const e = new CustomEvent<{ left: Id; right: Id }>(COMPARE_EVENT, {
    detail: { left, right },
    cancelable: true,
  })
  window.dispatchEvent(e)
  return e.defaultPrevented
}

export interface InSituGovernanceProps {
  conversation: Id
  turn: Id
  /** who is acting: the owner's own Participant, where one is known */
  me: Id | null
  /** an ask of the owner is open on this Turn, so a challenge on the material
   *  is already covered and is not offered a second time beside it */
  askCovers?: boolean
  /** the shell's own way into the inspector, where it passes one */
  onInspectEntry?: (entry: Id) => void
}

export default function InSituGovernance({
  conversation,
  turn,
  me,
  askCovers = false,
  onInspectEntry,
}: InSituGovernanceProps) {
  const index = useInSituIndex(conversation)
  const here = index.byTurn(turn)
  /* NOTHING TO SAY IS SAID BY SAYING NOTHING. A read that failed is a
     different matter and belongs to whoever asked for the read; an ordinary
     Turn must not grow a line because a request was slow. */
  if (here.items.length === 0) return null
  return (
    <div className="insitu" onClick={(e) => e.stopPropagation()}>
      {here.items.map((entry) => (
        <ItemCard
          key={entry}
          entry={entry}
          index={index}
          me={me}
          askCovers={askCovers}
          onInspectEntry={onInspectEntry}
        />
      ))}
    </div>
  )
}

/* --------------------------------- one item ------------------------------- */

type Opened = 'establish' | 'establish-replacement' | 'revise' | 'dispute' | null

function ItemCard({
  entry,
  index,
  me,
  askCovers,
  onInspectEntry,
}: {
  entry: Id
  index: InSituIndex
  me: Id | null
  askCovers: boolean
  onInspectEntry?: (entry: Id) => void
}) {
  const { item, error } = useItem(entry)
  const row = index.row(entry)
  const [open, setOpen] = useState<Opened>(null)
  /* LEFT FOR LATER IS NOT A STATE OF THE RECORD, and is not written as one.
     Leaving a proposal records nothing at all; this is the card folding
     itself away for the person who folded it, and Governance still lists the
     proposal exactly as it did. */
  const [folded, setFolded] = useState(false)
  const [leftProposed, setLeftProposed] = useState(false)
  const act = useAct()

  if (error)
    return (
      <p className="insitu-failed" role="status">
        This item could not be read ({error}).
      </p>
    )
  if (!item || !row) return null

  const kind = item.kind ?? row.kind
  const text = row.summary || '—'
  const facts: StandingFacts = {
    stands: row.state === 'stands',
    established_by: row.established_by,
    superseded_by: row.superseded_by,
    standing_apt: row.standing_apt,
  }
  const inspect = () => {
    if (onInspectEntry) return onInspectEntry(entry)
    if (!announceInspect(entry)) act.setFailed(`Governance is not open in this workspace. The item is ${entry}.`)
  }
  const Inspect = (
    <button className="insitu-link" onClick={inspect}>
      Inspect in Governance
    </button>
  )

  /* THE COLLAPSED LINES. Each states what happened and points onward; none of
     them offers an act, because the record has already answered. */
  if (item.state !== 'candidate' || folded)
    return (
      <div className="insitu-line">
        <Settled item={item} row={row} index={index} kind={kind} text={text} left={leftProposed} />
        {' · '}
        {Inspect}
        {act.failed && (
          <p className="insitu-failed" role="alert">
            {act.failed}
          </p>
        )}
        {act.landed && <Landing landed={act.landed} />}
      </div>
    )

  const openDispute = item.disputes.filter((d) => !d.set_aside)
  /* WHAT THIS CANDIDATE IS PUT FORWARD TO REPLACE, from the record. Its
     presence is what makes this the third card shape: a proposal that stands
     in for something is read beside the thing it would stand in for, because
     the question is not "is this any good" but "is this better than what is
     there". Every one of them GOES ON STANDING while this waits. */
  const replaces = row.proposed?.predecessors.items ?? []
  const applies = row.placed_at.some((p) => p.whole_brain)
    ? 'Once established it applies to whoever acts in any Conversation, and to work at Brain scope.'
    : row.placed_at.length
    ? `Once established it applies to whoever acts in ${andList(row.placed_at.map((p) => p.name ?? p.conversation))}.`
    : 'Once established it applies only to an execution that names it.'

  return (
    <section className="insitu-card">
      <p className="insitu-head">
        <span className="insitu-kind">
          {replaces.length ? `Proposes replacing a standing ${kind}` : `Proposed ${kind}`}
        </span>
        {standingWords(facts) && <span className="insitu-standing"> · {standingWords(facts)}</span>}
        {openDispute.length > 0 && <span className="insitu-disputed"> · disputed</span>}
      </p>
      {replaces.length > 0 ? (
        /* THE TWO TEXTS, SIDE BY SIDE, IN SITU (I-147). The standing one is
           first because it is the one in force; each carries its own standing
           word, so neither column can be read as the other's verdict. */
        <div className="insitu-pair">
          <div className="insitu-side">
            <p className="insitu-side-head">Stands now</p>
            {replaces.map((x) => (
              <blockquote className="insitu-text" key={x.link}>
                {x.summary || '—'}
                <span className="insitu-standing"> · {x.state}</span>
              </blockquote>
            ))}
          </div>
          <div className="insitu-side">
            <p className="insitu-side-head">Proposed replacement</p>
            <blockquote className="insitu-text">
              {text}
              <span className="insitu-standing"> · reaches nobody</span>
            </blockquote>
          </div>
        </div>
      ) : (
        <blockquote className="insitu-text">{text}</blockquote>
      )}
      <p className="insitu-reach">
        {replaces.length > 0 ? (
          <>
            The replacement reaches nobody until established; what it would replace keeps
            standing meanwhile. Nobody asked you.
          </>
        ) : (
          <>{applies} Until then it reaches nobody.</>
        )}
      </p>

      {/* A CHALLENGE ON IT, AND THE ANSWER TO ONE. Both facts stay true at
          once — it is disputed AND it is where it was — so the challenge is
          shown beside the material and never over it. */}
      {openDispute.map((d) => (
        <Challenge
          key={d.link}
          entry={entry}
          dispute={d}
          me={me}
          covered={askCovers}
          onDone={() => setOpen(null)}
        />
      ))}

      {open === null ? (
        <div className="insitu-acts">
          {replaces.length > 0 && (
            <button
              className="insitu-link"
              onClick={() => {
                if (!announceCompare(replaces[0].entry, entry))
                  act.setFailed(
                    `Governance is not open in this workspace. The two items are ` +
                      `${replaces[0].entry} and ${entry}.`,
                  )
              }}
            >
              Compare
            </button>
          )}
          {mayEstablish(facts, me) && (
            <button
              className="insitu-go"
              onClick={() => setOpen(replaces.length > 0 ? 'establish-replacement' : 'establish')}
            >
              {replaces.length > 0 ? 'Establish replacement…' : 'Establish…'}
            </button>
          )}
          {mayEstablish(facts, me) && replaces.length === 0 && (
            <button className="insitu-link" onClick={() => setOpen('revise')}>
              Revise &amp; establish…
            </button>
          )}
          {mayDispute(facts, me) && (
            <button className="insitu-link" onClick={() => setOpen('dispute')}>
              Dispute…
            </button>
          )}
          <RecordsNothing
            label="Leave proposed"
            title="Records nothing. It stays proposed, reaches nobody, and Governance still lists it."
            onClick={() => {
              setLeftProposed(true)
              setFolded(true)
            }}
          />
          {Inspect}
        </div>
      ) : open === 'establish' ? (
        <InlineForm
          kind="establish"
          intro={
            <>
              It will stand from the moment you confirm
              {row.placed_at.length > 0 && ', and apply to whoever acts here'}.
            </>
          }
          busy={act.busy}
          failed={act.failed}
          onCancel={() => setOpen(null)}
          onGo={(said) =>
            void act
              .run(`${cap(kind)} established.`, () => establish(entry, me, said || 'accepted'))
              .then((ok) => ok && setOpen(null))
          }
        />
      ) : open === 'establish-replacement' ? (
        /* THE ONE ACT, IN PLACE. The same route Governance calls: the
           successor is established and one `supersedes` link is written per
           predecessor, together. The intro says both before the fields,
           because that is what the single confirmation does. */
        <InlineForm
          kind="establish"
          intro={
            <>
              It will stand from the moment you confirm, and{' '}
              {replaces.length === 1 ? 'the one it replaces ends' : 'each one it replaces ends'} in
              the same act. Past delivery records that name them stay exactly as they are.
            </>
          }
          busy={act.busy}
          failed={act.failed}
          onCancel={() => setOpen(null)}
          onGo={(said) =>
            void act
              .run(
                `${cap(kind)} established; ${
                  replaces.length === 1 ? 'the previous one ended' : 'the previous ones ended'
                }.`,
                () =>
                  establishReplacement(
                    replaces[0].entry,
                    entry,
                    me,
                    said || 'the proposed replacement was accepted',
                    replaces.slice(1).map((x) => x.entry),
                  ),
              )
              .then((ok) => ok && setOpen(null))
          }
        />
      ) : open === 'revise' ? (
        <Revision
          entry={entry}
          item={item}
          text={text}
          me={me}
          act={act}
          onDone={() => setOpen(null)}
        />
      ) : (
        <InlineForm
          kind="dispute"
          intro="Recorded against it; nothing else changes."
          busy={act.busy}
          failed={act.failed}
          onCancel={() => setOpen(null)}
          onGo={(said) =>
            void act
              .run('Dispute recorded; the material is where it was.', () => dispute(entry, me, said))
              .then((ok) => ok && setOpen(null))
          }
        />
      )}
      {open === null && act.failed && (
        <p className="insitu-failed" role="alert">
          {act.failed}
        </p>
      )}
      {act.landed && <Landing landed={act.landed} />}
    </section>
  )
}

/* ------------------------------- what happened ---------------------------- */

/** ONE LINE FOR ANYTHING THE RECORD HAS ANSWERED, and the two texts side by
 *  side where one item replaced another, so the change can be read without
 *  going anywhere. */
function Settled({
  item,
  row,
  index,
  kind,
  text,
  left,
}: {
  item: ItemTimeline
  row: RegisterRow
  index: InSituIndex
  kind: string
  text: string
  left: boolean
}) {
  const replaced = item.supersedes[0]
  const was = replaced ? index.row(replaced.to) : null
  const successor = item.superseded_by[0]
  const now = successor ? index.row(successor.from) : null

  if (left && item.state === 'candidate')
    return (
      <>
        <span className="insitu-word">{cap(kind)} proposed, left for later.</span>{' '}
        <span className="insitu-quiet-text">
          Nothing was recorded. It still reaches nobody, and Governance still lists it.
        </span>
      </>
    )

  if (item.state === 'stands' && was)
    return (
      <>
        <span className="insitu-tick" aria-hidden="true">
          ✓
        </span>
        <span className="insitu-word">Replacement established; the earlier {kind} ended.</span>
        <span className="insitu-pair">
          <span className="insitu-was">
            <b>was</b> {was.summary || was.entry}
          </span>
          <span className="insitu-now">
            <b>now</b> {text}
          </span>
        </span>
      </>
    )

  if (item.state === 'stands')
    return (
      <>
        <span className="insitu-tick" aria-hidden="true">
          ✓
        </span>
        <span className="insitu-word">
          {cap(kind)} established: “{clip(text)}”
        </span>
        {standingWords(facts(row)) && (
          <span className="insitu-standing"> · {standingWords(facts(row))}</span>
        )}
      </>
    )

  if (item.state === 'replaced')
    return (
      <>
        <span className="insitu-tick" aria-hidden="true">
          ✓
        </span>
        <span className="insitu-word">
          Replaced by “{clip(now?.summary ?? successor?.from ?? '—')}”, which stands.
        </span>{' '}
        <span className="insitu-quiet-text">
          The proposal is unchanged and still readable; it was never established, so it never held.
        </span>
      </>
    )

  return (
    <>
      <span className="insitu-word">
        {cap(kind)} ended{now ? `; “${clip(now.summary)}” stands in its place` : ''}.
      </span>{' '}
      <span className="insitu-quiet-text">
        Nothing is deleted: it stays readable, and past delivery records keep naming it.
      </span>
    </>
  )
}

const facts = (row: RegisterRow): StandingFacts => ({
  stands: row.state === 'stands',
  established_by: row.established_by,
  superseded_by: row.superseded_by,
  standing_apt: row.standing_apt,
})

/* -------------------------------- a challenge ----------------------------- */

function Challenge({
  entry,
  dispute: d,
  me,
  covered,
  onDone,
}: {
  entry: Id
  dispute: ItemTimeline['disputes'][number]
  me: Id | null
  covered: boolean
  onDone: () => void
}) {
  const [open, setOpen] = useState(false)
  const act = useAct()
  return (
    <div className="insitu-dispute">
      <p>
        {/* WHO CHALLENGED IT. The alias where the read carries one; otherwise
            the identity as the record holds it, shortened — never "somebody"
            over an id the record does name. */}
        <span className="insitu-who">{d.by_alias ?? shortId(d.by, 14) ?? 'somebody'}</span> disputes
        this
        {d.reason ? `: “${clip(d.reason, 140)}”` : '.'}{' '}
        <span className="insitu-quiet-text">It revokes nothing until you act.</span>
      </p>
      {/* SUPPRESSED WHERE AN ASK ALREADY COVERS IT. Offering the same decision
          twice on one Turn makes two obligations out of one. */}
      {!covered &&
        (open ? (
          <InlineForm
            kind="set-aside"
            intro="The challenge stays recorded and still says what it said; what is recorded is that it was answered and the material held."
            busy={act.busy}
            failed={act.failed}
            onCancel={() => setOpen(false)}
            onGo={(said) =>
              void act
                .run('Dispute set aside; the material held.', () => setAside(entry, d.link, me, said))
                .then((ok) => {
                  if (ok) {
                    setOpen(false)
                    onDone()
                  }
                })
            }
          />
        ) : (
          <button className="insitu-link" onClick={() => setOpen(true)}>
            Set that dispute aside…
          </button>
        ))}
      {act.landed && <Landing landed={act.landed} />}
    </div>
  )
}

/* -------------------------------- a revision ------------------------------ */

/** REVISE AND ESTABLISH, IN ONE ACT AND WITHOUT AN EDIT.
 *
 *  The proposal is kept exactly as it was and was never established; the
 *  revised words become a new item of the same Kind, established, recorded as
 *  replacing it, and inheriting its placement. Which field the words belong in
 *  is the KIND'S answer, not this one's: the entry reports its Kind's declared
 *  fields in order, and the revision replaces the first one that carries a
 *  statement — the same field the register reads an item's summary from. */
function Revision({
  entry,
  item,
  text,
  me,
  act,
  onDone,
}: {
  entry: Id
  item: ItemTimeline
  text: string
  me: Id | null
  act: ReturnType<typeof useAct>
  onDone: () => void
}) {
  const body = item.body ?? {}
  const principal = Object.keys(body).find(
    (k) => typeof body[k] === 'string' && (body[k] as string).trim() === text.trim(),
  )

  if (!principal)
    return (
      <p className="insitu-failed" role="status">
        This item's Kind does not say which field carries its statement, so a revision cannot be
        written from here. Governance has the fields.{' '}
        <button className="insitu-link" onClick={onDone}>
          Cancel
        </button>
      </p>
    )

  return (
    <InlineForm
      kind="revise"
      intro="The proposal stays as it was. Your revision is established as a new item that replaces it."
      initial={text}
      busy={act.busy}
      failed={act.failed}
      onCancel={onDone}
      onGo={(said) =>
        void act
          .run('Your revision is established and replaces the proposal.', () =>
            revise(entry, { ...body, [principal]: said }, me),
          )
          .then((ok) => ok && onDone())
      }
    />
  )
}

/* --------------------------------- wording -------------------------------- */

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

const clip = (s: string, n = 80) => (s.length <= n ? s : s.slice(0, n - 1).trimEnd() + '…')

const andList = (xs: string[]): string =>
  xs.length <= 1 ? (xs[0] ?? '') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]
