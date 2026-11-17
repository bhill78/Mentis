/* WHAT A RECORD FORM IN HAND IS HOLDING, apart from React.
 *
 * THE DEFECT THIS ANSWERS (owner, ent-406244084c3e): a half-written Brain
 * record was lost without a word. A surface the reader can navigate away from
 * asks before leaving one, and to ask it has to know two things: whether
 * anything has been written here at all, and what to call it. Both are here,
 * apart from React and from any surface, so they are checkable
 * (`tests/quiet_nav_unit.ts`) and so no surface invents its own answer.
 *
 * OPENING A FORM HOLDS NOTHING. Only what was typed into it does, which is
 * why "Delete…" opened and left alone never stops anybody: the question is
 * for work that would be lost, not for a panel that happens to be open. */

/** WHAT AN ACT IN HAND IS CALLED, to somebody about to leave it. Used only in
 *  the question put before leaving ("Leave this revision unfinished?"), so
 *  each is a noun phrase and not a button's words. */
export const ACT_WORDS: Record<string, string> = {
  edit: 'this revision', place: 'this placement', unplace: 'this change',
  replace: 'this replacement', delete: 'this deletion',
  establish: 'this establishment', dispute: 'this challenge', revise: 'this revision',
  supersede: 'this replacement', 'set-aside': 'this answer', respond: 'this answer',
  write: 'this new instruction',
}

/** The act whose words would be lost by leaving now, or null where nothing
 *  has been written. The inline form is asked first: it is the one the reader
 *  is looking at when both are somehow in play. */
export function actUnsaved(
  form: { open: string | null; typed: boolean },
  dialog: { act: string | null; typed: boolean },
): string | null {
  if (form.open && form.typed) return ACT_WORDS[form.open] ?? 'this change'
  if (dialog.act && dialog.typed) return ACT_WORDS[dialog.act] ?? 'this act'
  return null
}

/** Whether a record BEING WRITTEN holds anything nothing has recorded: words
 *  typed into it, a supporting reference the reader changed, or -- the case
 *  that is easiest to lose and worst to lose -- a record already created
 *  whose remaining acts (its citation, its establishment, its placement) have
 *  not completed. A reference the door itself supplied is not something the
 *  reader typed, so it is compared with what the door gave. */
export function writingUnsaved(x: { created: boolean; typed: string[]; basis: string; basisGiven: string }): boolean {
  return x.created || x.typed.some((v) => v.trim() !== '') || x.basis.trim() !== x.basisGiven
}
