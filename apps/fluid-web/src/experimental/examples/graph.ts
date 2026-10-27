import { F3, type Example } from './model'

/* Bodies shared between a diagram and a whiteboard, so the gallery shows the
   same lines under both types: one reader (parseGraph), two intents. */
const REVIEW_FLOW = `# a flow with a decision, a loop and three groups
draft: "Write the change" kind=start group=Author
tests: "Run the tests" group=Author
pass: "Tests pass?" kind=decision group=Author
review: "Ask for review" group=Reviewer detail="Two approvals for anything touching storage"
ok: "Approved?" kind=decision group=Reviewer
fix: "Address comments" group=Author
merge: "Merge to main" group=Release
deploy: "Deploy" group=Release detail="Staged: canary first, then everyone"
done: "Done" kind=end group=Release
why: "Loops are fine: the layout breaks them itself" kind=note
draft -> tests
tests -> pass
pass -> review "yes"
pass -> fix "no"
review -> ok
ok -> merge "yes"
ok -> fix "changes asked"
fix -> tests
merge -> deploy -> done
why -> fix`

const SIGNUP_FLOW = `start: "Visitor lands" kind=start
form: "Fills the sign-up form"
valid: "Email valid?" kind=decision
send: "Send welcome mail"
retry: "Show the error"
done: "Account ready" kind=end
start -> form -> valid
valid -> send "yes"
valid -> retry "no"
retry -> form
send -> done`

export const graphExamples: Example[] = [
  /* ------------------------------------------------------------ timeline */
  {
    id: 'timeline-1',
    category: 'timeline',
    title: 'Product launch: three lanes, spans and moments',
    note:
      'Click an event for its detail and leave a note; step with Previous/Next; zoom with − / + (or Ctrl+wheel) and drag to pan. The author wrote only CSV and named its columns; the axis, lanes, colours and label packing are the renderer’s.',
    demands: [
      'Dates must be ISO (2026-03-05, 2026-03, 2026-03-05T14:30). “March 5” or “05/03/2026” are refused with a message, not guessed.',
      'A detail containing a comma must be in double quotes (it is CSV). A weak model forgetting that shifts every later cell; the row is then reported as having too many cells.',
      '“until” is inclusive of the period it names (until=2026-04 runs to the end of April). That is intuitive for people, but it is a rule to know.',
    ],
    source: `${F3}timeline version=1 title="Launch of Mentis 2" when=date what=event until=until group=team detail=detail
date,until,team,event,detail,owner
2026-01-12,2026-02-20,Engineering,Storage rewrite,"New store; migrations tested on a copy first",Ana
2026-02-02,,Engineering,Design freeze,,Ana
2026-02-23,2026-03-13,Engineering,Beta hardening,"Crash fixes only, no features",Raj
2026-03-16,,Engineering,Release candidate,,Raj
2026-03-30,,Engineering,General availability,Tagged and published,Ana
2026-04-06,2026-04-17,Engineering,Patch window,,Raj
2026-01-19,,Marketing,Messaging brief,,Lee
2026-02,,Marketing,Agency picked,"Month only: the exact day was not recorded",Lee
2026-03-02,2026-03-27,Marketing,Launch campaign,"Blog, video, two conference talks",Lee
2026-03-30T09:00,,Marketing,Launch post,Published at 09:00,Lee
2026-02-16,,Support,Docs outline,,Kim
2026-03-09,2026-03-20,Support,Train the support team,,Kim
2026-03-23,,Support,Help centre live,,Kim
2026-03-30,2026-04,Support,Launch surge rota,Extra cover through April,Kim
2026-04-20,,Support,First retrospective,,Kim
${F3}`,
  },
  {
    id: 'timeline-2',
    category: 'timeline',
    title: 'Incident, minute by minute (defaults: date and event columns)',
    note:
      'No attributes but version: the columns are simply called date and event, which are the defaults. Times of day use YYYY-MM-DDTHH:MM; zoom in to see minute ticks. Try writing 25:00 or 2026-02-30 to see the date check.',
    source: `${F3}timeline version=1 title="Checkout outage"
date,event
2026-05-14T13:58,Deploy 4812 goes out
2026-05-14T14:03,Error rate alert fires
2026-05-14T14:07,On-call acknowledges
2026-05-14T14:15,Rollback started
2026-05-14T14:22,Errors back to normal
2026-05-14T15:40,Incident closed
${F3}`,
  },
  {
    id: 'timeline-gantt',
    category: 'timeline',
    title: 'Gantt chart: PR branch open intervals and dependencies',
    note:
      'Gantt chart using the native timeline type: one lane per branch (group=), horizontal span bars from creation to merge (until=), and optional dependency links (parents=).',
    source: `${F3}timeline version=1 title="PR branch lifecycles — illustrative example data" when=start until=merged group=branch what=pr detail=detail id=pr parents=parent
start,merged,branch,pr,detail,parent
2026-07-25T07:20,2026-07-25T08:50,feat/gap-harvest-slice-a,#238,"3 commits · merged in 1h 30m",
2026-07-25T08:32,2026-07-25T08:50,experiment/memory-vs-file,#239,"3 commits · merged in 18m",
2026-07-25T09:33,2026-07-28T15:27,feat/agent-trial-authority,#240,"2 commits · waited 3 days to merge",#238
2026-07-25T16:31,2026-07-25T19:57,fix/verdict-overwrite,#242,"3 commits · merged in 3h 26m",#239
2026-07-25T20:56,2026-07-25T21:40,docs/accept-rate-floor,#245,"3 commits · merged in 44m",#242
2026-07-29T07:17,2026-07-29T19:20,feat/bulk-retag,#247,"2 commits · merged in 12h",#240
2026-07-29T19:34,2026-07-29T19:51,feat/a-gate-can-count-a-streak,#248,"2 commits · merged in 17m",#247
2026-07-30T00:03,2026-07-30T07:44,fix/the-preamble-answers,#249,"2 commits · merged in 7h 41m",#248
${F3}`,
  },

  /* ------------------------------------------------------------- diagram */
  {
    id: 'diagram-1',
    category: 'diagram',
    title: 'Sign-up flow (simple, with one loop)',
    note:
      'Nodes are “id: "Label"” lines, edges are “a -> b” lines; no positions anywhere. Click a box to see what comes from and goes to it, and leave a note. Try direction=right, or misspell an id in an edge.',
    demands: ['Every box needs a short id that edges refer to; a weak model may reuse an id or refer to the label instead of the id. Both are reported by line.'],
    source: `${F3}diagram version=1 title="Sign-up"
${SIGNUP_FLOW}
${F3}`,
  },
  {
    id: 'diagram-2',
    category: 'diagram',
    title: 'Code review: decisions, a loop, three groups and a note',
    note:
      'Groups become lanes (order from groups=…); the loop (fix -> tests) is drawn going back round the side. Tick “light the whole path” and select “Address comments” to see everything upstream and downstream. The whiteboard example “seeded from this diagram” has the identical body.',
    demands: [
      'Labels with spaces need double quotes, and detail="…" too. A label containing a double quote needs \\" — rare, but a weak model will not know it.',
      'group= must be spelled identically on every node of a group; “Reviewer” and “Reviewers” make two lanes (the second is reported as not in groups=…).',
    ],
    source: `${F3}diagram version=1 title="How a change ships" groups="Author,Reviewer,Release"
${REVIEW_FLOW}
${F3}`,
  },
  {
    id: 'diagram-git',
    category: 'diagram',
    title: 'Commit history graph: GitHub-style timeline',
    note:
      'Drawn natively with view=git from declared commit nodes and parent edges: branch tracks on the left with branch and merge curves, commit SHA badges, messages, authors and timestamps on the right.',
    source: `${F3}diagram version=1 view=git title="Commit and merge timeline — illustrative example data" groups="main,feat/gap-harvest-slice-a,feat/agent-trial-authority"
base: "d2ea956 (base)" group=main date="Jul 25 00:00" author="mentis"
c788: "feat(gaps): Slice A" group=feat/gap-harvest-slice-a date="Jul 25 07:20" author="builder"
c762: "experiment(gaps): replace falsifier" group=feat/gap-harvest-slice-a date="Jul 25 08:05" author="builder"
m238: "Merge PR #238" group=main date="Jul 25 08:50" author="Brian (GitHub)" tag="v0.1"
c399: "feat(authority): bounded trial" group=feat/agent-trial-authority date="Jul 25 09:33" author="builder"
c466: "test(authority): cover guards" group=feat/agent-trial-authority date="Jul 25 14:30" author="Mentis Dev"
m240: "Merge PR #240" group=main date="Jul 28 15:27" author="Brian (GitHub)"
base -> c788
c788 -> c762
c762 -> m238
base -> m238
m238 -> c399
c399 -> c466
c466 -> m240
m238 -> m240
${F3}`,
  },

  /* ---------------------------------------------------------- whiteboard */
  {
    id: 'whiteboard-1',
    category: 'whiteboard',
    title: 'Planning board: Now / Next / Later',
    note:
      'Zones come from groups=…; each card names its zone with group=. Drag a card to another zone, double-click to re-word it, “+ Card” to add one, “Connect two cards” then click two cards to link them. Source cards are solid, yours dashed; “Your changes” and the Degraded view say which is which.',
    demands: ['The zone word is group=, the same word the diagram uses for lanes. An author may expect zone= and gets an error naming the settings allowed.'],
    source: `${F3}whiteboard version=1 title="Q3 plan" groups="Now,Next,Later"
login: "Fix the login timeout" group=Now detail="Reported by three customers"
export: "CSV export" group=Now
audit: "Audit log" group=Next
sso: "Single sign-on" group=Next
mobile: "Mobile layout" group=Later
ideas: "Anything unplaced goes here" kind=note group=Later
login -> sso "unblocks"
${F3}`,
  },
  {
    id: 'whiteboard-2',
    category: 'whiteboard',
    title: 'Board seeded from the code-review diagram (identical body)',
    note:
      'Exactly the body of “Code review” under diagram, with the type word changed. The same reader reads it; the diagram’s groups become zones and cards fill each zone in flow order. Compare the two Degraded views: the diagram keeps notes on a fixed structure, the board records how you changed it.',
    source: `${F3}whiteboard version=1 title="How a change ships" groups="Author,Reviewer,Release"
${REVIEW_FLOW}
${F3}`,
  },
  {
    id: 'whiteboard-3',
    category: 'whiteboard',
    title: 'Board seeded from the sign-up diagram (no groups: the flow is the seed)',
    note:
      'The sign-up diagram’s body again. With no groups there are no zones, so cards start where the diagram’s layout puts them (one slot per box); moving one records a position in board slots, not pixels. direction=right would seed it sideways.',
    source: `${F3}whiteboard version=1 title="Sign-up"
${SIGNUP_FLOW}
${F3}`,
  },
]
