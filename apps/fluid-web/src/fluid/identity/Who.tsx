/* WHO SOMEBODY IS, DRAWN ONE WAY EVERYWHERE IN FLUID (E2; #568 1.4; FE #4).
 *
 * Production's `Avatar` (bits.tsx) and its rule: the picture somebody chose
 * for the name; else the mark of the runtime it ran on; else its initial on
 * its colour. One read of the people (`/api/participants`, people.ts), never
 * one per post. The name beside it is always `@alias`, whatever the record
 * stored -- the four ways Fluid used to write a name are this one.
 *
 *   show="avatar"  the face alone (its words are its title and label)
 *   show="chip"    face and name in a quiet pill
 *   show="line"    face and name in running text, with optional `meta` after
 *
 * `working` draws a soft live ring round the face from the theme's `--live`,
 * and says "working now" in words too, so colour is never the only signal.
 * Whether somebody is working is the caller's to say (identity/activity.ts:
 * `useIsWorking`, `workingOnPosts`), or, with `live`, the one activity
 * reader's: then the ring follows that name's live execution by itself.
 *
 * `runtime`, when given, is the runtime to mark this face with instead of
 * where the name last ran -- production's `runtime` input, for a post or a
 * run that ran somewhere in particular. `null` says: no mark.
 *
 * Production's component is not imported: it would pull bits.tsx, its
 * references and identity.tsx into the chunk production shares with /fluid
 * and move production's build. The marks are a Fluid-own copy at build
 * (runtimeMarks.tsx, vite.config.ts), and the colour is production's hash, so
 * a name looks alike in Classic and in Fluid. */

import { useState, type ReactNode } from 'react'
import { RUNTIME_LABEL, RuntimeMark, hasMark } from '../../runtimeMarks'
import type { Id } from '../store'
import { at, usePerson, whoColour } from './people'
import { useIsWorking } from './activity'
import './who.css'

export { whoColour } from './people'

const initial = (alias: string | null | undefined) => {
  const s = (alias ?? '').replace(/^@/, '')
  return s ? s[0].toUpperCase() : '?'
}

export interface AvatarProps {
  id: Id | null | undefined
  name: string
  size?: number
  /** a live execution: the soft live ring */
  working?: boolean
  /** the runtime to mark with; omitted, where the name last ran; null, none */
  runtime?: string | null
}

/** The face: picture, else runtime mark, else initial (production's rule). */
export function Avatar({ id, name, size = 24, working = false, runtime }: AvatarProps) {
  const p = usePerson(id)
  const picture = p?.avatar ?? null
  const rt = runtime !== undefined ? runtime : (p?.runtime ?? null)
  const [broken, setBroken] = useState<string | null>(null)
  const shown = picture && broken !== picture ? picture : null
  const mark = hasMark(rt) ? rt! : null
  return (
    <span className={'avatar' + (shown || mark ? ' avatar-drawn' : '') + (working ? ' fwho-live' : '')} aria-hidden="true"
      data-initial={shown || mark ? undefined : initial(name)}
      title={[name.replace(/^@/, ''), mark ? RUNTIME_LABEL[mark] : null, working ? 'working now' : null].filter(Boolean).join(' · ') || undefined}
      style={{ background: shown || mark ? undefined : whoColour(id), width: size, height: size, fontSize: Math.round(size * 0.44), lineHeight: `${size}px` }}>
      {shown ? <img src={`/api/artifacts/${shown}`} alt="" onError={() => setBroken(shown)} />
        : mark ? <RuntimeMark runtime={mark} size={size} />
          : null /* the initial is drawn (who.css), not text: "with @Nadia", never "with N@Nadia" */}
      {shown && mark && size >= 22 && (
        <span className="avatar-badge"><RuntimeMark runtime={mark} size={Math.max(10, Math.round(size * 0.42))} /></span>
      )}
    </span>
  )
}

export type WhoShow = 'avatar' | 'chip' | 'line'

export interface WhoProps extends AvatarProps {
  show?: WhoShow
  /** after the name, in `line` (a time, a number, what they did) */
  meta?: ReactNode
  /** words for hover and assistive technology, beside the name's own */
  title?: string
  className?: string
  /** shows the live ring by itself while this name is working (the one
   *  activity reader); `working` given says it instead */
  live?: boolean
  /** given, it is a button */
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void
}

/** Somebody, as Fluid draws them everywhere. */
export function Who({ id, name, size, working: said, live = false, runtime, show = 'chip', meta, title, className, onClick }: WhoProps) {
  const now = useIsWorking(live && said === undefined ? id : null)
  const working = said ?? now
  const label = at(name)
  /* a caller whose own words say it ("is working") is not said twice */
  const saysWorking = typeof meta === 'string' && /working/i.test(meta)
  const words = [label, working ? 'working now' : null, title].filter(Boolean).join(' · ')
  const face = <Avatar id={id} name={name} size={size ?? (show === 'avatar' ? 24 : show === 'chip' ? 18 : 20)} working={working} runtime={runtime} />
  const body = (
    <>
      {face}
      {show !== 'avatar' && <span className="fwho-name">{label}</span>}
      {show === 'line' && meta != null && meta !== false && <>{' '}<span className="fwho-meta">{meta}</span></>}
      {working && show !== 'avatar' && !saysWorking && <span className="fwho-sr">, working now</span>}
    </>
  )
  const cls = `fwho fwho-${show}` + (working ? ' fwho-working' : '') + (className ? ' ' + className : '')
  return onClick
    ? <button type="button" className={cls} title={words} aria-label={show === 'avatar' ? words : undefined} onClick={onClick}>{body}</button>
    : <span className={cls} title={words} role={show === 'avatar' ? 'img' : undefined} aria-label={show === 'avatar' ? words : undefined}>{body}</span>
}
