/* THE WORDS OF A DECISION, WITH WHAT THEY NAME READABLE AND OPENABLE.
 *
 * A question, an option or a finding may name things by id (`ent-…`,
 * `opr-…`). Whoever hosts the decision form may say how such words are drawn
 * -- an id as the name of the thing it is, and, where the words are not
 * inside a control of their own, as a link that opens that exact thing.
 * With no host saying so, words are drawn exactly as they were written.
 *
 * Presentation only: nothing here is sent anywhere, and what a choice records
 * is untouched (../decisions.ts). */
import { createContext, useContext } from 'react'

export interface RefWords {
  /** the words, each id as a link to the exact thing it names */
  links: (text: string) => React.ReactNode
  /** the words, each id as the thing's name: for words inside a button */
  names: (text: string) => string
  /** a way to open this exact reference, said as `words`; null where there is none */
  open?: (id: string, words: string) => React.ReactNode
}

export const RefWordsContext = createContext<RefWords | null>(null)

/** Words as their host draws them (`how`), or as written. */
export function Words({ children, how = 'links' }: { children: string | null | undefined; how?: 'links' | 'names' }) {
  const host = useContext(RefWordsContext)
  if (!children) return null
  if (!host) return <>{children}</>
  return <>{how === 'names' ? host.names(children) : host.links(children)}</>
}

/** A control that opens one exact reference, where the host offers one. */
export function OpenRef({ id, words }: { id: string; words: string }) {
  const host = useContext(RefWordsContext)
  return <>{host?.open?.(id, words) ?? null}</>
}
