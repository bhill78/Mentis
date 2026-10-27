/* EXPERIMENTAL: the Dungeon Helper, a conversation surface with a LOCAL model.

   The model (through the existing Mark IV local-model path, run by the helper
   backend in experiments/dungeon_helper) only chooses WHAT to show and WHICH
   interaction helps. The backend retrieves material within this helper's
   scope and compiles the model's intents into existing renderer blocks; this
   surface draws them with the ordinary prose reader, and pins what the model
   asked to keep beside the conversation.

   Every turn shows what went to the model and what came back, so what is
   "sent back" on later turns is visible rather than asserted.

   NOTHING IS CONTACTED UNTIL THE READER PRESSES CONNECT (./external.ts). The
   requested scope and that the backend is outside Mentis are said at rest. */
import { useEffect, useRef, useState } from 'react'
import { Prose } from '../../prose'
import type { TypeDef } from '../api'
import { HELPER_ORIGIN, Stale, ask, connect, declare, disconnect, linkOf, useExternal } from './external'
import { pinOne } from './ref'
import './helper.css'
import { helperSpec } from '../spec/helper'

/** The backend grants whatever scope the block asks for (experiments/dungeon_helper/server.py: "not an authorisation system"). */
export const HELPER_SCOPE_REQ_DETAIL =
  'Experiment backend, outside Mentis. The scope is whatever this block asks for; nobody checks whether you may see DM material. Campaign data is a disposable test file, not Mentis material.'
interface Turn { user: string; condition: 'A' | 'B'; markdown: string; trace: any; error?: string }
interface Held { turns?: Turn[]; hs?: any }

export const helper: TypeDef<{ scope: 'player' | 'dm' }, Held> = {
  ...helperSpec,
  Rich({ data, state, set, help, menu }) {
    useExternal()
    const [text, setText] = useState('')
    const [busy, setBusy] = useState<{ since: number; cond: string; session: string } | null>(null)
    const [now, setNow] = useState(Date.now())
    const [err, setErr] = useState<string | null>(null)
    const [note, setNote] = useState<string | null>(null)
    const turns = state?.turns ?? []
    const link = linkOf(help.key, data.scope)
    const on = link.status === 'on'
    /* Only a question asked under THIS connection is in progress; one left from an ended connection is not. */
    const asking = busy && on && busy.session === link.session ? busy : null
    /* The block's scope was edited, here or while this view was gone (an invalid
       source in between unmounts it): the connection made for the old scope ends;
       it is never reused. The block's last scope is kept by ./external.ts. */
    const was = useRef<string | undefined>(undefined)
    useEffect(() => { const release = declare(help.key, data.scope, was.current); was.current = data.scope; return release }, [help.key, data.scope])
    useEffect(() => { if (!busy) return; const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t) }, [busy])

    const send = async (condition: 'A' | 'B', message = text) => {
      if (!message.trim() || asking || !on) return
      const { session, scope } = link
      const mine = { since: Date.now(), cond: condition, session }
      setBusy(mine)
      setErr(null)
      setNote(null)
      try {
        const r = await ask(help.key, data.scope, { message, state: state?.hs ?? {}, condition })
        const turn: Turn = { user: message, condition, markdown: r.markdown, trace: r.trace }
        set({ turns: [...turns, turn], hs: condition === 'B' ? r.state : state?.hs })
        for (const id of r.pins ?? []) pinOne(id, help.key, `Dungeon Helper (${scope})`, session)
        setText('')
      } catch (e) {
        // Asked under a connection since ended: nothing is shown, held or pinned.
        if (e instanceof Stale) setNote('An answer arrived after that connection ended. It was discarded: nothing was shown, kept or pinned.')
        // A lost session is said by the connection line, with Reconnect; the question stays in the box.
        else if ((e as any).code !== 403) setErr(`The helper could not answer: ${(e as Error).message}`)
      } finally {
        setBusy((b) => (b === mine ? null : b))
      }
    }

    // The A/B comparison is part of the experiment, not of reading: it lives in the block's ⋯.
    menu?.([{ label: 'Experiment', items: [
      { label: 'Ask without renderers (A)', disabled: !on || !!asking || !text.trim(), onSelect: () => send('A') },
    ] }])

    return (
      <div className="rb-dh">
        <details className="rb-disclosure rb-dh-limit">
          <summary><b>External experiment. Scope {data.scope} is requested, not authorised.</b></summary>
          <div className="rb-disclosure-body">
            <p>{HELPER_SCOPE_REQ_DETAIL}</p>
            <p>
              For comparison, ⋯ › Ask without renderers (A) puts the same question to the same model, answered as plain text from full
              records.
            </p>
            <div className="rb-dh-who rb-muted">
              <b>Dungeon Helper</b> · local model <code>{turns.at(-1)?.trace?.observed_model ?? 'qwen3.5:9b'}</code> via the
              Mark IV local-model path · external experiment backend <code>{HELPER_ORIGIN}</code>, outside Mentis
            </div>
          </div>
        </details>
        <div className="rb-dh-scope" data-helper-scope>
          Scope <b>{data.scope}</b> is requested by this block, not authorised. The experiment backend grants whatever
          scope it is asked for; connecting is not DM or player authorization, and Mentis enforces nothing here.
        </div>
        <Connection link={link} scope={data.scope} onConnect={() => { setErr(null); setNote(null); connect(help.key, data.scope) }} onDisconnect={() => disconnect(help.key, data.scope)} />
        <div className="rb-dh-turns">
          {turns.length === 0 && on && (
            <p className="rb-muted">
              Try: “Who was the wizard we met at the inn?” · “Keep her up.” · “Make me a timeline of what happened last session.” ·
              “Put these clues somewhere I can work through them.” · “Make something I can use during the fight.”
            </p>
          )}
          {turns.map((t, i) => (
            <div key={i} className="rb-dh-turn">
              <div className="rb-dh-user">{t.user} {t.condition === 'A' && <span className="rb-tag">A: plain text, no renderers</span>}</div>
              <div className="rb-dh-reply">
                {t.condition === 'A' ? <div className="rb-dh-plain">{t.markdown}</div> : <Prose src={t.markdown || '(the helper chose nothing to show)'} scope={`${help.key}/t${i}`} />}
              </div>
              <Trace t={t} />
            </div>
          ))}
          {asking && (
            <p className="rb-muted">
              {turns.at(-1)?.trace?.model ?? 'the local model'} is working ({asking.cond}) … {Math.round((now - asking.since) / 1000)} s
            </p>
          )}
          {err && <p className="rb-bad">{err}</p>}
          {note && <p className="rb-muted" data-helper-discarded>{note}</p>}
        </div>
        <div className="rb-dh-input">
          <textarea
            value={text}
            disabled={!on}
            aria-label="Ask the helper"
            placeholder={on ? 'Ask the helper…' : 'Connect to the experiment backend to ask the helper'}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send('B') } }}
          />
          <div className="rb-row">
            <button className="btn primary" disabled={!on || !!asking || !text.trim()} onClick={() => send('B')}>Ask</button>
            <span className="rb-grow" />
            {turns.length > 0 && <button className="btn quiet" onClick={() => set(undefined)}>Start over</button>}
          </div>
        </div>
      </div>
    )
  },
  readable(d, _a, s) {
    const out = [
      `A conversation with the experimental Dungeon Helper (local model, behind an experiment backend outside Mentis), requesting ${d.scope} scope: requested, not authorised. Nothing is contacted until the reader connects. The conversation is surface state, not Mentis material.`,
      `scope ${d.scope} is requested, not authorised. ${HELPER_SCOPE_REQ_DETAIL}`,
    ]
    for (const t of s?.turns ?? []) out.push(`> ${t.user}`, `  (${t.condition}) ${(t.trace?.actions ?? []).map((a: any) => a.verb + ' ' + (a.ids ?? [a.id ?? a.text]).join(' ')).join('; ') || t.markdown.slice(0, 200)}`)
    return out.join('\n')
  },
  handoff(d, _a, s) {
    return { scope: d.scope, scope_is: 'requested by the block; not authorization, not enforced by Mentis', turns: (s?.turns ?? []).map((t) => ({ user: t.user, condition: t.condition, model_output: t.trace?.calls?.map((c: any) => c.raw) })) }
  },
}

/** Whether this tab may contact the experiment backend for this helper, and the door to change it. */
function Connection({ link, scope, onConnect, onDisconnect }: {
  link: ReturnType<typeof linkOf>; scope: string; onConnect: () => void; onDisconnect: () => void
}) {
  if (link.status === 'on')
    return (
      <div className="rb-dh-link on" data-helper-link="on" role="status">
        <span>
          Connected to {HELPER_ORIGIN} · session <code>{link.session.slice(0, 6)}…</code> opened requesting scope{' '}
          <b data-helper-connected-scope>{link.scope}</b>. Every campaign reference in this tab naming this session is read while
          connected; the session id is written into replies and pins, so it is not a secret.
        </span>
        <span className="rb-grow" />
        <button className="btn quiet" onClick={onDisconnect}
          title="Stops this tab using the session and reading every campaign reference under it. The experiment backend keeps the session until it restarts.">
          Disconnect
        </button>
      </div>
    )
  if (link.status === 'connecting')
    return (
      <div className="rb-dh-link" data-helper-link="connecting" role="status">
        <span>Connecting to {HELPER_ORIGIN}, requesting scope <b>{scope}</b>…</span>
        <span className="rb-grow" />
        <button className="btn quiet" onClick={onDisconnect} title="Stop connecting. A session opened anyway is never used.">Cancel</button>
      </div>
    )
  return (
    <div className="rb-dh-link" data-helper-link={link.status} role="status">
      <span>
        {link.status === 'failed'
          ? <span className="rb-bad">Could not connect ({link.error}). Is the backend running? python experiments/dungeon_helper/server.py</span>
          : link.status === 'lost'
            ? <span className="rb-bad">The experiment backend no longer knows this session ({link.error}); it may have restarted. Nothing was sent again.</span>
            : <>Not connected. Nothing has been sent. Connect opens one session at {HELPER_ORIGIN}, requesting scope <b>{scope}</b>, and sends it what you ask.</>}
      </span>
      <span className="rb-grow" />
      <button className="btn primary" onClick={onConnect}>{link.status === 'off' ? 'Connect' : link.status === 'failed' ? 'Retry' : 'Reconnect'}</button>
    </div>
  )
}

function Trace({ t }: { t: Turn }) {
  const tr = t.trace ?? {}
  const calls = tr.calls ?? []
  const saw = calls.map((c: any) => c.usage?.input_tokens).filter(Boolean)
  const out = calls.map((c: any) => c.usage?.output_tokens).filter((x: any) => x !== undefined)
  return (
    <details className="rb-dh-trace">
      <summary>Model trace</summary>
      <div className="rb-disclosure-body">
        <div className="rb-muted">
          {tr.condition && `Condition ${tr.condition} · `}
          prompt ≈{tr.prompt_tokens_est} tokens (model saw {saw.join(' + ') || '?'}) · model wrote {out.join(' + ') || '?'} tokens ·{' '}
          {calls.map((c: any) => c.s).join(' + ')} s{calls.length > 1 ? ' · repaired once' : ''}
          {tr.problems?.length ? ` · ${tr.problems.length} unresolved problem(s)` : ''}
        </div>
        <div className="rb-muted">Retrieved within scope “{tr.scope}”: {(tr.retrieved ?? []).join(', ')}</div>
        {tr.first_problems?.length > 0 && <div className="rb-bad">First-reply problems: {tr.first_problems.join(' · ')}</div>}
        <div className="rb-lbl">What the local model wrote</div>
        {calls.map((c: any, i: number) => <pre key={i} className="rb-pre">{c.raw || '(nothing)'}</pre>)}
        <div className="rb-lbl">The whole prompt it was given</div>
        <pre className="rb-pre">{tr.prompt}</pre>
      </div>
    </details>
  )
}
