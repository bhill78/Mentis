import { useEffect, useMemo, useRef, useState } from 'react'
import { post, useApi, type Id } from '../../api'
/* THE REVISE ROUTE HAS ONE CALLER SHAPE, and it lives with the other standing
   acts. Writing the request again here would be a second place to get the
   owner's attribution — and now `also_replaces` — wrong. */
import { establishReplacement, revise } from '../standing'
import './ActDialogs.css'

/* ------------------------------------------------------------------------ *
 * THE OWNER'S ACTS, EACH STATING ITS EFFECT BEFORE IT IS CONFIRMED.
 *
 * ONE DIALOG PER ACT, AND EVERY ONE OF THEM SAYS WHAT HAPPENS FIRST. The
 * effect block is not decoration and it is not a warning: it is the sentence
 * the owner is agreeing to, assembled from what the record says about this
 * item — where it is placed, whether it stands, what it would end, whether an
 * ask is waiting on it — and never from a template with the facts left out.
 * The confirm button then repeats the act in its own words ("Establish now",
 * "Record the dispute", "Establish the replacement now") so that nobody
 * confirms an "OK" whose meaning they had to remember from the heading.
 *
 * CANCELLING DOES NOTHING, AND A MEANINGLESS ACT IS REFUSED IN PLAIN WORDS.
 * "Change the text first." is not a validation error dressed as a complaint;
 * it is the interface declining to write a record that would say nothing
 * happened twice.
 *
 * NO KIND IS NAMED HERE. Which fields a revision or a replacement carries is
 * read from the entry's own declared `fields`; where material applies is read
 * from `/api/governance/applies`, which computes it from placements and the
 * composition vocabulary. This file contains no list of Kinds and no branch
 * on one.
 *
 * WHICH ROUTE EACH ACT TAKES, and why it is not always the obvious one:
 *
 *   establish   POST /api/entries/<id>/establish
 *   dispute     POST /api/entries/<id>/dispute — the reason is REQUIRED, and
 *               the route refuses an unevidenced one in its own words.
 *   set-aside   POST /api/entries/<id>/set-aside, naming the dispute answered
 *   revise      POST /api/entries/<id>/revise — writes the new material,
 *               inherits the placements, establishes it and records that it
 *               replaced what it revises, in ONE act. It takes
 *               `also_replaces` too, so a revision may replace several
 *               predecessors at once.
 *   supersede   the owner WRITES the replacement here, and a replacement has
 *               to be written, placed and established before it can end
 *               anything — which is exactly what `revise` does in one act, so
 *               that is the route it takes, carrying `also_replaces` when the
 *               one replacement ends both items in play.
 *               THERE IS NO "NAME AN EXISTING SUCCESSOR" SHAPE HERE. The one
 *               act that ends something with material that already exists is
 *               approving a recorded proposal, and that is `establish` with
 *               `ends` — read from a `proposes-to-supersede` link rather than
 *               from an id somebody typed.
 *   respond     a reply Turn addressed to the asker. It records an answer and
 *               closes the ask; it touches no governed material at all.
 *   write       POST /api/conversations/<id>/instructions with `establish`
 * ------------------------------------------------------------------------ */

export type ActName =
  | 'establish'
  | 'dispute'
  | 'supersede'
  | 'revise'
  | 'set-aside'
  | 'respond'
  | 'write'

/** A governed item, as the act needs to speak about it. The text is the
 *  record's own words and is never editable: material is immutable, and a
 *  replacement is written beside it rather than over it. */
export interface ActItem {
  entry: Id
  kind: string | null
  text: string
  /** true only where the record says it stands NOW. A proposal is false, and
   *  false is not "ended" — the words for that are said by whoever passes
   *  `standing`. */
  stands: boolean
  /** who the material is attributed to, as the record names them. Absent
   *  where the record does not say; never filled in from anything else. */
  author_alias?: string | null
  /** the standing word this interface is allowed to say about it, or null
   *  where the Kind has not declared that standing means anything. Null is
   *  UNKNOWN and is never rendered as "does not stand". */
  standing: string | null
}

/** One recorded challenge, as the set-aside dialog needs to quote it. */
export interface ActDispute {
  /** the `disputes` link. The act that answers it names this. */
  link: Id
  reason: string | null
  by: Id | null
  by_alias?: string | null
}

/** The open ask this act would answer, where one names this item. Its presence
 *  is what puts "The request to you is answered." into the effect block —
 *  never a guess, and never said when no ask names the item. */
export interface ActAsk {
  expectation: Id
  /** the Turn the ask was made in. A reply answers the Turn that asked. */
  turn: Id | null
  conversation: Id | null
  asked_by: Id | null
  asked_by_alias: string | null
  question: string | null
}

/** What happened, handed back so the surface that opened the dialog can say
 *  so and re-read. `answers_a_request` is the server's answer, not this
 *  interface's expectation of it. */
export interface ActOutcome {
  act: ActName
  entry: Id | null
  answered: boolean
  /** the sentence to show afterwards, already assembled */
  said: string
}

export interface ActDialogProps {
  act: ActName
  /** the item acted on. null only for `write`, which creates one. */
  item: ActItem | null
  /** a second item in play, so a replacement can be offered the choice of
   *  ending only the first, only the second, or both. Absent means one item,
   *  and then no choice is offered rather than a choice with one answer. */
  partner?: ActItem | null
  /** WHICH OF THE TWO THE DOOR ALREADY NAMED. A caller whose control said
   *  "Replace both with one…" has had that decision made before the dialog
   *  opened, and opening it on "only this one" would contradict the button
   *  that opened it. Absent, the choice starts on the item acted on. Ignored
   *  without a `partner`, because then there is nothing to choose between. */
  endsChosen?: 'this' | 'partner' | 'both'
  /** WHAT ESTABLISHING THIS ENDS, where the record says it was PROPOSED to
   *  replace them. Present only for `establish`, and only from a recorded
   *  `proposes-to-supersede` link — never inferred from two items being on
   *  screen together.
   *
   *  ITS PRESENCE IS WHAT MAKES ESTABLISHING ONE ACT. Empty or absent, this
   *  is the ordinary establishment and ends nothing; non-empty, the same
   *  dialog says so before the click and the owner's single confirmation
   *  establishes the successor and records its supersession of every one of
   *  them together. There is no second dialog and no second act path. */
  ends?: ActItem[]
  /** the dispute being set aside. Required by `set-aside` and ignored
   *  elsewhere. */
  dispute?: ActDispute | null
  /** the ask this act would answer, where the caller found one. */
  ask?: ActAsk | null
  /** who the act is attributed to. Every act is somebody's. */
  me: Id | null
  /** where `write` places the Instruction it writes. */
  conversation?: { id: Id; name: string | null } | null
  /** DRAWN IN PLACE rather than over a veil: Fluid runs an act inline on
   *  Stage while the conversation beside it stays usable. The same fields,
   *  words, refusals and routes; only the frame differs. Absent, the modal. */
  inline?: boolean
  onDone: (outcome: ActOutcome) => void
  onCancel: () => void
}

/* ---------------------------------------------------------------- reads --- */

/** Which way this material can reach an execution at all, read from the
 *  record. `placed` reaches everybody acting where it is placed; `by_persona`
 *  reaches only an execution started as it; `when_named` reaches nobody
 *  unless somebody names it for that invocation. */
interface Applies {
  rows?: { entry: Id; applies: string; placed_at: Id[] }[]
}

interface ConversationRow {
  id: Id
  name: string
}

interface EntryRead {
  id: Id
  kind: string | null
  /** the field names this entry's Kind declares, in the Kind's own order */
  fields?: string[]
  body?: Record<string, unknown>
  missing?: boolean
}

/** The names of the Conversations an item applies in, where the record has
 *  one. An id nobody named stays an id rather than becoming a guess. */
function placeNames(ids: Id[], rows: ConversationRow[]): string[] {
  return ids.map((id) => rows.find((c) => c.id === id)?.name ?? id)
}

/** A list said the way a person says one. */
function andList(xs: string[]): string {
  if (xs.length === 0) return ''
  if (xs.length === 1) return xs[0]
  return xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]
}

/** The item's own words, short enough to sit inside a sentence. */
function clip(s: string, n = 80): string {
  const t = s.replace(/\s+/g, ' ').trim()
  return t.length <= n ? t : t.slice(0, n - 1) + '…'
}

/* ------------------------------------------------------------- the shell --- */

/** The modal frame. ESCAPE CANCELS AND CANCELLING DOES NOTHING (I-132), which
 *  is why the escape handler is the same function as the Cancel button rather
 *  than a second path that might one day do something else. */
function Shell({
  title,
  onCancel,
  children,
  inline = false,
}: {
  title: string
  onCancel: () => void
  children: React.ReactNode
  inline?: boolean
}) {
  return inline ? (
    <InlineShell title={title} onCancel={onCancel}>{children}</InlineShell>
  ) : (
    <ModalShell title={title} onCancel={onCancel}>{children}</ModalShell>
  )
}

/** THE SAME ACT, IN PLACE. Escape cancels only from inside the act, so a key
 *  pressed in the conversation beside it never throws away what is being
 *  written here; the first field is focused once, as it opens. */
function InlineShell({
  title,
  onCancel,
  children,
}: {
  title: string
  onCancel: () => void
  children: React.ReactNode
}) {
  const box = useRef<HTMLElement | null>(null)
  useEffect(() => {
    box.current?.querySelector<HTMLElement>('textarea, input, button:not(.act-cancel)')?.focus()
  }, [])
  return (
    <section
      className="act-inline"
      role="group"
      aria-label={title}
      ref={box}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation()
          onCancel()
        }
      }}
    >
      <h2 className="act-title">{title}</h2>
      {children}
    </section>
  )
}

function ModalShell({
  title,
  onCancel,
  children,
}: {
  title: string
  onCancel: () => void
  children: React.ReactNode
}) {
  const box = useRef<HTMLDivElement | null>(null)
  /* The latest cancel, read when a key arrives: callers hand down a new
     `onCancel` on each render, and the surface under the dialog re-renders as
     it refreshes. Keyed on it, the focus below re-ran on every refresh and
     pulled the owner back to the first field mid-edit. */
  const cancelling = useRef(onCancel)
  cancelling.current = onCancel
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        cancelling.current()
      }
    }
    window.addEventListener('keydown', key, true)
    /* The first field, so a keyboard reaches the act without hunting. Once,
       as it opens. */
    const first = box.current?.querySelector<HTMLElement>(
      'textarea, input, button:not(.act-cancel)',
    )
    first?.focus()
    return () => window.removeEventListener('keydown', key, true)
  }, [])

  return (
    <div className="act-veil" onMouseDown={onCancel}>
      <div
        className="act-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={box}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 className="act-title">{title}</h2>
        {children}
      </div>
    </div>
  )
}

/** WHAT HAPPENS, said before anything is confirmed. Always headed the same
 *  way, so a reader learns where the sentence they are agreeing to lives. */
function Effect({ children }: { children: React.ReactNode }) {
  return (
    <p className="act-effect">
      <strong>What happens:</strong> {children}
    </p>
  )
}

/** The immutable words of something, shown and not editable. */
function Immutable({ label, text }: { label: string; text: string }) {
  return (
    <div className="act-field">
      <span className="act-label">{label}</span>
      <p className="act-immutable">{text}</p>
    </div>
  )
}

/* ------------------------------------------------------------------ act --- */

export default function ActDialog(props: ActDialogProps) {
  const { act, item, partner, dispute, ask, me, conversation } = props
  const replaces = props.ends ?? []
  const [because, setBecause] = useState('')
  const [falsifier, setFalsifier] = useState('')
  const [said, setSaid] = useState('')
  /* Which of the two items in play the replacement ends. Only offered when
     there are two; `both` is the multi-predecessor supersession the route's
     `also_replaces` was built for. It starts wherever the door that opened
     this dialog already said it was going. */
  const [ends, setEnds] = useState<'this' | 'partner' | 'both'>(props.endsChosen ?? 'this')
  const [fields, setFields] = useState<Record<string, string> | null>(null)
  const [busy, setBusy] = useState(false)
  const [refused, setRefused] = useState<string | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)

  /* WHERE IT WILL APPLY, computed by the record rather than assumed from the
     Kind. Asked for the item being acted on; `write` has no item yet. */
  const applies = useApi<Applies>(
    item && (act === 'establish' || act === 'supersede' || act === 'revise')
      ? '/api/governance/applies?entry=' + [item.entry, ...(act === 'establish' ? replaces.map(x => x.entry) : [])].map(encodeURIComponent).join('&entry=')
      : null,
  )
  const definitions = useApi<{ kinds: { kind: string; expects_falsifier: boolean | null }[] }>(act === 'establish' ? '/api/kinds' : null)
  const needsFalsifier = definitions.data?.kinds.find(k => k.kind === item?.kind)?.expects_falsifier === true
  const places = useApi<{ conversations: ConversationRow[] }>(
    item && (act === 'establish' || act === 'supersede' || act === 'revise')
      ? '/api/conversations'
      : null,
  )
  /* THE FIELDS THE KIND DECLARES, so a replacement or a revision is written in
     them and not in a "text" box this file invented. */
  const entry = useApi<EntryRead>(
    item && (act === 'supersede' || act === 'revise')
      ? '/api/entries/' + encodeURIComponent(item.entry)
      : null,
  )

  const declared = useMemo(() => entry.data?.fields ?? [], [entry.data])
  useEffect(() => {
    /* Pre-filled with what the record holds, because a revision is almost
       always a change to some of the words and retyping the rest is how a
       detail gets lost. The old entry is untouched either way. */
    if (!entry.data || fields !== null) return
    const body = entry.data.body ?? {}
    const seed: Record<string, string> = {}
    for (const f of declared) {
      const v = body[f]
      seed[f] = typeof v === 'string' ? v : v == null ? '' : JSON.stringify(v)
    }
    setFields(seed)
  }, [entry.data, declared, fields])

  const row = applies.data?.rows?.find(r => r.entry === item?.entry)
  const effectivePlaces = [...new Set((applies.data?.rows ?? []).filter(r => r.applies === 'placed').flatMap(r => r.placed_at))]
  const where = placeNames(effectivePlaces, places.data?.conversations ?? [])
  const answers = Boolean(ask)
  const answeredSentence = answers ? ' The request to you is answered.' : ''

  /* WHAT THE REPLACEMENT WOULD END, by the choice made above. One predecessor
     unless the owner said both. */
  const predecessors: ActItem[] =
    !partner || ends === 'this'
      ? item
        ? [item]
        : []
      : ends === 'partner'
        ? [partner]
        : item
          ? [item, partner]
          : [partner]

  /** more than one predecessor is in play, so every sentence about the act has
   *  to be plural. Derived from the choice, never from `partner` alone. */
  const bothSaid = predecessors.length > 1

  /* REPLACE BOTH WITH ONE IS ONE ACT, WHETHER THE SUCCESSOR ALREADY EXISTS OR
     IS BEING WRITTEN HERE. It used to be one act only in the first case: the
     supersede route took `also_replaces` and `revise` did not, so writing the
     new words and ending two proposals with them degraded into two acts, and
     this dialog said so rather than performing two while claiming one. `revise`
     now takes the same parameter in the same shape, so the choice above means
     the same thing on both paths and nothing here has to explain a gap. */

  const changed = useMemo(() => {
    if (!fields || !entry.data) return false
    const body = entry.data.body ?? {}
    return declared.some((f) => {
      const was = body[f]
      const now = fields[f] ?? ''
      return (typeof was === 'string' ? was : was == null ? '' : JSON.stringify(was)) !== now
    })
  }, [fields, entry.data, declared])

  const run = async (go: () => Promise<ActOutcome>) => {
    setBusy(true)
    setRefused(null)
    try {
      props.onDone(await go())
    } catch (e) {
      /* THE ROUTE'S OWN REFUSAL, IN ITS OWN WORDS. It knows things this file
         must not restate — that a replacement is the same Kind as what it
         replaces, that it has to be placed where the old material applied —
         and paraphrasing them here would be a second rulebook. */
      setRefused(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  /* AFTER ANY ACT, WHERE IT LANDED. The one-mechanism claim, said plainly:
     the card in a Turn and the register are two views of one record. */
  const landed = 'Recorded on the same governed item Governance shows.'
  const withAnswer = (r: { answers_a_request?: boolean }) =>
    landed + (r.answers_a_request ? ' The request to you is answered.' : '')

  const bail = (why: string) => {
    setBlocked(why)
    return true
  }

  /* -------------------------------------------------------- establish --- */
  if (act === 'establish' && item) {
    const reach =
      where.length
        ? ` From now on it applies in ${andList(where)}: composition will include it for executions there.`
        : row?.applies === 'by_persona'
          ? ' It becomes selectable. Nobody is started as it automatically.'
          : row?.applies === 'when_named'
            ? ' It reaches an execution only when somebody names it for that invocation.'
            : ''
    /* WHAT IT ENDS, FROM THE RECORD AND NOT FROM THE SCREEN. Said in the same
       sentence as what it does, because they are one act: the owner confirms
       once and the successor is established and every predecessor it was
       proposed to replace is ended together. */
    const endsSaid = replaces.length
      ? ` It ends ${andList(replaces.map((x) => `“${clip(x.text, 44)}”`))}.`
      : ''
    return (
      <Shell title="Establish · takes effect immediately" onCancel={props.onCancel} inline={props.inline}>
        <Immutable label={item.kind ? `The ${item.kind}` : 'The item'} text={item.text} />
        {replaces.map((x) => (
          <Immutable
            key={x.entry}
            label={`Stands now, and this replaces it (immutable)`}
            text={x.text}
          />
        ))}
        <Effect>
          it stands from now on.{reach}
          {endsSaid}
          {answeredSentence}
        </Effect>
        {/* ONE ACT, AND ONE LINK PER PREDECESSOR. "One act" and "one record"
            are not the same claim, and the second would be false: each ended
            item records what replaced it, which is what lets somebody walking
            back from any of them find the successor. */}
        {replaces.length > 1 && (
          <p className="act-note">
            One act, and one replacement link recorded against each of them.
          </p>
        )}
        <label className="act-field">
          <span className="act-label">Reason (recorded on the establishing link)</span>
          <textarea
            value={because}
            onChange={(e) => setBecause(e.target.value)}
            rows={2}
          />
        </label>
        {needsFalsifier && <label className="act-field"><span className="act-label">What would prove this wrong? (required by its Kind)</span><textarea aria-label="Falsifier" value={falsifier} onChange={e => setFalsifier(e.target.value)} rows={2} /></label>}
        {refused && <p className="act-refused">{refused}</p>}
        <Buttons
          confirm={replaces.length ? 'Establish the replacement now' : 'Establish now'}
          busy={busy}
          onCancel={props.onCancel}
          onConfirm={() => {
            /* SAY WHY, OR THE ACT DOES NOT HAPPEN. The route refuses an
               establish or a supersede that carries no reason, and this is that
               same refusal said earlier, in words the owner can act on. It does
               NOT invent one: a reason nobody typed is worse than none, because
               the record would then carry a justification no person ever gave
               for a change to what this Brain durably knows. */
            if (!because.trim() && bail('Say why first.')) return
            if (needsFalsifier && !falsifier.trim() && bail('Say what would prove this wrong.')) return
            void run(async () => {
              if (replaces.length) {
                /* THE ONE-ACT DOOR. The route establishes the successor and
                   writes one `supersedes` link per predecessor inside a single
                   transaction: all of it, or none of it and a refusal naming
                   the predecessor it is about. */
                const [first, ...rest] = replaces
                const r = await establishReplacement(
                  first.entry,
                  item.entry,
                  me,
                  because.trim(),
                  rest.map((x) => x.entry),
                  falsifier.trim(),
                )
                return {
                  act,
                  entry: item.entry,
                  answered: Boolean(r.answers_a_request),
                  said: withAnswer(r),
                }
              }
              const r = await post<{ entry: Id; answers_a_request?: boolean }>(
                '/api/entries/' + item.entry + '/establish',
                { attributed_to: me, because: because.trim(), ...(falsifier.trim() ? { falsifier: falsifier.trim() } : {}) },
              )
              return {
                act,
                entry: item.entry,
                answered: Boolean(r.answers_a_request),
                said: withAnswer(r),
              }
            })
          }}
        />
      </Shell>
    )
  }

  /* ---------------------------------------------------------- dispute --- */
  if (act === 'dispute' && item) {
    /* THE STANDING IT DOES NOT CHANGE, RESTATED. A dispute is an attributed
       note and a link; it confers nothing and revokes nothing, and the only
       way to say that without hand-waving is to say what the standing IS and
       that it is still that afterwards. Where the Kind has not declared that
       standing means anything, the sentence says what it can and claims
       nothing about standing. */
    const unchanged = item.stands
      ? 'it still stands. The dispute does not change where it reaches.'
      : item.standing
        ? `it is still ${item.standing}, and it still reaches nobody.`
        : 'whatever the record says about its standing is exactly what it said before.'
    return (
      <Shell title="Dispute" onCancel={props.onCancel} inline={props.inline}>
        <Immutable label={item.kind ? `The ${item.kind}` : 'The item'} text={item.text} />
        <Effect>
          an attributed note joins the record. Standing does not change: {unchanged}
        </Effect>
        <label className="act-field">
          <span className="act-label">Your challenge</span>
          <textarea
            value={said}
            onChange={(e) => {
              setSaid(e.target.value)
              setBlocked(null)
            }}
            rows={4}
          />
        </label>
        {blocked && <p className="act-blocked">{blocked}</p>}
        {refused && <p className="act-refused">{refused}</p>}
        <Buttons
          confirm="Record the dispute"
          busy={busy}
          onCancel={props.onCancel}
          onConfirm={() => {
            /* A DISPUTE WITHOUT A CHALLENGE IS NOT A DISPUTE. Blocked here in
               plain words, and refused again by the route, which says the
               same thing for callers that are not this interface. */
            if (!said.trim() && bail('Write the challenge first.')) return
            void run(async () => {
              const r = await post<{ answers_a_request?: boolean }>(
                '/api/entries/' + item.entry + '/dispute',
                { attributed_to: me, because: said.trim() },
              )
              return {
                act,
                entry: item.entry,
                answered: Boolean(r.answers_a_request),
                said: withAnswer(r),
              }
            })
          }}
        />
      </Shell>
    )
  }

  /* -------------------------------------------------------- set aside --- */
  if (act === 'set-aside' && item && dispute) {
    return (
      <Shell title="Set dispute aside" onCancel={props.onCancel} inline={props.inline}>
        <Immutable label={`On: ${item.kind ?? 'the item'}`} text={item.text} />
        <Immutable
          label={`The dispute${dispute.by_alias ? ` · ${dispute.by_alias}` : ''}`}
          text={dispute.reason ?? 'The record keeps no words for this challenge.'}
        />
        <Effect>
          the dispute is set aside by a new link. The dispute and its text stay in the
          record. The item&rsquo;s standing does not change.{answeredSentence}
        </Effect>
        <label className="act-field">
          <span className="act-label">Why it is set aside (recorded on the link)</span>
          <textarea
            value={said}
            onChange={(e) => {
              setSaid(e.target.value)
              setBlocked(null)
            }}
            rows={3}
          />
        </label>
        {blocked && <p className="act-blocked">{blocked}</p>}
        {refused && <p className="act-refused">{refused}</p>}
        <Buttons
          confirm="Set the dispute aside"
          busy={busy}
          onCancel={props.onCancel}
          onConfirm={() => {
            /* The route requires it too: setting a dispute aside is itself an
               answer on the same axis, and an answer with no words is not one. */
            if (!said.trim() && bail('Write your answer first.')) return
            void run(async () => {
              const r = await post<{ answers_a_request?: boolean }>(
                '/api/entries/' + item.entry + '/set-aside',
                { attributed_to: me, because: said.trim(), dispute: dispute.link },
              )
              return {
                act,
                entry: item.entry,
                answered: Boolean(r.answers_a_request),
                said: withAnswer(r),
              }
            })
          }}
        />
      </Shell>
    )
  }

  /* ------------------------------------------- supersede, and revise --- */
  if ((act === 'supersede' || act === 'revise') && item) {
    const isRevise = act === 'revise'
    const placedSaid = where.length
      ? `, and placed where the old one was (${andList(where)})`
      : ''
    const title = isRevise
      ? 'Revise and establish · takes effect immediately'
      : 'Supersede'
    const confirm = isRevise ? 'Establish your revision now' : 'Establish the replacement now'

    return (
      <Shell title={title} onCancel={props.onCancel} inline={props.inline}>
        <Immutable
          label={
            isRevise
              ? `Proposed by ${item.author_alias ?? 'somebody the record does not name'} (immutable)`
              : 'Old text (immutable)'
          }
          text={item.text}
        />
        {partner && (
          <Immutable label="The other item in play (immutable)" text={partner.text} />
        )}

        {partner && (
          <fieldset className="act-choice">
            <legend className="act-label">What the replacement ends</legend>
            {(
              [
                ['this', `only “${clip(item.text, 44)}”`],
                ['partner', `only “${clip(partner.text, 44)}”`],
                ['both', 'both, replaced by one'],
              ] as const
            ).map(([value, label]) => (
              <label key={value} className="act-radio">
                <input
                  type="radio"
                  name="act-ends"
                  checked={ends === value}
                  onChange={() => setEnds(value)}
                />
                <span>{label}</span>
              </label>
            ))}
          </fieldset>
        )}

        {/* THE REPLACEMENT IS WRITTEN HERE, IN THE FIELDS THE KIND DECLARES.
            Nothing in this file knows what they are called: they are read
            off the entry being replaced, because a replacement is of the
            same Kind and the route enforces that. */}
        <div className="act-fields">
          {entry.loading && <p className="act-faint">Reading what this Kind declares…</p>}
          {declared.map((f) => (
            <label key={f} className="act-field">
              <span className="act-label">
                {isRevise ? 'Your revision' : 'New text'} · {f}
              </span>
              <textarea
                rows={f === declared[0] ? 4 : 2}
                value={fields?.[f] ?? ''}
                onChange={(e) => {
                  setFields({ ...(fields ?? {}), [f]: e.target.value })
                  setBlocked(null)
                }}
              />
            </label>
          ))}
        </div>

        <label className="act-field">
          <span className="act-label">
            Reason (recorded on the {isRevise ? 'link' : 'supersedes link'})
          </span>
          <textarea value={because} onChange={(e) => setBecause(e.target.value)} rows={2} />
        </label>

        {isRevise ? (
          <Effect>
            A proposal cannot be edited. Your revision is written as a new{' '}
            {item.kind ?? 'item of that Kind'}, established at once, and recorded as
            replacing {bothSaid ? 'both proposals' : 'the proposal'}. Each one is kept,
            and none of them was ever established.
            {where.length ? ` The revision is placed where the proposal was (${andList(where)}).` : ''}
            {answeredSentence}
          </Effect>
        ) : (
          <Effect>
            the new item is written and established in one act{placedSaid}.{' '}
            <strong>It takes effect immediately:</strong> the replacement stands and{' '}
            {bothSaid ? 'both of the items it replaces end' : 'what it replaces ends'} as
            soon as you confirm. Past delivery records that name the old text stay exactly
            as they are.{answeredSentence}
          </Effect>
        )}

        {/* ONE LINK PER PREDECESSOR, SAID BEFORE THE CLICK, because "one act"
            and "one record" are not the same claim and the second one would be
            false: each replaced item records what replaced it, which is what
            lets somebody walking back from either of them find the successor. */}
        {bothSaid && (
          <p className="act-note">
            One act, and one replacement link recorded against each of them. The revision
            is placed everywhere either of them applied.
          </p>
        )}
        {blocked && <p className="act-blocked">{blocked}</p>}
        {refused && <p className="act-refused">{refused}</p>}
        <Buttons
          confirm={confirm}
          busy={busy}
          onCancel={props.onCancel}
          onConfirm={() => {
            if (!changed && bail('Change the text first.')) return
            /* SAY WHY, OR THE ACT DOES NOT HAPPEN. The route refuses an
               establish or a supersede that carries no reason, and this is that
               same refusal said earlier, in words the owner can act on. It does
               NOT invent one: a reason nobody typed is worse than none, because
               the record would then carry a justification no person ever gave
               for a change to what this Brain durably knows. */
            if (!because.trim() && bail('Say why first.')) return
            void run(async () => {
              /* WRITTEN HERE. `revise` is the one door that writes the
                 material, carries the placements over, establishes it and
                 records the replacement together — which is precisely the act
                 the dialog just described. The chosen predecessors go through
                 it in one call: the first in the path, the rest as
                 `also_replaces`, so "replace both with one" is one act here
                 exactly as it is for a successor that already stands. */
              const [first, ...rest] = predecessors
              const r = await revise(
                first.entry,
                fields ?? {},
                me,
                because.trim(),
                rest.map((p) => p.entry),
              )
              return {
                act,
                entry: r.revision,
                answered: Boolean(r.answers_a_request),
                said: withAnswer(r),
              }
            })
          }}
        />
      </Shell>
    )
  }

  /* ---------------------------------------------------------- respond --- */
  if (act === 'respond' && ask) {
    return (
      <Shell
        title={`Answer ${ask.asked_by_alias ?? 'the asker'} in your own words`}
        onCancel={props.onCancel}
        inline={props.inline}
      >
        {ask.question && <blockquote className="act-quote">{ask.question}</blockquote>}
        <label className="act-field">
          <span className="act-label">Your answer</span>
          <textarea
            value={said}
            onChange={(e) => {
              setSaid(e.target.value)
              setBlocked(null)
            }}
            rows={4}
          />
        </label>
        <Effect>
          your words are recorded as your reply to {ask.asked_by_alias ?? 'the asker'}, and
          the ask is closed. No governed material changes. To establish, supersede or
          dispute something, do that as its own act.
        </Effect>
        {blocked && <p className="act-blocked">{blocked}</p>}
        {refused && <p className="act-refused">{refused}</p>}
        <Buttons
          confirm="Record answer & close"
          busy={busy}
          onCancel={props.onCancel}
          onConfirm={() => {
            if (!said.trim() && bail('Write your answer first.')) return
            void run(async () => {
              const closed = await answerAsk(ask, said.trim(), me)
              return {
                act,
                entry: null,
                answered: closed === true,
                said: answeredSaid(said.trim(), ask.asked_by_alias ?? 'the asker', closed),
              }
            })
          }}
        />
      </Shell>
    )
  }

  /* ------------------------------------------------------------ write --- */
  if (act === 'write' && conversation) {
    return (
      <Shell
        title={`New Instruction in ${conversation.name ?? 'this Conversation'} · takes effect immediately`}
        onCancel={props.onCancel}
        inline={props.inline}
      >
        <label className="act-field">
          <span className="act-label">Text</span>
          <textarea
            value={said}
            onChange={(e) => {
              setSaid(e.target.value)
              setBlocked(null)
            }}
            rows={4}
          />
        </label>
        <label className="act-field">
          <span className="act-label">
            Subject it speaks to (optional; used to surface conflicts)
          </span>
          <textarea value={because} onChange={(e) => setBecause(e.target.value)} rows={1} />
        </label>
        <Effect>
          because you are the owner, it is written and established in one act and placed
          here. <strong>It takes effect immediately:</strong> from now on composition here
          includes it. There is no draft or propose step for the owner in this flow. Past
          delivery records do not change.
        </Effect>
        {blocked && <p className="act-blocked">{blocked}</p>}
        {refused && <p className="act-refused">{refused}</p>}
        <Buttons
          confirm="Write and establish now"
          busy={busy}
          onCancel={props.onCancel}
          onConfirm={() => {
            if (!said.trim() && bail('Write the Instruction first.')) return
            void run(async () => {
              const r = await post<{ entry: Id }>(
                '/api/conversations/' + conversation.id + '/instructions',
                {
                  text: said.trim(),
                  about: because.trim() || undefined,
                  attributed_to: me,
                  establish: true,
                },
              )
              return { act, entry: r.entry, answered: false, said: landed }
            })
          }}
        />
      </Shell>
    )
  }

  /* Nothing to act on. Said rather than rendered as an empty dialog. */
  return null
}

/* NO `disabled` HERE ANY MORE. It existed for one caller, which greyed the
   confirm out while explaining that "replace both with one" would take two
   acts. It takes one act now, so nothing blocks a choice this dialog offers,
   and a switch nothing turns on is a switch somebody will wire to the wrong
   thing. A meaningless act is still refused — in words, by `bail`. */
function Buttons({
  confirm,
  busy,
  onConfirm,
  onCancel,
}: {
  confirm: string
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="act-buttons">
      <button className="act-cancel" onClick={onCancel} disabled={busy}>
        Cancel
      </button>
      <button className="act-confirm" onClick={onConfirm} disabled={busy}>
        {busy ? 'Recording…' : confirm}
      </button>
    </div>
  )
}

/* ------------------------------------------------------------ answering --- */

/** Record an answer to an ask, and nothing else.
 *
 *  IT IS A REPLY, NOT A STATE CHANGE. The ask closes because somebody the ask
 *  was of replied to the Turn that asked — the same mechanism every other
 *  answer uses. Nothing here writes material, establishes anything or touches
 *  standing, which is exactly what the dialog promised before the click.
 *
 *  `record-only` is said explicitly. An answer must never cost a runtime.
 *
 *  WHETHER IT CLOSED IS THE RECORD'S TO SAY. A reply closes an ask asked as
 *  its own post; it does not close a question of a decision form (only a
 *  reply naming it does) or an input (only Done does). So the asking Turn is
 *  reread after the reply and its own `response_present` is returned: true
 *  closed, false still open, null the record did not say. */
export async function answerAsk(ask: ActAsk, text: string, me: Id | null): Promise<boolean | null> {
  if (!ask.conversation) throw new Error('the record does not say where this was asked')
  await post('/api/conversations/' + ask.conversation + '/turns', {
    author: me,
    action: 'record-only',
    text,
    parts: [{ type: 'text', text }],
    replies_to: ask.turn,
    addressed_to: ask.asked_by ? [ask.asked_by] : [],
    because: `answering expectation ${ask.expectation}`,
  })
  if (!ask.turn) return null
  try {
    const res = await fetch('/api/turns/' + encodeURIComponent(ask.turn), { headers: { 'X-Mentis-Client': '1' } })
    if (!res.ok) return null
    const t = (await res.json()) as { expectations?: { id: Id; response_present?: boolean }[] }
    const e = t.expectations?.find((x) => x.id === ask.expectation)
    return e ? e.response_present === true : null
  } catch {
    return null
  }
}

/** What answering by reply landed as, said from the record's own reread. */
export function answeredSaid(reply: string, who: string, closed: boolean | null): string {
  const said = `Answered “${clip(reply, 60)}” to ${who}: recorded`
  return closed
    ? `${said}, and the ask is closed. No governed material changed.`
    : closed === false
      ? `${said}, but the record still shows the ask open. No governed material changed.`
      : `${said}; the record has not yet said whether this closed the ask. No governed material changed.`
}
