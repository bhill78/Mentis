/* A MAGNET'S ACTIVATE, IN ITS PANE: what the actions in its T2 do (provider.ts),
 * through the one registry, said where the reader is looking. Running, what it
 * came to and every refusal, in the server's words, with the way to the result
 * in the Magnet's own Conversation. */

import { useEffect, useState } from 'react'
import * as nav from '../../nav'
import { registry } from '../actions/registry'
import type { ActionCtx, ActionId, ActionTarget } from '../actions/types'
import { useActivation } from './client'
import { activationRefusal, setUpChange } from './model'
import type { MagnetConfig, MagnetId } from './types'

export function ActivationBar({ id, config, target, ctx }: { id: MagnetId; config: MagnetConfig; target: ActionTarget; ctx: ActionCtx }) {
  const now = useActivation(id)
  const [failed, setFailed] = useState<string | null>(null)
  useEffect(() => setFailed(null), [id])
  const why = activationRefusal(config)?.message
  const running = now.phase === 'running'
  const run = (verb: ActionId) => { setFailed(null); void registry.run(verb, target, ctx).catch((e: Error) => setFailed(e.message)) }
  const result = now.result
  return <div className="mg-activation" data-phase={now.phase}>
    <button type="button" className="fl-btn mg-activate" disabled={!!why || running} title={why ?? 'Run its one extract step now, once'} onClick={() => run('magnet.activate')}>
      {running ? 'Running…' : now.sameKey ? 'Ask again (same key)' : 'Activate'}
    </button>
    {setUpChange(config) && <button type="button" className="fl-btn" title="Add manual activation with one extract step to this same Magnet. Nothing runs until you press Activate" onClick={() => run('magnet.setUpActivation')}>Set up manual activation</button>}
    {result && <button type="button" className="fl-btn" title="Read the page it recorded, in this Magnet’s own Conversation" onClick={() => nav.read(result.conversation, result.post, null)}>Read the result</button>}
    <button type="button" className="fl-btn" title="This Magnet’s own Conversation, not the one it reads. Made on this press if it has none" onClick={() => run('magnet.conversation')}>Its Conversation</button>
    {why && <p className="mg-why" data-code="state">{why}</p>}
    {now.words && <p className="mg-why" role="status" aria-live="polite" {...(now.phase === 'complete' ? {} : { 'data-code': now.phase })}>{now.words}</p>}
    {failed && <p className="mg-problems" role="alert">{failed}</p>}
  </div>
}
