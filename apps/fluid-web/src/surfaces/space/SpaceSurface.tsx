import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { qs, useApi } from '../../api'
import BrainSpace, { LAYER_TOKEN, type Palette } from './BrainSpace'
import ChosenCard from './ChosenCard'
import { useChosen } from './chosen'
import { firstSeen, isDark, orderHue, place, strands, type SpaceNode, type SpaceRead } from './layout'
import './space.css'

/* ------------------------------------------------------------------------ *
 * THE 3D BRAIN, AS A PLACE (`#/brain/space`, from the Brain menu).
 *
 * The whole Brain drawn in space from `/api/space`: every durable thing,
 * in the region of the Conversation the record puts it in, at the height its
 * Kind declares. The canvas is the space; the readable parts float over it.
 *
 * WHAT IS DELIBERATELY NOT HERE (owner, 2026-10-10): Mark III's detail
 * panels and its question tabs. Choosing a star says what it is in one line
 * and offers OPEN, which goes where that thing already lives in Mark IV --
 * its Conversation, its Turn, its Topic, or the record inspector -- the same
 * destinations a search result goes to. The 3D Brain is a way of seeing the
 * Brain, not a second place to read it.
 *
 * IN FLUID, OPEN IS A SURFACE OVER IT (fluid/brain/): the chosen thing's
 * record opens in a Fluid float over the field, and the float says where it
 * lives and goes there. The field stays the place; what floats is children,
 * drawn over it.
 *
 * LOADED ONLY WHEN SOMEBODY COMES HERE: Fluid's Shell imports this lazily
 * (fluid/brain/BrainPlace.tsx), so nothing about the rest of the interface
 * waits for it.
 * ------------------------------------------------------------------------ */

const LAYER_WORDS: Record<string, string> = {
  how: 'what directs work',
  that: 'what is known',
  place: 'conversations and topics',
  who: 'participants',
  said: 'turns',
  other: 'kinds that declare no knowing',
  material: 'acquired material',
}

export interface SpaceSurfaceProps {
  /** go where this thing lives */
  onOpen: (node: SpaceNode) => void
  /** the chosen card's drag (fluid/brain/address.ts): what it carries */
  onDragChosen?: (node: SpaceNode, e: React.DragEvent) => void
  /** each read of the Brain, for what floats over the field */
  onRead?: (data: SpaceRead) => void
  /** what floats over the field: drawn above it, passing the pointer through
   *  wherever it draws nothing */
  children?: ReactNode
}

export default function SpaceSurface({ onOpen, onDragChosen, onRead, children }: SpaceSurfaceProps) {
  const [material, setMaterial] = useState(false)
  /* LIVE, BUT NOT ON EVERY ADVANCE (review N2): the whole Brain is one read,
     so advances while this is open become at most one re-read every few
     seconds. */
  const read = useApi<SpaceRead>(`/api/space${qs({ material: material ? 1 : null })}`, { spacing: 5000 })
  const data = read.data
  const [selected, setSelected] = useState<string | null>(null)
  const [palette, setPalette] = useState<Palette>('none')
  const [allStrands, setAllStrands] = useState(false)
  const [turns, setTurns] = useState(true)
  const [options, setOptions] = useState(false)
  const [asOf, setAsOf] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)

  const nodes = useMemo(() => data?.nodes ?? [], [data])
  const layers = useMemo(() => data?.layers ?? [], [data])
  const placed = useMemo(() => place(nodes, layers), [nodes, layers])
  const links = useMemo(() => strands(placed, data?.edges ?? []), [placed, data])
  const byId = useMemo(() => new Map(nodes.map((n) => [n.entry, n])), [nodes])
  const hidden = useMemo(() => new Set(turns ? [] : ['said']), [turns])
  const names = data?.conversations
  useEffect(() => {
    if (data) onRead?.(data)
  }, [data, onRead])
  const nameOf = useCallback((c: string | null) => (c && names ? (names[c] ?? null) : null), [names])

  /* A selection that is no longer drawn -- its layer hidden, or the record
     moved -- is let go rather than pointed at nothing. */
  useEffect(() => {
    if (!selected) return
    const n = byId.get(selected)
    if (!n || hidden.has(n.layer)) setSelected(null)
  }, [selected, byId, hidden])

  /* ---- watch how it was built: the record's own clock, played ------------ */
  const span = useMemo(() => {
    const at = nodes.map((n) => n.at).filter((t): t is number => t !== null)
    return at.length ? ([Math.min(...at), Math.max(...at)] as const) : null
  }, [nodes])
  const began = useRef<{ wall: number; from: number } | null>(null)
  useEffect(() => {
    if (!playing || !span) return
    const PLAY_MS = 20000
    const whole = Math.max(1, span[1] - span[0])
    began.current = { wall: performance.now(), from: asOf ?? span[0] }
    let id = 0
    const tick = (now: number) => {
      const b = began.current!
      const next = b.from + ((now - b.wall) / PLAY_MS) * whole
      if (next >= span[1]) {
        setAsOf(span[1])
        setPlaying(false)
        return
      }
      setAsOf(next)
      id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, span])

  const drawnNow = useMemo(
    () => nodes.filter((n) => !hidden.has(n.layer) && (asOf === null || (n.at ?? 0) <= asOf)),
    [nodes, hidden, asOf],
  )
  const regions = useMemo(() => new Set(drawnNow.map((n) => n.conversation).filter(Boolean)).size, [drawnNow])
  const regionAt = useMemo(() => firstSeen(placed.map((p) => p.node.conversation)), [placed])
  const relationAt = useMemo(() => firstSeen(links.map((l) => l.relation)), [links])
  const inWeb = useMemo(() => {
    const m = new Map<string, number>()
    for (const l of links) m.set(l.relation, (m.get(l.relation) ?? 0) + 1)
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [links])
  const inLayers = useMemo(() => {
    const m = new Map<string, number>()
    for (const n of drawnNow) m.set(n.layer, (m.get(n.layer) ?? 0) + 1)
    return layers.filter((l) => m.has(l)).map((l) => [l, m.get(l)!] as const)
  }, [drawnNow, layers])
  const inConversations = useMemo(() => {
    const m = new Map<string, number>()
    for (const n of drawnNow) if (n.conversation) m.set(n.conversation, (m.get(n.conversation) ?? 0) + 1)
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [drawnNow])

  const dark = useDarkGround()
  /* THE SELECTION AND ITS WORDS, as data a card -- or a details pane beside
     the canvas, later -- reads. See chosen.ts. */
  const chosen = useChosen(selected ? (byId.get(selected) ?? null) : null)
  const count = drawnNow.length
  const said = `${count} ${count === 1 ? 'thing' : 'things'}` + (data && data.omitted > 0 ? ` of ${data.total}` : '')
  const caption = `${said} · ${regions} ${regions === 1 ? 'Conversation' : 'Conversations'}`

  return (
    <section className="space-surface" aria-label="3D Brain">
      {data && nodes.length > 0 && (
        <BrainSpace
          placed={placed}
          links={links}
          selected={selected}
          onSelect={setSelected}
          palette={palette}
          allStrands={allStrands}
          hidden={hidden}
          asOf={asOf}
          playing={playing}
          nameOf={nameOf}
          onOpen={(id) => {
            const n = byId.get(id)
            if (n) onOpen(n)
          }}
          label={`${caption}, arranged by the Conversation each belongs to and the layer its kind declares`}
        />
      )}

      <header className="space-head">
        <span className="space-eyebrow">Brain</span>
        <h2 className="space-title">3D Brain</h2>
        <p className="space-caption" aria-live="polite">
          {read.error && !data
            ? `Could not read this Brain: ${read.error}`
            : !data
              ? 'Reading the Brain…'
              : nodes.length === 0
                ? 'Nothing durable is held here yet.'
                : caption}
        </p>
      </header>

      <div className="space-tools">
        <button
          type="button"
          className="space-tool"
          aria-expanded={options}
          aria-controls="space-options"
          onClick={() => setOptions((o) => !o)}
        >
          Options
        </button>
        {options && (
          <div className="space-options" id="space-options" role="group" aria-label="Options">
            <label className="space-choice">
              <input type="checkbox" checked={allStrands} onChange={(e) => setAllStrands(e.target.checked)} />
              <span>
                Show every connection
                <small>{links.length} links the record holds between what is drawn</small>
              </span>
            </label>
            <label className="space-choice">
              <input type="checkbox" checked={turns} onChange={(e) => setTurns(e.target.checked)} />
              <span>
                Show turns
                <small>the talk itself; off leaves what is known and its structure</small>
              </span>
            </label>
            <label className="space-choice">
              <input type="checkbox" checked={material} onChange={(e) => setMaterial(e.target.checked)} />
              <span>
                Show acquired material
                <small>files and results brought in by work; can be thousands</small>
              </span>
            </label>
            <fieldset className="space-palette">
              <legend>Colour by</legend>
              {(
                [
                  ['none', 'nothing'],
                  ['layer', 'layer'],
                  ['conversation', 'Conversation'],
                ] as const
              ).map(([which, word]) => (
                <label key={which}>
                  <input
                    type="radio"
                    name="space-palette"
                    checked={palette === which}
                    onChange={() => setPalette(which)}
                  />
                  {word}
                </label>
              ))}
            </fieldset>
            {span && (
              <button
                type="button"
                className="space-play"
                onClick={() => {
                  setOptions(false)
                  setAsOf(span[0])
                  setPlaying(true)
                }}
              >
                <span>
                  <span aria-hidden="true">▶</span> Watch how it was built
                </span>
                <small>everything drawn, in the order the record received it</small>
              </button>
            )}
          </div>
        )}
      </div>


      <div className="space-legends">
        {chosen && (
          <div className="space-key" aria-label="What each colour means here">
            <p className="space-key-row">
              <span className="space-dot space-tie-chosen" />
              what you chose
            </p>
            <p className="space-key-row">
              <span className="space-dot space-tie-out" />
              what it points to
            </p>
            <p className="space-key-row">
              <span className="space-dot space-tie-in" />
              what points to it
            </p>
          </div>
        )}
        {!chosen && allStrands && inWeb.length > 0 && (
          <div className="space-key" aria-label="What each connection is">
            {inWeb.slice(0, 8).map(([relation, n]) => (
              <p key={relation} className="space-key-row">
                <span className="space-line" style={{ background: orderHue(relationAt.get(relation) ?? 0, dark) }} />
                <span className="space-key-name">{relation}</span>
                <b>{n}</b>
              </p>
            ))}
          </div>
        )}
        {!chosen && palette === 'layer' && (
          <div className="space-key" aria-label="What each colour is">
            {inLayers.map(([layer, n]) => (
              <p key={layer} className="space-key-row">
                <span className="space-dot" style={{ background: `var(${LAYER_TOKEN[layer]})` }} />
                <span className="space-key-name">{LAYER_WORDS[layer] ?? layer}</span>
                <b>{n}</b>
              </p>
            ))}
          </div>
        )}
        {!chosen && palette === 'conversation' && (
          <div className="space-key" aria-label="What each colour is">
            {inConversations.slice(0, 8).map(([c, n]) => (
              <p key={c} className="space-key-row">
                <span className="space-dot" style={{ background: orderHue(regionAt.get(c) ?? 0, dark) }} />
                <span className="space-key-name">{nameOf(c) ?? 'a Conversation'}</span>
                <b>{n}</b>
              </p>
            ))}
            {inConversations.length > 8 && <p className="space-key-more">and {inConversations.length - 8} more</p>}
          </div>
        )}
      </div>

      {/* THE FOOT: the record's clock and the chosen thing's card stack here,
          so neither is drawn over the other whatever height the card is. */}
      <div className="space-foot">
        {asOf !== null && span && (
          <div className="space-when" role="group" aria-label="When the Brain is shown as of">
            <button
              type="button"
              className="space-tool"
              aria-label={playing ? 'Pause' : 'Play'}
              onClick={() => setPlaying((p) => !p)}
            >
              {playing ? '❚❚' : '▶'}
            </button>
            <input
              type="range"
              className="space-scrub"
              min={span[0]}
              max={span[1]}
              step="any"
              value={asOf}
              aria-label="Move through the record"
              onChange={(e) => {
                setPlaying(false)
                setAsOf(Number(e.target.value))
              }}
            />
            <time className="space-when-said">{dayText(asOf)}</time>
            <button
              type="button"
              className="space-tool"
              onClick={() => {
                setPlaying(false)
                setAsOf(null)
              }}
            >
              Now
            </button>
          </div>
        )}
        {chosen && (
          <ChosenCard
            chosen={chosen}
            conversation={nameOf(chosen.node.conversation)}
            onOpen={() => onOpen(chosen.node)}
            onClose={() => setSelected(null)}
            onDrag={onDragChosen ? (e) => onDragChosen(chosen.node, e) : undefined}
          />
        )}
      </div>
      {children}
    </section>
  )
}

function dayText(at: number): string {
  return new Date(at * 1000).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Whether the ground is dark right now, measured as the canvas measures it,
 *  so a legend's swatches are the colours the stars are drawn in. */
function useDarkGround(): boolean {
  const read = () =>
    typeof getComputedStyle !== 'function'
      ? true
      : isDark(getComputedStyle(document.documentElement).getPropertyValue('--surface').trim())
  const [dark, setDark] = useState(read)
  useEffect(() => {
    const again = () => setDark(read())
    const mo = new MutationObserver(again)
    mo.observe(document.documentElement, { attributes: true })
    const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null
    mq?.addEventListener?.('change', again)
    return () => {
      mo.disconnect()
      mq?.removeEventListener?.('change', again)
    }
  }, [])
  return dark
}
