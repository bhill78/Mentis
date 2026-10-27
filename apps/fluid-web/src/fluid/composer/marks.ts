/* FORMATTING (#187 #8): production's marks and their shortcuts, one list, so
 * the button grid and the keystroke can never disagree about what bold is.
 * The edits themselves are production's (`composer/markdown.ts`). */

import { makeLink, toggleCode, toggleLinePrefix, toggleWrap, type Edit } from '../../composer/markdown'

export interface FormatMark { key: string; glyph: string; label: string; chord: string; apply: (t: string, s: number, e: number) => Edit }

export const MARKS: FormatMark[] = [
  { key: 'b', glyph: 'B', label: 'Bold', chord: 'ctrl B', apply: (t, s, e) => toggleWrap(t, s, e, '**') },
  { key: 'i', glyph: 'I', label: 'Italic', chord: 'ctrl I', apply: (t, s, e) => toggleWrap(t, s, e, '_') },
  { key: 'e', glyph: '<>', label: 'Code', chord: 'ctrl E', apply: (t, s, e) => toggleCode(t, s, e) },
  { key: 'k', glyph: '🔗', label: 'Link', chord: 'ctrl K', apply: (t, s, e) => makeLink(t, s, e) },
  { key: '8', glyph: '•', label: 'Bulleted list', chord: 'ctrl 8', apply: (t, s, e) => toggleLinePrefix(t, s, e, '- ') },
  { key: '7', glyph: '1.', label: 'Numbered list', chord: 'ctrl 7', apply: (t, s, e) => toggleLinePrefix(t, s, e, '1. ') },
  { key: '.', glyph: '❝', label: 'Quote', chord: 'ctrl .', apply: (t, s, e) => toggleLinePrefix(t, s, e, '> ') },
]
