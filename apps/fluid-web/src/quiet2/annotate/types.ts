/* ANNOTATION IN MARK 2: THE SHARED CONTRACT (annotation round).
 *
 * Three parts, each with its own files:
 *   Selection.tsx   the floating icon-only toolbar over a selected passage,
 *                   and the comment editor (Builder A)
 *   Margin.tsx      a post's existing annotations: margin marks level with
 *                   their passages, the passage wash, the card (Builder B)
 *   SendToAgent.tsx a passage and an instruction sent to an agent as an
 *                   ordinary reply through Fluid's own composer (Builder C)
 *
 * WHAT MENTIS HAS, and nothing else is invented: an ANCHOR is a precise place
 * in one immutable version of a post (`mentis/conversation/anchors.py`), and
 * asserts nothing. Pointed at it: REACTIONS (Fluid's tokens 👍 ❤️ 🤔 ❓), an
 * anchored COMMENT (a record-only reply carrying the anchor), a DEEP DIVE (a
 * conversation opened from it). There are no highlight colours and no private
 * notes in Mentis; a passage that carries anything is shown with a wash.
 *
 * A selection is described by the record's own identities: the post (Turn)
 * id, the exact version shown, and a passage inside one text part as Fluid's
 * commands take it (`fluid/actions.ts` Passage, utf16). */
import type { Passage } from '../../fluid/actions'
import type { Id } from '../../fluid/store'

/** Where the passage is drawn now, in viewport pixels (for placing what opens). */
export interface Box { left: number; top: number; right: number; bottom: number }

export interface Selected {
  /** the post (Turn) the passage is in */
  post: Id
  /** the conversation it is shown in (its home, or one it is included in) */
  conversation: Id
  /** the exact version the passage was read from */
  version: Id
  /** the passage, as Fluid's commands take it */
  passage: Passage
  /** the selected words, exactly as stored */
  excerpt: string
  /** the selection's box now */
  box: Box
  /** the box of the column it is in, so what opens stays inside it */
  bounds: Box
}

/** Opens Send to Agent for a selection (Builder C's component, mounted by the toolbar). */
export interface SendProps {
  sel: Selected
  onClose: () => void
  /** after a send: the post written (to reread its thread) */
  onSent?: (post: Id | null) => void
}
