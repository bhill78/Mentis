/* MIS-DECODED TEXT, REPAIRED FOR READING (round 2).
 *
 * Some agent replies in the record carry UTF-8 that was read as Windows-1252
 * on the way in: an em dash arrives as "â€”", a section sign as "Â§". The
 * record is append-only and stays as written; this repairs only what is
 * drawn. A run of such characters is turned back into the bytes it came
 * from and decoded as UTF-8; a run that does not decode cleanly is left
 * exactly as it was, so correct text is never touched. */

/* Windows-1252's 0x80-0x9F, which are not Latin-1 */
const CP1252: Record<number, number> = {
  0x20ac: 0x80, 0x201a: 0x82, 0x0192: 0x83, 0x201e: 0x84, 0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87,
  0x02c6: 0x88, 0x2030: 0x89, 0x0160: 0x8a, 0x2039: 0x8b, 0x0152: 0x8c, 0x017d: 0x8e,
  0x2018: 0x91, 0x2019: 0x92, 0x201c: 0x93, 0x201d: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
  0x02dc: 0x98, 0x2122: 0x99, 0x0161: 0x9a, 0x203a: 0x9b, 0x0153: 0x9c, 0x017e: 0x9e, 0x0178: 0x9f,
}
const byteOf = (c: number): number | null => c < 0x100 ? c : CP1252[c] ?? null

/* A lead byte followed by as many continuation characters as that lead
   byte promises (Â-ß one, à-ï two, ð-ô three): the shape a mis-decoded
   multi-byte character takes. */
const CONT = '[\u0080-\u00bf\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192\u02c6\u02dc\u2013\u2014\u2018-\u201e\u2020-\u2022\u2026\u2030\u2039\u203a\u20ac\u2122]'
const RUN = new RegExp(`[\u00c2-\u00df]${CONT}|[\u00e0-\u00ef]${CONT}{2}|[\u00f0-\u00f4]${CONT}{3}`, 'g')

const strict = new TextDecoder('utf-8', { fatal: true })

export function repairText(s: string): string {
  if (!/[Â-ô]/.test(s)) return s
  return s.replace(RUN, (run) => {
    const bytes: number[] = []
    for (const ch of run) {
      const b = byteOf(ch.codePointAt(0)!)
      if (b === null) return run
      bytes.push(b)
    }
    try {
      const out = strict.decode(new Uint8Array(bytes))
      /* one character, and not itself a control: otherwise it was real text */
      return [...out].length === 1 && out.codePointAt(0)! >= 0xa0 ? out : run
    } catch { return run }
  })
}
