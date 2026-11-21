/* WHICH VIEWER A FILE OPENS IN -- DECIDED ONCE (navigation review
 * adm-d9152e0643d7, B4).
 *
 * THE DEFECT THIS ANSWERS. `Post.tsx` sent a PDF to pdf.js and a picture to
 * the collection viewer; the dock wrapped EVERY item as `{ kind: 'file' }` and
 * hardcoded the Brain as its source. So the same PDF opened as a program from
 * a post and as a download offer from Needs you, a picture opened out of its
 * post's collection with no siblings, and a result chooser would have been a
 * third opinion. One dispatcher now answers for every path.
 *
 * THE SERVER'S OWN WORD DECIDES, NOT THE FILE NAME. `treatment.view`
 * (`mentis/artifacts.py` `treatment`) is read from the bytes themselves; where
 * it is there, it is the answer, and a file called `.pdf` that the server read
 * as HTML does not reach the PDF program. The claim and the name decide only
 * where NO treatment was read -- which is the ordinary case for a conversation
 * read, because a Turn read does not carry one (`quiet/media/view.ts` says
 * why). That is the one fallback, and it is the behaviour this build already
 * had; nothing is promoted on a claim that was not promoted before.
 *
 * Pure: an item in, a `Viewable` out. `tests/quiet2_result_viewable_unit.ts`
 * checks every row without a browser. */
import type { ViewerItem } from '../../quiet/media/view'
import type { Viewable, ViewImage } from './types'

/** Whether these bytes are a PDF, for the purpose of choosing a renderer.
 *
 *  A PDF's verified treatment is `pdf`, which `viewKindOf` maps to `file`
 *  (the server serves one as an attachment, and a PDF viewer is a program):
 *  that mapping is what loses the fact here, so the item's own `treatment`
 *  carries the server's word through. Where the server read something else,
 *  that is the answer and the name is not consulted. */
export function isPdf(i: ViewerItem): boolean {
  const treated = (i.treatment ?? '').trim().toLowerCase()
  if (treated) return treated === 'pdf'
  return /^application\/(?:x-)?pdf$/.test((i.mediaType || '').split(';')[0].trim().toLowerCase()) || /\.pdf$/i.test(i.name || '')
}

/** WHAT VIEWER THIS FILE OPENS IN, wherever it was pressed: a post's
 *  attachment, the Needs you dock, a Brain record, the result chooser.
 *
 *  `siblings` are the pictures shown beside it (a post's own collection), so
 *  a picture opens IN its collection with itself selected -- the behaviour
 *  `Post.tsx` has, now available to every other path. Without them a picture
 *  opens as a collection of one, which is what the dock and the Brain record
 *  already do. */
export function viewableOfItem(i: ViewerItem, siblings?: readonly ViewImage[]): Viewable {
  if (isPdf(i)) return { kind: 'pdf', url: i.url, name: i.name, size: i.size }
  if (i.kind === 'image') {
    const all = siblings ?? []
    const at = all.findIndex((x) => x.url === i.url)
    return at >= 0 ? { kind: 'gallery', images: [...all], start: at } : { kind: 'gallery', images: [{ url: i.url, name: i.name, alt: i.alt }], start: 0 }
  }
  /* Markdown, text, HTML, film, sound, and anything else offered as a
     download: the existing viewer body, with its existing refusals. No new
     renderer, and no claim that HTML runs. */
  return { kind: 'file', item: i }
}
