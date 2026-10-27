import { useEffect, useRef, useState } from 'react'

/* ------------------------------------------------------------------------ *
 * THE TITLE IS THE BRAIN'S DOOR (UI polish 2, #8).
 *
 * The owner: move the Brain icon into the "Mentis" title; it reads
 * "Mentis:[brain name]", same font, the name in another colour; and the
 * title opens a main menu -- Manage Brain (Governance), change brains, and
 * other settings later.
 *
 * So the separate Brain button is gone and nothing it did is lost: "Brain
 * home" is the first row here, and the title shows the same "you are at the
 * Brain" state the button did. The name is the one the Brain's own manifest
 * gives (`/api/brain` · `corpus_name`); where there is none it says so
 * rather than borrowing the folder's.
 *
 * CHANGING BRAINS IS SAID, NOT FAKED. This server opens one corpus for its
 * whole life and has no way to open another, so "Change brain" is a row that
 * says which Brain this is and why it cannot switch yet -- not a control
 * that does nothing.
 *
 * It opens on hover where there is a pointer that hovers, and on a press
 * everywhere (a press keeps it open). Esc, a press outside, or leaving it
 * closes it; Esc hands focus back to the title. Rows are ordinary buttons,
 * so Tab and Enter reach them; ↑/↓ move between them as in any menu.
 *
 * MORE SETTINGS LATER are one more entry in `rows` -- the menu has sections
 * so they have somewhere to go, and none is drawn empty in the meantime.
 *
 * MANAGE SOURCES IS THE FIRST OF THEM (Sources slice 1, U2), and this row is
 * its ONLY entry point: no Brain home band and no Conversation rail row.
 * Acquired material is managed here, in one place, and used everywhere by
 * reference.
 * ------------------------------------------------------------------------ */

export interface BrandMenuProps {
  /** the Brain's own name, or null where it has none */
  name: string | null
  /** why there is no name, in the server's words */
  whyNot?: string | null
  /** where this Brain's record lives, said in the Change brain row */
  path?: string | null
  /** standing at the whole Brain now */
  atBrain: boolean
  onBrainHome: () => void
  onManage: () => void
  /** Manage Sources (`#/brain/sources`) */
  onSources?: () => void
  /** standing in Manage Sources now */
  atSources?: boolean
  /** the 3D Brain (`#/brain/space`) */
  onSpace?: () => void
  /** standing in the 3D Brain now */
  atSpace?: boolean
  /** the other interface over the same Brain (shellSwitch.ts): Classic
   *  offers Fluid, Fluid offers Classic, each at the Conversation open now */
  switchTo?: { name: 'Fluid' | 'Classic'; run: () => void }
}

interface Row {
  key: string
  name: string
  sub: string
  run?: () => void
  current?: boolean
}

export default function BrandMenu({
  name,
  whyNot,
  path,
  atBrain,
  onBrainHome,
  onManage,
  onSources,
  atSources,
  onSpace,
  atSpace,
  switchTo,
}: BrandMenuProps) {
  const [open, setOpen] = useState<null | 'hover' | 'pinned'>(null)
  const opener = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const leave = useRef<number | null>(null)
  const hovers = typeof window !== 'undefined' && window.matchMedia?.('(hover: hover)').matches

  const close = (refocus = false) => {
    setOpen(null)
    if (refocus) requestAnimationFrame(() => opener.current?.focus())
  }

  useEffect(() => {
    if (!open) return
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        close(true)
      }
    }
    const away = (e: PointerEvent) => {
      const t = e.target as Node
      if (!menu.current?.contains(t) && !opener.current?.contains(t)) close()
    }
    window.addEventListener('keydown', key, true)
    window.addEventListener('pointerdown', away)
    return () => {
      window.removeEventListener('keydown', key, true)
      window.removeEventListener('pointerdown', away)
    }
  }, [open])

  const hoverIn = () => {
    if (leave.current) window.clearTimeout(leave.current)
    leave.current = null
    if (hovers && !open) setOpen('hover')
  }
  const hoverOut = () => {
    if (!hovers || open !== 'hover') return
    leave.current = window.setTimeout(() => setOpen((o) => (o === 'hover' ? null : o)), 260)
  }

  const said = name ?? 'unnamed'
  const sections: { title: string; rows: Row[] }[] = [
    {
      title: 'This Brain',
      rows: [
        {
          key: 'home',
          name: 'Brain home',
          sub: 'the whole Brain: what waits for you and what is working',
          run: onBrainHome,
          current: atBrain && !atSources && !atSpace,
        },
        {
          key: 'manage',
          name: 'Manage Brain',
          sub: 'Governance over the whole Brain: what stands, what is proposed',
          run: onManage,
        },
        ...(onSources
          ? [{
              key: 'sources',
              name: 'Manage Sources',
              sub: 'material acquired into this Brain, usable from every Conversation',
              run: onSources,
              current: !!atSources,
            }]
          : []),
        ...(onSpace
          ? [
              {
                key: 'space',
                name: '3D Brain',
                sub: 'the whole Brain in space: what it holds, where, and how it connects',
                run: onSpace,
                current: !!atSpace,
              },
            ]
          : []),
      ],
    },
    ...(switchTo
      ? [
          {
            title: 'Interface',
            rows: [
              {
                key: 'switch',
                name: `Switch to ${switchTo.name}`,
                sub:
                  switchTo.name === 'Fluid'
                    ? 'the same Brain in Fluid, at this conversation; Classic stays one click back'
                    : 'the same Brain in Classic, at this conversation; Fluid stays one click back',
                run: switchTo.run,
              },
            ],
          },
        ]
      : []),
    {
      title: 'Brains',
      rows: [
        {
          key: 'change',
          name: 'Change brain',
          sub:
            `This server serves one Brain${name ? `, ${name}` : ''}` +
            (path ? ` (${path})` : '') +
            '. Switching needs a server that can open another; that does not exist yet.',
        },
      ],
    },
  ]

  const rowsNow = () => [...(menu.current?.querySelectorAll<HTMLButtonElement>('button.brand-row') ?? [])]
  const onMenuKey = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const rows = rowsNow()
    const i = rows.indexOf(document.activeElement as HTMLButtonElement)
    const next = e.key === 'ArrowDown' ? (i + 1) % rows.length : (i - 1 + rows.length) % rows.length
    rows[next]?.focus()
  }

  return (
    <span className="brand-wrap" onPointerEnter={hoverIn} onPointerLeave={hoverOut}>
      <button
        ref={opener}
        className={'brand brand-menu-open' + (atBrain ? ' on' : '') + (open ? ' open' : '')}
        aria-haspopup="menu"
        aria-expanded={!!open}
        aria-label={`Mentis: ${said}. Brain menu`}
        title={name ? undefined : (whyNot ?? 'this Brain has no name')}
        onClick={() => setOpen((o) => (o === 'pinned' ? null : 'pinned'))}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setOpen('pinned')
            requestAnimationFrame(() => rowsNow()[0]?.focus())
          }
        }}
      >
        <span className="brain-glyph" aria-hidden="true" />
        <span className="brand-word">Mentis</span>
        <span className="brand-colon" aria-hidden="true">:</span>
        <span className={'brand-brain' + (name ? '' : ' none')}>{said}</span>
      </button>
      {open && (
        <div className="brand-menu" role="menu" aria-label="Brain menu" ref={menu} onKeyDown={onMenuKey}>
          {sections.map((s) => (
            <div className="brand-section" key={s.title} role="group" aria-label={s.title}>
              <div className="brand-section-title" aria-hidden="true">
                {s.title}
              </div>
              {s.rows.map((r) => (
                <button
                  key={r.key}
                  className="brand-row"
                  role="menuitem"
                  data-row={r.key}
                  aria-disabled={r.run ? undefined : true}
                  aria-current={r.current || undefined}
                  onClick={() => {
                    if (!r.run) return
                    close()
                    r.run()
                  }}
                >
                  <span className="brand-row-name">
                    {r.name}
                    {r.current && <span className="brand-row-here"> · you are here</span>}
                  </span>
                  <span className="brand-row-sub">{r.sub}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </span>
  )
}
