/* WHAT THE CHOOSER ASKS OF ITS HOST (result navigation, part N-B).
 *
 * The chooser draws what the server's bounded result read says and nothing
 * else. Three things it cannot do itself, so the host lends them:
 *
 *   OPENING a chosen result, which is the shared target opener's work (part
 *   N-C, `quiet2/results/targets.ts`): the chooser hands over the exact wire
 *   item and the group it was chosen from, and never builds a target, a URL
 *   or a viewer of its own.
 *
 *   READING MORE: older groups and a group's remaining items come from the
 *   existing work detail read (`/api/work/<expectation>` with
 *   `results_before` / `result_group` + `items_after`), whose client binding
 *   has one owner (part N-I). The chooser asks through `more`.
 *
 *   THE MAPPING of a post to the Work whose results it carries. That is the
 *   server's exact `origin` / `update_turns` answer, passed in by the host.
 *   The chooser never infers it from an author, a nearest reply or a post's
 *   expectations.
 *
 * Every one of these is optional. With no host -- archived Quiet, Fluid, a
 * fixture harness -- the chooser still lists the results honestly and says
 * what it cannot do here, which is the point of it being a presentation
 * module and not a navigator. */
import { createContext, useContext } from 'react'
import type { Id } from '../../api'
import type { ResultGroup, ResultPage, WorkResult } from '../../work/contract'

/** A reader chose one result. The item and group are the server's own. */
export interface ResultChoice {
  /** the Work (trunk expectation) whose read these results came from */
  work: Id
  group: ResultGroup
  item: WorkResult
}

/** A reader chose a group's source post -- a separate act from its items. */
export interface SourceChoice {
  work: Id
  group: ResultGroup
}

/** The host's bound continuation reads. Each returns the server's next page
 *  exactly; a moved or foreign cursor comes back as the server's refresh
 *  condition (HTTP 409 `ResultsRefreshRequired`), which the chooser shows as
 *  a reload offer rather than appending or skipping anything. */
export interface MoreResults {
  /** older groups: `results_before=<next_results_before>` */
  groupsBefore(work: Id, cursor: string): Promise<ResultPage>
  /** one group's remaining items: `result_group=<id>&items_after=<cursor>` */
  itemsAfter(work: Id, group: Id, cursor: string): Promise<ResultPage>
}

/** What the host lends the chooser. */
export interface ResultsHost {
  /** open the chosen result through the shared target opener */
  open(choice: ResultChoice): void
  /** go to a group's source post; absent: no source navigation here */
  openSource?: ((choice: SourceChoice) => void) | null
  /** read older groups and remaining items; absent: only this page is held */
  more?: MoreResults | null
}

/** The results one post carries, as the host's exact mapping says.
 *
 *  `mapping` says why these results are offered here, and on a post it is
 *  the server's fact: the Work's `origin` Turn (the request) or one of its
 *  `update_turns` (a recorded carrier claim or execution result reply).
 *  Nothing else carries a chooser on a post. `work` is for a list that
 *  stands for the Work itself rather than for any post of it -- the Latest
 *  list -- and claims no post mapping at all. */
export interface PostResults {
  work: Id
  /** the Work's title, for the chooser's heading; null when unknown */
  title: string | null
  mapping: 'request' | 'update' | 'work'
  page: ResultPage
}

/** Which results a post carries. The host answers from the Work read. */
export type PostResultsLookup = (post: Id) => PostResults[]

/** WHICH RESULTS A POST CARRIES, and the only answer to that question.
 *
 *  Nothing is drawn unless a host lent the mapping; a post the record does
 *  not map gets nothing, and a post that is not a real recorded post (the
 *  sample's, a draft) gets nothing either. A post mapped twice -- the same
 *  Work's request and its update, as a request post that was also claimed on
 *  -- keeps both, each said as what it is. */
export function postResultsOf(
  results: { of: PostResultsLookup } | null | undefined,
  post: { id: Id; real?: boolean },
): PostResults[] {
  if (!results || post.real === false) return []
  const seen = new Set<string>()
  const out: PostResults[] = []
  for (const r of results.of(post.id) ?? []) {
    const key = `${r.work}:${r.mapping}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(r)
  }
  return out
}

/** The host, where there is one. `null` is an ordinary, supported state. */
export const ResultsHostContext = createContext<ResultsHost | null>(null)

export const useResultsHost = (): ResultsHost | null => useContext(ResultsHostContext)
