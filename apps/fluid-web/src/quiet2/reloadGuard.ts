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

/** Ask before the page itself is left while a decision is half-written. Returns its undoing. */
export function guardReload(lost: () => boolean = unsentDecision): () => void {
  const warn = (e: BeforeUnloadEvent) => {
    if (!lost()) return
    e.preventDefault()
    e.returnValue = ''
  }
  window.addEventListener('beforeunload', warn)
  return () => window.removeEventListener('beforeunload', warn)
}
