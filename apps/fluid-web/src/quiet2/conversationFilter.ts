import type { Post } from './sample'

/** The server classifies agent work; a directly linked thread remains reachable. */
export function showConversationPost(post: Post, showWork: boolean, linkedRoot?: string): boolean {
  return showWork || !post.agentWork || post.id === linkedRoot
}
