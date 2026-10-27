import type React from 'react'
import { useState } from 'react'
import { CITE_IN_TEXT, isRefId, parseExtractedCite, REF_IN_TEXT } from './refid'
import AcquiredChip from './surfaces/sources/AcquiredChip'
import CiteChip from './surfaces/sources/CiteChip'
import { TurnQuote } from './turnQuote'
import { Ref } from './refs'
import { nameOf, RenderableBlock, type RBlock } from './experimental/renderable'
import { keyOf, namesFor, type Names } from './experimental/objects'
import { blocksOf, placedRef, type Block } from './blocks'

export { blocksAt, blocksOf, placedRef, type Block, type PlacedBlock } from './blocks'

/* ------------------------------------------------------------------------ *
 * WHAT AN AGENT ACTUALLY WROTE, RENDERED AS THEY WROTE IT.
 *
 * THE PROBLEM THIS FIXES. Turn bodies were rendered as a single paragraph
 * with `white-space: normal`, which is correct for a sentence and destroys
 * anything longer. A realistic agent report — headings, a results table, a
 * code block, a blockquote of what it is NOT claiming — arrived as one
 * unbroken wall with `##` and `|---|` inline. The sparse fixture hid this
 * completely, because every turn in it was one or two plain sentences.
 *
 * WHY NOT A MARKDOWN LIBRARY. `MarkedText` matches recorded media spans
 * against the turn's RAW TEXT by exact `indexOf` — the span is a durable
 * string an agent wrote into the record, and it is never reworded or guessed.
 * A third-party renderer rewrites the text into its own node tree and that
 * matching cannot survive it. So this is a small, bounded reader for the
 * subset agents actually write, and it hands each paragraph's raw text back
 * to the caller so span-marking still works exactly as before.
 *
 * IT IS A READER, NOT AN INTERPRETER. Nothing here infers meaning, rewrites
 * content or drops anything it does not understand: a line it cannot classify
 * is a paragraph, and the characters are the ones the author typed.
 * ------------------------------------------------------------------------ */

/** True where a body needs more than one paragraph to be read honestly. */
export const isStructured = (src: string): boolean => {
  const b = blocksOf(src)
  return b.length > 1 || (b[0] !== undefined && b[0].kind !== 'para')
}

/* ------------------------------------------------------------------------ *
 * INLINE. Bold, italic, inline code and links — the four an agent uses in a
 * sentence. Everything else is left exactly as typed.
 * ------------------------------------------------------------------------ */

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(!\[[^\]\n]*\]\(adm-[0-9a-f]{8,}\))|(\[[^\]]+\]\([^)\s]+\))|(\bhttps?:\/\/[^\s<>()]+)/g

/* A REFERENCE AN AGENT TYPED IS A WAY IN. "It is yours to establish:
   `ent-de912abf1e41`" used to be inert text, and the owner had no ordinary
   path to the thing they were being asked about. Each reference becomes the
   one inspectable reference component, which says what it is on hover and
   opens it on click; what it IS is answered by the record, not by this text.
   A reference written as inline code is the same reference. */
/* A CITATION OF EXTRACTED TEXT IS ONE CHIP (Sources C, C4), matched before
   the bare `adm-` inside it would be. Its quote, for when the citation
   cannot be reproduced here, is found in the whole Turn (`turnQuote`,
   provided by `Prose`); inside a run of text with no Turn around it, the
   last quoted passage before it in that run. */
const CITE_OR_REF = new RegExp(`${CITE_IN_TEXT.source}|${REF_IN_TEXT.source}`, 'g')
const QUOTED = /[“"]([^”"]{3,})[”"]/g

function quoteBefore(src: string, i: number): string | undefined {
  const all = [...src.slice(0, i).matchAll(QUOTED)]
  return all.length ? all[all.length - 1][1] : undefined
}

/** A blockquote's words as the passage quoted: any citation in it, inline
 *  code marks around one, and the dash or bracket that introduced it taken
 *  out; whitespace runs read as one space. Nothing else is changed. */
function passage(text: string): string | undefined {
  const s = text
    .replace(new RegExp('`?' + CITE_IN_TEXT.source + '`?', 'g'), ' ')
    .replace(/[\s—–-]*[([]?\s*[)\]]?\s*$/u, '')
    .replace(/\s+/g, ' ')
    .trim()
  return s.length >= 3 ? s : undefined
}

/** THE PASSAGE A TURN QUOTED WITH A CITATION, read from the Turn's own text
 *  -- never guessed beyond it:
 *
 *  1. a passage in quotation marks before it in the same paragraph, list
 *     item or cell (`"…" adm-…`);
 *  2. otherwise, when it sits inside a Markdown blockquote, that
 *     blockquote's words (`> … adm-…`);
 *  3. otherwise the nearest blockquote before it under the same heading
 *     that carries no citation of its own (`> …` then `— adm-…`), which is
 *     how a model quotes.
 *
 *  Undefined when there is none: the chip then says the quote is the Turn's
 *  own text beside it. */
export function turnQuote(src: string, cite: string): string | undefined {
  const blocks = blocksOf(src)
  const at = blocks.findIndex((b) => readable(b).some((t) => t.includes(cite)))
  if (at < 0) return undefined
  const b = blocks[at]
  for (const t of readable(b)) {
    const i = t.indexOf(cite)
    if (i < 0) continue
    const q = quoteBefore(t, i)
    if (q !== undefined) return q
    break
  }
  if (b.kind === 'quote') {
    const q = passage(b.text)
    if (q !== undefined) return q
  }
  for (let j = at - 1; j >= 0; j--) {
    const p = blocks[j]
    if (p.kind === 'heading') break
    if (p.kind !== 'quote') continue
    CITE_IN_TEXT.lastIndex = 0
    if (CITE_IN_TEXT.test(p.text)) {
      CITE_IN_TEXT.lastIndex = 0
      break
    }
    const q = passage(p.text)
    if (q !== undefined) return q
  }
  return undefined
}

function plain(src: string, key: string, out: React.ReactNode[]) {
  let at = 0
  let n = 0
  for (const m of src.matchAll(CITE_OR_REF)) {
    const i = m.index ?? 0
    if (i > at) out.push(src.slice(at, i))
    if (parseExtractedCite(m[0])) {
      out.push(
        <span key={`${key}-c${n++}`} data-src-text={m[0]}>
          <CiteChip cite={m[0]} quote={quoteBefore(src, i)} />
        </span>,
      )
      at = i + m[0].length
      continue
    }
    /* `data-src-text`: what this stands for in the stored text, so a
       selection over it can be placed there (surfaces/passage.ts). */
    out.push(
      <span key={`${key}-r${n++}`} data-src-text={m[0]}>
        <Ref id={m[0]} n={m[0].length} />
      </span>,
    )
    at = i + m[0].length
  }
  if (at < src.length) out.push(src.slice(at))
}

/* WHERE A LINK IN A BODY IS ALLOWED TO GO, DECIDED HERE AND NOT BY REACT.
 *
 * A Markdown link's destination went into `href` as written. React happens
 * to refuse `javascript:`, but that is a library's current behaviour, not a
 * boundary this reader owns -- and it let `data:`, `vbscript:`, `file:`,
 * `blob:`, `//elsewhere` and same-origin `/api/...` through unchanged, all
 * measured against the real `inline`. So the destination is parsed as a URL
 * with NO base: anything relative, protocol-relative or same-origin fails
 * to parse and is refused. What parses must be one of three schemes. The URL
 * parser is the one the browser will use on the same string, so case,
 * surrounding whitespace and control characters are read the way the
 * browser would read them, not the way a regex would guess.
 *
 * THE HREF IS THE PARSED URL, NOT THE STRING THAT WAS CHECKED. Found by
 * review: `http:/api/x` parses without a base as `http://api/x`, but the
 * browser resolves the raw string against the page, where a same-scheme URL
 * with no `//` is relative -- `http://127.0.0.1:8760/api/x`. Handing over the
 * serialised absolute URL means the link goes where the check said it did,
 * whatever the page's own address. */
const LINK_SCHEMES = new Set(['http:', 'https:', 'mailto:'])

/** The absolute URL a link may point to, or null. */
export function safeHref(raw: string): string | null {
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    return null
  }
  return LINK_SCHEMES.has(u.protocol) ? u.href : null
}

/* A REFUSED LINK IS STILL WHAT THE AUTHOR WROTE. It is shown as its label
   and its destination, as text nobody can click, so nothing written is
   lost and the reader can see why it is not a link. */
function link(label: string, dest: string, k: string): React.ReactNode {
  const href = safeHref(dest)
  if (href !== null)
    return (
      <a key={k} href={href} target="_blank" rel="noreferrer noopener">
        {label}
      </a>
    )
  return (
    <span key={k} className="pr-link-refused" title="not a link: only http, https and mailto addresses are followed">
      {label === dest ? dest : `${label} (${dest})`}
    </span>
  )
}

export function inline(src: string, key = 'i'): React.ReactNode[] {
  const out: React.ReactNode[] = []
  let at = 0
  let n = 0
  for (const m of src.matchAll(INLINE)) {
    const i = m.index ?? 0
    if (i > at) plain(src.slice(at, i), `${key}-p${n}`, out)
    const [tok] = m
    const k = `${key}-${n++}`
    if (tok.startsWith('`') && parseExtractedCite(tok.slice(1, -1)))
      out.push(
        <span key={k} data-src-text={tok}>
          <CiteChip cite={tok.slice(1, -1)} quote={quoteBefore(src, i)} />
        </span>,
      )
    else if (tok.startsWith('`') && isRefId(tok.slice(1, -1)))
      out.push(
        <span key={k} data-src-text={tok}>
          <Ref id={tok.slice(1, -1)} n={tok.length} className="ref-code" />
        </span>,
      )
    else if (tok.startsWith('`')) out.push(<code key={k}>{tok.slice(1, -1)}</code>)
    /* Emphasis is read INSIDE as well. `**[a title](url)**` is how an agent
       writes a bold link, and taking the inside as plain text printed the
       brackets and the URL instead of the link. */
    else if (tok.startsWith('**')) out.push(<strong key={k}>{inline(tok.slice(2, -2), k)}</strong>)
    else if (tok.startsWith('*')) out.push(<em key={k}>{inline(tok.slice(1, -1), k)}</em>)
    /* AN IMAGE WHOSE DESTINATION IS A HELD ARTIFACT, `![alt](adm-…)`, is that
       reference with its alt as the words. It used to be read as a link to
       nowhere and printed as `!alt (adm-…)`; the reference resolves to a
       picture or a chip by what the record says, never by this syntax. */
    else if (tok.startsWith('![')) {
      const cut = tok.indexOf('](')
      out.push(
        <span key={k} data-src-text={tok}>
          <Ref id={tok.slice(cut + 2, -1)} label={tok.slice(2, cut) || undefined} />
        </span>,
      )
    } else if (tok.startsWith('[')) {
      const cut = tok.indexOf('](')
      out.push(link(tok.slice(1, cut), tok.slice(cut + 2, -1), k))
    } else out.push(link(tok, tok, k))
    at = i + tok.length
  }
  if (at < src.length) plain(src.slice(at), `${key}-p${n}`, out)
  return out
}

/* ------------------------------------------------------------------------ *
 * AN HTML BLOCK CAN BE LOOKED AT, NOT ONLY READ.
 *
 * Somebody who asks for a mockup wants to see it, and copying it out into a
 * file to do that is a chore. So a fence the author labelled `html` offers a
 * preview beside its source. It is still the source first: the characters
 * the author wrote are what the record holds, and the preview is only a way
 * of looking at them, opened on request.
 *
 * WHAT THE PREVIEW IS ACTUALLY ALLOWED TO DO, AND WHICH CONTROL DOES IT.
 * There are two controls and they do different jobs, so neither is credited
 * with the other's work. Each line below was measured: a request-logging
 * server, every subresource, link and form in the document aimed at it, and
 * the same document re-run with each control taken away as a positive
 * control. `experiments/html_preview_guard/drive.py` is that run.
 *
 * `sandbox=""` gives the frame an opaque origin, so nothing in it can reach
 * this page, its origin or the API behind it. It is what stops SCRIPTS and
 * what stops FORM SUBMISSION -- with the policy in place but the sandbox
 * removed, a GET form, a POST form and an image-input form all reached the
 * server, because `form-action` does not fall back to `default-src`. It does
 * NOT stop the frame loading subresources: with the sandbox alone, an
 * `<img src>`, a nested `<iframe src>` and an external stylesheet were all
 * fetched on open. A fence in a body was a working tracking beacon.
 *
 * So a policy is injected into the document as well -- see `guarded` -- and
 * that, not the sandbox, is what makes nothing load. Subresources are
 * refused by the browser rather than by us: no scripts, no external
 * stylesheets, no webfonts, no fetch, no nested frames, no remote images.
 * Inline CSS and `data:` images still work, which is what a mockup needs.
 * The two overlap on scripts only: either one alone stopped them.
 *
 * LINKS ARE THE ONE THING NEITHER CONTROL COVERS, AND THE CAPTION SAYS SO.
 * No CSP directive governs following a link -- `navigate-to` was specified
 * and then dropped -- so a click can still take a browsing context
 * somewhere. `<base target="_blank">` is injected to send every link that
 * does not name its own target into a popup the sandbox has no
 * `allow-popups` for.
 *
 * BOTH LINK CASES HAVE NOW BEEN CLICKED FOR REAL. The extension's synthetic
 * clicks do not cross into a sandboxed cross-origin frame; a separate
 * headless Chrome driven over CDP with `Input.dispatchMouseEvent` does. A
 * link with no target of its own did NOT reach the server, and the same
 * link with the guard removed DID -- so the click lands, and the injected
 * base target is what makes it inert. A link naming `target="_self"`
 * navigated the frame and reached the server, exactly as the caption warns.
 * That one is accepted, and it is why the caption warns about links instead
 * of claiming they are switched off.
 *
 * Only a fence the author labelled is previewed. An unlabelled block that
 * happens to contain tags is not guessed at.
 * ------------------------------------------------------------------------ */

/** A fence the author labelled as html. Lives here, beside the reader that
 *  classifies fences, because a fence's language is this module's business. */
export const isHtmlLang = (lang: string | null) => {
  const l = (lang ?? '').toLowerCase()
  return l === 'html' || l === 'htm'
}

/* THE POLICY, and the one place it is written. `default-src 'none'` refuses
   every subresource the document asks for, including the nested frames and
   remote images that used to load on open; the two exceptions are what a
   mockup is made of and neither leaves this machine. `<base target="_blank">`
   is first in the document, so it wins the target a link inherits. */
const GUARD =
  '<meta http-equiv="Content-Security-Policy" content="' +
  "default-src 'none'; style-src 'unsafe-inline'; img-src data:" +
  '">' +
  '<base target="_blank">'

/** HOW MUCH OF THE DOCUMENT MUST STAY IN FRONT OF THE GUARD.
 *
 *  Leading whitespace, comments, a bogus comment such as an XML prolog, and
 *  the doctype. Nothing else -- and nothing in here looks at a tag or an
 *  attribute, because that is where the previous version went wrong.
 *
 *  A doctype ends at the FIRST `>`, even one inside a quoted identifier: the
 *  tokeniser calls that an abrupt-doctype parse error, ends the token there
 *  and turns the rest into text. Trying to be cleverer than that was tried
 *  and it leaked -- `<!DOCTYPE html SYSTEM "about:legacy-compat>x">` put the
 *  guard past the real end of the doctype, so its `<head>` start tag arrived
 *  in the body, where it is ignored and a meta policy does not count. That
 *  document fired a beacon until this matched the tokeniser instead.
 *
 *  An unterminated comment or doctype swallows the rest of the document, so
 *  there the scan simply stops: the guard goes in front of a document that
 *  renders nothing anyway. */
function preamble(html: string): number {
  let i = 0
  const space = () => {
    while (i < html.length && /\s/.test(html[i])) i++
  }
  space()
  for (;;) {
    if (html.startsWith('<!--', i)) {
      /* `-->` and `--!>` both close a comment. */
      const a = html.indexOf('-->', i + 4)
      const b = html.indexOf('--!>', i + 4)
      const end = a < 0 ? b : b < 0 ? a : Math.min(a, b)
      if (end < 0) return i
      i = end + (end === b && (a < 0 || b < a) ? 4 : 3)
    } else if (html.startsWith('<?', i)) {
      const end = html.indexOf('>', i + 2)
      if (end < 0) return i
      i = end + 1
    } else break
    space()
  }
  if (!/^<!doctype/i.test(html.slice(i, i + 9))) return i
  const end = html.indexOf('>', i + 9)
  return end < 0 ? i : end + 1
}

/** Put GUARD where the browser will honour it: a meta policy counts only in
 *  the document's real `<head>`.
 *
 *  THIS USED TO SEARCH FOR THE AUTHOR'S `<head>` AND THAT WAS A BYPASS. The
 *  search ran over raw text, so the first TEXTUAL `<head` won even when it
 *  was not a tag: a comment reading `<!-- the <head> section -->`, a script
 *  holding `var t='<head attr>'`, a `<textarea>` showing markup, or an
 *  attribute value containing `<head>` all took the guard into inert text,
 *  where it is not a meta element at all. The document then rendered with no
 *  policy and no `<base>`: an `<img src>` announced the reader to a stranger
 *  on open, and links navigated. Three of those shapes were confirmed firing
 *  a beacon in a real browser before this was changed.
 *
 *  Masking the inert regions first was the other candidate, and it is the
 *  bigger of the two: to be right it has to know comments, `<script>`,
 *  `<style>`, `<textarea>`, `<title>` AND every quoted attribute value --
 *  which is a tokeniser, and an HTML tokeniser made of regexes is exactly
 *  the thing that keeps being wrong by one context.
 *
 *  So the author's head is not searched for at all. A fresh head carrying
 *  the guard is inserted immediately after the preamble, and the parser does
 *  the rest: a later `<head>` start tag is ignored, a later `<html>` merges
 *  its attributes onto the element already open, and head content such as
 *  `<title>` is still put in the head. The guard is therefore FIRST in the
 *  real head, which is also what makes its `<base target>` the one a link
 *  inherits. The doctype is never moved: putting anything in front of it
 *  would silently drop the document into quirks mode and the preview would
 *  stop being a preview. */
export function guarded(html: string): string {
  const at = preamble(html)
  return html.slice(0, at) + '<head>' + GUARD + '</head>' + html.slice(at)
}

/** THE ONE FRAME ANY WRITTEN HTML IS DRAWN IN, so there is exactly one place
 *  its permissions are decided. */
export function HtmlFrame({
  html,
  title,
  className,
  style,
}: {
  html: string
  title: string
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <iframe
      className={className}
      style={style}
      title={title}
      sandbox=""
      referrerPolicy="no-referrer"
      srcDoc={guarded(html)}
    />
  )
}

function HtmlBlock({ lang, text }: { lang: string; text: string }) {
  const [view, setView] = useState<'source' | 'preview'>('source')
  const pick = (v: 'source' | 'preview') => (e: React.MouseEvent) => {
    e.stopPropagation()
    setView(v)
  }
  return (
    <div className="pr-html" data-view={view}>
      <div className="pr-html-bar" role="tablist" aria-label="how to show this html">
        <button role="tab" aria-selected={view === 'source'} onClick={pick('source')}>
          Source
        </button>
        <button role="tab" aria-selected={view === 'preview'} onClick={pick('preview')}>
          Preview
        </button>
      </div>
      {view === 'source' ? (
        <pre className="pr-code" data-lang={lang}>
          <code>{text}</code>
        </pre>
      ) : (
        <>
          <HtmlFrame className="pr-html-frame" title="preview of this html" html={text} />
          <p className="pr-html-note">
            Preview only · nothing is loaded from the network, and scripts and forms do not
            run. Following a link can still leave the preview.
          </p>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------------ *
 * VIDEOS NAMED IN A BODY.
 *
 * Only a link that is unmistakably ONE YouTube video counts: a channel or a
 * playlist names no single thing to preview, so it stays a link. The label
 * is the one the author wrote around the link, if they wrote one; nothing is
 * fetched to supply a title they did not give.
 *
 * WHY THIS IS NOT A REGEX. It was one, and the regex asserted things the
 * record did not say. `(?:[^\s)]*&)?v=` skipped greedily to the LAST `v=`,
 * so `?v=AAA&v=BBB` drew a card for BBB while the link beside it played AAA
 * -- a card naming a different video from its own href. Being unanchored, it
 * matched `https://evil.com/x?u=https://youtube.com/watch?v=ZZZ` and turned
 * a stranger's URL into a YouTube card. `[A-Za-z0-9_-]{11}` took the first
 * eleven characters of a longer id, naming a video nobody mentioned, and
 * `[^\s)<>]*` swept trailing punctuation into the href.
 *
 * So the URL is parsed as a URL. `URL` does the host, `URLSearchParams` does
 * the query, and every candidate must survive an exact host match, an exact
 * path shape and an exact eleven-character id or it stays a plain link. That
 * is what rejects `youtube.com@evil.com` (whose host is evil.com),
 * `youtube.com.evil.com`, and `javascript:` outright.
 * ------------------------------------------------------------------------ */

export interface Video {
  id: string
  url: string
  /** the author's own words for it, or null where the link was bare */
  label: string | null
}

/** Exact hosts. A suffix or substring test is what lets a lookalike through. */
const YT_HOSTS = new Set([
  'youtube.com',
  'www.youtube.com',
  'm.youtube.com',
  'music.youtube.com',
  'youtu.be',
  'www.youtu.be',
])

/** Eleven characters, anchored. An id of any other length is not an id, and
 *  is left alone rather than trimmed into one that names another video. */
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/

/** The id of the one video this URL is, or null. Null for a playlist, a
 *  channel, a search, a bare host, a lookalike, or anything malformed. */
export function youtubeId(raw: string): string | null {
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    return null
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null
  const host = u.hostname.toLowerCase()
  if (!YT_HOSTS.has(host)) return null

  const seg = u.pathname.split('/').filter(Boolean)
  let id: string | null = null
  if (host === 'youtu.be' || host === 'www.youtu.be') {
    if (seg.length === 1) id = decodeURIComponent(seg[0])
  } else if (seg.length === 1 && seg[0] === 'watch') {
    /* `.get` returns the FIRST `v`, which is the one the browser plays. The
       card and its link must name the same video or the card is a lie. */
    id = u.searchParams.get('v')
  } else if (seg.length === 2 && (seg[0] === 'shorts' || seg[0] === 'embed' || seg[0] === 'live')) {
    id = decodeURIComponent(seg[1])
  }
  return id !== null && VIDEO_ID.test(id) ? id : null
}

/** A bare URL in prose. Stops at whitespace and at the characters that end a
 *  link rather than belong to one; trailing sentence punctuation is trimmed
 *  after, because `...watch?v=ID).` must not put `).` in the href. */
const URL_TOKEN = /https?:\/\/[^\s<>"'`]+/g
const TRAILING = /[.,;:!?'")\]}]+$/
const MD_LINK = /\[([^\]]*)\]\(([^)\s]+)\)/g

/** Video links in a body, in reading order.
 *
 *  READ FROM BLOCKS, NOT FROM RAW TEXT. Run over the raw body, this drew
 *  cards for URLs inside FENCED CODE -- a turn showing somebody the shape of
 *  a YouTube URL got a playable card under it -- and for URLs inside inline
 *  code. Only the blocks that are prose a person is reading are scanned, and
 *  inline code spans are blanked inside those.
 *
 *  EVERY SHAPE PROSE COMES IN, NOT JUST PARAGRAPHS. Scanning only paragraphs
 *  and quotes was too narrow in the other direction: a numbered list of
 *  video links -- the shape an agent actually writes when it lists five
 *  things to watch -- got no cards at all, and neither did a bullet, a
 *  heading or a table cell, all of which render their links through the same
 *  `inline` reader. `readable` names the texts that are prose; code fences
 *  are still not among them.
 *
 *  ONE CARD PER VIDEO, AND THE LABELLED MENTION WINS. Keeping the first
 *  occurrence silently dropped a labelled `youtu.be/ID?t=42` in favour of a
 *  bare mention earlier in the body, losing both the author's words and
 *  their timestamp. A labelled mention now replaces a bare one already held,
 *  in the position the bare one had. */
/** The texts inside a block that a reader reads as prose, in reading order.
 *  A code fence and a rule have none: a fence is source being shown, not a
 *  link being made. Everything listed here is rendered through `inline`, so
 *  a link written in it really is a link on the page. */
export function readable(b: Block): string[] {
  switch (b.kind) {
    case 'para':
    case 'quote':
    case 'heading':
      return [b.text]
    case 'list':
      return b.items
    case 'table':
      return [...b.head, ...b.rows.flat()]
    default:
      return []
  }
}

export function videosOf(src: string): Video[] {
  const out: Video[] = []
  const at = new Map<string, number>()

  for (const b of blocksOf(src)) for (const raw of readable(b)) {
    const text = raw.replace(/`[^`]*`/g, ' ')

    const found: { url: string; label: string | null }[] = []
    /* Markdown links are taken first and removed, so their target is not
       also read a second time as a bare URL. */
    const rest = text.replace(MD_LINK, (_all, label: string, target: string) => {
      found.push({ url: target, label: label.trim() || null })
      return ' '
    })
    for (const m of rest.matchAll(URL_TOKEN))
      found.push({ url: m[0].replace(TRAILING, ''), label: null })

    for (const f of found) {
      const id = youtubeId(f.url)
      if (id === null) continue
      const prior = at.get(id)
      if (prior === undefined) {
        at.set(id, out.length)
        out.push({ id, url: f.url, label: f.label })
      } else if (f.label !== null && out[prior].label === null) {
        out[prior] = { id, url: f.url, label: f.label }
      }
    }
  }
  return out
}

/** Render blocks. `paragraph` lets the caller keep its own treatment of plain
 *  prose — which is how recorded media spans stay matchable against the raw
 *  text they were written against. */
export function Prose({
  src,
  paragraph,
  scope,
  inlineOf = inline,
  untrusted = false,
  names,
}: {
  src: string
  paragraph?: (text: string, key: string) => React.ReactNode
  /** EXPERIMENTAL: where this text comes from, so a marked block's state has
   *  a key. Required: there is no shared default, because a default made every
   *  caller that forgot it share one block's state (audit R1). Posted text is
   *  keyed by its origin -- `turnPartScope` -- not by where it is shown. */
  scope: string
  /** How running text inside every block is read. A stored note's embeds
   *  are drawn by its caller (Sources B3); everything else reads `inline`. */
  inlineOf?: (src: string, key: string) => React.ReactNode[]
  /** TEXT NOBODY IN THIS BRAIN WROTE (a stored note): fences are shown as
   *  their source and nothing more -- no renderable blocks, and no HTML
   *  preview, not even on request. */
  untrusted?: boolean
  /** EXPERIMENTAL: the names declared in this text's Turn part, handed down
   *  by a panel to the text inside it. Without it, this text is the top of
   *  its own part and its names are read here. */
  names?: Names
}) {
  const blocks = blocksOf(src)
  const seen: Record<string, number> = {}
  const nm = untrusted ? undefined : names ?? namesFor(src, scope)
  return (
    <TurnQuote.Provider value={(cite) => turnQuote(src, cite)}>
      {blocks.map((b, i) => {
        const k = `b${i}`
        switch (b.kind) {
          case 'heading': {
            const H = `h${Math.min(6, b.level + 2)}` as keyof React.JSX.IntrinsicElements
            return (
              <H key={k} className={'pr-h pr-h' + b.level}>
                {inlineOf(b.text, k)}
              </H>
            )
          }
          case 'code':
            if (b.info !== undefined && !untrusted) {
              const type = b.lang as RBlock['type']
              const n = (seen[type] = (seen[type] ?? -1) + 1)
              const block = { type, info: b.info, body: b.text, closed: b.closed ?? true }
              return (
                <RenderableBlock
                  key={k}
                  block={block}
                  blockKey={keyOf(scope, type, n, nameOf(block, nm), nm)}
                  where={scope}
                  names={nm}
                />
              )
            }
            return isHtmlLang(b.lang) && !untrusted ? (
              <HtmlBlock key={k} lang={b.lang!} text={b.text} />
            ) : (
              <pre key={k} className="pr-code" data-lang={b.lang ?? undefined}>
                <code>{b.text}</code>
              </pre>
            )
          case 'quote':
            return (
              <blockquote key={k} className="pr-quote">
                {b.text.split('\n\n').map((p, j) => (
                  <p key={j}>{inlineOf(p, `${k}-${j}`)}</p>
                ))}
              </blockquote>
            )
          case 'list':
            return b.ordered ? (
              <ol key={k} className="pr-list">
                {b.items.map((it, j) => (
                  <li key={j}>{inlineOf(it, `${k}-${j}`)}</li>
                ))}
              </ol>
            ) : (
              <ul key={k} className="pr-list">
                {b.items.map((it, j) => (
                  <li key={j}>{inlineOf(it, `${k}-${j}`)}</li>
                ))}
              </ul>
            )
          case 'table':
            return (
              <div key={k} className="pr-table-wrap">
                <table className="pr-table">
                  <thead>
                    <tr>
                      {b.head.map((c, j) => (
                        <th key={j}>{inlineOf(c, `${k}-h${j}`)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j}>
                        {r.map((c, m) => (
                          <td key={m}>{inlineOf(c, `${k}-${j}-${m}`)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          case 'rule':
            return <hr key={k} className="pr-rule" />
          default: {
            /* An image placed on its own is a figure in the flow of the post;
               text nobody here wrote (a stored note) draws its own embeds. */
            const fig = untrusted ? null : placedRef(b.text)
            if (fig)
              return (
                <div key={k} className="pr-placed" data-src-text={b.text.trim()}>
                  <AcquiredChip id={fig.id} said={fig.label} placed />
                </div>
              )
            return paragraph ? (
              paragraph(b.text, k)
            ) : (
              <p key={k}>{inlineOf(b.text, k)}</p>
            )
          }
        }
      })}
    </TurnQuote.Provider>
  )
}
