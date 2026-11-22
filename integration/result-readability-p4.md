# P4 — readability at the press, for post, Brain-record and conversation results

What this is, what is merged here, what is not, and exactly what stands in the
way of the rest. Written against `result-p4-readability` at the commit that
carries it; the opener-side half is `result-readability-p4.patch` beside this
file.

## The defect

A result row says what the server said when the page last read it. Between that
read and the press a post can be deleted, a conversation permanently deleted
with everything in it, and a record can stop being readable.

The explicit **artifact** open already asks again on the press
(`results/refRead.ts` over `GET /api/artifacts/<ref>?describe=1`). The other
three destinations do not. Their readers are the page's own guarded moves —
`openFromDock` / `pickConversation` / `enterBrain` — which report **the guard's
outcome and the navigation**, never whether the target is still readable. So a
denied, deleted or unreadable post, record or conversation was discovered by
**arriving at it**: the press moved the reader out of where they were, and the
destination page, not the press, said it could not be read.

Recorded as discovered work `ent-ad53f85e4add` / `opr-234d8422c98b`.

## What was assessed, and what already worked

The server side already answers this, freshly, and in its own words. Probed
directly against a synthetic fixture Brain:

| target | after it stops being readable | reported |
| --- | --- | --- |
| post, deleted | `state: deleted`, `available: false`, `opens: null` | `"This post was deleted."` |
| post, permanently deleted | `state: erased` | `"This was permanently deleted with its conversation."` |
| post with no home conversation | `available: false`, `opens: null` | its own sentence |
| record / conversation not held | `state: missing` | `"This Brain holds nothing with this id."` |
| anything that raised | `state: unreadable` | `"This could not be read."` |

That is `mentis/fluid/inspect.py` `_Resolver.of`, which
`mentis/operational/result_destinations.py` `enrich` already calls **outside
every cache** on each read of `/api/work/<id>`, stamping
`availability_checked_at`.

**So no new route, no new parameter and no new reader was needed, and none was
added.** What was missing was that nothing asked it again at the moment of the
press.

One honest limit found by probing: a conversation **in Trash** still reports
`available: true, opens: 'conversation'`. That is not treated as a defect here —
Trash is a list a reader can open from — but it is not pinned either, and is
named so a reviewer can disagree.

## The mechanism

The press re-reads **the result page the pressed row came from**, for the one
group it is in:

```
GET /api/work/<expectation>?result_group=<group>
```

the existing route (`workDetailPath`), which re-runs the existing reader for
exactly those items. `ResultDestination` already carries `work` and `group`, so
nothing new has to be remembered to ask.

**No authorisation rule is decided anywhere on this path.** The read goes
through the same door as the same viewer; the module can only ever **refuse** an
open the stale row offered, never grant one.
`tests/test_result_readability_contract.py::test_re_reading_gains_no_reach_it_did_not_have`
pins that the readability answer does not depend on who asks, so asking again
buys no reach.

Fail-closed order, in `src/work/freshness.ts` `verdict`:

1. the reader moved on since the press → **dropped**: nothing said, nothing moved;
2. the page has moved to another Brain → refused in the page's own words;
3. the read failed → refused (`ResultsRefreshRequired` → "read the results again");
4. the answer is about other work, the group is gone, the row is gone, or the
   row now answers as an artifact → refused;
5. `available` **and** `opens` must both say yes, and `opens` must still be what
   was pressed;
6. only then, open — **at the facts the fresh answer gave**, never the row's.

## What is merged, on this branch

| part | where |
| --- | --- |
| the decision module | `apps/fluid-web/src/work/freshness.ts` |
| its contract widening (`number`, `conversation_name`, both already sent) | `apps/fluid-web/src/work/contract.ts` |
| 24 cases over the shipped module | `apps/fluid-web/tests/work_result_freshness_unit.ts` |
| what the press rests on, at the route it calls | `tests/test_result_readability_contract.py` (6 cases) |

## What is NOT merged, and exactly why

**The host wiring is not mounted anywhere on this branch, and nothing here
claims it is.** Nothing in this tree renders or presses a Work result item:
`result_groups` / `result_summary` are typed and read by nothing. The surface
that presses them is `apps/fluid-web/src/quiet2/results/` on the sibling branch
`result-target-opener`, which this branch does not contain.

Three exact blockers:

1. **The opener is unreviewed and under re-review.** `result-target-opener`
   9118db60 is the correction returned at Conversation post `ent-4b624cbee29b`
   and is being independently re-reviewed under an exclusive lease on
   `result-opener-rereview-9118db60`. Merging it here would carry unreviewed
   work into a reconciled TEST baseline.
2. **Neither branch compiles against the other alone.** `freshness.ts` needs the
   result-projection half (`workDetailPath`, `ResultsRefreshRequired`,
   `ResultPage`/`WorkResult`), which is on **this** branch and not on the
   opener's; the opener's `results/*` needs `address.ts`'s result arm,
   `places.ts` `backTo` and `viewer/viewableOfItem.ts`, which are on **its**
   branch and not on this one. Verified: applying the patch to 9118db60 alone
   fails to typecheck with `Module '"./api"' has no exported member
   'workDetailPath'`.
3. **The host members the wiring needs do not exist until that merge.**
   `ResultPage` gains `viewer?`, `brainMoved?` and `resultNow?` — all optional,
   all defaulting to what the module does on its own.

### The patch, and that it was actually tested

`result-readability-p4.patch` is the opener-side half, as a real diff against
9118db60: `results/refNow.ts` (new), the `read` adapter in `results/mount.ts`,
the read gate in `results/opener.ts` lifted from the file route to all four, and
`tests/quiet2_result_p4_unit.ts` (46 checks against the real composition).

It was applied and run, in a **disposable clone of its own**
(`result-p4-opener-integration`, separately claimed; the builder's clone and the
re-review's leased worktree were read, never written):

- `git merge --no-ff` of this branch into 9118db60 + the patch: **one conflict**,
  `apps/fluid-web/tsconfig.test.json`, where both branches append to the same
  explicit test-include list. Resolved by taking both lists. Nothing else
  conflicted.
- On that integrated tree: `npm run build` exit 0; `npm run typecheck:tests`
  exit 0; `node tests/run.mjs` 146 suites, all ok — including the opener's own
  re-review falsifier suites (`quiet2_result_mount_unit`,
  `quiet2_result_opener_unit`), which this patch changes.
- Targeted + boundary pytest on that tree: 144 passed, 23 skipped, 0 failed,
  0 errors (the 23 are the known `MENTIS_R3_FRONT names no front` skips).
- Mutation-checked both halves: reverting the `mount.ts` adapter to
  `{how:'unchecked'}`, and reverting the `opener.ts` gate to the file route
  alone, each fail `quiet2_result_p4_unit` on its own first assertion.

### What it still does not reach

Nothing rendered and nothing in a browser. These are the real calls against the
real stores, checked without a DOM, a Brain or a server — the same limit the
opener's own suites state. A mounted candidate still owes its own review and its
own rendered check.
