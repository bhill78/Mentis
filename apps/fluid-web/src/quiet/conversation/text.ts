import type { Part, Turn } from '../../api'

/** The post's words, exactly as written: every text (and inline reference)
 *  part, joined in order. Nothing is stripped or summarised -- `Prose` reads
 *  the raw Markdown this returns, fences and all. */
export function textOf(turn: Turn): string {
  return turn.parts
    .filter((p: Part) => p.type === 'text' || p.type === 'turn' || p.type === 'topic' ||
      p.type === 'conversation' || p.type === 'acquired' || p.type === 'object')
    .map((p) => p.text ?? '')
    .join('')
}

/** A plain first line of a post, for a collapsed row. Markdown punctuation is
 *  flattened so a heading or a list item reads as a sentence, not as syntax. */
export function excerpt(turn: Turn, max = 160): string {
  const flat = textOf(turn).replace(/[#*_`>|[\]()-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return flat.length > max ? flat.slice(0, max - 1) + '…' : flat
}
