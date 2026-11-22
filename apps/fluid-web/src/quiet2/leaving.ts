/* LEAVING A PAGE THAT HOLDS UNFINISHED WORK.
 *
 * THE DEFECT THIS ANSWERS (owner, 2026-11-17): clicking a conversation from
 * Manage Sources could do nothing at all. A reader must never be held in a
 * management view: a conversation press always begins going there.
 *
 * So the page never refuses. It either goes at once, or it ASKS -- Stay, or
 * discard and switch -- and the asking happens only where something would
 * actually be lost. The rule, in the owner's own words:
 *
 *   - nothing unsaved would be lost  -> switch immediately
 *   - an unfinished setup with unsaved changes -> Stay / Discard changes and switch
 *   - a completed but unapplied preview counts as unfinished setup
 *   - an ingestion or refresh running -> say whether it continues on its own
 *     or would be interrupted; never cancel it silently
 *   - merely viewing a source, a file, a Brain record or a management page
 *     never blocks anything
 *
 * A page that can hold unfinished work says so with `useUnfinished`; nothing
 * else has to know what pages exist. `leaving` is the whole decision, apart
 * from React and the browser, so it is checkable (`tests/quiet_nav_unit.ts`).
 *
 * WHERE THE WORK IS DECIDES WHAT TAKES IT AWAY (independent review
 * ent-d960d458078c, W1). A form in the centre reading column goes with a
 * conversation press and with the browser's own Back; a form open BESIDE the
 * conversation does not -- it stays open while the conversation changes, so
 * holding that press up would be a refusal with nothing behind it. But its own
 * column's close DOES take it away, and that was losing a half-written record
 * without a word. So each page says where it is (`LeavingPlace`, the column it
 * is drawn in) and each way out asks about its own place only. */
import { createContext, useContext, useEffect, useRef } from 'react'

/** What a running operation is, to somebody about to leave it. */
export interface Running {
  /** what it is doing, in the reader's words ("Refreshing Notes") */
  what: string
  /** true where leaving loses the ANSWER (the run itself is never cancelled) */
  interrupted?: boolean
  /** where its answer goes when the reader does not stay for it ("The source
   *  is added to the Brain either way"). A run that LANDS somewhere says so:
   *  "it carries on" alone leaves the reader wondering what becomes of it.
   *  Only for a run that is not interrupted. */
  lands?: string
}

/** What a page says of itself when the reader is about to leave it. */
export interface Standing {
  /** the page, in the reader's own words ("Add a source", "Notes") */
  what: string
  /** something typed or chosen here that nothing has recorded */
  dirty?: boolean
  /** the one line saying what would be lost, where the page's own words are
   *  plainer than the general ones (a Brain record is not "filled in": it is
   *  written, and leaving means nothing of it reaches the record) */
  lost?: string
  /** a preview in hand that has not been applied */
  preview?: boolean
  /** an operation running now */
  run?: Running | null
}

/** The question put to the reader before leaving. */
export interface Ask {
  title: string
  lines: string[]
  stay: string
  leave: string
}

export interface Leaving {
  /** asked before leaving; null where leaving happens at once */
  ask: Ask | null
  /** said after leaving, where something carries on without the reader */
  note: string | null
}

export const STAY = 'Stay'
export const DISCARD = 'Discard changes and switch'
export const ANYWAY = 'Switch anyway'

/** A run that is not interrupted, said in the one way it is always true:
 *  it is not stopped, and -- where the page knows it -- where it lands. */
const carriesOn = (run: Running, either: boolean) =>
  `${run.what} carries on${either ? ' either way' : ''}. Leaving does not stop it.${run.lands ? ` ${run.lands}` : ''}`

/** What leaving `s` should do: ask first, or go and say what carries on. */
export function leaving(s: Standing | null | undefined): Leaving {
  if (!s) return { ask: null, note: null }
  const run = s.run ?? null
  const loses = !!s.dirty || !!s.preview
  const stranded = !!run?.interrupted
  /* MERELY VIEWING, or watching something the server is doing on its own:
     nothing is lost, so nothing is asked. A run that carries on is still
     said, so leaving never looks like cancelling it. */
  if (!loses && !stranded) return { ask: null, note: run ? carriesOn(run, false) : null }

  const lines: string[] = []
  if (s.dirty) lines.push(s.lost ?? 'What you have filled in here is not saved anywhere.')
  if (s.preview) lines.push('The preview you have in hand has not been applied: nothing has been added to the Brain.')
  if (stranded) lines.push(`${run!.what} is still running. Leaving does not cancel it, but its answer would land nowhere and you would ask for it again.`)
  else if (run) lines.push(carriesOn(run, true))
  return {
    ask: { title: `Leave ${s.what} unfinished?`, lines, stay: STAY, leave: loses ? DISCARD : ANYWAY },
    note: null,
  }
}

/** Ask all displaced places before ONE commit. Accepting an early question
 * changes no content; Stay on any later one abandons the whole transition. */
export function guardPlaces(places: Place[], on: {
  standing(place: Place): Standing | null;
  ask(question: Ask, proceed: () => void, stay: () => void): void;
  note(words: string): void; commit(): void; stay(): void;
}) {
  const unique = [...new Set(places)]
  const next = (i: number) => {
    if (i === unique.length) { on.commit(); return }
    const was = leaving(on.standing(unique[i]))
    if (was.ask) { on.ask(was.ask, () => next(i + 1), on.stay); return }
    if (was.note) on.note(was.note)
    next(i + 1)
  }
  next(0)
}

/** WHAT UNSAVED GOVERNANCE AUTHORING LOSES. A Brain record being written,
 *  revised, challenged, established or decided is not a form being filled in:
 *  until the act is recorded, nothing of it is in the Brain at all. Every
 *  record form says it the same way. */
export const LOST_RECORD = 'What you have written here has not been recorded: nothing of it is in the Brain.'

/** A record form, holding words nothing has recorded. `what` is the form in
 *  the reader's own words ("this new rule", "this challenge"). */
export const authoring = (what: string): Standing => ({ what, dirty: true, lost: LOST_RECORD })

/** What a record form tells the column it is drawn in: what it holds, or
 *  nothing where it holds nothing. WHICH column that is -- and so which way
 *  out asks about it -- is `LeavingPlace`, not the form's own business. */
export const written = (what: string, dirty: boolean): Standing | null =>
  (dirty ? authoring(what) : null)

/* -- which pages hold unfinished work, while they are on the page ---------- */

/** The column a page is drawn in: the centre reading column, or a working
 *  surface beside the conversation (`s1`, `s2`). */
export type Place = string
/** the main reading area, which a conversation press and Back take away */
export const CENTRE = 'centre'

/** Where the page being drawn is. A working surface puts its own column here
 *  (Surface.tsx); everything else is the centre reading column. */
export const LeavingPlace = createContext<Place>(CENTRE)

type Teller = () => Standing | null

const telling = new Map<Teller, Place>()

/** A page in `place` holds unfinished work until the answer is called. The
 *  registry itself, apart from React, so what the hook does is what a check
 *  can do (`tests/quiet_nav_unit.ts`). */
export function tell(get: Teller, place: Place = CENTRE): () => void {
  telling.set(get, place)
  return () => { telling.delete(get) }
}

/** This page holds unfinished work while it is mounted; `get` is asked at the
 *  moment of leaving, so it always reads what is there now. It is heard by
 *  whatever would take its own column away, and by nothing else. */
export function useUnfinished(get: () => Standing | null) {
  const place = useContext(LeavingPlace)
  const now = useRef(get)
  now.current = get
  useEffect(() => tell(() => now.current(), place), [place])
}

/** What is unfinished in `place` now, or null where nothing is. */
export function unfinished(place: Place = CENTRE): Standing | null {
  for (const [teller, where] of telling) {
    if (where !== place) continue
    const s = teller()
    if (s && (s.dirty || s.preview || s.run)) return s
  }
  return null
}

/** Only for a check that has no React: forget every page. */
export function forgetUnfinished() { telling.clear() }
