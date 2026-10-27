/* THE LOOK SHEET (#568 4.4; TH #8-#10, owner: "I absolutely love it").
 *
 * Production's atmosphere selector, in the bar's Look sheet: every look is a
 * small picture of the room it makes -- its ground, its words, its highlight,
 * and its picture where it has one -- under "Your pictures" (the looks made
 * from a picture, with "From a picture…" to make another) and "Ready-made".
 * One plain switch says where a choice applies: this conversation, or all of
 * them. "From a picture…" opens production's own panel (picture/Maker), with
 * its choice of the picture as the background or a plain ground in the
 * picture's colours (TH #10). Above them, Light / Dark / System, which the
 * Mentis look and any look without a ground of its own follow.
 *
 * The tile is surfaces/AtmosphereMenu.tsx's, drawn with its classes
 * (picture/picture.css). It is kept here rather than imported: importing
 * that module would bring the Brain menu's helpers into the chunk /fluid
 * shares with production and change production's build. */

import { useState } from 'react'
import type { Atmosphere, BuiltIn } from '../../atmosphere'
import Maker from '../../picture/Maker'
import { UNREACHABLE, type PresentationStore } from '../../picture/store'
import { closeSheet } from './Sheet'
import { useLayer } from './layer'
import { setLookPreview, setTheme, startMaking, useLookControls, useMaking, useTheme, type Theme } from './look'
import { showToast } from './toasts'

/** What each built-in looks like, for its tile (surfaces/AtmosphereMenu.tsx). */
const LOOK: Record<BuiltIn, { ground: string; text: string; accent: string; image?: string; veil?: string }> = {
  default: { ground: '#fdfcfa', text: '#1a1916', accent: '#2b6a5e' },
  saltmarsh: { ground: '#0e1518', text: '#ece3d4', accent: '#d8a04a', image: 'radial-gradient(120% 80% at 8% 108%, rgba(196,104,42,.45) 0%, rgba(196,104,42,0) 58%), linear-gradient(176deg, #101b20, #0a1013)' },
  research: { ground: '#fbf9f4', text: '#1d2024', accent: '#1f3d5c', image: 'repeating-linear-gradient(180deg, transparent 0 9px, rgba(31,61,92,.08) 9px 10px)' },
  development: { ground: '#16181c', text: '#dfe3e8', accent: '#7ad6b2', image: 'linear-gradient(rgba(122,214,178,.08) 1px, transparent 1px) 0 0 / 10px 10px, linear-gradient(90deg, rgba(122,214,178,.08) 1px, transparent 1px) 0 0 / 10px 10px' },
  mist: { ground: '#f4f6f7', text: '#1b2124', accent: '#3d6f86', image: 'radial-gradient(70% 60% at 20% 10%, rgba(126,160,178,.35), transparent), radial-gradient(60% 60% at 90% 90%, rgba(170,190,200,.4), transparent)' },
  tidewater: { ground: '#12252d', text: '#f6f9f9', accent: '#ffc27a', image: "url('/atmospheres/shoreline.jpg')", veil: 'rgba(18,37,45,.45)' },
  nightfall: { ground: '#05070d', text: '#eef1f7', accent: '#d8b98c', image: "url('/atmospheres/nightfall.jpg')", veil: 'rgba(5,7,13,.3)' },
  shoal: { ground: '#f6f5f1', text: '#1c1f22', accent: '#2f6f62', image: "url('/atmospheres/shoal.jpg')", veil: 'rgba(246,245,241,.62)' },
  downland: { ground: '#2a2c3a', text: '#f6f3ee', accent: '#f0a24e', image: "url('/atmospheres/downland.jpg')", veil: 'rgba(26,27,39,.4)' },
  monolith: { ground: '#111823', text: '#eef2f6', accent: '#e6d27c', image: "url('/atmospheres/monolith.jpg')", veil: 'rgba(12,18,27,.35)' },
  hailmary: { ground: '#1a0b0e', text: '#f8eeee', accent: '#f2b84b', image: "url('/atmospheres/hailmary-wide.jpg')", veil: 'rgba(20,8,11,.4)' },
}
const isBuiltIn = (a: Atmosphere): a is BuiltIn => !a.startsWith('look-')

/** A tile: a very small room in the look -- never just a band of colours. */
function Tile({ at, pictures }: { at: Atmosphere; pictures: PresentationStore }) {
  let ground: string, text: string, accent: string, image: string | undefined, veil: string | undefined, pos = 'center'
  if (isBuiltIn(at)) {
    ;({ ground, text, accent, image, veil } = LOOK[at] ?? LOOK.default)
  } else {
    const t = pictures.looks.find((p) => p.id === at)
    const w = t?.theme.wide ?? {}
    ground = w['--canvas'] ?? '#222'
    text = w['--text'] ?? '#eee'
    accent = w['--accent'] ?? '#999'
    // a look that only takes the picture's colours shows no picture here
    const src = t?.theme.backdrop === 'plain' ? undefined : pictures.thumb(at)
    image = src ? `url('${src}')` : undefined
    veil = src ? w['--canvas'] + (t!.theme.scheme === 'dark' ? '66' : 'a0') : undefined
    pos = w['--canvas-image-position'] ?? 'center'
  }
  const layers = [veil && `linear-gradient(${veil}, ${veil})`, image].filter(Boolean).join(', ')
  return (
    <span className="atm-tile big" aria-hidden="true"
      style={{ backgroundColor: ground, backgroundImage: layers || undefined, backgroundSize: 'cover', backgroundPosition: pos }}>
      <i style={{ background: text, width: '54%' }} />
      <i style={{ background: text, width: '70%', opacity: 0.7 }} />
      <i style={{ background: text, width: '40%', opacity: 0.7 }} />
      <b style={{ background: accent }} />
    </span>
  )
}

const THEMES: { t: Theme; label: string }[] = [{ t: 'light', label: 'Light' }, { t: 'dark', label: 'Dark' }, { t: 'system', label: 'System' }]

export function LookBody() {
  const theme = useTheme()
  const c = useLookControls()
  const [scope, setScope] = useState<'here' | 'brain'>('here')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  if (!c) return null
  const here = scope === 'here' && !!c.conversation
  const nameOf = (a: Atmosphere) => c.choices.find((x) => x.id === a)?.name ?? 'Mentis'
  /* Change the look, and offer to put it back (production's one-step Undo).
     The sheet closes on a choice, as production's menu does: the look is
     seen at once, and the Undo is one press away. */
  const choose = (a: Atmosphere | null) => {
    if (busy) return
    const was = here ? (c.explicit ? c.current : null) : c.brain
    const p = here ? c.choose(a) : c.chooseBrain(a ?? 'default')
    setBusy(true); setErr(null)
    closeSheet()
    p.then(() => {
      showToast({
        text: here ? `${c.scopeName} now uses ${nameOf(a ?? c.inherited)}` : `All conversations now use ${nameOf(a ?? 'default')}`,
        action: { label: 'Undo', run: () => void (here ? c.choose(was) : c.chooseBrain(was ?? 'default')).catch(() => showToast({ text: UNREACHABLE })) },
      })
    }, (e: Error) => { setErr(e.message || UNREACHABLE); showToast({ text: `Could not change the look: ${e.message || UNREACHABLE}` }) })
      .finally(() => setBusy(false))
  }
  /** what is "on" in the scope being chosen for */
  const chosen = here ? (c.explicit ? c.current : null) : c.brain
  const tile = (id: Atmosphere, name: string) => {
    const on = chosen === id
    const usual = here && !c.explicit && c.current === id
    return (
      <div key={id} className="atm-cell">
        <button className={'atm-look' + (on ? ' on' : '') + (usual ? ' usual' : '')} aria-pressed={on} title={name}
          data-atmosphere-pick={id} disabled={busy} onClick={() => choose(id)}>
          <Tile at={id} pictures={c.pictures} />
          <span className="atm-look-name">{name}</span>
          {on && <span className="atm-tick" aria-label="in use">✓</span>}
        </button>
      </div>
    )
  }
  const built = c.choices.filter((x) => isBuiltIn(x.id))
  const mine = c.choices.filter((x) => !isBuiltIn(x.id))
  /* LIGHT OR DARK SAYS WHERE IT APPLIES, only when it would not be seen
     (#568 4.2): only the Mentis look leaves its ground to the theme; every
     other look -- a picture's, or a ready-made one -- keeps its own. Under
     one of those the control says so where it is pressed, and pressing it
     says what it changed. Under the Mentis look it says nothing more. */
  const own = c.current !== 'default'
  const lookName = nameOf(c.current)
  const pickTheme = (t: Theme) => {
    setTheme(t)
    if (own) showToast({ text: `${lookName} keeps its own colours. ${THEMES.find((x) => x.t === t)?.label} is for the Mentis look.` })
  }
  return (
    <div className="fb-looks" aria-busy={busy || undefined}>
      <div className="fx-sec" id="fb-theme-sec">{own ? 'Light or dark · for the Mentis look' : 'Light or dark'}</div>
      <div className="fb-seg" role="radiogroup" aria-labelledby="fb-theme-sec" data-own-ground={own ? '' : undefined}>
        {THEMES.map((x) => (
          <button key={x.t} role="radio" aria-checked={theme === x.t} className={theme === x.t ? 'on' : ''} data-theme-pick={x.t}
            title={own ? `${lookName} keeps its own colours; this is for the Mentis look` : undefined}
            onClick={() => pickTheme(x.t)}>{x.label}</button>
        ))}
      </div>
      {c.conversation && (
        <div className="fb-seg fb-scope" role="radiogroup" aria-label="For">
          <button role="radio" aria-checked={scope === 'here'} className={scope === 'here' ? 'on' : ''} onClick={() => setScope('here')}>This conversation</button>
          <button role="radio" aria-checked={scope === 'brain'} className={scope === 'brain' ? 'on' : ''} onClick={() => setScope('brain')}>All conversations</button>
        </div>
      )}
      <div className="fx-sec">Your pictures</div>
      <div className="atm-grid fb-atm-grid">
        {mine.map((x) => tile(x.id, x.name))}
        <div className="atm-cell">
          <button className="atm-look atm-make" data-act="from-picture"
            onClick={() => { closeSheet(); startMaking(here ? 'conversation' : 'everywhere') }}>
            <span className="atm-tile big atm-make-tile" aria-hidden="true"><span className="atm-plus">+</span></span>
            <span className="atm-look-name">From a picture…</span>
          </button>
        </div>
      </div>
      <div className="fx-sec">Ready-made</div>
      <div className="atm-grid fb-atm-grid">{built.map((x) => tile(x.id, x.name))}</div>
      {here && c.explicit && (
        <button className="fx-row fb-more" disabled={busy} onClick={() => choose(null)}>
          <span>Go back to the usual look ({nameOf(c.inherited)})</span>
        </button>
      )}
      {err && <p className="fx-none fb-err" role="alert">Could not change the look: {err}</p>}
    </div>
  )
}

/** Production's "make a look from a picture" panel, over the frame while it
 *  is open (drawn in the frame's layer, outside the bar). */
export function LookMaker() {
  const making = useMaking()
  const c = useLookControls()
  useLayer(!making || !c ? null : (
    <Maker
      scope={making}
      canScopeConversation={!!c.conversation}
      scopeName={c.scopeName}
      onPreview={setLookPreview}
      onClose={() => startMaking(null)}
      onUse={async (m) => {
        // A failure here is the panel's to say, so it stays open.
        const id = await c.pictures.save(m.name, m.theme, m.images)
        startMaking(null)
        if (m.scope === 'everywhere' || !c.conversation) await c.chooseBrain(id)
        else await c.choose(id)
        showToast({ text: m.scope === 'everywhere' || !c.conversation ? `All conversations now use ${m.name}` : `${c.scopeName} now uses ${m.name}` })
      }}
    />
  ))
  return null
}
