/* EXPERIMENTAL: the reading half of panel (drawn in ../types/panel.tsx). */
import type { TypeSpec } from './api'
import { blocksOf } from '../../blocks'

export const panelSpec: TypeSpec<string> = {
  type: 'panel',
  summary: 'A composite surface: several marked blocks (and prose) kept together, sent back together.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    arrange: { req: 'optional', choices: ['stack', 'side-by-side'], says: 'stack (default) or side-by-side; the renderer decides widths' },
  },
  nests: true,
  body: 'ordinary Markdown, including marked blocks fenced with ``` inside a ```` panel',
  /* A SECTION OF PROSE is a panel whose first line is its heading: the heading
     names the section, so it can be collapsed to it and found by it. */
  heading(body) {
    const first = blocksOf(body)[0]
    return first?.kind === 'heading' ? first.text : undefined
  },
  parse(body, a, c) {
    /* A panel with a name or a label is a section, which is what it is for. */
    if (!/^ {0,3}(`{3,}|~{3,})\s*\w/m.test(body) && !a.title && !c.shared?.name && !c.shared?.label)
      c.warn('body', 'This panel contains no marked blocks, so it is only a heading around prose.')
    return body
  },
}
