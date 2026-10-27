/* EXPERIMENTAL: one gallery example. */
export interface Example {
  id: string
  /** The experimental category it explores (form, table, ...). */
  category: string
  title: string
  /** What to try, and what the author had to write to get it. One or two sentences. */
  note: string
  /** Where the declaration stops being simple for a human or a weak model. Empty = none observed. */
  demands?: string[]
  source: string
}

/** Markdown fence helper so examples can contain nested fences readably. */
export const F3 = '```'
export const F4 = '````'
