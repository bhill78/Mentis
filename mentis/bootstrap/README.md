# New Brain setup: baseline, then Welcome

Run explicitly as the owner, after creating a Brain:

```sh
python -m mentis.bootstrap "<brain-path>" --owner "@your-alias"
```

It installs the baseline (`baseline.py`, `baseline.json`) and then seeds the
welcome tour (`welcome.py`), in one transaction. `--check` reports what it
would match and write and writes nothing. `--no-tour` installs the baseline
only. `--update-tour` appends a newer tour's additions to an existing
tour (below). `--runtime <name>` sets the runtime of a newly designated carrier; it
never changes an existing one. Each step alone:
`python -m mentis.bootstrap.baseline` and `python -m mentis.bootstrap.welcome`
(the tour refuses until a baseline resolves).

## The baseline

`baseline.json` is the owner-approved release data (version 4): the owner and
`@Caretaker` Participants, five Personas (Caretaker, Planner, Builder,
Reviewer, Independent Reviewer), five rules, one decision, no lessons, one
Discipline (`cli-mars-development`), one Workflow (`software-change`), and the
designation that `@Caretaker` carries intake wearing the Caretaker Persona.
Version 2 added the Discipline and the Workflow (docs/operating-model.md §2).
Version 4 carries the owner's review ruling (2026-10-29) in the Workflow (plan,
plan review, review, correction with scoped re-review) and in
`coordinated-work`; on the owner's Brain they are established from
`docs/governance/workflow-2026-10-29.json`.
The Caretaker text is the one standing in the owner's Brain, not Turn #27's.
`carried_from` and `status` are provenance for people; nothing reads them, and
release text naming another Brain's record ids is refused. An item names
another by `baseline:<key>`, written as that item's entry in this Brain.

Items are ordinary Persona, rule, decision, Discipline and Workflow entries,
written as the owner, with origin `bootstrap:mentis-baseline@<version>/<key>`.
One `bootstrap-applied` act per version maps every key to its entry in this
Brain. The Discipline and Workflow need vocabulary revision
`operating-model-1`; a Brain made before it is revised first with
`tools/operating_vocabulary.py`, and the baseline refuses until it is.

- **New Brain.** Everything is established, the owner's act.
- **Brain with material.** Exact standing text is matched and nothing is
  written for it. A same-named Persona with other text stays standing and the
  shipped text is proposed to supersede it. A rule or decision with no exact
  match in a Brain already holding that Kind is refused: say
  `--match <key>=<entry>` or `--match <key>=new`. An existing owner and a
  resolved intake carrier are reused; a carrier wearing a Persona other than
  the matched Caretaker, unresolved designations, or ambiguous names are
  refused.
- **Later version.** Changed items are proposed to supersede the item's
  current entry, which follows the owner's successors. Nothing is established
  or ended; an existing identical proposal is reused; items already carrying
  the new text get nothing; items the owner ended are reported as `ended`;
  dropped items are reported as `removed`; new items arrive as proposals.
- **Same version again.** Writes nothing, and re-validates.

Before reporting success the run checks, inside its transaction, that every
key resolves to an entry of its Kind here, the owner is the owner, and intake
resolves to the baseline carrier wearing the current Caretaker item. Failure
refuses and rolls back.

## Welcome tour

The guide is the carrier the baseline resolves to, and `{guide_alias}` in the
tour text renders as its alias. Tour version 2 contains eight Topics, 36 main
posts, two passage comments with sample replies, two reactions, Guidance, and
a separate deep dive with Origin. It records sample Turns without dispatching
work. `bootstrap-applied` acts make each step idempotent. Broken excerpts are
checked before writes. Missing screenshot files are omitted. Held image
captions retain the prototype's names.

There is no installer or new-Brain setup entry point in this repository to
wire this into. `open_corpus` is a general storage seam used by tests and
existing Brains; it must not silently seed or designate. An external
installer should run the command above once after creation. Web startup
prints a warning when the baseline is missing or intake does not resolve,
with the setup command, and changes nothing.

## Updating an existing tour

A later tour version only adds. Its new material lives under `additions` in
`welcome_tour.json`, with its own version. A fresh Brain gets it in place,
in each Topic. A Brain already holding an earlier version is not changed by
an ordinary run. That run makes no writes and reports `tour_update_available`
(for example `{"from": 1, "to": 2, "with": "--update-tour"}`). To add the new
material, the owner runs (or `python -m mentis.bootstrap.welcome "<brain-path>"
--update-tour` for the tour step alone):

```sh
python -m mentis.bootstrap "<brain-path>" --owner "@your-alias" --update-tour
```

This appends the addition's Turns, comment and reactions to the existing
tour Conversation. They are filed under its Topics, found by name and then
by description, so a renamed Topic is still found. A Topic is opened again
only if both are gone, and the result lists it under `topics_opened`. No
existing Turn is edited, moved or replied to, so an owner's edits stand.
Running it again makes no writes. An addition's replies and anchors may only
name its own Turns; `validate_spec` refuses anything else before writing.
Version 1 Brains keep two sentences that version 2 rewrote for fresh seeds
(how `@` mentions work, how to bring in an agent). The appended posts give
the accurate account.

## Release data

`baseline.json`, `welcome_tour.json` and `screenshots/*.png` live beside the module under
`mentis/`. This repository has no wheel/setup packaging: `tools/release.py`
publishes a sparse clone of the entire `mentis/` directory, so these data
files ship with the release. Keep them tracked when adding another packaging
format.

## Retaking screenshots

The screenshots were taken by Mark IV's `capture_welcome`, which drove the
built web UI. This headless Mentis serves no interface, so that script is
gone; the shipped images are kept as data. Retake them with whatever
interface client serves this API.

## Existing Brain trial

Before seeding an existing Brain, take a SQLite online backup of `corpus.db`
(not a WAL file copy). Retain its held artifact bytes separately if the backup
must restore images too. Run the setup with `--check` first, then
from the reviewed checkout with the owner's alias. Check the returned conversation/deep-dive references in
the running UI. Do not restart production just to refresh its view. Stop on
a refusal or unexpected result; do not repair the existing store as part of
this tour setup.
