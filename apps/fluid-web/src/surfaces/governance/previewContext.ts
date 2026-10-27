/** The composing door's address, with the material named for it (I-103/104).
 *
 *  NAMED AS A DISPATCH NAMES IT. `/api/context` takes two lists: `behavioural`
 *  is durable material named by reference -- what a dispatch passes for the
 *  governed items it names (`web/dispatch.py`) -- and `material` is TEXT
 *  supplied for one invocation, which would compose the id as a string and
 *  not the item. So the references go as `behavioural`, once per item,
 *  because the engine takes a sequence and `qs` sets one value per key.
 *
 *  `base` is what `qs` made of the rest: '' or '?k=v&…'. */
export function contextPath(base: string, named: string[]): string {
  if (named.length === 0) return '/api/context' + base
  const p = new URLSearchParams(base.replace(/^\?/, ''))
  for (const id of named) p.append('behavioural', id)
  return '/api/context?' + p.toString()
}
