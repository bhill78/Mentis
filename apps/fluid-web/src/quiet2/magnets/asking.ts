/* The real Composer owns addressing, split send and Work permissions. This
 * adapter owns only the Magnet's isolated draft, the destination of send, and
 * the attached discussion reference it carries onto the submitted message. */
import type { WorkspaceAsking } from '../../fluid/Composer'
import type { MagnetResource } from './contract'
import { miniComposerDraft, miniComposerWhere, saveMiniComposer, subscribeMiniComposer,
  withContext, type MiniConversation } from './conversation'

export function miniAsking(resource: MagnetResource, conversation: MiniConversation): WorkspaceAsking {
  const where = miniComposerWhere(resource)
  return {
    where, key: where, heading: 'Message this Magnet',
    drafts: {
      load: () => miniComposerDraft(resource),
      save: (draft) => saveMiniComposer(resource, draft),
      subscribe: (changed) => subscribeMiniComposer(resource, changed),
    },
    /* The attached reference goes on the post the Composer built, before any
       routing: one text part naming it, so the recorded message says what it
       is about and the card draws it as an inspect link. The reference only --
       never captured content -- and the same post is what a frozen retry
       reuses, so a retry carries exactly what the first attempt did. */
    send: (post, op, brain) => conversation.submit(withContext(resource, post), op, brain),
  }
}
