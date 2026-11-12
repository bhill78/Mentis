/* JUMP TO LATEST (usability 5.6, revised with the owner): where work last
 * ended in this conversation, one step away.
 *
 * A round down-arrow beside the composer -- never over the conversation's
 * words or the composer itself -- on a solid, theme-aware ground so it reads
 * over any wallpaper. It pulses softly while the conversation's newest post
 * is out of view (still, where reduced motion is asked for).
 *
 * Activated, it opens a small list upward: one row per reply chain that
 * moved within the last hour, at that chain's newest post, newest first --
 * and always the conversation's newest post, however old (latest.ts
 * `chainsOf`). Not an activity feed: a chain is offered once, whatever
 * moved in it. Each row says what the chain is about (its starter's first
 * line) and when it last moved. Choosing one goes to that exact post, its
 * replies revealed and the post marked (Quiet2.tsx `goTo`). Arrow keys move,
 * Enter chooses, Escape closes and puts focus back on the arrow. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { postOf } from './real'
import { CHAIN_WINDOW, chainsOf, readRecent, readWords, subjectOf, type Activity, type Chain } from './latest'
import { useNow, whenExact, whenSaid } from './when'
import type { Id } from './sample'

interface Row { chain: Chain; subject: string }

export const ArrowDown = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 5v14M6 13l6 6 6-6" />
  </svg>
)

/** The chains to offer, each with its subject: read when the list opens. */
async function readRows(conversation: Id): Promise<Row[]> {
  const recent = await readRecent(conversation)
  const chains = chainsOf(recent, Date.now() / 1000)
  const words = new Map<Id, string>()
  for (const c of chains) {
    const held = postOf(c.root)
    const own = recent.find((p) => p.id === c.root)
    const w = held ? held.title ?? held.text ?? '' : own?.excerpt ?? null
    if (w) words.set(c.root, w)
  }
  const missing = chains.map((c) => c.root).filter((r) => !words.has(r))
  if (missing.length) for (const [k, v] of await readWords(missing).catch(() => new Map<Id, string>())) words.set(k, v)
  return chains.map((chain) => ({ chain, subject: subjectOf(words.get(chain.root)) || (chain.newest.number ? `Thread of #${chain.newest.number}` : 'A thread') }))
}

export default function JumpToLatest({ conversation, away, onGo, onBack }: {
  conversation: Id
  /** the conversation's newest post is out of view: the arrow pulses */
  away: boolean
  onGo: (to: Activity) => void
  /** after a jump within the flow: back to where the reader was */
  onBack: (() => void) | null
}) {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const now = useNow()

  useEffect(() => { setOpen(false); setRows(null) }, [conversation])
  useEffect(() => {
    if (!open) return
    let live = true
    setError(null)
    readRows(conversation).then((r) => { if (live) setRows(r) }, (e: unknown) => { if (live) setError(String(e)) })
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', away)
    return () => { live = false; document.removeEventListener('pointerdown', away) }
  }, [open, conversation])
  /* the first row has focus once the list is drawn */
  const items = () => [...(box.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])]
  useLayoutEffect(() => { if (open) (items()[0] ?? box.current)?.focus() }, [open, rows])

  const close = (refocus: boolean) => { setOpen(false); if (refocus) requestAnimationFrame(() => button.current?.focus()) }
  const onKey = (e: React.KeyboardEvent) => {
    const all = items()
    const at = all.indexOf(document.activeElement as HTMLButtonElement)
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); return }
    if (e.key === 'Tab') { close(false); return }
    const to = e.key === 'ArrowDown' ? at + 1 : e.key === 'ArrowUp' ? at - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? all.length - 1 : null
    if (to === null || !all.length) return
    e.preventDefault()
    all[(to + all.length) % all.length].focus()
  }
  const go = (c: Chain) => { setOpen(false); onGo(c.newest) }

  return (
    <div className="q2-jump-wrap">
      <button ref={button} type="button" className="q2-jump" data-away={away || undefined}
        aria-haspopup="menu" aria-expanded={open} aria-label="Jump to latest"
        title={away ? 'Jump to latest: newer posts are out of view' : 'Jump to latest'}
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => { if (e.key === 'ArrowUp' && !open) { e.preventDefault(); setOpen(true) } }}>
        <ArrowDown />
      </button>
      {open && (
        <div ref={box} className="q2-jump-menu" role="menu" aria-label="Jump to latest" tabIndex={-1} onKeyDown={onKey}>
          <p className="q2-jump-head" aria-hidden="true">Jump to latest <span>where work last ended · the last {CHAIN_WINDOW / 60} minutes</span></p>
          {onBack && (
            <button role="menuitem" className="q2-jump-row q2-jump-back" onClick={() => { setOpen(false); onBack() }}>
              <span className="q2-jump-subject">↑ Back to where you were</span>
            </button>
          )}
          {error ? <p className="q2-jump-note" role="alert">Could not read the latest posts: {error}</p>
            : !rows ? <p className="q2-jump-note">Reading…</p>
            : !rows.length ? <p className="q2-jump-note">Nothing has been posted here yet.</p>
            : rows.map(({ chain, subject }) => {
              const p = chain.newest
              const when = p.at != null ? whenSaid(p.at, now) : ''
              const said = [p.number ? `#${p.number}` : null, p.author?.replace(/^@/, '') ?? null, when].filter(Boolean).join(' · ')
              return (
                <button key={chain.root} role="menuitem" className="q2-jump-row" onClick={() => go(chain)}
                  title={p.at != null ? whenExact(p.at) : undefined}
                  aria-label={`${subject}. Last post ${said}${chain.latest ? ', the newest in this conversation' : ''}`}>
                  <span className="q2-jump-subject">{subject}</span>
                  <span className="q2-jump-meta">{said}{chain.latest && <span className="q2-jump-newest">newest</span>}</span>
                </button>
              )
            })}
        </div>
      )}
    </div>
  )
}
