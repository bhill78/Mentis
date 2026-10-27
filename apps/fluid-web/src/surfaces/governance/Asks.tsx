import { useEffect, useMemo, useRef, useState } from 'react'
import { ago, useApi, type Expectation, type Id, type Turn } from '../../api'
import ActDialog, {
  answerAsk,
  answeredSaid,
  type ActAsk,
  type ActDispute,
  type ActItem,
  type ActName,
  type ActOutcome,
} from './ActDialogs'
import './Asks.css'
import type { Toast } from '../Toasts'
import type { useNotificationHistory } from '../notifications'
import { itemLine, itemWords, ITEMS_PATH, type NeedsItem, type NeedsItems } from '../../needsItems'
import { readProposal } from '../standing'
import { DecisionForm } from '../../experimental/types/decision'
import * as D from '../../experimental/decisions'

/* ------------------------------------------------------------------------ *
 * WHAT ASKS YOU, AND NOTHING THAT MERELY EXISTS.
 *
 * A PROPOSAL IS NOT AN OBLIGATION; AN EXPLICIT ASK IS. The counter counts
 * expectations recorded OF this participant that nobody has answered — "N
 * asks of you", or "Nothing asks you". Proposals are counted separately, said
 * separately, and the two numbers are never added together, because adding
 * them would turn somebody else's suggestion into something the owner owes.
 * The popover says the proposal count in its own sentence and offers a way to
 * go and look at them; it never pushes them into the count above.
 *
 * THE ACTION SET COMES FROM THE RECORD, NEVER FROM A LABEL ON THE ASK. An ask
 * does not carry a type. What the ask is about does: material that has not
 * been established is a proposal; material that stands and carries an open
 * challenge from the person asking is a challenge; material that stands and
 * shares a subject with something else here is an overlap; anything else is
 * an ask, and is offered what can honestly be done to what it names. Nothing
 * here reads a Kind name.
 *
 * LEAVE OPEN RECORDS NOTHING, AND THAT IS SAID BEFORE THE CLICK. Every ask
 * card carries the same sentence distinguishing the two paths, every action
 * carries a title saying what it will record, and each one says afterwards
 * what actually landed. An interface that only tells you afterwards has
 * already spent the decision.
 *
 * WHY EACH CARD READS FOR ITSELF. `/api/owed` answers the obligation — who is
 * asked, by whom, in which Conversation — and deliberately does not answer
 * what the ask is ABOUT, because owing is not a fact about material. So the
 * card reads the Turn the ask hangs on (which carries the question in its own
 * prose, and the expectation's recorded `material` and `options`), then the
 * register row for what that material is, and only where the material stands,
 * the challenges against it and the conflicts around it. Open asks are few by
 * construction; this is a handful of reads on a handful of cards, and the
 * alternative is a route that pretends owing and material are one fact.
 * ------------------------------------------------------------------------ */

/* ------------------------------------------------------------------ types -- */

/** One unanswered expectation of this participant, as `/api/owed` records it.
 *  Every field is the record's; nothing is computed here. */
export interface AskRow {
  expectation: Id
  expects: string
  conversation: Id | null
  conversation_name: string | null
  turn: Id | null
  number: number | null
  asked_by: Id | null
  asked_by_alias: string | null
  /** the requester's own reason for needing this. IT IS NOT THE QUESTION. */
  because: string | null
  options: number
  at: number
  /** A QUESTION OF A DECISION FORM (P7): its form and its own words. Such a
   *  question closes only on a reply naming it, sent at its form -- never on
   *  a plain reply to the post. Absent on every other ask. */
  form?: string | null
  question?: string | null
}

/** ONE CARD PER FORM: the questions of one decision form are one thing to
 *  answer, drawn as one form, and counted as one (P11). Every other ask is
 *  its own card. Order is kept: a form sits where its newest question is. */
export function onePerForm(asks: AskRow[]): AskRow[] {
  const seen = new Set<string>()
  return asks.filter((a) => {
    if (!a.form) return true
    if (seen.has(a.form)) return false
    seen.add(a.form)
    return true
  })
}

interface Owed {
  error?: string
  owed: AskRow[] | null
  total: number | null
  omitted: number | null
}

/** The Turn the ask was made in. Its prose is the question; its expectations
 *  carry what the ask names and the alternatives it stated.
 *
 *  THE SHARED SHAPE, BECAUSE A SECOND ONE GOT THE KEY WRONG. This declared the
 *  expectation's id as `expectation`; the route has always called it `id`, as
 *  `Expectation` in the API types says and as every other reader of a Turn
 *  already reads it. So the lookup below matched nothing, `material` was always
 *  empty, and every card fell through to the generic "asks you" — no item, no
 *  partner, no Compare, and no way to reach the dialog that replaces two
 *  proposals with one. Found by driving that dialog. */
type TurnRead = Pick<Turn, 'id'> & {
  parts?: { type: string; text?: string }[]
  expectations?: Expectation[]
}

/** One row of the register: what the record says this material IS. `state` is
 *  the server's own classification — the same four words `standing_state`
 *  produces — so this interface never computes a second answer to it. */
interface GovernedRow {
  entry: Id
  kind: string
  state: 'candidate' | 'stands' | 'ended' | 'replaced' | null
  summary: string
  author_alias: string | null
  disputed_by: Id[]
}

interface Governed {
  error?: string
  groups?: Record<string, GovernedRow[]>
  totals?: Record<string, number>
}

interface DisputeRow {
  link: Id
  reason: string | null
  by: Id | null
  open: boolean
}

interface Disputes {
  disputes?: DisputeRow[]
}

interface Context {
  conflicts?: { about: string | null; components: (string | null)[] }[]
}

/** What the RECORD says about the item, which is the only thing an action set
 *  may be derived from. */
export type AskKind = 'proposal' | 'challenge' | 'overlap' | 'other'

/** What each kind of ask is, said in the ask's own header. */
const ASK_WHAT: Record<AskKind, string> = {
  proposal: 'asks you to decide on a proposal',
  challenge: 'asks you to reconsider standing material',
  overlap: 'asks whether two standing items overlap',
  other: 'asks you',
}

/** Said in words, never by a hue alone: ended used to hold; replaced never did. */
const STATE_SAID: Record<NonNullable<GovernedRow['state']>, string> = {
  candidate: 'proposed',
  stands: 'stands',
  ended: 'ended',
  replaced: 'replaced before establishment',
}

/** THE HINT EVERY ASK CARRIES, and the only place the two paths are told
 *  apart before anything is clicked. */
const HINT =
  'Leave open records nothing: it stays owed. Any Answer (a choice, or your own words), Establish, Supersede and Set aside each record a response and close the ask.'

function clip(s: string, n = 80): string {
  const t = (s || '').replace(/\s+/g, ' ').trim()
  return t.length <= n ? t : t.slice(0, n - 1) + '…'
}

/** The prose of a Turn, which is where an ask's question actually lives. */
function proseOf(t: TurnRead | null): string {
  if (!t?.parts) return ''
  return t.parts
    .filter((p) => p.type === 'text' && p.text)
    .map((p) => p.text as string)
    .join('\n\n')
    .trim()
}

/* ---------------------------------------------- a form, answered here --- */

/** THE DECISION FORM THIS ASK IS A QUESTION OF, drawn with the one form every
 *  view uses, so a choice here posts the reply that names its question
 *  (`chose`) exactly as the post's own form does. Read by its post where it
 *  is on one -- the same read the post draws, so the two stay one -- and by
 *  the ask's id where it is on no post yet. */
export function FormHere({ ask, me, onChanged }: { ask: Pick<AskRow, 'expectation' | 'turn'>; me: Id | null; onChanged?: () => void }) {
  const byPost = D.useDecisions(ask.turn ? D.keyOf({ post: ask.turn }) : null)
  const onPost = byPost?.read ? D.groupsOf(byPost.read, [ask.expectation]) : null
  const needIds = !ask.turn || !!byPost?.error || (onPost !== null && onPost.length === 0)
  const byIds = D.useDecisions(needIds ? D.keyOf({ ids: [ask.expectation] }) : null)
  const read = onPost?.length ? byPost!.read! : byIds?.read ?? null
  const groups = onPost?.length ? onPost : read ? D.groupsOf(read, [ask.expectation]) : []
  if (!groups.length) {
    const failed = byIds?.error ?? (needIds ? null : byPost?.error)
    return <p className="ask-faint">{failed ? `Couldn't read the form (${failed}).` : 'Reading the form…'}</p>
  }
  return (
    <div className="ask-form" onKeyDown={(e) => e.stopPropagation()}>
      {groups.map((g) => <DecisionForm key={g.key} group={g} me={me ?? read?.you ?? null} onChanged={onChanged} />)}
    </div>
  )
}

/* ------------------------------------------------------------- one card --- */

export interface AskCardProps {
  onProposeNewVersion?: (entry: Id) => void
  ask: AskRow
  /** true in the popover, which triages across Conversations and so has to
   *  say which one each ask belongs to. False in a Turn, where it is already
   *  obvious and repeating it is noise. */
  showConversation?: boolean
  /** who is acting. Every act is somebody's, and without one nothing is
   *  offered rather than being attributed to nobody. */
  me: Id | null
  /** open the item in Governance. Navigation belongs to whoever owns the
   *  address, so this card asks rather than routing. */
  onInspect?: (entry: Id) => void
  /** put two items side by side without choosing between them. */
  onCompare?: (entry: Id, partner: Id | null) => void
  /** something was recorded; whoever holds the reads should take them again. */
  onChanged?: () => void
  /** THE HOST DRAWS THE ACT. Given, an act this card would open as a dialog is
   *  handed over with everything the dialog needs -- the same props, the same
   *  outcome handler -- so the host can run it in place (Fluid's Stage).
   *  Absent, the card opens its own dialog as it always has. */
  onAct?: (request: ActRequest) => void
  /** open the post this was asked on, at its form or block (P11's
   *  navigation). Absent, a form is still answered here; an input says
   *  where its Done is. */
  onOpenItem?: (item: NeedsItem) => void
}

/** One act an ask card asks its host to run: `ActDialog`'s own props, minus
 *  who acts and how cancelling closes it, which the host owns. */
export interface ActRequest {
  act: ActName
  item: ActItem | null
  ends?: ActItem[]
  partner?: ActItem | null
  dispute?: ActDispute | null
  ask?: ActAsk | null
  onDone: (outcome: ActOutcome) => void
}

export function AskCard({
  onProposeNewVersion,
  ask,
  showConversation,
  me,
  onInspect,
  onCompare,
  onChanged,
  onAct,
  onOpenItem,
}: AskCardProps) {
  const [dialog, setDialog] = useState<ActName | null>(null)
  const [approval, setApproval] = useState<Awaited<ReturnType<typeof readProposal>> | null>(null)
  const [busy, setBusy] = useState(false)
  /* WHAT LANDED, said where the decision was made. An act that does not
     visibly land is an act somebody will do twice. */
  const [landed, setLanded] = useState<string | null>(null)
  /* AN ANSWERED ASK COLLAPSES TO ONE LINE. Held here until the reread shows
     it; the record is still what closes the ask, not this. */
  const [answered, setAnswered] = useState<string | null>(null)

  const turn = useApi<TurnRead>(ask.turn ? '/api/turns/' + encodeURIComponent(ask.turn) : null)
  const mine = turn.data?.expectations?.find((e) => e.id === ask.expectation) as
    | (Expectation & { form?: string | null; question?: string | null })
    | undefined
  /* WHAT A REPLY CANNOT CLOSE. A question of a decision form closes only on
     a reply naming it, at its form; an input on a block closes only on Done
     at that block. Neither is offered a plain reply here. */
  const form = ask.form ?? mine?.form ?? null
  const input = ask.expects === 'input'
  /* THE QUESTION, not the post: a form's post holds several questions and
     the prose around them; each question has its own words. */
  const question = form ? (ask.question ?? mine?.question ?? '') : proseOf(turn.data)
  const named = useMemo(() => mine?.material ?? [], [mine])
  /* WHERE IT IS ANSWERED, as the Needs You entries say it (P11). */
  const items = useApi<NeedsItems>((form || input) && onOpenItem ? ITEMS_PATH : null)
  const needsItem: NeedsItem | null =
    items.data?.items?.find((it) => it.asks.includes(ask.expectation)) ??
    (form && ask.turn
      ? ({
          key: form, kind: 'decision', expects: ask.expects, form, asks: [ask.expectation],
          question: question || null, block: null, anchor: `decision-form:${form}`, post: ask.turn,
          post_number: ask.number, lead: null, conversation: ask.conversation,
          conversation_name: ask.conversation_name, asked_by: ask.asked_by ?? '',
          asked_by_name: ask.asked_by_alias ?? '', because: ask.because, at: ask.at,
        } as NeedsItem)
      : null)
  const entry = named[0] ?? null
  const capabilities = useApi<{ governance_actions: Record<string, boolean | string | null> }>(
    onProposeNewVersion && entry ? '/api/entries/' + encodeURIComponent(entry) : null,
  )
  const partnerId = named[1] ?? null

  /* ONE READ PER ITEM THE ASK NAMES, because `q` is a haystack search and its
     tokens are ANDed: asking for one item's id finds that item and cannot find
     the other. A single read for the first id was silently answering the second
     question with "no such row", so an ask naming two items rendered as an ask
     naming one -- no partner, no Compare, and no way to reach the choice of
     what a replacement ends. Two asks, because an ask names one item or two. */
  const reg = useApi<Governed>(
    entry ? '/api/governed?q=' + encodeURIComponent(entry) + '&limit=20' : null,
  )
  const partnerReg = useApi<Governed>(
    partnerId ? '/api/governed?q=' + encodeURIComponent(partnerId) + '&limit=20' : null,
  )
  const rows = useMemo(
    () => Object.values(reg.data?.groups ?? {}).flat() as GovernedRow[],
    [reg.data],
  )
  const partnerRows = useMemo(
    () => Object.values(partnerReg.data?.groups ?? {}).flat() as GovernedRow[],
    [partnerReg.data],
  )
  const item = rows.find((r) => r.entry === entry) ?? null
  const partnerRow = partnerId
    ? (partnerRows.find((r) => r.entry === partnerId) ?? null)
    : null

  const stands = item?.state === 'stands'
  const disputes = useApi<Disputes>(
    stands && entry ? '/api/governance/disputes?entry=' + encodeURIComponent(entry) : null,
  )
  const context = useApi<Context>(
    stands && ask.conversation
      ? '/api/context?conversation=' + encodeURIComponent(ask.conversation)
      : null,
  )

  /* THE ASKER'S OWN OPEN CHALLENGE, which is what makes an ask a challenge
     rather than a general request about standing material. Set aside is
     offered against exactly this one. */
  const theirs =
    disputes.data?.disputes?.find((d) => d.open && d.by === ask.asked_by) ?? null

  /* MENTIS DOES NOT CHOOSE BETWEEN OVERLAPPING ITEMS, and neither does this:
     the conflict is a group the record computed from a shared subject, and
     all the card does is notice that this item is in one. */
  const conflict = entry
    ? (context.data?.conflicts?.find(
        (c) => c.components.includes(entry) && c.components.length > 1,
      ) ?? null)
    : null
  const overlapWith =
    (conflict?.components.find((c) => c && c !== entry) as Id | undefined) ?? partnerId

  const kind: AskKind = !item
    ? 'other'
    : item.state === 'candidate'
      ? 'proposal'
      : stands && theirs
        ? 'challenge'
        : stands && conflict
          ? 'overlap'
          : 'other'

  const actItem: ActItem | null = item
    ? {
        entry: item.entry,
        kind: item.kind,
        text: item.summary,
        stands: item.state === 'stands',
        author_alias: item.author_alias,
        standing: item.state ? STATE_SAID[item.state] : null,
      }
    : null
  const actPartner: ActItem | null = partnerRow
    ? {
        entry: partnerRow.entry,
        kind: partnerRow.kind,
        text: partnerRow.summary,
        stands: partnerRow.state === 'stands',
        author_alias: partnerRow.author_alias,
        standing: partnerRow.state ? STATE_SAID[partnerRow.state] : null,
      }
    : null
  const actDispute: ActDispute | null = theirs
    ? { link: theirs.link, reason: theirs.reason, by: theirs.by, by_alias: ask.asked_by_alias }
    : null
  const actAsk: ActAsk = {
    expectation: ask.expectation,
    turn: ask.turn,
    conversation: ask.conversation,
    asked_by: ask.asked_by,
    asked_by_alias: ask.asked_by_alias,
    question: question || ask.because,
  }

  const who = ask.asked_by_alias ?? 'somebody the record does not name'

  const answer = async (reply: string) => {
    setBusy(true)
    try {
      /* CLOSED ONLY WHEN THE RECORD SAYS SO: the ask is reread after the
         reply, and the card says what the record says became of it. */
      const closed = await answerAsk(actAsk, reply, me)
      if (closed) setAnswered(reply)
      setLanded(answeredSaid(reply, who, closed))
      onChanged?.()
    } catch (e) {
      setLanded(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const done = (o: ActOutcome) => {
    setDialog(null)
    if (o.answered) setAnswered(`acted on the material: ${o.act}`)
    setLanded(o.said)
    onChanged?.()
  }

  /* OPEN AN ACT: here, as a dialog, or handed to the host with exactly the
     props the dialog below would have been given. */
  const openAct = (act: ActName, approved: Awaited<ReturnType<typeof readProposal>> | null = null) => {
    if (!onAct) {
      if (approved) setApproval(approved)
      setDialog(act)
      return
    }
    onAct({
      act,
      item: act === 'establish' ? approved?.successor ?? actItem : actItem,
      ends: act === 'establish' ? approved?.ends : undefined,
      partner: kind === 'overlap' ? actPartner : null,
      dispute: actDispute,
      ask: actAsk,
      onDone: done,
    })
  }

  /* I-42: once answered, the card is one line saying what was answered. The
     ask is out of the working view and the record is still one click away. */
  if (answered) {
    return (
      <div className="ask-card ask-done">
        <p className="ask-done-line">
          ✓ You answered {who}: “{clip(answered, 90)}”
        </p>
        {entry && onInspect && (
          <button className="ask-act" onClick={() => onInspect(entry)}>
            Inspect in Governance
          </button>
        )}
      </div>
    )
  }

  /* THE ACTION SET. Order is the approved order, and every entry says what it
     records before it is clicked. `records` is the title; it is not decoration
     and it is not the same sentence for two different acts. */
  type Action = { label: string; title: string; run: () => void; pri?: boolean }
  const inspect = (label: string): Action[] =>
    entry && onInspect
      ? [
          {
            label,
            title: 'Opens it in Governance. Records nothing.',
            run: () => onInspect(entry),
          },
        ]
      : []
  const canned = (reply: string): Action => ({
    label: `Answer “${reply}” & close`,
    title: `Records your reply to ${who} and closes this ask. Governed material does not change.`,
    run: () => void answer(reply),
  })
  const own: Action = {
    label: 'Answer in your own words…',
    title: `Records your reply to ${who} and closes this ask. Governed material does not change.`,
    run: () => openAct('respond'),
  }
  const leave: Action = {
    label: onProposeNewVersion ? 'Not now' : 'Leave open',
    title: 'Records nothing. The ask stays owed.',
    run: () => setLanded('Left open: nothing was recorded, and it is still owed.'),
  }
  const establish: Action = {
    label: 'Establish…',
    title: 'Opens the act that makes it stand. Nothing is recorded until you confirm.',
    run: () => {
      if (!entry) return
      setBusy(true)
      void readProposal(entry).then(p => openAct('establish', p))
        .catch(e => setLanded((e as Error).message)).finally(() => setBusy(false))
    },
    pri: true,
  }
  const dispute: Action = {
    label: 'Dispute…',
    title: 'Opens the act that joins an attributed note to the record. Standing does not change.',
    run: () => openAct('dispute'),
  }
  const supersede: Action = {
    label: onProposeNewVersion ? 'Propose new version…' : 'Supersede…',
    title: 'Opens the act that replaces it. Nothing is recorded until you confirm.',
    run: () => onProposeNewVersion && entry ? onProposeNewVersion(entry) : openAct('supersede'),
  }
  const setAside: Action = {
    label: 'Set aside…',
    title: 'Opens the act that answers the challenge. The dispute stays in the record.',
    run: () => openAct('set-aside'),
  }
  const compare: Action = {
    label: 'Compare',
    title: 'Puts them side by side. Nothing is recorded, and nothing is chosen for you.',
    run: () => onCompare?.(entry as Id, overlapWith ?? null),
    pri: true,
  }

  /* A FORM OR AN INPUT IS ANSWERED WHERE IT IS ANSWERED. Nothing here
     sends a reply that would leave it open while saying it closed. */
  const atForm: Action[] =
    needsItem && needsItem.post && onOpenItem
      ? [
          {
            label: input ? 'Open the post at the block' : 'Open the post at the form',
            title: input
              ? 'Opens the post this was asked on, at the block. Done there closes it. Records nothing.'
              : 'Opens the post this was asked on, at its form. Records nothing.',
            run: () => onOpenItem(needsItem),
            pri: input,
          },
        ]
      : []
  const replyable = !form && !input
  const offered: Action[] =
    onProposeNewVersion && kind === 'proposal'
      ? [...inspect('Inspect'), ...(capabilities.data?.governance_actions.establish === true ? [establish] : []),
          ...(capabilities.data?.governance_actions.dispute === true ? [dispute] : []), leave]
      : onProposeNewVersion && kind === 'challenge'
        ? [...inspect('Inspect challenge'), ...(capabilities.data?.governance_actions.edit === true ? [supersede] : []),
            ...(capabilities.data?.governance_actions.set_aside === true ? [setAside] : []), leave]
      :
    kind === 'proposal'
      ? [...inspect('Inspect'), establish, dispute, canned('Not now'), own, leave]
      : kind === 'challenge'
        ? [...inspect('Inspect challenge'), supersede, setAside, canned('Not now'), own, leave]
        : kind === 'overlap'
          ? [
              ...(entry && onCompare ? [compare] : []),
              supersede,
              canned('Keep both'),
              canned('Not now'),
              own,
              leave,
            ]
          : [
              ...inspect('Inspect'),
              ...(stands ? [supersede, dispute] : []),
              canned('Not now'),
              own,
              leave,
            ]
  /* The form has its own Leave open; an input keeps this one. */
  const actions: Action[] = replyable
    ? offered
    : [...atForm, ...offered.filter((a) => a !== own && !a.label.startsWith('Answer “') && (input || a !== leave))]

  return (
    <div className="ask-card">
      <p className="ask-head">
        <span className="ask-who">{who}</span> {ASK_WHAT[kind]}
        {showConversation && ask.conversation_name && (
          <> · <span className="ask-where">{ask.conversation_name}</span></>
        )}
        {' · '}
        <span className="ask-when">{ago(ask.at)}</span>
      </p>

      {form ? null : question ? (
        <blockquote className="ask-question">{question}</blockquote>
      ) : (
        <p className="ask-faint">
          {turn.loading
            ? 'Reading the Turn this was asked in…'
            : 'The record keeps no prose for this ask.'}
        </p>
      )}

      {item ? (
        <p className="ask-item">
          <span className="ask-kind">{item.kind}</span>{' '}
          <span className="ask-text">“{clip(item.summary)}”</span>{' '}
          {item.state && <span className="ask-standing">{STATE_SAID[item.state]}</span>}
        </p>
      ) : (
        named.length === 0 &&
        !turn.loading &&
        replyable && (
          <p className="ask-faint">
            This ask names no governed material. Answering it records a reply and nothing
            else.
          </p>
        )
      )}

      {form && <FormHere ask={ask} me={me} onChanged={onChanged} />}
      {input && (
        <p className="ask-faint ask-input-where">
          Waiting for your input
          {needsItem?.block?.block ? <> at the block <b>{needsItem.block.block}</b></> : ' at a block on the post'}
          . Done at that block closes it; a reply does not.
        </p>
      )}

      <div className="ask-actions">
        {actions.map((a) => (
          <button
            key={a.label}
            className={'ask-act' + (a.pri ? ' ask-pri' : '')}
            title={a.title}
            disabled={busy}
            onClick={a.run}
          >
            {a.label}
          </button>
        ))}
      </div>

      {replyable && <p className="ask-hint">{HINT}</p>}
      {landed && <p className="ask-landed">{landed}</p>}

      {dialog && (
        <ActDialog
          act={dialog}
          item={dialog === 'establish' ? approval?.successor ?? actItem : actItem}
          ends={dialog === 'establish' ? approval?.ends : undefined}
          partner={kind === 'overlap' ? actPartner : null}
          dispute={actDispute}
          ask={actAsk}
          me={me}
          onDone={done}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  )
}

/* --------------------------------------------------------- the counter --- */

export interface AsksCounterProps {
  notifications: ReturnType<typeof useNotificationHistory>
  onNotification: (t: Toast) => void
  /** whose obligations. Without one nothing is counted: the route refuses to
   *  answer for everybody, and so does this. */
  me: Id | null
  onInspect?: (entry: Id) => void
  onCompare?: (entry: Id, partner: Id | null) => void
  /** go and look at what has been proposed. It is a different list and a
   *  different question, so it is a different place. */
  onSeeProposals?: () => void
  onChanged?: () => void
  /** open the post an item was asked on, at its form (P11) */
  onOpenItem?: (item: NeedsItem) => void
}

/** "N asks of you" / "Nothing asks you", and the popover behind it.
 *
 *  THE TWO NUMBERS ARE NEVER BLENDED. The count is explicit asks. The
 *  proposal count is read separately, said in its own sentence at the foot of
 *  the popover, and never added to anything. */
export default function AsksCounter({
  me,
  onInspect,
  onCompare,
  onSeeProposals,
  onChanged,
  notifications,
  onNotification,
  onOpenItem,
}: AsksCounterProps) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    notifications.onPanel(open)
    return () => notifications.onPanel(false)
  }, [open, notifications.onPanel])
  const at = useRef<HTMLButtonElement | null>(null)
  const pop = useRef<HTMLDivElement | null>(null)

  const owed = useApi<Owed>(me ? '/api/owed?participant=' + encodeURIComponent(me) + '&limit=50' : null)
  /* Counted only, and asked for only while the popover is open: a proposal
     asks nothing of anybody, so nothing about it belongs in the app bar. */
  const proposed = useApi<Governed>(open ? '/api/governed?state=proposed&limit=1' : null)

  /* THE COUNT IS OPEN FORMS AND INPUTS (P11): one per decision form, one per
     decision asked as its own post, one per block waiting for input, one per
     other ask -- never one per question. The same read as Fluid's bell. */
  const items = useApi<NeedsItems>(me ? ITEMS_PATH : null)
  const asks = owed.data?.owed ?? []
  /* THREE ANSWERS, AND ONLY ONE OF THEM IS "nothing". `/api/owed` deliberately
     answers `{error, owed: null, total: null}` where it cannot answer, and no
     read is made at all while `me` is null -- which is the state of the bar on
     first paint. All three used to render the positive claim "Nothing asks
     you", so the default before identity resolved was a statement that
     somebody waiting for an answer is not waiting. `null` is UNKNOWN here and
     claims neither, exactly as the proposal count six lines below already
     does. */
  const n: number | null = items.data && !items.data.unknown ? items.data.counts?.total ?? null : null
  const words = itemWords(items.data?.counts ?? null)
  /* And why it is unknown, in the record's own words where it gave any. */
  const unanswered: string | null =
    n !== null
      ? null
      : !me
        ? 'Nobody is named as you yet, so the record has not been asked.'
        : items.error
          ? items.error
          : items.data?.unknown
            ? items.data.why ?? 'This brain names no owner.'
            : 'Reading what is owed…'
  const p = proposed.data?.totals?.proposed ?? null
  /* One ask is an ask. The count is read aloud by whoever reads the bar, and
     "1 asks of you" is not a sentence anybody says. */
  const said =
    n === null ? 'Asks of you (not known yet)' : n > 0 ? `${words} waiting on you` : 'Nothing asks you'

  useEffect(() => {
    if (!open) return
    /* ESCAPE CLOSES THIS BEFORE IT CLOSES ANYTHING ELSE, and a click outside
       closes it too. Capturing, so a surface behind does not act first. */
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setOpen(false)
      }
    }
    const away = (e: MouseEvent) => {
      const t = e.target as Node
      if (!pop.current?.contains(t) && !at.current?.contains(t)) setOpen(false)
    }
    window.addEventListener('keydown', key, true)
    window.addEventListener('mousedown', away)
    return () => {
      window.removeEventListener('keydown', key, true)
      window.removeEventListener('mousedown', away)
    }
  }, [open])

  return (
    <span className="asks-wrap">
      <button
        ref={at}
        className={'asks-counter' + (open ? ' on' : '') + ((n ?? 0) > 0 ? ' asks-owed' : '')}
        aria-expanded={open}
        aria-label={`${said}; ${notifications.unseen} unseen notifications`}
        title={`${said}. Recent notifications: ${notifications.unseen} unseen. Explicit requests for your decision; proposals alone are not counted.`}
        data-owed={n ?? undefined}
        onClick={() => setOpen(!open)}
      >
        {/* A MARK AND A NUMBER (UI polish 2, #9). The owner: "Nothing asks
            you" should be an icon, a star or a triangle, with the number of
            items that need attention. A star, because a triangle reads as a
            warning even at 0. The sentence is still its name -- read aloud
            and shown on hover -- so nothing it said is lost; unknown is a
            dash, never a 0, for the reason given above. */}
        <svg className="asks-mark" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
          <path
            d="M9 1.9l2.15 4.5 4.95.62-3.63 3.42.92 4.9L9 12.95l-4.39 2.39.92-4.9L1.9 7.02l4.95-.62Z"
            strokeLinejoin="round"
            strokeWidth="1.4"
          />
        </svg>
        <span className="asks-n" aria-hidden="true">
          {n === null ? '–' : n}
        </span>
        {notifications.unseen > 0 && <span className="notification-dot" aria-hidden="true" />}
      </button>

      {open && (
        <div className="asks-pop" ref={pop} role="dialog" aria-label="Needs you and recent notifications">
          <h2 className="asks-title">Needs you</h2>
          <p className="asks-sub">
            Explicit requests only: someone asked you, and you owe an answer. Quick
            responses are beside each one; Compare and Inspect open Governance where there
            is room to decide.
          </p>

          {/* ONE ENTRY PER FORM (P11), each opening its post at the form. */}
          {n !== null && n > 0 && (
            <div className="asks-items" data-needs-words={words}>
              <p className="asks-sub"><b>{words}</b> waiting on you.</p>
              {(items.data?.items ?? []).map((it) => {
                const { kind, what } = itemLine(it)
                return (
                  <button key={it.key} className="asks-item" data-item={it.key} data-kind={it.kind} disabled={!it.post || !onOpenItem}
                    title={it.post ? 'Opens the post at the form. Records nothing.' : 'Not on a post yet'}
                    onClick={() => { if (it.post && onOpenItem) { setOpen(false); onOpenItem(it) } }}>
                    <span className="asks-item-kind">{kind}</span>
                    <span className="asks-item-what">{what}</span>
                    <span className="asks-item-where">{it.conversation_name ?? 'a conversation'}{it.post_number != null ? ` · #${it.post_number}` : ''}</span>
                  </button>
                )
              })}
            </div>
          )}
          {owed.error && <p className="ask-landed">{owed.error}</p>}
          {unanswered !== null ? (
            <p className="asks-empty">{unanswered}</p>
          ) : asks.length === 0 ? (
            <p className="asks-empty">Nothing asks you.</p>
          ) : (
            onePerForm(asks).map((a) => (
              <AskCard
                key={a.form ?? a.expectation}
                ask={a}
                showConversation
                me={me}
                onInspect={onInspect}
                onCompare={onCompare}
                onChanged={onChanged}
                onOpenItem={onOpenItem ? (it) => { setOpen(false); onOpenItem(it) } : undefined}
              />
            ))
          )}

          {/* THE PROPOSAL COUNT, SAID SEPARATELY AND NEVER ADDED IN. Absent
              until the read answers, because zero is a claim and a pending
              read is not. */}
          {p !== null && p > 0 && (
            <p className="asks-foot">
              {p} other proposals ask nothing of you. They reach nobody until someone
              establishes them.{' '}
              {onSeeProposals && (
                <button className="asks-link" onClick={onSeeProposals}>
                  See them in Brain Governance
                </button>
              )}
            </p>
          )}
          <section className="notifications-recent" aria-label="Recent notifications">
            <h2 className="asks-title">Recent</h2>
            {notifications.storageError && <p className="asks-sub">{notifications.storageError}</p>}
            {!notifications.items.length && <p className="asks-empty">No recent notifications.</p>}
            {notifications.items.map(t => <button className="notification-row" key={t.key} onClick={() => {
              onNotification(t)
              setOpen(false)
            }}>
              <span className="toast-kind">{t.kind === 'result' ? 'Result' : 'For you'}</span>
              <time dateTime={new Date(t.at).toISOString()}>{new Date(t.at).toLocaleString()}</time>
              <strong>{t.headline}</strong>
              <span>in {t.where}</span>
              {t.excerpt && <span>{t.excerpt}</span>}
              {t.more > 0 && <span>{t.more} more {t.kind === 'result' ? 'results' : 'requests'} in {t.convName}</span>}
            </button>)}
          </section>
        </div>
      )}
    </span>
  )
}
