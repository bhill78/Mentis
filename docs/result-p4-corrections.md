# P4 readability correction integration

This branch composes the P4 proof `99b07ba448d49fd3b75336223a00017c79519bae`
with serving-binding opener `a7518f3a1b4dbd0092f9cbefd43b6e465855f233`, then
F3 correction `3a59d4a6fadcf2c8b83a6100c62649f29bb202f5`. The latter was returned
as implemented and verified, **not independently re-reviewed**, at composition
time. Its acceptance is a separate dependency. No shared checkout is changed.
The P4 source in the original proof matches candidate `bcd081001b6c9bc67210cc661486d44849beab32`;
the original review and evidence are retained separately, not overwritten.

## Corrected boundaries

- B1: Work launches read the exact group and follow `next_items_after` through
  `items_after`. A typed refresh refusal is returned unchanged. Omitted rows,
  malformed pages, repeated cursors and the 100-page limit mean uncheckable,
  never absent. Only a complete selected group can establish absence.
- B2: `ResultDestination.ref` carries the stored inspection/association reference.
  `destinationOfRef` supplies it, including an `opr-` resolving to a post. The
  fresh reader compares that reference; the opener separately compares the
  resolved navigation target. Labels, source provenance and Work basis remain
  separate facts. A custom Work adapter must carry `WorkResult.ref` into this field.
- B3: without both Work and group, posts, records and conversations read
  `/fluid/api/result-ref?ref=<exact-ref>`. This new single-reference GET uses the
  existing Fluid read boundary and the same `_Resolver` as Work/Needs You. It
  returns inspection and corpus-plus-instance identity together. It never creates
  a Work association or grants agent authority. Missing endpoint, HTTP refusal,
  malformed answer, changed target or unknown state refuses without navigation.
- B4/C1: graph `spaceKey` is only viewer provenance. The serving state comes from
  the live page binding, including the serving instance, at press and completion.
  The P4 adapter carries the original launch through `holds(entry, launch)`;
  centre movement or a newer opening silences stale completions. The F3 merge
  preserves the confirmed/unconfirmed/moved gates for artifacts, chooser and
  saved history. Both test include sets are retained.
- N1/N2: nested success shapes are checked before traversal, and only a known
  `ok` inspection with both affirmative availability flags can open. Unknown
  states retain a supplied reason and otherwise say the check could not be made.

## Host limits

The shared Quiet/Fluid hosts still do not mount these result adapters. This is
compiled composition and real disposable HTTP-route verification, not a rendered
or shipping UI change. The existing `results/HOST-INTEGRATION.md` remains the
host wiring contract; its serving binding is required, not inferred from the 3D
graph. Production hosts must omit test reader/serving overrides, bind the page,
use the compiled opener on all launch surfaces, and preserve their own navigation
guard and draft stores. Backend and client must both contain the direct reader;
an older backend safely refuses it. The default Rust route table forwards this
unowned route to Python; no Rust executable is verified by this work.

Freshness is a check at the press, not a lock until a later Go. The adapters
cannot atomically pin a server or stop a host's already scheduled navigation;
the host still owns its guarded continuation. Mounted browser, keyboard,
narrow-screen, actual draft-store and navigation acceptance remain with host
integration. No TEST, production, main, push or deployment is part of this branch.

## Reproduction

`tests/test_p4_corrections_routes.py` adapts the independent review's fixture and
Node probe to require the corrected results, with the original evidence preserved.
It runs the shipped client modules and default readers against real loopback HTTP,
including a continuation result, request alias, direct launches, worker-header
refusal, deletion, erasure and the real page binding. `work_result_freshness_unit`
and `quiet2_result_p4_unit` cover malformed/unknown answers, opaque cursors,
refresh/cycle refusal, centre/latest-opening movement, launch identity and all
three non-artifact routes. The final report records commands and counts on the
exact returned commit, separately from intermediate focused runs.
