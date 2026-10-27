import { useRef, useState } from 'react'
import { qs, termOf, useApi, when, type Act, type Id, type Product, type Provenance } from '../api'
import { Callout } from './Happening'
import { standingWords, type StandingFacts } from './standing'

/* ------------------------------------------------------------------------ *
 * A DURABLE OBJECT THAT SOME WORK MINTED.
 *
 * FOUR THINGS, AND THEY ARE NOT THE SAME THING:
 *
 *   a Happening marker   something happened at this point
 *   a KIND MARKER        a durable object was MINTED at this point
 *   a KIND CARD          that object, revealed in the Conversation beneath
 *                        the Turn whose downstream work minted it
 *   Graph / History      the causal structure, and the detailed record
 *
 * This file is the middle two. It is not a summary, a feed, a digest or a
 * sentence generator — an earlier pass made it one of those, and that was
 * wrong twice over: it described the work instead of showing what the work
 * left behind, and it put the description on the Turn instead of the mark on
 * the spine.
 *
 * A KIND CARD IS NOT A TURN. No number, no author, no reply affordance, no
 * conversational identity. It is a durable object shown at the place in the
 * conversation that explains where it came from.
 *
 * NOTHING HERE ENUMERATES A KIND. A Kind is self-describing and anybody may
 * define one, so the marker's identity is DERIVED from the Kind's own
 * declared name and the card's body is rendered from the Kind's own declared
 * fields and meaning. A Kind defined tomorrow gets a mark and a card without
 * this file being edited.
 * ------------------------------------------------------------------------ */

/** The marker's letter, derived from the Kind's OWN NAME.
 *
 *  This is the whole trick, and it is why there is no registry: `finding`
 *  marks itself F, `problem` marks itself P, `constraint` marks itself C, and
 *  a Kind invented next year marks itself with its own initial. Nothing was
 *  taught any of them, and a reader never memorises an arbitrary symbol —
 *  the letter is the first letter of the word the preview shows. */
export const initialOf = (p: Product): string =>
  (termOf(p).replace(/[^a-z]/gi, '')[0] ?? '?').toUpperCase()

/** WHAT A DURABLE OBJECT IS CALLED, IN WORDS — NEVER ITS ADDRESS.
 *
 *  The one-line summary is the first declared field holding text, and for a
 *  held artifact that field is a content hash: true, and nothing a reader can
 *  use. Printed in a narrow column it was all that showed of each row. The
 *  name the bytes arrived under is what they are called, read from the
 *  Admission's own envelope exactly as `HeldThing` reads it; any other
 *  summary that is itself an address says nothing and is left out. The
 *  address stays where addresses belong, one step in under inspect. */
export const nameOf = (p: Product): string | null => {
  if (isHeld(p.body)) {
    const env = (p.body.envelope ?? {}) as Record<string, unknown>
    if (typeof env.claimed_name === 'string' && env.claimed_name.trim()) return env.claimed_name
  }
  const s = p.summary?.trim()
  return s && !isAddress(s) ? s : null
}

/** A content hash or a record id: an address, not a name. Shape only. */
const isAddress = (s: string): boolean =>
  /^(sha256:)?[0-9a-f]{16,}$/i.test(s) || /^(ent|opr|adm)-[0-9a-f]{8,}$/.test(s)

/* ------------------------------------------------------------------------ *
 * THE MARKER, on the Happening spine.
 *
 * It must not read as an ordinary Happening tick. A tick is a thin line
 * saying "something happened"; this is a small solid badge carrying a letter,
 * saying "a durable object was minted". Different shape, different weight,
 * different meaning — the two are never merged.
 * ------------------------------------------------------------------------ */
export function KindMark({
  product,
  on,
  top,
  pinned,
  onPin,
  armed,
  onDown,
  goes,
  onReveal,
}: {
  product: Product
  on: boolean
  top: number
  pinned?: boolean
  onPin?: () => void
  /** touched once: previewing, and the next touch goes (see `useTapFirst`) */
  armed?: boolean
  onDown?: (e: React.PointerEvent) => void
  goes?: () => boolean
  onReveal: () => void
}) {
  const at = useRef<HTMLButtonElement | null>(null)
  const [peek, setPeek] = useState(false)
  const term = termOf(product)
  const says = [
    `${term} produced here`,
    nameOf(product) ?? '',
    on ? 'shown below its Turn — select to go to it' : 'select to show it below its Turn',
  ]
    .filter(Boolean)
    .join(' · ')
  const showing = peek || pinned || armed
  return (
    <>
      <button
        ref={at}
        role="listitem"
        className={'kind-mark' + (on ? ' on' : '') + (pinned ? ' pinned' : '')}
        style={{ top: `${top}%` }}
        aria-pressed={on}
        aria-label={says}
        onMouseEnter={() => setPeek(true)}
        onMouseLeave={() => setPeek(false)}
        onFocus={() => setPeek(true)}
        onBlur={() => setPeek(false)}
        onPointerDown={onDown}
        onClick={() => {
          if (!goes || goes()) onReveal()
        }}
      >
        <span className="kind-badge" aria-hidden="true">
          {initialOf(product)}
        </span>
      </button>
      {showing && (
        <Callout
          at={at.current}
          pinned={pinned}
          onPin={onPin}
          go={armed ? { label: 'Go to it', run: onReveal } : undefined}
        >
          <KindPreview product={product} />
        </Callout>
      )}
    </>
  )
}

/** The compact preview a Kind marker shows on hover and on focus: the Kind,
 *  and enough of the object itself to know which one this is. */
export function KindPreview({ product }: { product: Product }) {
  const name = nameOf(product)
  return (
    <>
      <span className="kind-peek-head">
        <span className="kind-badge small" aria-hidden="true">
          {initialOf(product)}
        </span>
        <span className="kind-peek-term">{termOf(product)}</span>
      </span>
      {name && <span className="kind-peek-said">{name}</span>}
      {product.meaning && <span className="kind-peek-meaning">{product.meaning}</span>}
    </>
  )
}

/* ------------------------------------------------------------------------ *
 * HOW THIS CAME TO EXIST — the same record, read backwards.
 *
 * `produced-by` is the inverse of the Relation the forward direction reads,
 * and the chain is `caused_by` walked back from the producing act. Nothing is
 * stored twice; this is reconstructed on every read, which is why a fresh
 * process can answer it at all.
 * ------------------------------------------------------------------------ */
function Trace({ entry }: { entry: Id }) {
  const p = useApi<Provenance>(`/api/provenance${qs({ entry })}`)
  if (p.loading) return <span className="kc-faint">reading the record…</span>
  if (p.error) return <span className="kc-faint">could not read: {p.error}</span>
  const got = p.data
  if (!got) return null
  if (got.produced_by.length === 0)
    return <span className="kc-faint">{got.why_not ?? 'nothing claims to have produced this'}</span>
  return (
    <div className="kc-trace">
      {got.produced_by.map((b) =>
        b.missing ? (
          <span className="kc-faint" key={b.act}>
            the producing act is named but not readable here
          </span>
        ) : (
          <div className="kc-trace-one" key={b.act}>
            <span className="kc-trace-line">
              <b>{b.act_type}</b>
              <span>{(b.actor_alias ?? '').replace(/^@/, '')}</span>
              {b.runtime && <span className="kc-faint">{b.runtime}</span>}
            </span>
            {b.because && <span className="kc-faint">because {b.because}</span>}
            <span className="kc-trace-line">
              {b.turn_number != null && <span>from Turn #{b.turn_number}</span>}
              {b.at && <span className="kc-faint">{when(b.at)}</span>}
            </span>
            {(b.caused_by?.length ?? 0) > 0 && (
              <span className="kc-faint">
                {b.caused_by!.length} {b.caused_by!.length === 1 ? 'act' : 'acts'} of ancestry back
                to the steer
              </span>
            )}
          </div>
        ),
      )}
    </div>
  )
}

/** What `/api/artifacts/<ref>?describe=1` says about bytes Mentis holds. */
export interface HeldArtifact {
  state: string
  name?: string | null
  claimed_media_type?: string | null
  size?: number | null
  treatment?: { view?: string | null; content_type?: string | null } | null
}

/** Whether a durable object is an Admission whose bytes Mentis holds. */
export const isHeld = (body: Record<string, unknown>) => body.content === 'held'

/** The server's account of a held artifact, or nothing when `entry` is null. */
export const useHeld = (entry: Id | null) =>
  useApi<HeldArtifact>(entry ? `/api/artifacts/${entry}?describe=1` : null, {
    live: false, // content-addressed: nothing another act does changes these bytes
  })

export const sizeWords = (n: number) =>
  n < 1024 ? `${n} bytes` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`

/** A held artifact, as the thing it is. Falls back to what the Admission's
 *  own envelope recorded while the server's answer is on its way, or if it
 *  cannot be had. Shared by the card and the inspector, so the two never
 *  describe one artifact differently. */
export function HeldThing({
  entry,
  body,
  about,
  loading,
  onOpen,
  large,
}: {
  entry: Id
  body: Record<string, unknown>
  about: HeldArtifact | null
  loading: boolean
  onOpen?: () => void
  large?: boolean
}) {
  const env = (body.envelope ?? {}) as Record<string, unknown>
  const name = about?.name ?? (typeof env.claimed_name === 'string' ? env.claimed_name : null)
  const type =
    about?.claimed_media_type ?? (typeof body.payload_type === 'string' ? body.payload_type : null)
  const size = about?.size ?? (typeof env.size === 'number' ? env.size : null)
  const gone = about && about.state !== 'held'
  const image = about?.state === 'held' && about.treatment?.view === 'image'
  const img = <img src={`/api/artifacts/${entry}`} alt={name ?? 'held image'} />
  return (
    <div className={'kc-held-thing' + (large ? ' large' : '')}>
      <span className="kc-held-name">{name ?? 'an unnamed artifact'}</span>
      <span className="kc-faint">
        {[type, size != null ? sizeWords(size) : null].filter(Boolean).join(' · ')}
        {gone ? ` · Mentis no longer holds these bytes (${about.state})` : ''}
        {loading && !about ? ' · reading…' : ''}
      </span>
      {image &&
        (onOpen ? (
          <button className="kc-preview" onClick={onOpen} title="open it">
            {img}
          </button>
        ) : (
          <span className="kc-preview">{img}</span>
        ))}
    </div>
  )
}

/* ------------------------------------------------------------------------ *
 * THE CARD — A FIRST-CLASS DURABLE OBJECT, STANDING IN THE CONVERSATION.
 *
 * IT IS NOT TURN METADATA, AND THE LAYOUT MUST NOT SAY IT IS. An earlier pass
 * rendered this inside the originating Turn's own container, which made a
 * Finding read as extra information underneath Brian's message. It is not:
 * once minted it is something Mentis HOLDS. It may later carry Decisions,
 * yield Lessons, be superseded, trigger work or change behaviour, and none of
 * that is true of an attachment to somebody's post.
 *
 * So it stands in the chronological flow at the point it was minted, as a
 * sibling of the Turns rather than a child of one. Its relationship to the
 * work that made it is carried by PROVENANCE — named, and navigable — not by
 * containment.
 *
 * VISUALLY IT IS NOT A TURN: no avatar, no Turn number of its own, no author
 * line, no reply control and no conversational identity. The badge sits in
 * the column a Turn's avatar would occupy so the flow keeps its rhythm, and
 * everything else about it differs.
 *
 * TWO GRAMMARS, CHOSEN BY SUBSTRATE FAMILY AND NEVER BY KIND NAME. An
 * `entry` is an epistemic object: its declared fields and its Kind's declared
 * meaning are the point. An `admission` is a work product: the thing itself
 * is the point, and it opens. Family is substrate — closed, small, and read
 * from the record — where a Kind is open-ended and may never be enumerated.
 * ------------------------------------------------------------------------ */
export default function KindCard({
  product,
  by,
  who,
  turnNumber,
  openable,
  aimed,
  onOpen,
  onGoToTurn,
  onInspect,
  onDismiss,
}: {
  product: Product
  /** the act that minted it, for the quiet provenance line */
  by?: Act
  /** that act's actor, by the name the conversation uses */
  who?: string | null
  turnNumber?: number
  /** true only where the media surface actually holds this artifact */
  openable?: boolean
  /** just navigated to. A brief, quiet acknowledgement that this is the one
   *  — not a selected state, and not another box. */
  aimed?: boolean
  onOpen?: () => void
  /** go to the Turn the work started at — provenance, not ownership */
  onGoToTurn?: () => void
  /** THE CARD IS A DOOR. Everything the record knows about this object lives
   *  in the contextual Details region, one depth in; the card stays short. */
  onInspect?: () => void
  onDismiss: () => void
}) {
  const [tracing, setTracing] = useState(false)
  const term = termOf(product)
  const isWorkProduct = product.family === 'admission'
  /* THE CARD IS RENDERED FROM THE ITEM'S CURRENT STATE, standing included.
     A proposal an agent made reads, in the place it arose, as proposed —
     not as something held. Read from the record each time the card is shown,
     never carried from the moment the work produced it. */
  const now = useApi<StandingFacts & { incoming?: Record<string, Id[]> }>(
    isWorkProduct ? null : `/api/entries/${product.entry}`,
  )
  const standing = standingWords(now.data)
  const disputed = (now.data?.incoming?.disputes ?? []).length > 0 && standing !== null
  /* The Kind's OWN declared fields, in its own declared order. A card that
     reached for `body.text` would render a Kind whose field is called
     something else as blank — the difference between reading a declaration
     and guessing at a convention. */
  const fields = product.fields.filter((f) => {
    const v = product.body[f]
    return v !== undefined && v !== null && v !== ''
  })
  /* A HELD ARTIFACT IS SHOWN AS THE THING, NOT ITS ADDRESS. Its declared
     fields are a content hash and a submission id, which say where the bytes
     are and nothing about what they are; a card of only those told a reader
     nothing. What the record knows about the thing -- its name, what it
     claims to be, its size, and for an image the image -- is read from the
     server, which verifies what it holds. The address stays one step in,
     under inspect. */
  const held = isWorkProduct && isHeld(product.body)
  const about = useHeld(held ? product.entry : null)
  return (
    <article
      className={
        'kind-card' + (isWorkProduct ? ' work-product' : '') + (aimed ? ' aimed' : '')
      }
      aria-label={`${term}, a durable object Mentis holds`}
      data-entry={product.entry}
    >
      {/* The badge sits where a Turn's avatar would, so the flow keeps its
          rhythm — and it is a badge, not a face, so nothing reads as somebody
          having said this. */}
      <div className="kc-gutter" aria-hidden="true">
        <span className="kind-badge big">{initialOf(product)}</span>
      </div>

      <div className="kc-body">
        <header className="kc-head">
          <span className="kc-term">{term}</span>
          <span className="kc-held">Mentis holds this</span>
          {standing && (
            <span className="kc-standing">
              {standing}
              {disputed ? ' · disputed' : ''}
            </span>
          )}
          <span className="kc-spacer" />
          <button className="kc-x" aria-label={`hide this ${term}`} onClick={onDismiss}>
            ×
          </button>
        </header>

        {held ? (
          <HeldThing
            entry={product.entry}
            body={product.body}
            about={about.data}
            loading={about.loading}
            onOpen={onOpen}
          />
        ) : (
          <dl className="kc-fields">
            {fields.map((f) => (
              <div key={f}>
                <dt>{f}</dt>
                <dd>{String(product.body[f])}</dd>
              </div>
            ))}
          </dl>
        )}

        {/* An epistemic object says what its Kind means. A work product does
            not pretend to: it is a thing, and the thing is what opens. */}
        {!isWorkProduct && (
          <p className={'kc-meaning' + (product.meaning ? '' : ' none')}>
            {product.meaning ?? 'this Kind declares no meaning, so none is shown'}
          </p>
        )}

        {/* PROVENANCE, NOT OWNERSHIP. It says where this came from and lets a
            reader go there; it does not make this part of that Turn. */}
        <footer className="kc-from">
          <span className="kc-from-what">
            {by ? by.act : 'produced by work'}
            {who ? ` · ${who}` : ''}
          </span>
          {turnNumber != null &&
            (onGoToTurn ? (
              <button
                className="kc-from-turn"
                onClick={onGoToTurn}
                title={`go to Turn #${turnNumber}, where this work started`}
              >
                from work on #{turnNumber}
              </button>
            ) : (
              <span className="kc-from-turn">from work on #{turnNumber}</span>
            ))}
          <span className="kc-id">{product.entry}</span>
        </footer>

        <div className="kc-more">
          {onInspect && (
            <button className="kc-link strong" onClick={onInspect}>
              inspect
            </button>
          )}
          {openable && onOpen && (
            <button className="kc-link" onClick={onOpen}>
              open it
            </button>
          )}
          <button className="kc-link" aria-expanded={tracing} onClick={() => setTracing(!tracing)}>
            {tracing ? 'hide how this came to exist' : 'how did this come to exist?'}
          </button>
        </div>
        {tracing && <Trace entry={product.entry} />}
      </div>
    </article>
  )
}
