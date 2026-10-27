/* EXPERIMENTAL: what one marked-block TYPE says about its MARKDOWN, and nothing
   about how it is drawn.

   This directory is the reading half of every type: attributes, body grammar
   and the parse that validates them. It imports no React, no DOM and no CSS,
   so the same code runs in the browser (types/*.tsx spread these specs into
   their TypeDefs) and on the server, where `check.ts` is bundled into
   dist/render-check.js and run in an embedded engine to tell an agent what
   will not render before anybody reads it. One reader, two callers: a type's
   rules are changed here or nowhere.                                        */

export interface AttrSpec {
  req: 'required' | 'optional'
  /** Allowed values, if the attribute is an enumeration. */
  choices?: string[]
  /** One line for the author: what to write. Shown in the gallery. */
  says: string
}

/** The sizes a workspace may draw a block at (the shared `sizes`/`prefer`). */
export type Size = 'compact' | 'medium' | 'large'

/** The five shared attributes any marked block may carry, read and checked
    by the core (./core.ts, `readShared`), defaults applied. */
export interface Shared {
  /** stable identity within the Turn part; null when none (or not usable) */
  name: string | null
  /** whether it starts open where it can collapse; always true without a label */
  open: boolean
  sizes: Size[]
  prefer: Size
  /** a suggested working page, or null for the Post page */
  page: string | null
  /** what it is called when collapsed: its title, or a panel's leading heading */
  label: string | null
  /** where the label came from; a heading label is drawn once, as the label */
  labelFrom: 'title' | 'heading' | null
}

export interface Ctx {
  /** `fix`, when given, is what the author should change; the UI shows `msg` only. */
  err(where: string, msg: string, fix?: string): void
  warn(where: string, msg: string, fix?: string): void
  /** The block's shared attributes (name, open, sizes, prefer, page), already
      read and checked by the core. A type never declares them itself. */
  shared?: Readonly<Shared>
}

export interface TypeSpec<D = any> {
  type: string
  /** One line: what this surface is for. */
  summary: string
  attrs: Record<string, AttrSpec>
  /** What the author writes in the body, one line. */
  body: string
  /** Read the body. Called only when the attributes are acceptable. Report
      problems through ctx; returning anything is fine when there are errors. */
  parse(body: string, attrs: Record<string, string>, ctx: Ctx): D
  /** The heading a body opens with, when the type lets that heading name the
      whole block (a panel's first line). Used as the label when there is no
      title. Pure: reads the body, draws nothing. */
  heading?(body: string): string | undefined
  /** The body is Markdown whose own marked blocks are drawn as blocks
      (help.Nested), so a checker reads them too. */
  nests?: boolean
}
