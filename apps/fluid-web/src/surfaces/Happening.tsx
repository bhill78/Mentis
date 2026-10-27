import { useMemo, useRef, useState } from 'react'
import { ago, said, when, type Act, type Id, type Product } from '../api'
import { anchored } from '../bits'
import type { Resolution } from '../layouts/composition'
import { productsAt, shapeOf, type Node } from './CausalShape'
import { KindMark } from './DurableKind'

/* ------------------------------------------------------------------------ *
 * HAPPENING — THE GLANCE RESOLUTION OF THIS SCOPE'S OPERATIONAL HISTORY.
 *
 * Happening, Graph and History are not three surfaces. They are ONE scoped
 * operational history at three resolutions:
 *
 *     Happening = glance        this file
 *     Graph     = structure     CausalGraph, grown leftward from here
 *     History   = explanation   HistoryPane, the same record in words
 *
 * At its smallest it is an extremely quiet vertical spine immediately left of
 * the conversation, and it is also the BOUNDARY: the stable edge between the
 * navigation/history side of the canvas and the work itself. Expanding a
 * resolution grows leftward into whatever room is there; this spine does not
 * move, so the conversation does not jump when the graph opens.
 *
 * WHAT IT IS NOT. It is not the conversation rail's activity mark. The rail
 * answers "which conversations are moving"; this answers "what happened
 * inside THIS conversation or topic". Two different questions, two different
 * marks, and this one never carries the other's.
 *
 * Scope follows the current Conversation/Topic automatically — there is no
 * scope control here and there must never be one.
 *
 * IT IS NOT AN EVENT LOG, AND THE DIFFERENCE IS THE WHOLE POINT. A spine with
 * one mark per act is a barcode: Turn #7's twelve acts would be twelve marks,
 * eleven of them one agent's ordinary working, and the shape of the work would
 * be buried in its texture. So the marks here are the STRUCTURAL acts — the
 * asking, the taking up, the branching, the coming back, the producing — and
 * the routine interior is GATHERED ONTO the act it happened under, where it
 * thickens that mark and stays reachable rather than disappearing.
 *
 * That compression is `CausalShape`'s, which the Graph already used. There is
 * no importance score and no ranked list of act names deciding what matters:
 * an act is structural because of the kind of move the record says it was, or
 * because it produced something durable. Nothing is ranked and nothing is
 * dropped — `shape.all` still holds every act, and History still prints them.
 *
 * TWO KINDS OF MARK SHARE THE ONE TIME AXIS, AND THEY MEAN DIFFERENT THINGS:
 *
 *   a tick    something HAPPENED at this point
 *   a badge   a durable object was MINTED at this point
 *
 * The second is not a decoration on the first and is never merged into it.
 * A durable object is not an event — it outlives the work, it can be opened,
 * and it is the thing a reader came looking for. It exists here ONLY through
 * the `produced` relationship; an act that merely names a Kind in `about[]`
 * referenced it and mints nothing, so no badge appears.
 * ------------------------------------------------------------------------ */

export interface HappeningProps {
  /** this scope's acts, oldest first — already scoped by the caller */
  acts: Act[]
  resolution: Resolution
  onResolution: (r: Resolution) => void
  /** the timeline/graph switch, drawn at the head of the spine */
  toggle?: React.ReactNode
  selected: Id | null
  onSelect: (a: Act) => void
  aliasOf: (id: Id) => string | null
  /** the conversation or topic this history is about, for the accessible name */
  scopeName: string
  /** Turns that currently owe the person reading this something, with the
   *  reason in the record's own words. THE SAME FACT the Turn's own mark
   *  carries — one meaning, two places, never a second interpretation. */
  owed?: Map<Id, string>
  onGoToOwed?: (turn: Id) => void
  /** which fraction of the Conversation is on screen, as {top, height} in
   *  0..1 — drawn on the spine itself rather than beside it */
  viewport?: { top: number; height: number } | null
  /** durable objects currently revealed as cards in the Conversation */
  revealed?: Set<Id>
  /** show (or hide) this durable object beneath the Turn its work started at */
  onRevealKind?: (product: Product, by: Act) => void
}

/* Older above, newer below — the same direction the conversation reads, and
   the same direction the graph grows. `shapeOf` sorts by time already, so the
   spine inherits that order rather than imposing a second one. */

/* ------------------------------------------------------------------------ *
 * WHAT A READER MAY LOOK AT ONE GROUP OF.
 *
 * These are not categories invented for a filter. Each is a distinction the
 * spine ALREADY DRAWS differently because the record already makes it:
 * something happened, something durable was minted, something is owed. There
 * is no importance score here and no ranking — the groups are the marks that
 * exist.
 *
 * The default is everything, always. Filtering is presentation and nothing
 * else: no act is removed from the record, and the control says so while it
 * is on so that a narrowed spine is never mistaken for a quiet history.
 * ------------------------------------------------------------------------ */
export type Lens = 'all' | 'kinds' | 'owed' | 'events'

const LENSES: { id: Lens; label: string; says: string }[] = [
  { id: 'all', label: 'Everything', says: 'every mark this scope has' },
  { id: 'kinds', label: 'Durable', says: 'only what work left behind' },
  { id: 'owed', label: 'Owed', says: 'only what is waiting on you' },
  { id: 'events', label: 'Events', says: 'only what happened, without products' },
]

/** How many marks a spine can carry before they stop being distinguishable.
 *  Beyond this the oldest are folded into one quiet "earlier" mark rather
 *  than drawn at a size nobody can hit. */
const MOST = 60

export default function Happening({
  acts,
  resolution,
  onResolution,
  toggle,
  selected,
  onSelect,
  aliasOf,
  scopeName,
  owed,
  onGoToOwed,
  viewport,
  revealed,
  onRevealKind,
}: HappeningProps) {
  const [lens, setLens] = useState<Lens>('all')
  const [lensOpen, setLensOpen] = useState(false)
  /* One preview may be kept while the reader looks around it. Everything else
     is transient: a spine hung with callouts is the clutter this was meant to
     cure. */
  const [pinned, setPinned] = useState<string | null>(null)
  const lensAt = useRef<HTMLButtonElement | null>(null)
  const tap = useTapFirst()
  /* THE SHAPE, NOT THE STREAM. Structural acts get a mark; the routine
     interior is gathered onto the act it happened under. Nothing is dropped —
     `shape.all` still holds every act, and Graph and History read the same
     shape, so all three resolutions agree about what happened. */
  const shape = useMemo(() => shapeOf(acts), [acts])
  const all = useMemo(() => (shape ? shape.nodes : []), [shape])
  const folded = Math.max(0, all.length - MOST)
  const shown = folded > 0 ? all.slice(folded) : all

  /* ONE TIME AXIS, TWO KINDS OF MARK. A durable object sits at its own
     moment, not on the tick of the act that made it: it is a different sort
     of thing and the spine says so by drawing it differently, in its own
     place. Where an act and its product land at the same instant the pins are
     nudged apart below, exactly as two acts would be. */
  const pins = useMemo<Pin[]>(() => {
    const out: Pin[] = shown.map((node) => ({ what: 'act', at: node.act.at, node }))
    for (const node of shown)
      for (const product of productsAt(node))
        out.push({ what: 'kind', at: product.at ?? node.act.at, product, by: node.act })
    return out.sort((a, b) => a.at - b.at)
  }, [shown])

  /* The lens narrows what is DRAWN and nothing else. `shape.all` is untouched
     and Graph and History still hold every act. */
  const visible = useMemo(
    () =>
      pins.filter((p) => {
        if (lens === 'all') return true
        if (lens === 'kinds') return p.what === 'kind'
        if (lens === 'events') return p.what === 'act'
        return p.what === 'act' && !!(p.node.act.turn && owed?.has(p.node.act.turn))
      }),
    [pins, lens, owed],
  )
  const hidden = pins.length - visible.length

  const expand = () =>
    onResolution(resolution === 'glance' ? 'structure' : 'glance')

  return (
    <div className="happening" data-resolution={resolution}>
      {/* The boundary itself. It is a control, but it is drawn as an edge:
          the whole point is that it reads as the seam between the history
          side and the work, not as another button. */}
      <button
        className="happening-edge"
        aria-expanded={resolution !== 'glance'}
        aria-label={
          resolution === 'glance'
            ? `what happened in ${scopeName} — open the causal graph`
            : `close the causal graph for ${scopeName}`
        }
        title={
          resolution === 'glance'
            ? `what happened in ${scopeName} — open the graph`
            : 'close the graph'
        }
        onClick={expand}
      />

      {/* THE HEAD OF THE SPINE: timeline or graph, one press apart. It sits
          above the marks rather than over them, so it never covers the
          oldest act, and in the flow rather than on the edge, so the edge
          stays live everywhere below it. */}
      {toggle}

      {/* THE SPINE IS A TIMELINE, SO POSITION MEANS TIME. Each mark sits at
          its own moment between the first and the last, older above and newer
          below — a quiet reading of when the work actually clustered, rather
          than a barcode of evenly spaced ticks that says nothing. Marks are
          nudged apart only enough to stay separately hittable. */}
      {viewport && viewport.height < 0.995 && (
        <span
          className="happening-view"
          aria-hidden="true"
          style={{
            top: `${Math.max(0, viewport.top) * 100}%`,
            height: `${Math.min(1, viewport.height) * 100}%`,
          }}
        />
      )}

      <div className="happening-marks" role="list" aria-label={`what happened in ${scopeName}`}>
        {folded > 0 && (
          <span className="happen-earlier" title={`${folded} earlier`} aria-hidden="true" />
        )}
        {placed(visible).map(({ pin, top: y }) =>
          pin.what === 'act' ? (
            <Mark
              key={pin.node.act.id}
              node={pin.node}
              top={y}
              on={pin.node.act.id === selected || pin.node.inside.some((x) => x.id === selected)}
              aliasOf={aliasOf}
              owes={pin.node.act.turn ? (owed?.get(pin.node.act.turn) ?? null) : null}
              onOwed={
                pin.node.act.turn && onGoToOwed
                  ? () => onGoToOwed(pin.node.act.turn!)
                  : undefined
              }
              pinned={pinned === pin.node.act.id}
              onPin={() =>
                setPinned((was) => (was === pin.node.act.id ? null : pin.node.act.id))
              }
              armed={tap.armed === pin.node.act.id}
              onDown={tap.down}
              goes={() => tap.goes(pin.node.act.id)}
              onSelect={() => onSelect(pin.node.act)}
            />
          ) : (
            <KindMark
              key={pin.product.entry}
              product={pin.product}
              top={y}
              on={!!revealed?.has(pin.product.entry)}
              pinned={pinned === pin.product.entry}
              onPin={() =>
                setPinned((was) => (was === pin.product.entry ? null : pin.product.entry))
              }
              armed={tap.armed === pin.product.entry}
              onDown={tap.down}
              goes={() => tap.goes(pin.product.entry)}
              onReveal={() => onRevealKind?.(pin.product, pin.by)}
            />
          ),
        )}
      </div>

      {/* THE LENS. An instrument control, not a toolbar: one small mark that
          says what it is showing only when that is not everything. */}
      <div className="happening-lens">
        <button
          ref={lensAt}
          className={'lens-mark' + (lens !== 'all' ? ' on' : '')}
          aria-expanded={lensOpen}
          aria-label={
            lens === 'all'
              ? `showing every mark in ${scopeName} — narrow what is shown`
              : `showing only ${LENSES.find((l) => l.id === lens)?.label.toLowerCase()} — ` +
                `${hidden} further ${hidden === 1 ? 'mark is' : 'marks are'} recorded and not drawn`
          }
          title={lens === 'all' ? 'narrow what is shown' : 'filtered — ' + hidden + ' not drawn'}
          onClick={() => setLensOpen(!lensOpen)}
        >
          <span aria-hidden="true" />
        </button>
        {lensOpen && (
          <>
            <span className="scrim" onClick={() => setLensOpen(false)} />
            <span className="lens-menu" role="menu" style={anchored(lensAt.current, 210)}>
              {LENSES.map((l) => (
                <button
                  key={l.id}
                  role="menuitemradio"
                  aria-checked={lens === l.id}
                  className={'lens-item' + (lens === l.id ? ' on' : '')}
                  onClick={() => {
                    setLens(l.id)
                    setLensOpen(false)
                  }}
                >
                  <span className="lens-item-name">{l.label}</span>
                  <span className="lens-item-says">{l.says}</span>
                </button>
              ))}
              {lens !== 'all' && (
                <span className="lens-note">
                  {hidden} {hidden === 1 ? 'mark is' : 'marks are'} recorded here and not
                  drawn. Nothing has been removed.
                </span>
              )}
            </span>
          </>
        )}
      </div>

      {/* The explanation rung. Two resolutions are reachable from the spine
          and neither is behind a menu; the third IS the spine. */}
      <button
        className={'happening-words' + (resolution === 'explanation' ? ' on' : '')}
        aria-pressed={resolution === 'explanation'}
        aria-label={`read what happened in ${scopeName} in words`}
        title="read it in words"
        onClick={() => onResolution(resolution === 'explanation' ? 'glance' : 'explanation')}
      >
        <span className="happening-words-mark" aria-hidden="true" />
      </button>
    </div>
  )
}

/** One mark on the spine: either something that happened, or something
 *  durable that was minted. Both carry their own moment. */
type Pin =
  | { what: 'act'; at: number; node: Node }
  | { what: 'kind'; at: number; product: Product; by: Act }

/** Where each mark sits, as a percentage of the spine's height: its own
 *  moment between the first and the last. A minimum separation is applied
 *  downward so that a burst of marks a second apart is still several a finger
 *  can tell apart rather than one thick smear. A Kind badge is larger than a
 *  tick, so it asks for more room than one. */
function placed(pins: Pin[]): { pin: Pin; top: number }[] {
  if (pins.length === 0) return []
  const first = pins[0].at
  const last = pins[pins.length - 1].at
  const span = Math.max(1, last - first)
  const gap = Math.min(4, 92 / Math.max(1, pins.length))
  let previous = -Infinity
  return pins.map((pin) => {
    const wanted = ((pin.at - first) / span) * 92
    const room = pin.what === 'kind' ? gap * 1.8 : gap
    const top = Math.max(wanted, previous + room)
    previous = top
    return { pin, top: Math.min(top, 99) }
  })
}

/** ONE STRUCTURAL ACT, AT GLANCE RESOLUTION.
 *
 *  A short horizontal tick. Its weight says whether work ran under it and how
 *  much routine working it gathered; its position says when. It says that
 *  SOMETHING HAPPENED and nothing more — what the work left behind is a Kind
 *  badge of its own, further down this spine, and the two are never merged.
 *
 *  THE CALLOUT IS IMMEDIATE AND IT IS OURS. A native `title` appears after a
 *  second, in the operating system's font, at the pointer rather than at the
 *  mark — which on a spine of forty marks tells you almost nothing about
 *  WHICH one you are on. This opens at once, beside the mark it belongs to,
 *  and it says what the record says: the act as its own type names it, who
 *  did it, and their reason if they recorded one.
 *
 *  HOVER PREVIEWS. CLICK NAVIGATES. PIN PERSISTS. Three gestures, three
 *  meanings, and none of them doing another's work. Navigating takes the
 *  reader to the Turn the act belongs to and opens its Details; a finger's
 *  first tap is the preview (see `useTapFirst`).
 */
function Mark({
  node,
  top,
  on,
  aliasOf,
  owes,
  onOwed,
  pinned,
  onPin,
  armed,
  onDown,
  goes,
  onSelect,
}: {
  node: Node
  top: number
  on: boolean
  aliasOf: (id: Id) => string | null
  /** why this point owes the reader something, in the record's own words */
  owes?: string | null
  onOwed?: () => void
  pinned?: boolean
  onPin?: () => void
  /** touched once: previewing, and the next touch goes */
  armed?: boolean
  onDown?: (e: React.PointerEvent) => void
  goes?: () => boolean
  onSelect: () => void
}) {
  const at = useRef<HTMLButtonElement | null>(null)
  const [open, setOpen] = useState(false)
  const a = node.act
  const who = aliasOf(a.actor) ?? a.actor
  const gathered = node.inside.length
  const says = [
    owes || '',
    said(a.act),
    who,
    a.because,
    gathered > 0 ? `${gathered} routine ${gathered === 1 ? 'step' : 'steps'} under it` : '',
    ago(a.at),
  ]
    .filter(Boolean)
    .join(' · ')
  const showing = open || pinned || armed
  const go = () => {
    if (owes && onOwed) onOwed()
    else onSelect()
  }
  return (
    <>
      <button
        ref={at}
        role="listitem"
        className={
          'happen' +
          (on ? ' on' : '') +
          (a.execution ? ' ran' : '') +
          (gathered > 0 ? ' gathered' : '') +
          ' role-' +
          node.role +
          (owes ? ' owes' : '') +
          (pinned ? ' pinned' : '')
        }
        style={{ top: `${top}%` }}
        aria-current={on}
        aria-label={says}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onPointerDown={onDown}
        onClick={() => {
          if (!goes || goes()) go()
        }}
      >
        {owes && (
          <span className="happen-owed" aria-hidden="true">
            !
          </span>
        )}
      </button>
      {showing && (
        <Callout
          at={at.current}
          pinned={pinned}
          onPin={onPin}
          go={armed ? { label: a.turn ? 'Go to its Turn' : 'Go to it', run: go } : undefined}
        >
          {owes && <span className="peek-owed">{owes}</span>}
          <span className="peek-head">
            <span className="peek-term">{said(a.act)}</span>
            <span className="peek-who">{who}</span>
          </span>
          {a.because && <span className="peek-why">{a.because}</span>}
          {gathered > 0 && (
            <span className="peek-aside">
              {gathered} routine {gathered === 1 ? 'step' : 'steps'} gathered here
            </span>
          )}
          <span className="peek-aside">{ago(a.at)}</span>
        </Callout>
      )}
    </>
  )
}

/** A callout attached to one mark.
 *
 *  It is anchored to the mark rather than floated near the pointer, and it
 *  carries a small stem so the eye can see WHICH mark it belongs to — on a
 *  spine of forty, a card hanging in space beside them answers the wrong
 *  question. It is transient unless the reader pins it.
 *
 *  `go` is the explicit way on for a finger: a tap only previews (see
 *  `useTapFirst`), so the preview it opened carries the step a click takes. */
export function Callout({
  at,
  pinned,
  onPin,
  go,
  children,
}: {
  at: HTMLElement | null
  pinned?: boolean
  onPin?: () => void
  go?: { label: string; run: () => void }
  children: React.ReactNode
}) {
  const box = at?.getBoundingClientRect()
  if (!box) return null
  const top = Math.max(8, Math.min(box.top + box.height / 2, window.innerHeight - 30))
  /* Beside the mark where there is room for it; kept on screen where there
     is not — a History opened at the right-hand edge of a tablet would
     otherwise put its explanation past the glass. */
  const width = Math.min(290, window.innerWidth - 16)
  const left = Math.max(8, Math.min(box.right + 8, window.innerWidth - width - 8))
  return (
    <span
      className={'peek' + (pinned ? ' pinned' : '') + (go ? ' armed' : '')}
      role="tooltip"
      style={{ position: 'fixed', left, top, maxWidth: width }}
    >
      <span className="peek-stem" aria-hidden="true" />
      {children}
      {go && (
        <button
          className="peek-go"
          onClick={(e) => {
            e.stopPropagation()
            go.run()
          }}
        >
          {go.label}
        </button>
      )}
      {onPin && (
        <button
          className={'peek-pin' + (pinned ? ' on' : '')}
          aria-pressed={!!pinned}
          aria-label={pinned ? 'unpin this preview' : 'keep this preview while looking around'}
          title={pinned ? 'unpin' : 'keep this open'}
          onClick={(e) => {
            e.stopPropagation()
            onPin()
          }}
        >
          <span aria-hidden="true">{pinned ? '◉' : '○'}</span>
        </button>
      )}
    </span>
  )
}

/** WHAT ONE ACT WAS, IN WORDS, for a callout: what happened, who did it,
 *  their reason if they recorded one, and where and when it belongs. Never
 *  an id — the record's ids stay in Details. */
export function ActPreview({
  act,
  who,
  what,
  turn,
  where,
}: {
  act: Act
  who: string
  what: string
  turn?: number
  /** the Conversation it belongs to, said only when that is not this one */
  where?: string | null
}) {
  return (
    <>
      <span className="peek-head">
        <span className="peek-term">{what}</span>
        <span className="peek-who">{who}</span>
      </span>
      {act.because && <span className="peek-why">{act.because}</span>}
      <span className="peek-aside">
        {[turn !== undefined ? `Turn #${turn}` : null, where ? `in ${where}` : null, when(act.at)]
          .filter(Boolean)
          .join(' · ')}
      </span>
    </>
  )
}

/** HOVER PREVIEWS AND CLICK GOES — AND A FINGER HAS NO HOVER.
 *
 *  A tap arrives as a click, so without this a touch screen never sees a
 *  preview at all: the first touch of a mark would already have moved the
 *  reader somewhere else. So a touch press on a mark ARMS it and shows its
 *  preview; touching the same mark again, or the Go in that preview, goes.
 *  A mouse click and Enter on the keyboard go at once, as they always did.
 *
 *  Nothing here is durable, and arming changes nothing but what is drawn. */
export function useTapFirst() {
  const touch = useRef(false)
  const [armed, setArmed] = useState<string | null>(null)
  return {
    armed,
    disarm: () => setArmed(null),
    /** on the mark's pointerdown: say what kind of press this is */
    down: (e: React.PointerEvent) => {
      touch.current = e.pointerType === 'touch' || e.pointerType === 'pen'
    },
    /** on the mark's click: true when this press should go, false when it
     *  only previewed */
    goes: (id: string): boolean => {
      const byTouch = touch.current
      touch.current = false
      if (!byTouch || armed === id) {
        setArmed(null)
        return true
      }
      setArmed(id)
      return false
    },
  }
}
