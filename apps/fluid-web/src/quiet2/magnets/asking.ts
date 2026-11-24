/* The real Composer owns addressing, split send and Work permissions. This
 * adapter owns only the Magnet's isolated draft, the destination of send, and
 * the attached discussion reference it carries onto the submitted message. */
import type { WorkspaceAsking } from '../../fluid/Composer'
import type { MagnetResource } from './contract'
import { carryContext, miniComposerDraft, miniComposerWhere, saveMiniComposer, subscribeMiniComposer,
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
    /* Exact authored parts and separately versioned selectors are frozen
       together under this operation key. No generated context becomes prose. */
    send: (post, op, brain) => {
      carryContext(resource, op)
      return conversation.submit(post, op, brain)
    },
  }
}
