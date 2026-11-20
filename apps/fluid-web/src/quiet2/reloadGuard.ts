/* A RELOAD OR A CLOSED TAB WARNS WHILE A DECISION IS HALF-WRITTEN (owner, 2026-11-20).
 *
 * A half-written decision -- the reason, falsifier or edited wording of an adoption
 * (./brain/adoptionDraft.ts), or words typed into an answer in Needs you
 * (../experimental/draftKeep.ts) -- is kept in memory for the page, so closing it, pressing
 * Escape, switching conversation or going Back loses nothing, and asks nothing. Only leaving the
 * page itself -- a reload, a closed tab, an address typed over it -- would lose it, and that
 * now asks first, with the browser's own question (as the compact editor's unrecorded record
 * does: ./brain/author/Editor.tsx). Nothing is written to the browser's storage. */
import { anyTyped } from '../experimental/draftKeep'
import { adoptionDraft } from './brain/adoptionDraft'

/** Something written in a decision would be lost by leaving the page. */
export const unsentDecision = (): boolean => adoptionDraft.anyWritten() || anyTyped()

let asked = false
/** The page is being left on purpose, ALREADY ASKED (a Brain switch that asked before it changed
 *  anything): the leaving does not ask again. */
export function leavingAsked() { asked = true }

/** Before the page itself does something that leaves it and cannot be undone by staying (a Brain
 *  switch tells the server first): ask, when a decision is half-written. True: go ahead. */
export function mayLeave(say: (q: string) => boolean = (q) => window.confirm(q)): boolean {
  if (!unsentDecision()) return true
  return say('A decision you are writing has not been sent. Leaving this page loses it. Leave anyway?')
}

/** Ask before the page itself is left while a decision is half-written. Returns its undoing. */
export function guardReload(lost: () => boolean = unsentDecision): () => void {
  const warn = (e: BeforeUnloadEvent) => {
    if (asked || !lost()) return
    e.preventDefault()
    e.returnValue = ''
  }
  window.addEventListener('beforeunload', warn)
  return () => window.removeEventListener('beforeunload', warn)
}
