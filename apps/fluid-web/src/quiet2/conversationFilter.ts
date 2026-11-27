import type { Post } from './sample'

/** The server classifies what folds -- agent work, and a Magnet's own
 *  bookkeeping (`kind: 'mechanics'`: a collection page extracted, a
 *  Perspective created, prepared, bound, reconciled) -- and this hides it
 *  until the reader asks. A directly linked thread remains reachable. */
export function showConversationPost(post: Post, showWork: boolean, linkedRoot?: string): boolean {
  return showWork || !post.agentWork || post.id === linkedRoot
}
