/* WHERE OPEN GOES, AND THE ROW'S ORDER (objects/actions.ts). Browser-free,
 * so it is testable.
 *
 * Open is the full view with its own navigation; it is not Peek (a light
 * look that changes nothing) and not Focus (the stable large area):
 *
 *   post:<id>      the post's own detail: it is read, and This post shows
 *                  its context -- what a click on the post card does
 *   brain:<entry>  the Brain entry's inspector, the record's own reader
 *   anything else  the object's detail (workspace/Detail.tsx) out of its card */

export type ObjectAction = 'open' | 'peek' | 'float' | 'keep' | 'primary' | 'focus'

/** The one order every row draws: Open · Peek · Float · Keep · ◎ · ⛶. */
export const ACTION_ORDER: readonly ObjectAction[] = ['open', 'peek', 'float', 'keep', 'primary', 'focus']

export type OpenRoute =
  | { to: 'post'; id: string }
  | { to: 'brain'; entry: string }
  | { to: 'object'; address: string }

const POST = 'post:'
const BRAIN = 'brain:'

export function openRoute(address: string): OpenRoute {
  if (address.startsWith(POST) && address.length > POST.length) return { to: 'post', id: address.slice(POST.length) }
  if (address.startsWith(BRAIN) && address.length > BRAIN.length) return { to: 'brain', entry: address.slice(BRAIN.length) }
  return { to: 'object', address }
}
