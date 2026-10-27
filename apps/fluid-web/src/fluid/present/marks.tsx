/* QUIET MARKS: what an object is and where it came from (B4), and the icons
 * a zone's head shows on hover for what it shows (C4).
 *
 * One small set of drawings, all `currentColor`, so each takes the colour of
 * the text around it in every look and theme, and none adds a colour of its
 * own. What each says is in words too -- in a title and an accessible name
 * -- so the drawing is never the only way to know. */

import type { ReactElement } from 'react'
import { kindOf, type Family, type ObjectIs } from '../../experimental/objectkinds'
import { usePeople } from '../conversation/facts'
import type { PostObjectEntry } from '../store'
import { usePost } from '../workspace/hooks'

const P = (d: string) => <path d={d} fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />

/** A drawing for each family of object, and for the zone's own choices. */
export const GLYPHS: Record<string, ReactElement> = {
  section: P('M2.5 3.5h11v9h-11zM2.5 6.5h11M6.5 6.5v6'),
  media: P('M2.5 3.5h11v9h-11zM2.5 10.5l3-3 2.5 2.5 2-2 3.5 3.5M10.5 6a.5.5 0 1 0 0 .01'),
  video: P('M2.5 3.5h11v9h-11zM6.5 6v4l3.5-2z'),
  file: P('M4 2.5h5l3 3v8H4zM9 2.5v3h3'),
  link: P('M6.5 9.5l3-3M7 4.5l1.2-1.2a2.6 2.6 0 0 1 3.7 3.7L10.7 8.2M9 11.5l-1.2 1.2a2.6 2.6 0 0 1-3.7-3.7L5.3 7.8'),
  text: P('M3 4h10M3 7h10M3 10h7M3 13h5'),
  everything: P('M3 3.5h10M3 6h10M3 8.5h6M2.5 10.5h11v3h-11z'),
  /* things of every kind -- a square, a circle, a triangle -- not a grid,
     which the Cards layout's own drawing beside it already is (C4 repair) */
  objects: P('M2.5 2.5h4.5v4.5h-4.5zM9 4.75a2.25 2.25 0 1 0 4.5 0a2.25 2.25 0 1 0-4.5 0M8 8.5l3.5 5h-7z'),
  kinds: P('M2.5 3.5h11l-4 5v4l-3 1v-5z'),
  /* a form: labels beside the fields they name; what to fill in: lines and a pen */
  form: P('M2.5 3.5h11v9h-11zM4.5 6h2M4.5 9.5h2M8 5.25h4v1.5H8zM8 8.75h4v1.5H8z'),
  fillable: P('M2.5 4.5h8M2.5 8h5M2.5 11.5h3.5M8.5 13.5v-1.5l4-4 1.5 1.5-4 4z'),
  'needs-you': P('M8 2.5a4 4 0 0 1 4 4v3l1.5 2h-11L4 9.5v-3a4 4 0 0 1 4-4zM6.5 13.5a1.5 1.5 0 0 0 3 0'),
  kept: P('M8 2.5l5 5.5-5 5.5-5-5.5z'),
  focus: P('M3 6V3h3M10 3h3v3M13 10v3h-3M6 13H3v-3M6 6h4v4H6z'),
}

export function Glyph({ name, className }: { name: string; className?: string }) {
  return <svg className={'pz-glyphsvg' + (className ? ' ' + className : '')} viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">{GLYPHS[name] ?? GLYPHS.objects}</svg>
}

const glyphOf = (is: ObjectIs): string => (is.word === 'video' ? 'video' : (is.family as Family))

/** Is this participant an agent? One that has run, or names a runtime. */
function useIsAgent(author: string | undefined): boolean | null {
  const people = usePeople(!!author)
  if (!author || !people.data) return null
  const p = people.data.find((x) => x.participant === author)
  return p ? !!(p.runtime || p.default_runtime) : null
}

/** Where an object came from, in a few words. */
export function sourceWords(o: PostObjectEntry, agent: boolean | null): string {
  const is = kindOf(o)
  switch (is.source) {
    case 'returned': return 'returned by a run'
    case 'attachment': return agent ? 'attached by an agent' : 'attachment'
    case 'link': return o.link?.domain ?? 'link'
    case 'figure': return agent ? 'placed in an agent reply' : 'placed in a post'
    case 'text': return agent ? 'agent reply' : 'post'
    default: return agent ? 'in an agent reply' : 'in a post'
  }
}

/** THE QUIET SOURCE LINE (B4): "▦ chart · in an agent reply", beside the
 *  caption that traces it to its post. */
/** `compact`: its drawing only, the words in its title and accessible name
 *  (a detail's head, where the title needs the room). */
export function SourceMark({ o, compact }: { o: PostObjectEntry; compact?: boolean }) {
  const post = usePost(o.post)
  const agent = useIsAgent(post?.author)
  const is = kindOf(o)
  const where = sourceWords(o, agent)
  const said = `${is.word} · ${where}`
  return (
    <span className="pz-src" data-source={is.source} data-family={is.family} data-agent={agent ? '' : undefined} title={said} aria-label={said}>
      <Glyph name={glyphOf(is)} />
      {!compact && <span className="pz-srcword">{is.word}</span>}
      {!compact && <span className="pz-srcwhere">{where}</span>}
    </span>
  )
}
