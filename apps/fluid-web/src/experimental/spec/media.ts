/* EXPERIMENTAL: the reading half of image and gallery (drawn in ../types/media.tsx). */
import type { TypeSpec } from './api'
import { csvTable, listOf } from '../util'

export interface Item {
  id: string
  title: string
  caption: string
  alt: string
  ref: string
}

export const URL_RE = /\bhttps?:\/\/\S+/i

/** refs rules, the same as pad's. */
export function checkRefs(a: Record<string, string>, err: (w: string, m: string) => void) {
  if (a.source === 'refs' && !a.refs) err('refs', 'source=refs needs refs=… listing the items it may use.')
  if (a.refs && a.source !== 'refs') err('refs', `refs is only allowed with source=refs (this block says source=${a.source ?? '(not given)'}).`)
}

export const GAL_COLS = ['id', 'title', 'caption', 'ref', 'alt']

export const imageSpec: TypeSpec<string> = {
  type: 'image',
  summary: 'One picture: show an existing item, or ask for a new one. Drawn as a labelled MOCK; nothing is generated or retrieved.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    alt: { req: 'required', says: 'what the picture shows, in words, for anyone who cannot see it' },
    intent: { req: 'required', choices: ['show', 'generate'], says: 'show (an existing item) or generate (ask for a new one)' },
    source: { req: 'optional', choices: ['none', 'conversation', 'refs'], says: 'where the picture may come from (shown, never resolved)' },
    refs: { req: 'optional', says: 'the item(s) meant, when source=refs' },
  },
  body: 'the caption (intent=show) or the description of the picture wanted (intent=generate)',
  parse(body, a, c) {
    checkRefs(a, c.err)
    const text = body.trim()
    if (a.intent === 'show' && (!a.source || a.source === 'none'))
      c.err('intent', 'intent=show means an existing item, so say where it is: source=refs refs=… or source=conversation.')
    if (a.intent === 'generate' && !text)
      c.err('body', 'intent=generate needs a description in the body: what the new picture should show.')
    if (URL_RE.test(text + ' ' + (a.refs ?? '')))
      c.warn('body', 'This block contains a URL. It is shown as text and never loaded; the experiment retrieves nothing.')
    return text
  },
}

export const gallerySpec: TypeSpec<Item[]> = {
  type: 'gallery',
  summary: 'A set of pictures to look through, select from and annotate. Every picture is a labelled MOCK.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    select: { req: 'optional', choices: ['none', 'one', 'many'], says: 'how many a person may pick: none (default), one or many' },
    source: { req: 'optional', choices: ['none', 'conversation', 'refs'], says: 'where the pictures come from (shown, never resolved)' },
    refs: { req: 'optional', says: 'the items, when source=refs' },
  },
  body: 'CSV with a header: id,title then optionally caption, ref, alt; one picture per row',
  parse(body, a, c) {
    checkRefs(a, c.err)
    const t = csvTable(body, c.err, 'pictures')
    if (!t) return []
    const { header, rows } = t
    for (const need of ['id', 'title'])
      if (!header.includes(need)) c.err('header', `The header needs a “${need}” column. The columns are: ${header.join(', ')}.`)
    const odd = header.filter((h) => !GAL_COLS.includes(h))
    if (odd.length) c.warn('header', `Unknown column(s) ${odd.join(', ')} are ignored. Columns are: ${GAL_COLS.join(', ')}.`)
    if (!header.includes('alt')) c.warn('header', 'There is no alt column, so each title is used as its alt text.')
    const col = (r: string[], k: string) => (header.includes(k) ? (r[header.indexOf(k)] ?? '').trim() : '')
    const items = rows.map((r) => ({ id: col(r, 'id'), title: col(r, 'title'), caption: col(r, 'caption'), ref: col(r, 'ref'), alt: col(r, 'alt') || col(r, 'title') }))
    const seen = new Set<string>()
    const listed = listOf(a.refs)
    items.forEach((it, n) => {
      const where = `data line ${n + 2}`
      if (!it.id) c.err(where, 'This picture has no id.')
      else if (seen.has(it.id)) c.err(where, `The id “${it.id}” is used twice; ids must differ.`)
      seen.add(it.id)
      /* A row's ref must be one of refs, or sit under one (album:x/7 is under album:x). */
      if (it.ref && a.source === 'refs' && !listed.some((r) => it.ref === r || it.ref.startsWith(r + '/')))
        c.warn(where, `ref “${it.ref}” is not among (or under) refs=${a.refs}. It is shown as declared.`)
      if (URL_RE.test(it.caption + ' ' + it.ref)) c.warn(where, 'This row contains a URL. It is shown as text and never loaded.')
    })
    return items
  },
}
