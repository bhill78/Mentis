/* WHAT NEEDS YOU, ITEM BY ITEM (forms build P11), shared by Fluid's bell and
 * Classic's counter.
 *
 * ONE ITEM PER FORM, not per question and not per conversation
 * (`GET /fluid/api/needs-you/items`, home.needs_you_items): the questions of
 * one decision form are one item, a decision asked as its own post is one,
 * a block waiting for the owner's input is one until Done, and any other ask
 * is one. The count is said by kind: "2 decisions, 1 input".
 *
 * AN ENTRY OPENS THE ASKING POST AT THE FORM. Whoever opens the post (Fluid
 * by address, Classic by its Turn) then calls `landOn`, which waits for the
 * form to be drawn there and scrolls it into view. The form is found by what
 * every view already marks it with: a decision form's `data-decision-form`,
 * a kept block's `data-block-key`. */

export type ItemKind = 'decision' | 'input' | 'request'

export interface NeedsItem {
  key: string
  kind: ItemKind
  expects: string | null
  form: string | null
  /** the asks this item answers: a form's questions, or the one ask */
  asks: string[]
  question: string | null
  /** an input's block: its name=, part, type and response set */
  block: { set: string; block: string; part: number; type: string | null } | null
  /** where on the post it is drawn: `decision-form:<key>` or `block:<name>` */
  anchor: string | null
  post: string | null
  post_number: number | null
  lead: string | null
  conversation: string | null
  conversation_name: string | null
  asked_by: string
  asked_by_name: string
  because: string | null
  at: number | null
}

export interface NeedsItems {
  items: NeedsItem[]
  counts: { decision: number; input: number; request: number; total: number } | null
  words: string | null
  owner: string | null
  unknown?: boolean
  why?: string
}

export const ITEMS_PATH = '/fluid/api/needs-you/items'

const WORDS: Record<ItemKind, [string, string]> = {
  decision: ['decision', 'decisions'],
  input: ['input', 'inputs'],
  request: ['request', 'requests'],
}

/** "2 decisions, 1 input"; '' for nothing. The server says the same (`words`). */
export function itemWords(counts: NeedsItems['counts']): string {
  if (!counts) return ''
  return (['decision', 'input', 'request'] as ItemKind[])
    .filter((k) => counts[k] > 0)
    .map((k) => `${counts[k]} ${WORDS[k][counts[k] === 1 ? 0 : 1]}`)
    .join(', ')
}

/** What an entry is called: its kind, then its question or the asking post's first line. */
export function itemLine(it: NeedsItem): { kind: string; what: string } {
  const kind = it.kind === 'decision' ? (it.asks.length > 1 ? `Decision · ${it.asks.length} questions` : 'Decision')
    : it.kind === 'input' ? `Input · ${it.block?.block ?? 'a block'}` : 'Request'
  const what = it.question || it.lead || it.because || `${it.asked_by_name.replace(/^@?/, '@')} asks you`
  return { kind, what }
}

export async function readItems(): Promise<NeedsItems> {
  const res = await fetch(ITEMS_PATH, { headers: { 'X-Mentis-Client': '1' } })
  const body = await res.json().catch(() => null)
  if (!res.ok || !body) throw new Error(body?.error ?? (res.statusText || String(res.status)))
  return body as NeedsItems
}

/* ---------------------------------------------------------------- landing */

/** The element an item is drawn as on its post, if it is on the page. A
 *  copy in a Needs You zone or the bell's own sheet is not the post's. */
export function formElement(it: Pick<NeedsItem, 'kind' | 'key' | 'post' | 'block'>, root: ParentNode = document): HTMLElement | null {
  const away = (el: Element) => !!el.closest('.nyc-list, .fb-sheet, .asks-pop, .ask-card')
  let found: Element[] = []
  if (it.kind === 'decision') {
    found = [...root.querySelectorAll(`[data-decision-form="${CSS.escape(it.key)}"]`)]
  } else if (it.kind === 'input' && it.block) {
    const tail = `/@${it.block.block}:`
    const all = [...root.querySelectorAll<HTMLElement>('[data-block-key]')].filter((el) => (el.dataset.blockKey ?? '').includes(tail))
    const exact = it.post ? all.filter((el) => (el.dataset.blockKey ?? '').startsWith(`Turn ${it.post}`)) : []
    found = exact.length ? exact : all
  }
  return (found.find((el) => !away(el)) as HTMLElement | undefined) ?? null
}

let landing = 0

/** Wait (up to `ms`) for the item's form to be drawn on its post, then
 *  scroll it into view and mark it `data-landed`. Resolves whether it landed. */
export function landOn(it: Pick<NeedsItem, 'kind' | 'key' | 'post' | 'block'>, ms = 10000): Promise<boolean> {
  const mine = ++landing
  const until = Date.now() + ms
  return new Promise((done) => {
    const look = () => {
      if (mine !== landing) return done(false)
      const el = formElement(it)
      if (el) {
        document.querySelectorAll('[data-landed]').forEach((x) => x.removeAttribute('data-landed'))
        el.setAttribute('data-landed', '')
        el.scrollIntoView({ block: 'center', behavior: 'auto' })
        /* A second look once the page has settled: posts drawn above it
           after the first scroll move it. */
        window.setTimeout(() => { if (mine === landing && el.isConnected) el.scrollIntoView({ block: 'center', behavior: 'auto' }) }, 400)
        return done(true)
      }
      if (Date.now() > until) return done(false)
      window.setTimeout(look, 120)
    }
    look()
  })
}
