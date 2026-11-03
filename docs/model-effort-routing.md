# Model and effort routing

Mentis picks a model and an effort for work when nobody named them, using what
MARS advertises. This is operational routing, not authority. A named runtime,
model or effort is never replaced, and nothing here grants anything. There is no
classifier, scheduler or model registry: the code is `mentis/core/routing.py` and
`MentisService.execution_select`.

## What MARS provides

`_mars/backends` adds two fields to each backend:

- `routingModels`: `[{id, tier, efforts, defaultEffort?}]`
- `effectiveDefaultModel`: the model that runs when none is asked for

Automatic routing only reaches tuples that MARS advertises:

- Tiers are `economy`, `coding` and `frontier`.
- Efforts are ordered `none < minimal < low < medium < high < xhigh < max`.
- `default`, `ultra`, other values and untagged aliases can only be named.

## The tier a request needs

Only structured fields count, never the words of the brief.

| Input | Tier |
| --- | --- |
| `authority_sensitive: true` (request or activity), any `review_of`, or a review Persona | frontier |
| The stronger of the activity's `default_tier` and the delegator's `advisory_tier` | that tier |
| `difficulty`: `mechanical` | economy |
| `difficulty`: `bounded`, `routine` | coding |
| `difficulty`: `complex`, `architecture`, `debugging` | frontier |

Each row beats the rows below it. `ordinary` and `default` imply no tier. The
target efforts are `low`, `medium` and `high` for the three tiers. Selection takes
a model at or above the tier, at the least advertised effort at or above the
target, preferring the least sufficient tuple.

## What selection does

| Situation | Result |
| --- | --- |
| Nothing named, adequate tuple survives | Least sufficient tuple |
| Nothing named, tuples exist, none adequate | Refused, naming what was considered; the tier is never lowered |
| No tuples on any eligible runtime | Legacy selection, `tier_unfulfilled=no_catalogue_metadata` |
| Fixed field, tier can fill the rest | Filled inside the fixed field |
| Fixed field, tier cannot be met | Runs as fixed, remainder left to the runtime, `tier_unfulfilled=fixed_binding` |
| Named runtime unavailable or lacking a required capability | Refused |
| Named runtime held, or its model or effort unlisted | Runs exactly, disclosed |
| Named model, no runtime, nobody offers it | Refused |
| Named model, no runtime, every offering runtime held | Best offering runtime, model kept, disclosed |
| Named effort alone | Places nothing; passed exactly, support recorded |
| Review | Prefers another runtime among adequate tuples; if only the author's is adequate, runs there, disclosed |

A Participant's default runtime is a preference. It yields when it has no usable
tuple for the tier. Participants have no model or effort defaults.

## Quota holds

Holds are keyed by runtime and model:

- A runtime-wide hold matches every model. A model's hold matches that exact model.
- A failure holds the model its `execution-started` act recorded, or the whole
  runtime if that is unknown.
- A success on a known model clears that model's hold and the runtime-wide hold,
  not sibling models' holds. A success on an unknown model clears only the
  runtime-wide hold.
- A run whose model is unknown (none asked for, no advertised default) treats any
  model's hold on the runtime as applying to it.

## Which runs share what

| | Same request again (resume, retry, a start handed on) | New request continuing it |
| --- | --- | --- |
| Runtime | Kept | Kept (owner ruling, #14) |
| Model, effort | Kept (`execution_scope`, read in `_dispatch`) | Selected afresh |
| Tier inputs | Kept | Its own |

Discovered work stores these on its pick-up's assignment act, because the
discovered request's own record is never rewritten.

A handle is reused only for the same runtime, effective model and effort. Two
unset values count as equal.

## What the record says

`execution-started` carries `selected_model`, `selected_effort`, `effective_model`,
`field_sources`, `field_binding`, `routing` and `selection_because`. Each
`field_binding` row has one of these bindings:

| Binding | Meaning |
| --- | --- |
| `owner-bound_claimed` | Source is `named` and the field's own basis is a Turn the owner wrote. The wording of the Turn is not checked, so this is a claim; `basis` and `supplied_by` are there to inspect |
| `carrier-bound` | Any other named field, including records older than `field_sources` |
| `preference` | A Participant's default runtime |
| `continued-bound`, `reassigned-bound` | A runtime carried on or moved by a recorded act |
| `advisory`, `routed` | Filled by the tier, with an advisory tier deciding it or not |
| `automatic` | Chosen by the capacity ranking |

`constraint_basis` cites the runtime only. `constraint_bases` holds one Turn per
field, and each is checked against who asked for the work. A carrier whose
requester is not the owner cannot cite the owner's Turn: the delegation is
refused, and retrying without the citation records `carrier-bound`.

## When a run fails

`delivery-failed` carries `selected`, `field_sources` and `routing`. Nothing
retries: a coordinator may authorize a new execution, for example with a stronger
`advisory_tier`.

MARS's `error.data.mars.option` (exactly `model` or `effort`) and `offered` are
kept in `runtime_evidence`. `failure_classification` is set only when the tier
chose that option:

- `model_unavailable/catalogue_changed`
- `effort_unavailable/catalogue_changed`

A named option being rejected, and any failure with no `option`, stays unclassified.
No error message is ever read for this.
