/* A REFUSAL, SAID WHOLE (WS-I, mentis/refusal.py).
 *
 * A door's refusal is `{error, kind, refusal?}`; a structured one carries
 * `refusal = {op, boundary, why, recovery[], who}` beside its words. Fluid's
 * actions throw it as `Refused` (fluid/actions.ts), the whole answer kept.
 * Where Mark 2 says a refusal, it says the server's words and then whatever
 * of the structure those words do not already say: why, what can be done
 * instead, who can lift it, and at which boundary it was refused -- each the
 * server's own, never composed or guessed here. A refusal with no structure
 * (an older server, a legacy refusal) is its words alone, as before. */

/** The structure a structured refusal carries (`StructuredRefusal.as_dict`). */
export interface RefusalFields { op?: string | null; boundary?: string | null; why?: string | null; recovery?: string[] | null; who?: string | null }

const fieldsOf = (body: unknown): RefusalFields | null => {
  const r = (body as { refusal?: unknown } | null)?.refusal
  return r && typeof r === 'object' && typeof (r as RefusalFields).boundary === 'string' ? r as RefusalFields : null
}

/** A refusal's words: the server's sentence, then what of its structure the
 *  sentence leaves out. `x` is a thrown error (Fluid's `Refused` carries the
 *  whole answer as `refusal`) or a door's answer itself. */
export function refusalWords(x: unknown): string {
  const body = x instanceof Error ? (x as Error & { refusal?: unknown }).refusal ?? null : x
  const said = x instanceof Error ? x.message : typeof (body as { error?: unknown } | null)?.error === 'string' ? (body as { error: string }).error : String(x ?? '')
  const f = fieldsOf(body)
  if (!f) return said
  const has = (t: string | null | undefined) => !!t && said.includes(t.replace(/\.$/, ''))
  const out = [said.trim()]
  if (f.why && !has(f.why)) out.push(f.why.replace(/\.?$/, '.'))
  const recovery = (f.recovery ?? []).filter((r) => !has(r))
  if (recovery.length) out.push(`What you can do instead: ${recovery.join('; ')}.`)
  if (f.who && !has(f.who)) out.push(`Who can lift this: ${f.who.replace(/\.$/, '')}.`)
  out.push(`(Refused at the ${f.boundary} boundary${f.op ? `: ${f.op}` : ''}.)`)
  return out.filter(Boolean).join(' ')
}
