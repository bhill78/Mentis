/* The real Composer owns addressing, split send and Work permissions. This
 * adapter owns only the Magnet's isolated draft and the destination of send. */
import type { WorkspaceAsking } from '../../fluid/Composer'
import type { MagnetResource } from './contract'
import { miniComposerDraft, miniComposerWhere, saveMiniComposer, subscribeMiniComposer,
  type MiniConversation } from './conversation'

export function miniAsking(resource: MagnetResource, conversation: MiniConversation): WorkspaceAsking {
  const where = miniComposerWhere(resource)
  return {
    where, key: where, heading: 'Message this Magnet',
    drafts: {
      load: () => miniComposerDraft(resource),
      save: (draft) => saveMiniComposer(resource, draft),
      subscribe: (changed) => subscribeMiniComposer(resource, changed),
    },
    send: (post, op, brain) => conversation.submit(post, op, brain),
  }
}
