/* EXPERIMENTAL: the reading half of timer (drawn in ../types/timer.tsx).

   A TIMER is a stopwatch in a post, with an optional time box (owner
   decisions T1, T2; plan adm-4fc92741cf96, A1):

     ```timer version=1 name=focus title="Deep work" box=25m break=5m
     ```

   What it counts is not in the Markdown. Each person's starts and stops are
   kept by Mentis as `timer-mark` entries in that person's own response set
   (mentis/conversation/timers.py), and every total is read from them. The
   Markdown says only what the timer is: its name (without one nothing is
   kept, and it is a stopwatch in the reader's tab), its title, and the box
   and break lengths.

   DURATIONS are whole minutes and hours: `25m`, `2h`, `1h30m`, from 1m to
   12h. `break=` needs `box=`. The body is empty; anything in it is ignored,
   with a note. Pure: no React, no DOM, so the server reads the same rules.

   ABOUT (owner addition T8). `about="ent-…, ent-…"` names one or more
   Topics, Conversations or posts the timer's time is spent on. A malformed
   id is an error here; an id the record does not hold is the server's to
   say (a warning: it is shown as unresolved, never dropped). "Time spent on
   X" adds up one person's runs across every timer whose current post names
   X (mentis/conversation/timers.py, `time_spent`).

   AN AGENT IS DIRECTED TO A TIMER BY ITS EXACT REFERENCE, `ent-<post>#<name>`
   (`timerReference`), written by the owner in the request. */
import type { TypeSpec } from './api'

export interface TimerData {
  /** the box length in seconds, or null for a plain stopwatch */
  box: number | null
  /** the break length in seconds, or null for none */
  brk: number | null
  /** what the time is spent on: Topic, Conversation or post ids, in order */
  about: string[]
}

/** A Mentis entry id, as about= takes it. */
export const ENTRY_ID = /^ent-[0-9a-f]{6,}$/

/** How an owner names this timer to an agent: `ent-<post>#<name>`. */
export const timerReference = (post: string, name: string) => `${post}#${name}`

/** about= read into its ids (blank entries left out), with the ones that
    are not entry ids. */
export function aboutOf(text: string | undefined): { ids: string[]; bad: string[] } {
  const ids: string[] = [], bad: string[] = []
  for (const raw of (text ?? '').split(',')) {
    const t = raw.trim()
    if (!t) continue
    if (!ENTRY_ID.test(t)) bad.push(t)
    else if (!ids.includes(t)) ids.push(t)
  }
  return { ids, bad }
}

/** The shortest and longest box or break, in seconds. */
export const MIN_SPAN = 60
export const MAX_SPAN = 12 * 3600

/** `25m`, `2h`, `1h30m` as seconds; null when it is not one of those. */
export function parseSpan(text: string): number | null {
  const m = /^(?:(\d{1,3})h)?(?:(\d{1,4})m)?$/.exec(text.trim())
  if (!m || (m[1] === undefined && m[2] === undefined)) return null
  return Number(m[1] ?? 0) * 3600 + Number(m[2] ?? 0) * 60
}

/** A number of seconds as the attributes write it: `25m`, `2h`, `1h30m`. */
export function spanText(seconds: number): string {
  const h = Math.floor(seconds / 3600), m = Math.round((seconds % 3600) / 60)
  return (h ? `${h}h` : '') + (m || !h ? `${m}m` : '')
}

export const timerSpec: TypeSpec<TimerData> = {
  type: 'timer',
  summary: 'A stopwatch, with an optional time box. Each person\'s runs are kept by Mentis; the Markdown says only what the timer is.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    box: { req: 'optional', says: 'a time box: 25m, 2h or 1h30m (1m to 12h)' },
    break: { req: 'optional', says: 'the break after each box, written like box=; needs box=' },
    about: { req: 'optional', says: 'what the time is spent on: one or more Topic, Conversation or post ids, comma-separated (ent-…, ent-…)' },
  },
  body: 'empty',
  parse(body, a, c) {
    const span = (k: 'box' | 'break'): number | null => {
      if (!(k in a)) return null
      const s = parseSpan(a[k])
      if (s === null) { c.err(k, `${k}=“${a[k]}” is not a length of time. Write minutes or hours: 25m, 2h or 1h30m.`, `Change ${k}= to a length such as 25m.`); return null }
      if (s < MIN_SPAN || s > MAX_SPAN) { c.err(k, `${k}=${a[k]} is outside 1m to 12h.`, `Change ${k}= to a length from 1m to 12h.`); return null }
      return s
    }
    const box = span('box'), brk = span('break')
    if ('break' in a && !('box' in a))
      c.err('break', 'break= needs box=: a break comes after a time box.', 'Add box=… (e.g. box=25m), or remove break=.')
    let about: string[] = []
    if ('about' in a) {
      const got = aboutOf(a.about)
      for (const b of got.bad)
        c.err('about', `about= names “${b}”, which is not a Mentis id. It takes Topic, Conversation or post ids such as ent-3f2a….`, `Replace “${b}” with an existing ent-… id found with the tools, or remove it.`)
      if (!got.bad.length && !got.ids.length)
        c.err('about', 'about= is empty: name at least one Topic, Conversation or post (ent-…).', 'Add an ent-… id, or remove about=.')
      about = got.ids
    }
    if (body.trim())
      c.warn('body', 'A timer has no body; what is written in it is ignored.', 'Remove the text between the fences.')
    if (!c.shared?.name)
      c.warn('name', 'This timer has no usable name=, so its runs are not kept: it is a stopwatch in this browser tab only.',
        'Add name=<a short lowercase name, unique in this post>, e.g. ```timer version=1 name=focus')
    return { box, brk, about }
  },
}
