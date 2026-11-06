/* PACKAGE D owns this module: open decisions, answerable where they are
   shown. Its mount is in B's margin, beside the runs.

   WHAT IS OWED HERE, ANSWERED HERE. `Conversation.owed` (`/api/conversations/
   <id>?batch=0`) is the whole, un-paged list of outstanding obligations --
   right even when the Turn they hang on is an older page the flow has not
   loaded -- but it carries no options: those live on the Turn's own
   `expectations`, read one at a time (`/api/turns/<id>`) the way a reader
   with "a handful of links learned from a first read" always has (`read`,
   api.ts). An obligation with no options offered is not drawn here; it is
   answered in the thread, in the owner's own words, as it always was.

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
  const options = expectation?.options ?? []
  if (!options.length) return null
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
    <p>{expectation?.because || o.expects}</p>
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
  const [turns, setTurns] = useState<Map<Id, TurnDetail>>(new Map())
  useEffect(() => {
    if (!owed.length) { setTurns(new Map()); return }
    let live_ = true
    Promise.all(owed.map((o) => read<TurnDetail>(`/api/turns/${encodeURIComponent(o.turn)}`).catch(() => null)))
      .then((got) => { if (live_) setTurns(new Map(got.filter((t): t is TurnDetail => !!t).map((t) => [t.id, t]))) })
    return () => { live_ = false }
  }, [JSON.stringify(owed.map((o) => o.turn))])
  if (!owed.length) return null
  return <div className="qc-decisions">
    {owed.map((o) => <Decision key={o.expectation} o={o} turn={turns.get(o.turn)} me={me?.participant ?? null} conversation={conversation} topic={topic} />)}
  </div>
}
