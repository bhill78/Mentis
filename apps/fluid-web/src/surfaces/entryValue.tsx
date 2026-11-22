/* WHAT A RECORD'S FIELD ACTUALLY HOLDS, READ AS WHAT IT IS (re-review finding
 * F2-R1).
 *
 * A Kind declares its fields; what a field HOLDS is whatever the corpus
 * accepted for it, and that is not always a line of text. A declared field may
 * hold a structured value -- a design with a purpose and a restriction, a
 * contribution's list of content parts -- and the inspector printed every field
 * through `String(value)`, which for anything but a string, a number or a
 * boolean is the word `[object Object]`. The record's own words were in the
 * entry read the whole time and nowhere on the screen.
 *
 * That is not cosmetic where this inspector is the ONLY way to inspect the
 * exact record a decision approves: Fluid's exact-source opener sends every
 * supported non-post record here (`../fluid/present/decisionRefWords`
 * `openExact`), and an approval is supposed to be answerable only by somebody
 * who can read the thing being approved.
 *
 * WHAT THIS DOES, AND WHAT IT NEVER DOES.
 *   - IT PRESERVES THE CONTENT. Every leaf the value holds is drawn, under the
 *     name the record gave it, in the order the record holds it. Nothing is
 *     summarised, truncated, counted instead of shown, or replaced by a
 *     description of itself.
 *   - IT SUBSTITUTES NOTHING. It reads the value it was handed and no other,
 *     looks nothing up, matches no titles and infers no fields. An empty list
 *     or an empty record is said to be empty -- which is what it is -- and is
 *     never filled in.
 *   - TEXT IS STILL TEXT. A string leaf is drawn by `Prose`, exactly as a
 *     single-string field always was, so references, quotes and blocks inside
 *     a nested string read as they do everywhere else. The one-string case is
 *     byte-for-byte what it was before.
 *   - IT NAMES NO KIND. There is no special case for `contribution`, for
 *     `parts`, or for any other Kind or field: the shape of the value decides
 *     how it is drawn, which is why a Kind defined after this was written
 *     reads correctly too.
 *
 * Presentation only: nothing here reads the server, and nothing here writes. */
import { Prose } from '../prose'

/** Said where a field is declared and holds a list with nothing in it. */
export const EMPTY_LIST = 'an empty list'
/** Said where it holds a structured value with no parts in it. */
export const EMPTY_RECORD = 'no parts recorded'

/* ONE STATE KEY NAMES EXACTLY ONE FIELD PATH (re-review finding F2-R1, and
 * the rule behind it). A marked block keeps its state under its `scope`, so
 * two different places in a record must never share one: a field named "a.b"
 * and a field "a" holding "b" did, and so did the list item [1] and the part
 * named "1" -- editing one changed the other's draft. Every segment is now
 * written so it can only be read back one way: the field's name as a JSON
 * string, a part's name as ["name"], a list position as [i]. A JSON string is
 * self-delimiting, so no name, however it is spelled, can pass for a path. */

/** The scope of a record's declared field: the entry, then the field's name. */
export function fieldScope(entry: string, field: string): string {
  return `entry:${entry}:${JSON.stringify(field)}`
}

/** The scope of a named part of a structured value. */
export function partScope(scope: string, name: string): string {
  return `${scope}[${JSON.stringify(name)}]`
}

/** The scope of a list item, by its position. */
export function itemScope(scope: string, index: number): string {
  return `${scope}[${index}]`
}

const structured = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)

/** WHAT THE VALUE SAYS, AS ONE LINE OF PLAIN TEXT, for the places that can only
 *  take a string -- an act that must state what it is about, and the folded
 *  identity pairs. Every leaf is still there, under its own name; nothing is
 *  dropped. `String(value)` is kept for a string, a number and a boolean, so
 *  those read exactly as they did. */
export function valueWords(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) return v.length ? v.map(valueWords).filter((s) => s !== '').join(' · ') : EMPTY_LIST
  if (structured(v)) {
    const parts = Object.entries(v).map(([k, x]) => `${k}: ${valueWords(x)}`)
    return parts.length ? parts.join(' · ') : EMPTY_RECORD
  }
  return String(v)
}

/** ONE FIELD'S VALUE, DRAWN AS WHAT IT IS. A string reads as prose, as it
 *  always did; a list reads as its items in order; a structured value reads as
 *  its named parts, each drawn the same way again. `scope` keys a marked
 *  block's state and so must name where this leaf came from. */
export function FieldValue({ value, scope }: { value: unknown; scope: string }) {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return <Prose src={value} scope={scope} />
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <span className="ei-val-plain">{String(value)}</span>
  }
  if (Array.isArray(value)) {
    if (!value.length) return <span className="ei-val-empty">{EMPTY_LIST}</span>
    return (
      <ol className="ei-val-list">
        {value.map((v, i) => (
          <li key={i}><FieldValue value={v} scope={itemScope(scope, i)} /></li>
        ))}
      </ol>
    )
  }
  if (structured(value)) {
    const parts = Object.entries(value)
    if (!parts.length) return <span className="ei-val-empty">{EMPTY_RECORD}</span>
    return (
      <dl className="ei-val-parts">
        {parts.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd><FieldValue value={v} scope={partScope(scope, k)} /></dd>
          </div>
        ))}
      </dl>
    )
  }
  /* anything else the record happens to hold, said as the record holds it */
  return <span className="ei-val-plain">{String(value)}</span>
}
