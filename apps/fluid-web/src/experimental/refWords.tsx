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
  /** HOW THIS EXACT REFERENCE STANDS NOW, where the host resolved that id and
   *  nothing else (`quiet2/needs/inspect.ts`, from the server's own
   *  `availability`): whether there is anything to look at, what became of it,
   *  and the record's own reason. Null for an id the host did not resolve.
   *
   *  A HOST THAT RESOLVES NO REFERENCES LEAVES THIS OUT, and then nothing is
   *  claimed about any of them -- not that they are there, and not that they
   *  are gone (../decisionPresentation `Standing`). */
  standing?: (id: string) => { available: boolean; state: string; why?: string | null } | null
}

export const RefWordsContext = createContext<RefWords | null>(null)

/** Words as their host draws them (`how`), or as written. */
export function Words({ children, how = 'links' }: { children: string | null | undefined; how?: 'links' | 'names' }) {
  const host = useContext(RefWordsContext)
  /* THE RECORD MAY HOLD SOMETHING THAT IS NOT WORDS where words were expected
     -- a number, a list -- and the backends report that as a problem rather
     than refusing the read (`nonblank_string`). Nothing is drawn for it here:
     what is wrong with it is said where what is missing is said, and a stored
     value that is not text never stops the form being read. */
  if (typeof children !== 'string' || !children) return null
  if (!host) return <>{children}</>
  return <>{how === 'names' ? host.names(children) : host.links(children)}</>
}

/** A control that opens one exact reference, where the host offers one. */
export function OpenRef({ id, words }: { id: string; words: string }) {
  const host = useContext(RefWordsContext)
  return <>{host?.open?.(id, words) ?? null}</>
}
