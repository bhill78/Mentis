/* PACKAGE D owns this module: open decisions, answerable where they are
   shown. Its mount is in B's margin, beside the runs.

   WHAT IS OWED HERE, ANSWERED HERE. `Conversation.owed` (`/api/conversations/
   <id>?batch=0`) is the whole, un-paged list of outstanding obligations --
   right even when the Turn they hang on is an older page the flow has not
   loaded -- and each row already carries its own `options` and `because`
   (`expectation_state`'s own fields, not only the Turn's `expectations`).
   The Turn is still read, one at a time (`/api/turns/<id>`) the way a
   reader with "a handful of links learned from a first read" always has
   (`read`, api.ts), but only to prefer its copy when a Turn exists; a
   standard pending decision form carries `turn: null` until it lands on a
   post, and answers straight from `owed` alone rather than going unread --
   its question included, which is the one thing a post would otherwise
   have carried (`asked`, below).

   THE ANSWER IS AN ORDINARY POST. `postingBody`'s `chose` is the only thing
   that marks it as answering rather than saying something new -- so the
   reply reads in the thread exactly as a typed answer would. */
import { useEffect, useState } from 'react'
import { post, read, useApi, type Conversation, type Id, type OwedHere, type ParticipantsList, type TurnDetail } from '../../api'
import { message, postingBody, type Chose } from '../model'

function Decision({ o, turn, me, conversation, topic }: {
  o: OwedHere; turn: TurnDetail | undefined; me: Id | null; conversation: Id; topic: Id | null
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const expectation = turn?.expectations.find((e) => e.id === o.expectation)
  /* The Turn's own copy where there is a Turn; `owed`'s own `options` and
   * `because` where there is none yet -- a standard pending decision form
   * (`turn: null`) still answerable here rather than going unread. */
  const options = expectation?.options ?? o.options ?? []
  const because = expectation?.because ?? o.because
  /* WHAT IS BEING ASKED, IN THE ASKER'S WORDS. A Turn-backed decision reads
   * as the post it hangs on, whose text the stream already shows, and
   * `because` is its recorded reason. A form with `turn: null` has no post:
   * its question travels in the `owed` row's own `question`, and its
   * `because` is the generic fallback `_decision_form` supplies -- so the
   * question comes first where there is one, or the rail would offer
   * options for something nobody can read. */
  const asked = o.question || because || o.expects
  if (!options.length) return <div className="qc-decision"><p>{asked}</p></div>
  const answer = async (index: number) => {
    if (!me || busy) return
    setBusy(true)
    setError(null)
    const opt = options[index]
    const chose: Chose = { expectation: o.expectation, option: index, label: opt.label }
    try {
      await post('/fluid/api/posts', postingBody(opt.label, 'record-only', me, conversation, topic, turn ?? null, crypto.randomUUID(), chose))
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  return <div className="qc-decision">
    <p>{asked}</p>
    <div className="qc-decision-options">
      {options.map((opt, i) => <button key={i} type="button" disabled={busy || !me} onClick={() => void answer(i)}>{opt.label}</button>)}
    </div>
    {error && <p role="alert" className="qc-error">{error}</p>}
  </div>
}

export default function Decisions({ conversation, topic }: { conversation: Id; topic: Id | null }) {
  const facts = useApi<Conversation>(`/api/conversations/${encodeURIComponent(conversation)}?batch=0`)
  const people = useApi<ParticipantsList>('/api/participants')
  const me = people.data?.participants.find((p) => p.about === 'the owner') ?? people.data?.participants[0]
  const owed = facts.data?.owed ?? []
  /* Only a row that can be answered here needs its Turn (the answer replies
   * to it); reading every owed row's Turn at once sent hundreds of requests
   * in a busy conversation. */
  const answerable = owed.filter((o) => o.turn && o.options?.length)
  const [turns, setTurns] = useState<Map<Id, TurnDetail>>(new Map())
  useEffect(() => {
    if (!answerable.length) { setTurns(new Map()); return }
    let live_ = true
    Promise.all(answerable.map((o) => o.turn
      ? read<TurnDetail>(`/api/turns/${encodeURIComponent(o.turn)}`).catch(() => null)
      : Promise.resolve(null)))
      .then((got) => { if (live_) setTurns(new Map(got.filter((t): t is TurnDetail => !!t).map((t) => [t.id, t]))) })
    return () => { live_ = false }
  }, [JSON.stringify(answerable.map((o) => o.turn))])
  if (!owed.length) return null
  return <div className="qc-decisions">
    {owed.map((o) => <Decision key={o.expectation} o={o} turn={o.turn ? turns.get(o.turn) : undefined} me={me?.participant ?? null} conversation={conversation} topic={topic} />)}
  </div>
}
