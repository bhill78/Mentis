/* EXPERIMENTAL: small helpers every marked-block type may use. No imports,
   so type modules can use them without an import cycle through the core. */

/** RFC-4180-ish CSV: quoted cells, doubled quotes, CR ignored. */
export function csvRows(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = [], cell = '', q = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++ }
      else if (c === '"') q = false
      else cell += c
    } else if (c === '"' && cell === '') q = true
    else if (c === ',') { row.push(cell); cell = '' }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = '' }
    else if (c !== '\r') cell += c
  }
  if (cell !== '' || row.length) { row.push(cell); rows.push(row) }
  return rows
}

/** A CSV body with a header row, checked for shape. `err` gets plain-language problems. */
export function csvTable(body: string, err: (where: string, msg: string) => void, what = 'data') {
  const rows = body.trim() ? csvRows(body.replace(/^\n+|\n+$/g, '')) : []
  if (!rows.length) {
    err('body', `There is no ${what}. Put CSV under the opening line: a header row, then one row per line.`)
    return null
  }
  const header = rows[0].map((h) => h.trim())
  const data = rows.slice(1)
  if (!data.length) err('body', `There is a header row but no ${what} rows.`)
  const dup = header.filter((h, i) => header.indexOf(h) !== i)
  if (dup.length) err('header', `Column names repeat: ${[...new Set(dup)].join(', ')}.`)
  data.forEach((r, n) => {
    if (r.length !== header.length)
      err(`data line ${n + 2}`, `This row has ${r.length} cells but the header has ${header.length} columns.`)
  })
  return { header, rows: data }
}

/** Split `a,b,"c d"` into items (a comma list whose items may be quoted). */
export function listOf(v: string | undefined): string[] {
  if (v === undefined || v === '') return []
  return csvRows(v)[0]?.map((s) => s.trim()) ?? []
}

/** `key=value` / `key="quoted value"` pairs after a leading part of a body line. */
export function pairsOf(s: string): { pairs: Record<string, string>; flags: string[]; residue: string } {
  const pairs: Record<string, string> = {}
  const flags: string[] = []
  let rest = s
  const re = /^\s*([A-Za-z][A-Za-z0-9_-]*)(?:=(?:"((?:[^"\\]|\\.)*)"|([^\s"]+)))?(?=\s|$)/
  while (rest.trim()) {
    const m = re.exec(rest)
    if (!m) return { pairs, flags, residue: rest.trim() }
    if (m[2] === undefined && m[3] === undefined) flags.push(m[1])
    else pairs[m[1]] = m[2] !== undefined ? m[2].replace(/\\(.)/g, '$1') : m[3]
    rest = rest.slice(m[0].length)
  }
  return { pairs, flags, residue: '' }
}

/** A leading "quoted string" at the start of s: [text, rest] or null. */
export function quoted(s: string): [string, string] | null {
  const m = /^\s*"((?:[^"\\]|\\.)*)"/.exec(s)
  return m ? [m[1].replace(/\\(.)/g, '$1'), s.slice(m[0].length)] : null
}

export const q = (s: unknown) => JSON.stringify(s)

/** Deterministic small hash, for mock imagery and stable colours. */
export function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
  return h >>> 0
}

/** A normal categorical palette the RENDERER chooses; authors never name colours. */
export const PALETTE = ['#3a6ea5', '#c0504d', '#6a9a3a', '#8064a2', '#d08a1e', '#2a9d8f', '#b5536b', '#6b7a8f']
