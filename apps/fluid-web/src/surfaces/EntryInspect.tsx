import Bounded from './governance/Bounded'
import { useState } from 'react'
import {
  announceAdvance,
  useApi,
  when,
  type DisputeRead,
  type Id,
  type Offers,
  type ProposedRead,
  type VersionsRead,
  type Deletion,
} from '../api'
/* uiux/edit: append-only Edit / Delete and the version history. */
import { EntryVersionActs, VersionList } from './Versions'
import { Empty, Loading } from '../bits'
import { useMe } from '../identity'
import { HeldThing, initialOf, isHeld, useHeld } from './DurableKind'
import KindWeb from './KindWeb'
import {
  Fold,
  InUseLeg,
  Life,
  Received,
  StandingLeg,
} from './governance/WorkspaceItemLegs'
/* THE ACTS THE TIMELINE OFFERS ARE THE ACTS THAT ALREADY EXIST. Setting a
   dispute aside and establishing a successor are both implemented in
   `ActDialog`, which states each effect before it is confirmed; the timeline
   opens those dialogs rather than growing a second path to the same routes. */
import ActDialog, { type ActItem, type ActOutcome } from './governance/ActDialogs'
import { useAskCoverage } from './governance/askCoverage'
import { isRefId } from '../refid'
import { Prose } from '../prose'
import {
  dispute,
  establish,
  mayDispute,
  mayEstablish,
  maySupersede,
  readProposal,
  standingOf,
  standingUndeclared,
  standingWords,
  supersede,
  supersedeEffect,
  type StandingFacts,
} from './standing'

/* ------------------------------------------------------------------------ *
 * A DURABLE OBJECT, INSPECTED.
 *
 * The Kind card in the Conversation is a DOOR: what is this, what does it
 * say, roughly where did it come from. This is the room behind it, and it
 * shows what the record actually knows — no more, and nothing invented.
 *
 * IT IS COMPOSED, NOT DUMPED. An earlier version listed every fact at one
 * level, which read as a settings inspector: the object itself had no more
 * weight than the id of the thing that wrote it. So the OBJECT LEADS — its
 * Kind, its principal statement, what that Kind means — and everything else
 * is support, in bands separated by space and a rule rather than by boxes.
 * Identity, hand and standing are folded away until asked for, because a
 * reader who came here to read a Finding did not come to read a UUID.
 *
 * TWO QUESTIONS, NEVER MERGED:
 *   what work produced it           the work that minted it -- provenance,
 *                                   a fold under History
 *   what it stands in relation to   ordinary Relations to other knowledge,
 *                                   its own band, drawn by `KindWeb`
 * They are different graphs with different sorts of node, and answering one
 * with the other would let "made by that run" read like "follows from that
 * finding".
 *
 * THREE PROVENANCE FACTS ARE KEPT APART for the same reason the substrate
 * stores them apart: `attributed_to` is whose assertion this is,
 * `written_by` is what actually typed it, `origin` is where the material came
 * from. A field the record does not carry is said to be absent.
 *
 * NO KIND IS NAMED IN THIS FILE. Fields come from the Kind's own declaration,
 * in its own declared order; relations explain themselves through the meaning
 * whoever defined them wrote.
 * ------------------------------------------------------------------------ */

interface Provenance {
  produced_by: {
    act: Id
    act_type?: string
    actor_alias?: string
    because?: string | null
    at?: number
    execution?: Id | null
    runtime?: string | null
    conversation?: Id | null
    turn?: Id | null
    turn_number?: number | null
    caused_by?: Id[]
  }[]
  why_not?: string
}

interface EntryDetail {
  id: Id
  missing?: boolean
  kind: string | null
  version?: number
  family?: string | null
  body: Record<string, unknown>
  attributed_to: Id
  author_alias: string
  written_by: string | null
  origin: unknown
  at: number
  stands: boolean
  /* THE CURRENT KIND'S ANSWER, NOT THIS ENTRY'S. Whether instances of this Kind
     participate in standing at all. Read by the server from the current Kind
     definition — `standing_apt_from` says so — while this entry's own `fields`
     and `meaning` stay pinned to the version it was written against. null is
     UNKNOWN and is never read as false. */
  standing_apt?: boolean | null
  standing_apt_from?: string
  standing_apt_kind_version?: number | null
  established_by: Id[]
  superseded_by: Id[]
  incoming: Record<string, Id[]>
  /** what is merely PROPOSED to replace this, and what this proposes to
   *  replace. Never `superseded_by`: these have ended nothing. Null where the
   *  record declares no such relation, which is not "none recorded". */
  proposed?: ProposedRead | null
  fields: string[]
  properties: Record<string, unknown>
  meaning: string | null
  provenance: Provenance
  /* uiux/edit: its versions, whether it was deleted, and what may be done. */
  versions?: VersionsRead
  deleted?: Deletion | null
  may?: Offers
}

const badge = (kind: string | null, family: string | null) =>
  initialOf({ kind, family } as never)

export interface EntryInspectProps {
  readOnly?: boolean
  id: Id
  onOpenEntry: (id: Id) => void
  /** follow the provenance link to the Turn this was proposed in, which is
   *  then flashed. The only history the Standing leg surfaces. */
  onGoToTurn?: (turn: Id) => void
  /** the Conversation this is being read in, or null for the Brain. "In use"
   *  means something different in each, so the sentence is scoped and says
   *  which scope it was computed for. */
  conversation?: Id | null
  conversationName?: string | null
  /** read inside the Governance workspace, where the doors below lead
   *  somewhere. Absent, the sections still render; only the doors are not
   *  offered, because offering one that goes nowhere is worse than not. */
  governance?: boolean
  /** folds a link asked to be open. A deep link that lands on a proposal
   *  opens the fold that explains it. */
  openFolds?: string[]
  onOpenExecution?: (execution: Id) => void
  onTrace?: (entry: Id) => void
  onCompare?: (left: Id, right: Id) => void
  onPreview?: () => void
  onOpenParticipant?: (participant: Id) => void
  /** Opens the media viewer on this entry's bytes, where it holds them. */
  onOpenMedia?: () => void
}

export default function EntryInspect({
  readOnly = false,
  id,
  onOpenEntry,
  onGoToTurn,
  conversation = null,
  conversationName,
  governance,
  openFolds,
  onOpenExecution,
  onTrace,
  onCompare,
  onPreview,
  onOpenParticipant,
  onOpenMedia,
}: EntryInspectProps) {
  const e = useApi<EntryDetail>(`/api/entries/${id}`)
  const d = e.data
  /* A HELD ARTIFACT IS SHOWN AS THE THING, NOT ITS ADDRESS -- as its card
     shows it. Its declared fields are a content hash and a submission id; they
     move down among the identity facts, where a reference belongs. */
  const held = !!d && !d.missing && isHeld(d.body)
  const about = useHeld(held ? id : null)
  const { me: owner } = useMe()
  const me = readOnly ? null : owner
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  /* WHICH ACT IS BEING PREPARED. One at a time, and none at rest: every act
     here says what it will do before it is done, so choosing one opens its
     explanation rather than performing it. */
  const [preparing, setPreparing] = useState<'establish' | 'dispute' | 'supersede' | null>(null)
  const [why, setWhy] = useState('')
  const [successor, setSuccessor] = useState('')
  /* THE ACT THE HISTORY OFFERS, held as the thing it is about: the challenge
     being answered. It opens a dialog rather than acting, for the same reason
     the act row above does. */
  const [answering, setAnswering] = useState<DisputeRead | null>(null)
  /* A PROPOSED SUCCESSOR THE OWNER IS ABOUT TO APPROVE, and everything that
     approving it would end. Held together because the dialog has to state
     both before the click: approving is ONE act, and an act that ends three
     things while naming one would be describing itself falsely. */
  const [approving, setApproving] = useState<
    { successor: ActItem; ends: ActItem[] } | null
  >(null)
  /* WHAT LANDED, said where the act was taken. An act that does not visibly
     land is an act somebody does twice. */
  const [landed, setLanded] = useState<string | null>(null)

  /* WHETHER AN ASK ALREADY COVERS THIS ITEM. A dispute this interface offers to
     set aside beside an open ask about the same material would make two
     obligations out of one, so the offer is withheld while one does — and
     withheld while the answer is still UNKNOWN, which is not the same as no ask
     covering it. */
  const asks = useAskCoverage(me)

  /* THE OWNER'S ACTS ON AN ENTRY, WHERE THEY ARE ALREADY READING IT. No new
     route and no new semantics: the same generic acts the header uses,
     offered where the entry is read. */
  const perform = async (run: () => Promise<unknown>) => {
    setBusy(true)
    setFailed(null)
    try {
      await run()
      setPreparing(null)
      setWhy('')
      setSuccessor('')
      /* EVERY READER, NOT ONLY THIS ONE. The same item may be on screen
         elsewhere -- its card where it arose, the header's lists -- and a card
         still saying "proposed" beside an inspector saying it stands is two
         readings of one record disagreeing. Measured: it did, until the next
         poll. So the advance is announced and each reader rereads its own. */
      e.reload()
      announceAdvance()
    } catch (err) {
      /* Said, not swallowed: an act that did not land must not look as though
         it did. The route's own refusal is the explanation. */
      setFailed(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  /* THE DIALOG'S OUTCOME. The act is recorded on the governed item this surface
     is reading, so it closes, says what landed, and tells every other reader of
     that item to read it again. */
  const settled = (outcome: ActOutcome) => {
    setAnswering(null)
    setLanded(outcome.said)
    e.reload()
    announceAdvance()
  }

  /* uiux/edit: LOADING ONLY WHEN THERE IS NOTHING YET TO SHOW. Every advance
     in the record rereads this, and returning <Loading> on a reread unmounted
     the whole inspector -- and any edit, delete or dispute half-written in it. */
  if (e.loading && !e.data) return <Loading state={e} />
  if (!d || d.missing) return <Empty>this brain does not hold that entry</Empty>

  const term = d.kind ?? d.family ?? 'entry'
  const declared = (d.fields.length ? d.fields : Object.keys(d.body)).filter((f) => {
    const v = d.body[f]
    return v !== undefined && v !== null && v !== ''
  })
  /* THE OBJECT LEADS. The Kind's FIRST declared field is the thing itself and
     is set as the statement; the rest are supporting values. The Kind decides
     which that is, by the order it declared its fields — this makes no
     judgement of its own and knows no Kind names. */
  const [principal, ...rest] = declared
  /* UNKNOWN IS NOT A STANDING. Where the Kind has not declared whether
     standing applies, no standing word is computed at all — `standing` is
     null, so none of the lines below that speak of standing can render —
     and the recorded links are shown as the facts they are. */
  const undeclared = standingUndeclared(d)
  const standing = undeclared ? null : standingOf(d)
  /* `disputes` is the substrate's own seeded Relation, read by its name: a
     Relation of the vocabulary, not a Kind. */
  const disputes = d.incoming?.disputes ?? []
  /* What may be done here, from the Kind's current definition and this
     entry's standing, never from which Kind it is. */
  const offers = (
    [
      ['establish', mayEstablish(d, me)],
      ['dispute', mayDispute(d, me)],
      ['supersede', maySupersede(d, me)],
    ] as const
  )
    .filter(([, ok]) => ok)
    .map(([a]) => a)

  /* MAY A CHALLENGE BE ANSWERED FROM HERE? Three conditions, and none of them
     is about the Kind: somebody has to be acting, the material has to still
     STAND — answering a challenge to a proposal would be answering the wrong
     question, and the record has already answered one that ended — and no open
     ask may cover it. `known` is what keeps UNKNOWN from reading as "nothing
     covers it". */
  /* WHETHER THIS ACT ANSWERS A REQUEST, SAID BEFORE IT IS TAKEN (I-41). The
     route answers every open ask whose expectation names this item when it is
     established or disputed (`_answered_asks`); the owner's open asks and what
     they name are already read above, so the sentence is the record's answer
     and not a guess. Unknown is said as unknown. */
  const answersSaid = !asks.known
    ? 'Whether a request to you names it is not known yet.'
    : asks.named.has(d.id)
      ? 'An open request to you names it: doing this answers that request.'
      : 'No open request to you names it, so this answers no request.'

  const mayAnswerChallenge =
    Boolean(me) && d.stands && asks.known && !asks.named.has(d.id)

  /* WHAT ESTABLISHING THIS SUCCESSOR WOULD END, READ FROM THE RECORD BEFORE
     ANYTHING IS SAID ABOUT IT. The proposal may name several predecessors and
     the one being read here is only the one the reader happens to be standing
     on, so the successor's own read is asked for the rest. Nothing is inferred
     from what is on screen. */
  const openApproval = async (successor: Id) => {
    setFailed(null)
    try {
      setApproving(await readProposal(successor))
    } catch (err) {
      setFailed((err as Error).message)
    }
  }

  /* THE ITEM, AS AN ACT NEEDS TO SPEAK ABOUT IT. The statement is the Kind's
     own first declared field, exactly as the lede above reads it, and the
     standing word is the one this interface is allowed to say. */
  const actItem: ActItem = {
    entry: d.id,
    kind: d.kind,
    text: principal ? String(d.body[principal]) : 'nothing written in its fields',
    stands: d.stands,
    author_alias: d.author_alias,
    standing: standingWords(d),
  }

  return (
    <article className="ei">
      <header className="ei-lede">
        <div className="ei-what">
          <span className="kind-badge" aria-hidden="true">
            {badge(d.kind, d.family ?? null)}
          </span>
          <span className="ei-term">{term}</span>
          {/* Superseded after it held, or superseded before it ever did: two
              different histories, and the second is never called ended. */}
          {standing === 'ended' && <span className="ei-flag">superseded</span>}
          {standing === 'replaced' && (
            <span className="ei-flag">replaced before establishment</span>
          )}
          {/* uiux/edit */}
          {d.deleted && <span className="ei-flag">deleted</span>}
        </div>
        {d.deleted && (
          <p className="ei-aside">
            deleted by {d.versions?.deleted?.by_alias ?? 'somebody'} · {when(d.deleted.at)}
            {d.deleted.because && d.deleted.because !== 'deleted' ? ` — ${d.deleted.because}` : ''}.
            It has no current standing or effect and nothing new builds on it; what it said is kept
            below as history.
          </p>
        )}
        {undeclared && (
          <p className="ei-aside ei-undeclared">
            standing not declared (UNKNOWN): this Kind's definition doesn't say whether standing
            applies, so this is not said to stand or not to stand
          </p>
        )}
        {held ? (
          <>
            <HeldThing
              entry={d.id}
              body={d.body}
              about={about.data}
              loading={about.loading}
              onOpen={onOpenMedia}
              large
            />
            {onOpenMedia && (
              <p className="ei-acts">
                <button className="ei-link" onClick={onOpenMedia}>
                  open it
                </button>
              </p>
            )}
          </>
        ) : (
          <>
            {principal && <div className="ei-statement"><Prose src={String(d.body[principal])} scope={`entry:${id}:${principal}`} /></div>}
            <p className={'ei-meaning' + (d.meaning ? '' : ' none')}>
              {d.meaning ?? 'this Kind declares no meaning, so none is shown'}
            </p>
          </>
        )}
        {disputes.length > 0 && (
          <p className="ei-aside">
            disputed{disputes.length > 1 ? ` ${disputes.length} times` : ''}
            {!undeclared && ' · '}
            {!undeclared &&
              (d.stands ? 'it still stands: a dispute does not end it' : 'it is still only proposed')}
          </p>
        )}
        {standing === 'candidate' && d.standing_apt === true && (
          <p className="ei-aside">proposed: it reaches nobody unless it is established</p>
        )}
        {offers.length > 0 && (
          <p className="ei-acts">
            {offers.map((a, i) => (
              <span key={a}>
                {i > 0 && ' · '}
                <button
                  className={'ei-link' + (preparing === a ? ' on' : '')}
                  aria-expanded={preparing === a}
                  disabled={busy}
                  onClick={() => {
                    setFailed(null)
                    setPreparing(preparing === a ? null : a)
                  }}
                >
                  {a}
                </button>
              </span>
            ))}
          </p>
        )}
        {preparing === 'establish' && (
          <div className="ei-prepare">
            <p className="ei-aside">
              Establishing makes this stand now, as your act.
              {d.author_alias ? ` ${d.author_alias.replace(/^@/, '')} stays its author.` : ''}{' '}
              {answersSaid}
            </p>
            <div className="ei-prepare-go">
              <button disabled={busy} onClick={() => void perform(() => establish(d.id, me))}>
                Establish now
              </button>
              <button className="ei-link" onClick={() => setPreparing(null)}>
                not now
              </button>
            </div>
          </div>
        )}
        {preparing === 'dispute' && (
          <div className="ei-prepare">
            <textarea
              value={why}
              rows={2}
              placeholder="Why you disagree"
              onChange={(ev) => setWhy(ev.target.value)}
            />
            <p className="ei-aside">
              Records your objection beside it, in your words.{' '}
              {d.stands
                ? 'It does not end it: it still stands.'
                : 'It does not answer it: it stays proposed.'}{' '}
              {answersSaid}
            </p>
            <div className="ei-prepare-go">
              <button
                disabled={busy || !why.trim()}
                onClick={() => void perform(() => dispute(d.id, me, why.trim()))}
              >
                Record dispute
              </button>
              <button className="ei-link" onClick={() => setPreparing(null)}>
                not now
              </button>
            </div>
          </div>
        )}
        {preparing === 'supersede' && (
          <Supersede
            facts={d}
            value={successor}
            onValue={setSuccessor}
            busy={busy}
            onOpenEntry={onOpenEntry}
            onGo={(to) => void perform(() => supersede(d.id, to, me))}
            onCancel={() => setPreparing(null)}
          />
        )}
        {/* THE ANSWER A PROPOSAL GOT. Nobody established it and somebody
            superseded it, so the supersession is the recorded answer to it.
            It is shown as it was written, nothing is offered on it, and what
            replaced it is one step away. */}
        {standing === 'replaced' && (
          <p className="ei-aside">
            proposed, never established, and replaced by{' '}
            {d.superseded_by.map((s, i) => (
              <span key={s}>
                {i > 0 && ', '}
                <button className="ei-link" onClick={() => onOpenEntry(s)}>
                  {d.superseded_by.length > 1 ? `successor ${i + 1}` : 'its successor'}
                </button>
              </span>
            ))}
          </p>
        )}
        {/* uiux/edit: offered only where the server says the act would land */}
        <EntryVersionActs
          d={d}
          me={me}
          onDone={(said) => {
            setLanded(said)
            e.reload()
          }}
        />
        {failed && <p className="ei-aside ei-failed">not done: {failed}</p>}
      </header>

      {!held && rest.length > 0 && (
        <Band>
          <dl className="ei-pairs">
            {rest.map((f) => (
              <div key={f}>
                <dt>{f}</dt>
                <dd><Prose src={String(d.body[f])} scope={`entry:${id}:${f}`} /></dd>
              </div>
            ))}
          </dl>
        </Band>
      )}

      {/* ------------------------------------------------ STANDING --- *
          What the record SAYS about it: authority, the establishing reason,
          the challenges and the successors. NO EXECUTION HISTORY AND NO DATES
          OF DELIVERY appear here — those are the two questions below, and they
          open only when somebody asks them. */}
      <Band title="Standing">
        <StandingLeg
          entry={d.id}
          authorAlias={d.author_alias}
          authorId={d.attributed_to}
          stands={d.stands}
          establishedBy={d.established_by}
          supersededBy={d.superseded_by}
          fromTurn={d.provenance.produced_by.find((b) => b.turn)?.turn ?? null}
          provenanceWhyNot={
            d.provenance.produced_by.length === 0
              ? (d.provenance.why_not ??
                'Nothing claims to have produced this, so where it was proposed is absent from the record.')
              : null
          }
          conversationName={conversationName}
          onOpenEntry={onOpenEntry}
          onGoToTurn={onGoToTurn}
          onOpenParticipant={onOpenParticipant}
          onSetAside={mayAnswerChallenge ? setAnswering : undefined}
          onEstablishReplacement={me ? (s) => void openApproval(s) : undefined}
        />
      </Band>

      {/* --------------------------------------------------- IN USE --- *
          One sentence, scoped, saying whether it reaches work here and why or
          why not — and naming the MACHINE'S OWN REASON where composition
          withholds it. Computed from what stands. It is not a record and it
          does not say what any execution received. */}
      <Band title={'In use' + (conversation ? ' · ' + (conversationName ?? conversation) : '')}>
        <InUseLeg
          entry={d.id}
          conversation={conversation}
          conversationName={conversationName}
          governance={governance}
          stands={d.stands}
          onTrace={onTrace}
          onCompare={onCompare}
          onPreview={onPreview}
        />
      </Band>

      {/* -------------------------------------------------- HISTORY --- *
          BOTH FOLDS CLOSED UNTIL OPENED. History appears when it is asked
          for; it does not occupy the surface. */}
      <Band title="History">
        <p className="ei-aside">opens only when you ask</p>
        {/* uiux/edit: every version, and the deletion that ended the line */}
        {d.versions && (d.versions.versions.length > 1 || d.versions.deleted) && (
          <Fold title={`Versions (${d.versions.versions.length})`} open={openFolds?.includes('versions')}>
            <VersionList read={d.versions} principal={principal} onOpenEntry={onOpenEntry} />
          </Fold>
        )}
        <Fold
          title="Where did it come from, and what did it replace?"
          open={openFolds?.includes('came-from')}
        >
          <Life
            entry={d.id}
            onOpenEntry={onOpenEntry}
            onSetAside={mayAnswerChallenge ? setAnswering : undefined}
            /* I-57: approve a proposed successor from the line that records
               it. The same one act the Standing leg offers, and the same
               dialog performs it. */
            onEstablishReplacement={me ? (s) => void openApproval(s) : undefined}
          />
        </Fold>
        <Fold
          title="What executions actually received it?"
          open={openFolds?.includes('received')}
        >
          <Received
            entry={d.id}
            conversation={conversation}
            onOpenExecution={onOpenExecution}
          />
        </Fold>
        {/* THE WORK THAT MINTED IT, RE-HOMED RATHER THAN DROPPED. It was its
            own top-level band, "how it came to exist"; composing the surface
            into legs took the band out and did not put its facts anywhere,
            so `act_type`, the actor's alias, the producing act's `because`,
            its runtime, when it was produced and how far its ancestry runs
            back to the steer all left the interface -- and every producing
            act after the first went with them, because what remained read
            only `produced_by.find(b => b.turn)`.

            It belongs here: "where did it come from" and "what produced it"
            are the same question asked of two graphs, and History is where
            this surface asks about the past. It is still never merged with
            "what it stands in relation to": that is ordinary Relations
            between knowledge, and answering one with the other would let
            "made by that run" read like "follows from that finding". */}
        <Fold
          title="What work produced it?"
          open={openFolds?.includes('produced-by')}
        >
          {d.provenance.produced_by.length === 0 ? (
            <p className="ei-faint">
              {d.provenance.why_not ?? 'nothing claims to have produced this'}
            </p>
          ) : (
            /* EVERY PRODUCING ACT, not the first one that happens to carry a
               Turn. More than one act claiming to have produced something is
               a fact about the record and showing one of them hides it. */
            <Bounded items={d.provenance.produced_by} label="Producing acts">{(b) => (
              <div className="ei-prov" key={b.act}>
                <p className="ei-prov-lede">
                  <b>{(b.actor_alias ?? '').replace(/^@/, '')}</b> {(b.act_type ?? 'recorded an act').replaceAll('-', ' ')}
                  {b.turn_number != null && onGoToTurn && b.turn && (
                    <>
                      {' · '}
                      <button className="ei-link" onClick={() => onGoToTurn(b.turn as Id)}>
                        from work on Turn #{b.turn_number}
                      </button>
                    </>
                  )}
                </p>
                {b.because && <p className="ei-aside">because {b.because}</p>}<details><summary>Technical details</summary><pre>{JSON.stringify(b, null, 2)}</pre></details>
                <p className="ei-aside">
                  {[
                    b.runtime,
                    b.at ? when(b.at) : null,
                    b.caused_by?.length
                      ? `${b.caused_by.length} acts of ancestry back to the steer`
                      : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </div>
            )}</Bounded>
          )}
        </Fold>
      </Band>

      <Band title="what it stands in relation to">
        <KindWeb id={id} onOpenEntry={onOpenEntry} />
      </Band>

      {/* Supporting facts, folded away. A reader who came to read a Finding
          did not come to read a reference id. */}
      <details className="ei-more">
        <summary>identity, hand and standing</summary>
        <dl className="ei-pairs">
          <Pair label="reference" value={d.id} mono />
          {held &&
            declared.map((f) => <Pair key={f} label={f} value={String(d.body[f])} mono />)}
          <Pair label="attributed to" value={d.author_alias} />
          <Pair
            label="written by"
            value={d.written_by}
            absent="not honestly known, so not recorded"
          />
          <Pair label="origin" value={d.origin ? String(d.origin) : null} absent="none recorded" />
          <Pair label="recorded" value={when(d.at)} />
          <Pair
            label="standing"
            value={
              undeclared
                ? /* The links are recorded facts; what they would mean for
                     standing is exactly what is not declared. */
                  'not declared (UNKNOWN)' +
                  (d.established_by.length || d.superseded_by.length
                    ? ' · recorded links: ' +
                      [
                        d.established_by.length
                          ? `establish ×${d.established_by.length}`
                          : null,
                        d.superseded_by.length ? `supersede ×${d.superseded_by.length}` : null,
                      ]
                        .filter(Boolean)
                        .join(', ')
                    : ' · no establish or supersede link recorded')
                : (d.stands
                    ? 'stands'
                    : standing === 'replaced'
                      ? 'never stood · replaced before establishment'
                      : 'does not stand') +
                  (d.established_by.length ? ` · established by ${d.established_by.length}` : '') +
                  (d.superseded_by.length ? ` · superseded by ${d.superseded_by.length}` : '')
            }
          />
          {Object.entries(d.properties)
            .filter(([k]) => k !== 'meaning')
            .map(([k, v]) => (
              <Pair key={k} label={k} value={String(v)} />
            ))}
        </dl>
      </details>

      {landed && (
        <p className="ei-landed" role="status">
          {landed}
        </p>
      )}

      {approving && (
        <ActDialog
          act="establish"
          item={approving.successor}
          ends={approving.ends}
          me={me}
          onCancel={() => setApproving(null)}
          onDone={(outcome) => {
            setApproving(null)
            settled(outcome)
          }}
        />
      )}

      {answering && (
        <ActDialog
          act="set-aside"
          item={actItem}
          dispute={{
            link: answering.link,
            reason: answering.reason,
            by: answering.by,
            by_alias: answering.by_alias,
          }}
          me={me}
          onCancel={() => setAnswering(null)}
          onDone={settled}
        />
      )}
    </article>
  )
}

/** CHOOSING WHAT REPLACES IT. The successor is an entry that already exists
 *  (material is immutable, so a change is new material and a link, never an
 *  edit) and it is named by its reference. What that reference IS is read
 *  from the record and shown before anything is done; whether it may replace
 *  this is the route's to decide, and a refusal comes back as its reason. */
function Supersede({
  facts,
  value,
  onValue,
  busy,
  onOpenEntry,
  onGo,
  onCancel,
}: {
  facts: StandingFacts
  value: string
  onValue: (v: string) => void
  busy: boolean
  onOpenEntry: (id: Id) => void
  onGo: (successor: Id) => void
  onCancel: () => void
}) {
  const ref = value.trim()
  const seen = useApi<EntryDetail>(isRefId(ref) ? `/api/entries/${ref}` : null)
  const s = seen.data
  const found = !!s && !s.missing
  const first = found
    ? (s.fields.length ? s.fields : Object.keys(s.body)).find(
        (f) => s.body[f] !== undefined && s.body[f] !== null && s.body[f] !== '',
      )
    : undefined
  return (
    <div className="ei-prepare">
      <input
        value={value}
        spellCheck={false}
        placeholder="the successor's reference, ent-…"
        onChange={(ev) => onValue(ev.target.value)}
      />
      {ref && !isRefId(ref) && <p className="ei-aside">that is not a record reference</p>}
      {isRefId(ref) && seen.loading && <p className="ei-aside">reading the record…</p>}
      {isRefId(ref) && s?.missing && (
        <p className="ei-aside">the record holds no entry under that reference</p>
      )}
      {found && (
        <div className="ei-successor">
          <p className="ei-aside">
            <button className="ei-link" onClick={() => onOpenEntry(s.id)}>
              {s.kind ?? s.family ?? 'entry'}
            </button>
            {' · '}
            {s.stands ? 'stands' : 'does not stand'}
            {s.author_alias ? ` · ${s.author_alias.replace(/^@/, '')}` : ''}
          </p>
          {first && <p className="ei-successor-text">{String(s.body[first])}</p>}
        </div>
      )}
      <p className="ei-aside">Superseding {supersedeEffect(facts)}.</p>
      <div className="ei-prepare-go">
        <button disabled={busy || !found} onClick={() => found && onGo(s.id)}>
          Supersede
        </button>
        <button className="ei-link" onClick={onCancel}>
          not now
        </button>
      </div>
    </div>
  )
}

/** A band of one continuous surface. Separated by space and a hairline, not
 *  by a box: this is one object being read down, not a stack of cards. */
function Band({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <section className="ei-band">
      {title && <h4 className="ei-label">{title}</h4>}
      {children}
    </section>
  )
}

function Pair({
  label,
  value,
  absent,
  mono,
}: {
  label: string
  value: string | null | undefined
  absent?: string
  mono?: boolean
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={(mono ? 'ei-mono ' : '') + (value ? '' : 'ei-faint')}>
        {value ?? absent ?? 'not recorded'}
      </dd>
    </div>
  )
}
