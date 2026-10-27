"""A realistic synthetic corpus, built to stress the interface rather than to
demonstrate it.

WHY THIS EXISTS. The demo fixture is a teaching example: three conversations,
short turns, four artifacts, one noisy execution. Every judgement about
density, spacing, measure, thread depth, media handling and navigation made
against it is a judgement about a toy. This corpus is deliberately the other
thing — long agent reports, heavy formatting, a thread nobody would read in
one sitting, a dozen topics with overlapping activity, dozens of artifacts and
enough durable objects that the spine has to cope with them clustering.

WHAT IT IS NOT. It is not Mark III data and nothing here was copied from it.
It is not a benchmark and nothing measures it. It invents no mechanism: every
call below is one a real participant could make through the same public
surface, and where the substrate cannot represent something the corpus simply
does not contain it.

Build it beside the demo rather than instead of it:

    python -m mentis.web.stress stress_corpus
    python -m mentis.web stress_corpus --demo-activity
"""

from __future__ import annotations
from mentis.corpus.store import (DAY_TO_DAY as _DAY_TO_DAY,
                                 role_at as _role_at)

import os
import sys
import time

import mentis.api as api
from mentis.conversation import text as part
from mentis.web.fixture import produced_link


def _now():
    return time.time()


# ---------------------------------------------------------------------------
# prose. Long, formatted, and shaped like something an agent would actually
# write: headings, tables, code, quotes, lists, references and hashes.


REPORT_CYCLING = """\
## Cycling results, runs 41-58

**Summary.** Capacity fade is not uniform across the pack. Cells in positions
3, 4 and 9 lose capacity roughly twice as fast as the rest, and the split
tracks position rather than cell lot — which rules out the supplier
explanation we had been carrying since the January batch.

### What the runs show

| position | cycles to 80% | lot   | mean dT (C) |
|----------|---------------|-------|-------------|
| 1        | 1420          | B-221 | 3.1         |
| 2        | 1385          | B-221 | 3.4         |
| 3        | 690           | B-221 | 11.8        |
| 4        | 715           | B-219 | 11.2        |
| 5        | 1362          | B-219 | 3.6         |
| 9        | 702           | B-219 | 12.1        |

The three fast-fading positions are the three with the worst thermal gradient.
Lot membership is mixed across both groups, so it is not the lot.

### Method

Runs were 1C/1C to 80% capacity, 25C ambient, with the pack instrumented at
each cell tab. The analysis script is at `analysis/cycling/fade_by_position.py`
and the raw frames are in the admitted dataset below.

```python
fade = (
    frames.groupby(["run", "position"])
          .apply(lambda g: cycles_to(g, fraction=0.80))
          .unstack("position")
)
# positions 3, 4, 9 separate cleanly on the second component
assert fade.loc[:, [3, 4, 9]].mean().mean() < fade.drop(columns=[3, 4, 9]).mean().mean()
```

### What I am not saying

> This does not establish a cause. Position correlates with thermal gradient
> and with coolant path length, and those two are not separated by anything in
> these runs.

Separating them needs the manifold swap, which is a rig change and not mine to
make. I have recorded it as a problem rather than doing it.

Cross-check against the earlier thermal survey: 4f2a1c7 changed the tab
instrumentation, so anything before that commit is not comparable on dT.
"""

REPORT_MANIFOLD = """\
## Coolant manifold: what a swap would and would not settle

Asked to say whether swapping the manifold separates position from thermal
gradient. Short answer: partly, and the part it does not settle is the part we
care about.

### The confound

Position determines three things at once:

1. distance along the coolant path;
2. proximity to the pack wall, which is the dominant radiative path;
3. tab length, because the busbar geometry is not symmetric.

A manifold swap reverses (1) and leaves (2) and (3) untouched. So if fade
follows the coolant path it moves with the swap; if it follows wall proximity
or tab length it does not. That is a real discriminator for (1), and it is
silent on whether (2) and (3) matter.

### Cost

| option              | rig time | parts     | settles          |
|---------------------|----------|-----------|------------------|
| manifold swap       | 2 days   | in stock  | coolant path     |
| rotated pack        | 4 hours  | none      | wall proximity   |
| symmetric busbar    | 3 weeks  | fabricate | tab length       |

The rotated-pack run is four hours and settles the second confound. I would do
that first regardless of what we decide about the manifold, because it is
nearly free and it changes what the manifold result means.

### Recommendation

Run the rotation this week. Hold the manifold swap until the rotation says
whether wall proximity is carrying the effect. Do not fabricate a symmetric
busbar on current evidence — three weeks against a confound we have no
positive reason to suspect.
"""

REPORT_SOURCES = """\
## What the literature actually claims about position-dependent fade

I read eleven papers. Four are relevant and only two measure what we measure.

**Directly relevant**

- Okonkwo et al. (2021) instrument per-cell and find the same position split,
  with a 2.1x fade ratio against our 2.0x. They attribute it to coolant path.
  They did not rotate the pack.
- Lindqvist & Moreau (2023) rotate the pack and find the effect *follows the
  coolant path*, not the wall. This is the closest thing to our rotation
  experiment that exists, and it supports doing it.

**Relevant but measuring something else**

- Two papers measure module-level fade and cannot see position at all.

**Not relevant**

- Seven papers are cell-level or chemistry-focused.

### The honest gap

Nobody has separated tab length. Both directly relevant papers use symmetric
busbars, so the question does not arise for them and their results say nothing
about ours.
"""

REPORT_INSTRUMENT = """\
## Instrumentation audit

The tab thermocouples drift. I checked because the dT numbers in the fade
report looked too clean for contact thermocouples on a vibrating rig.

### Findings

- Channels 3 and 7 read 0.4-0.6C high against the reference bath after four
  hours of cycling. The others are within 0.1C.
- The drift is *monotonic with run time*, which is a contact problem, not
  calibration.
- It does not change the position conclusion: the effect is 8C and the drift
  is under 1C.

### What needs doing

Re-seat channels 3 and 7 before the rotation run and re-check against the bath
at the start and the end. I have not done this — the rig is in use.
"""

REPORT_LOTS = """Checked properly rather than assumed.

### Incoming inspection, both lots

| metric             | B-221     | B-219     | spec           |
|--------------------|-----------|-----------|----------------|
| formation capacity | 4.91 Ah   | 4.90 Ah   | > 4.85         |
| DC impedance       | 18.2 mOhm | 18.4 mOhm | < 21           |
| thickness          | 11.02 mm  | 11.01 mm  | 11.0 +/- 0.15  |

No separation on any receipt metric. The two lots are the same population as
far as we can measure them, and the fade split cuts across both.

I would stop carrying the supplier story. It has been shaping qualification
decisions for a lot that incoming inspection says is fine.
"""

RULE_TEXT = (
    "A rig change that alters instrumentation invalidates comparison against "
    "runs made before it. Record the change as an act and cite it on any "
    "analysis that crosses it, rather than relying on run numbers."
)

LESSON_TEXT = (
    "When an effect correlates with a position, enumerate everything that "
    "position determines before attributing it to the first plausible one. "
    "Here position fixed coolant path, wall proximity and tab length at once, "
    "and the cheap experiment separated a different one than the obvious one."
)


# ---------------------------------------------------------------------------


def build(root: str) -> dict:
    # THE REAL BRAIN IS NOT A PLACE FOR THIS. Refused rather than documented:
    # a fixture pointed at the owner's day-to-day corpus by a stray argument
    # would seed it with people who do not exist, and no amount of deleting
    # rows afterwards makes a corpus untouched again.
    if _role_at(root) == _DAY_TO_DAY:
        raise PermissionError(
            "refusing to write fixture or stress material into the real "
            "day-to-day Brain at %s. Point this at a development or "
            "disposable corpus." % root)
    # A BUILDER MAKES ITS BRAIN, explicitly, where there is none (D2: opening
    # never creates one); an existing one must be writable as it stands.
    corpus = (api.open_corpus(root, access="write")
              if os.path.isfile(os.path.join(root, "corpus.db"))
              else api.create_corpus(root))
    brain = api.brain(corpus)
    cv = brain.conversations

    who = {a: cv.resolve_participant(a, about=b) for a, b in [
        ("@brian", "the owner"),
        ("@Nadia", "durable research agent; coordinates and integrates"),
        ("@Vera", "durable research agent; independent challenge"),
        ("@Ada", "durable research agent; analysis and sources"),
        ("@Kiro", "durable engineering agent; rigs and instrumentation"),
        ("@Petra", "durable materials agent; cells and chemistry"),
        ("@Sol", "durable data agent; pipelines and frames"),
        ("@Mira", "durable game agent; runs scenes"),
        ("@Jarvis", "durable assistant; works at brain scope, joins nothing"),
    ]}
    personas = {n: cv.define_persona(n, b) for n, b in [
        ("Researcher", "Say what each source states before you say what you infer."),
        ("Challenger", "Argue the strongest case against the current conclusion."),
        ("Engineer", "Say what it costs and what it would settle."),
        ("Analyst", "Separate what was measured from what was concluded."),
        ("Personal Assistant", "Report only what the record shows."),
    ]}

    # -- vocabulary: several Kinds, all through the ordinary public path -----
    # NOTHING IN THE INTERFACE KNOWS ANY OF THESE NAMES. Several are new here,
    # and one deliberately does not use a field called `text`.
    kinds = [
        ("finding", ["text"], "What looking established, concluded from "
                              "examining something.", True),
        ("problem", ["text"], "Something in the way, noticed and worth naming.",
         False),
        ("hypothesis", ["text"], "A claim put up to be tested, not yet "
                                 "established.", True),
        ("measurement", ["quantity", "value", "conditions"],
         "A number obtained under stated conditions.", True),
        ("rule", ["statement"], "How work here is to be done, stated so it can "
                                "be followed.", False),
        ("lesson", ["learned"], "Something worth carrying to the next "
                                "occurrence of this shape.", False),
        ("risk", ["text", "if_realised"], "Something that has not gone wrong "
                                          "and could.", False),
        ("constraint", ["limit"], "A boundary the work must stay inside, found "
                                  "by doing the work rather than chosen in "
                                  "advance.", True),
    ]
    for name, fields, meaning, truth_apt in kinds:
        # WHAT A SEEDED KIND ALREADY DECLARED IS CARRIED FORWARD, because
        # `define_kind` REPLACES rather than merges and some of these names are
        # already defined. This loop used to drop `knowing` and `standing_apt`
        # from those -- silently, which is exactly the loss the spine now
        # refuses. Starting from the current body and overlaying only what this
        # builder means to say keeps the stress corpus a demonstration of the
        # vocabulary rather than a quiet contradiction of it.
        was = corpus.current_definition(name)
        props = dict((was or {}).get("body", {}))
        props.pop("kind", None)
        props.pop("fields", None)
        props.update({"meaning": meaning, "truth_apt": truth_apt})
        corpus.define_kind(name, fields=fields, attributed_to="human:brian",
                           properties=props)

    corpus.define_relation(
        "produced", inverse="produced-by", attributed_to="human:brian",
        properties={"meaning": "This operational act brought this durable "
                               "Entry into being as a result of the act."})

    made = []

    def relate(frm, to, relation, reason, by="@Nadia"):
        """An ordinary semantic Relation between two durable Entries.

        EVERY RELATION USED HERE IS ALREADY SEEDED BY THE SPINE and none is
        invented: `derived-from`, `supports`, `disputes` and `supersedes` are
        defined in `mentis/spine/seed.py`. Production code had never written
        one — they existed as vocabulary with no instances, so any view over
        them was untestable. This corpus writes them, which is what makes a
        neighbourhood something to look at rather than something to imagine.
        """
        corpus.write(body={"reason": reason}, attributed_to=who[by],
                     link={"from": frm, "to": to, "relation": relation})

    def mint(kind, body, by, act_id):
        eid = corpus.create_and_establish(
            kind=kind, body=body, attributed_to=who[by],
            written_by=f"claude/{by[1:].lower()}-1")
        produced_link(corpus, act_id, eid, f"the work established this {kind}")
        made.append(eid)
        return eid

    # =======================================================================
    # THE MAIN CONVERSATION. Long, formatted, many topics, one huge thread.
    # =======================================================================
    study = cv.open_conversation(
        "Cell degradation study",
        about="why the Mark-7 pack fades unevenly, and what to do about it")
    for a in ("@brian", "@Nadia", "@Vera", "@Ada", "@Kiro", "@Petra", "@Sol"):
        cv.join(who[a], study)
    cv.instruct_conversation(
        study, "Say what was measured before you say what it means. Cite the "
               "run and the commit.", about="evidence")
    cv.instruct_conversation(
        study, "A rig change is an act. Record it.", about="method")

    topics = {n: cv.open_topic(study, n, about=a) for n, a in [
        ("Fade by position", "the effect itself"),
        ("Thermal", "gradients, coolant, the manifold"),
        ("Instrumentation", "what the rig can and cannot measure"),
        ("Sources", "what the literature says"),
        ("Rotation experiment", "the cheap discriminator"),
        ("Manifold swap", "the expensive one"),
        ("Busbar geometry", "tab length, held"),
        ("Cell lots", "ruled out, kept for the record"),
        ("Data pipeline", "frames, scripts, reproducibility"),
        ("Scheduling", "rig time and who has it"),
        ("Reporting", "what goes to the programme review"),
        ("Task gravity", "side work nobody has picked up"),
    ]}

    t = topics

    def say(author, body, *, to=(), topic=None, replies=None, parts=None):
        p = parts if parts is not None else [part(body)]
        tid = cv.say(study, who[author], p, addressed_to=[who[x] for x in to],
                     replies_to=replies,
                     written_by=None if author == "@brian"
                     else f"claude/{author[1:].lower()}-1")
        if topic:
            cv.assign_topic(tid, t[topic])
        return tid

    # ---- the opening: a short steer, a long answer ------------------------
    n1 = say("@brian", "The Mark-7 pack fades unevenly and I want to know why "
                       "before the programme review. Nadia, take it.",
             to=["@Nadia"], topic="Fade by position")
    cv.expect(n1, of=who["@Nadia"], kind="result", by=who["@brian"],
              because="the review is in three weeks")

    nex = cv.begin_execution(participant=who["@Nadia"], conversation=study,
                             persona=personas["Researcher"], runtime="claude")
    a = cv.record_act(actor=who["@Nadia"], act="execution-started",
                      conversation=study, turn=n1, execution=nex.reference,
                      runtime="claude", because="the owner asked on Turn #1")
    for act, why in [("consulted-mentis", "what is already known about the pack"),
                     ("records-read", "the last sixty cycling runs")]:
        a = cv.record_act(actor=who["@Nadia"], act=act, conversation=study,
                          turn=n1, execution=nex.reference, runtime="claude",
                          caused_by=a, because=why)
    n2 = say("@Nadia", "Taking it. I will split this three ways: Sol on the "
                       "frames, Ada on what is already published, Vera to "
                       "argue against whatever we land on. Kiro for anything "
                       "that needs the rig.",
             to=["@brian"], topic="Scheduling", replies=n1)
    cv.record_act(actor=who["@Nadia"], act="help-requested", conversation=study,
                  turn=n2, execution=nex.reference, runtime="claude",
                  caused_by=a, about=[who["@Sol"], who["@Ada"], who["@Vera"]],
                  because="three independent readings")

    # ---- a long agent report with heavy formatting ------------------------
    n3 = say("@brian", "Go.", to=["@Nadia"], topic="Scheduling", replies=n2)

    sex = cv.begin_execution(participant=who["@Sol"], conversation=study,
                             persona=personas["Analyst"], runtime="codex")
    s0 = cv.record_act(actor=who["@Sol"], act="execution-started",
                       conversation=study, turn=n3, execution=sex.reference,
                       runtime="codex", because="Nadia asked for the frames")
    a = s0
    for act, why in [
        ("records-read", "runs 41 through 58"),
        ("records-read", "the temperature logs beside them"),
        ("records-read", "the lot manifests"),
        ("measurement-taken", "cycles to 80% per position"),
        ("measurement-taken", "mean tab dT per position"),
        ("measurement-taken", "capacity at cycle 500, per position"),
        ("comparison-made", "position against lot"),
        ("comparison-made", "position against thermal gradient"),
        ("artifact-changed", "the analysis script, rewritten to group by position"),
        ("records-read", "the January batch notes, to check the supplier story"),
        ("comparison-made", "this pack against the January batch"),
    ]:
        a = cv.record_act(actor=who["@Sol"], act=act, conversation=study,
                          turn=n3, execution=sex.reference, runtime="codex",
                          caused_by=a, because=why)

    frames = corpus.admit(
        source="rig", locator="artifact:data/cycling-runs-41-58.parquet",
        observed_at=_now(), content="external", payload=None,
        payload_type="application/vnd.apache.parquet",
        attributed_to=who["@Sol"], written_by="codex/sol-1")
    s_art = cv.record_act(actor=who["@Sol"], act="artifact-produced",
                          conversation=study, turn=n3,
                          execution=sex.reference, runtime="codex", caused_by=a,
                          about=["artifact:data/cycling-runs-41-58.parquet", frames],
                          because="so the working can be checked")
    produced_link(corpus, s_art, frames, "the run wrote these frames")
    made.append(frames)

    s_find = cv.record_act(actor=who["@Sol"], act="finding-recorded",
                           conversation=study, turn=n3,
                           execution=sex.reference, runtime="codex",
                           caused_by=s_art, because="this is what the runs show")
    fade = mint("finding", {"text":
                "Capacity fade tracks pack POSITION, not cell lot. Positions "
                "3, 4 and 9 reach 80% capacity in roughly half the cycles of "
                "the rest, and those three positions carry the worst thermal "
                "gradient. Lot membership is mixed across both groups."},
                "@Sol", s_find)

    s_meas = cv.record_act(actor=who["@Sol"], act="measurement-recorded",
                           conversation=study, turn=n3,
                           execution=sex.reference, runtime="codex",
                           caused_by=s_art, because="the number behind the finding")
    ratio = mint("measurement", {"quantity": "fade ratio, fast positions to rest",
                                 "value": "2.03 (95% CI 1.88-2.19)",
                                 "conditions": "runs 41-58, 1C/1C to 80%, 25C "
                                               "ambient, per-tab instrumentation"},
                 "@Sol", s_meas)

    s_prob = cv.record_act(actor=who["@Sol"], act="problem-noticed",
                           conversation=study, turn=n3,
                           execution=sex.reference, runtime="codex",
                           caused_by=s_find,
                           because="position fixes three things at once")
    confound = mint("problem", {"text":
                    "Position determines coolant path length, wall proximity "
                    "and tab length simultaneously. Nothing in runs 41-58 "
                    "separates them, so 'position causes fade' is as far as "
                    "these runs reach."},
                    "@Sol", s_prob)

    n4 = say("@Sol", REPORT_CYCLING, to=["@Nadia", "@brian"],
             topic="Fade by position")
    cv.assign_topic(n4, t["Data pipeline"])
    cv.record_act(actor=who["@Sol"], act="result-returned", conversation=study,
                  turn=n4, execution=sex.reference, runtime="codex",
                  caused_by=s_find, about=[fade, ratio, confound])
    cv.end_execution(sex.reference)

    # ---- sources -----------------------------------------------------------
    aex = cv.begin_execution(participant=who["@Ada"], conversation=study,
                             persona=personas["Researcher"], runtime="claude")
    a0 = cv.record_act(actor=who["@Ada"], act="execution-started",
                       conversation=study, turn=n3, execution=aex.reference,
                       runtime="claude", because="Nadia asked what is published")
    a = a0
    for i, why in enumerate(["the position-dependent fade literature",
                             "two papers that rotate the pack",
                             "the module-level papers, to rule them out"]):
        a = cv.record_act(actor=who["@Ada"], act="records-read",
                          conversation=study, turn=n3, execution=aex.reference,
                          runtime="claude", caused_by=a, because=why)
    a_find = cv.record_act(actor=who["@Ada"], act="finding-recorded",
                           conversation=study, turn=n3, execution=aex.reference,
                           runtime="claude", caused_by=a,
                           about=[fade], because="somebody has run our experiment")
    prior = mint("finding", {"text":
                 "Lindqvist & Moreau (2023) rotated the pack and found the "
                 "fade effect follows the coolant path rather than wall "
                 "proximity. It is the closest published analogue to the "
                 "rotation we have not yet run, and it supports running it."},
                 "@Ada", a_find)
    n5 = say("@Ada", REPORT_SOURCES, to=["@Nadia"], topic="Sources")
    cv.record_act(actor=who["@Ada"], act="result-returned", conversation=study,
                  turn=n5, execution=aex.reference, runtime="claude",
                  caused_by=a_find, about=[prior])
    cv.end_execution(aex.reference)

    # ---- the challenge, and a hypothesis --------------------------------
    vex = cv.begin_execution(participant=who["@Vera"], conversation=study,
                             persona=personas["Challenger"], runtime="gpt")
    v0 = cv.record_act(actor=who["@Vera"], act="execution-started",
                       conversation=study, turn=n3, execution=vex.reference,
                       runtime="gpt", because="argue against the position story")
    v_hyp = cv.record_act(actor=who["@Vera"], act="hypothesis-put",
                          conversation=study, turn=n3, execution=vex.reference,
                          runtime="gpt", caused_by=v0, about=[fade, confound],
                          because="the cheap experiment is not the obvious one")
    hyp = mint("hypothesis", {"text":
               "If wall proximity rather than coolant path carries the effect, "
               "rotating the pack 180 degrees leaves the fade pattern fixed to "
               "the WALL and not to the position index. Four hours of rig time "
               "distinguishes this from the coolant-path account."},
               "@Vera", v_hyp)
    n6 = say("@Vera", "Before anyone books the manifold swap: the position "
                      "story has three candidate mechanisms and the swap tests "
                      "one of them. Rotating the pack is four hours and tests a "
                      "different one. Do the cheap one first.",
             to=["@Nadia", "@brian"], topic="Rotation experiment")
    cv.assign_topic(n6, t["Thermal"])
    cv.record_act(actor=who["@Vera"], act="result-returned", conversation=study,
                  turn=n6, execution=vex.reference, runtime="gpt",
                  caused_by=v_hyp, about=[hyp])
    cv.end_execution(vex.reference)

    # ---- engineering: cost, and a rule that comes out of a mistake --------
    kex = cv.begin_execution(participant=who["@Kiro"], conversation=study,
                             persona=personas["Engineer"], runtime="claude")
    k0 = cv.record_act(actor=who["@Kiro"], act="execution-started",
                       conversation=study, turn=n6, execution=kex.reference,
                       runtime="claude", because="cost both candidate runs")
    a = k0
    for why in ["the rig calendar", "the manifold parts list",
                "the busbar drawings", "the thermocouple channel map"]:
        a = cv.record_act(actor=who["@Kiro"], act="records-read",
                          conversation=study, turn=n6, execution=kex.reference,
                          runtime="claude", caused_by=a, because=why)
    k_prob = cv.record_act(actor=who["@Kiro"], act="problem-noticed",
                           conversation=study, turn=n6, execution=kex.reference,
                           runtime="claude", caused_by=a,
                           because="the dT numbers are cleaner than the "
                                   "hardware can produce")
    drift = mint("problem", {"text":
                 "Tab thermocouples on channels 3 and 7 drift 0.4-0.6C high "
                 "over a four-hour run, monotonically with run time. That is a "
                 "contact problem rather than calibration, and it is not "
                 "corrected in any run so far."},
                 "@Kiro", k_prob)
    k_rule = cv.record_act(actor=who["@Kiro"], act="rule-proposed",
                           conversation=study, turn=n6, execution=kex.reference,
                           runtime="claude", caused_by=k_prob,
                           because="we already crossed one rig change without "
                                   "noticing")
    rule = mint("rule", {"statement": RULE_TEXT}, "@Kiro", k_rule)
    n7 = say("@Kiro", REPORT_MANIFOLD, to=["@Nadia", "@brian"],
             topic="Manifold swap")
    cv.assign_topic(n7, t["Thermal"])
    n8 = say("@Kiro", REPORT_INSTRUMENT, to=["@Nadia"], topic="Instrumentation")
    cv.record_act(actor=who["@Kiro"], act="result-returned", conversation=study,
                  turn=n8, execution=kex.reference, runtime="claude",
                  caused_by=k_prob, about=[drift, rule])
    cv.end_execution(kex.reference)

    # ---- the owner is asked to decide -------------------------------------
    n9 = say("@Nadia", "Three of us agree the rotation run comes first: four "
                       "hours, and it changes what a manifold result would "
                       "mean. Kiro also found the channel-3/7 drift, which "
                       "wants re-seating before any new run. That is half a "
                       "day of rig time this week. Do you want it?",
             to=["@brian"], topic="Scheduling", replies=n7)
    cv.expect(n9, of=who["@brian"], kind="decision", by=who["@Nadia"],
              because="the rig calendar is full after Thursday")

    # =======================================================================
    # ONE VERY LARGE THREAD. 48 replies under a single Turn.
    # =======================================================================
    big = say("@Nadia", "Working thread for the rotation run. Everything about "
                        "setup, channels and what we expect goes here so the "
                        "main conversation stays readable.",
              topic="Rotation experiment")
    cv.assign_topic(big, t["Instrumentation"])

    thread_script = [
        ("@Kiro", "Re-seated channels 3 and 7. Bath check before and after, "
                  "both within 0.08C now."),
        ("@Sol", "Frames pipeline is pointed at the new run id. Nothing else "
                 "changed, so the comparison holds."),
        ("@Vera", "State the prediction before the run, please. Otherwise we "
                  "will read whatever comes out as confirmation."),
        ("@Nadia", "Fair. Coolant-path account: fade follows the position "
                   "index, so after rotation the fast positions are still 3, 4 "
                   "and 9 by index."),
        ("@Nadia", "Wall-proximity account: fade follows physical location, so "
                   "after rotation the fast cells are the ones that were 1, 2 "
                   "and 12."),
        ("@Vera", "And if it is tab length, neither moves and we learn nothing "
                  "except that it is not the other two."),
        ("@Kiro", "Correct, and that is still worth four hours."),
        ("@Ada", "Lindqvist rotated and got the coolant-path answer. Their "
                 "busbar is symmetric so tab length could not confound them."),
        ("@Petra", "Chemistry note: the cells are the same lot split across "
                   "both groups, so nothing about the rotation changes the "
                   "cell population."),
        ("@Sol", "Run started 09:14. Logging at 1Hz per tab."),
        ("@Kiro", "Ambient is holding at 25.1C."),
        ("@Sol", "Cycle 40. Nothing separating yet, which is expected — the "
                 "split did not open until cycle 300 last time."),
        ("@Vera", "Do not look at it until 300. We will talk ourselves into a "
                  "pattern."),
        ("@Nadia", "Agreed. Next report at 300."),
        ("@Sol", "Cycle 300. Early separation is following PHYSICAL location, "
                 "not index. The cells that were in positions 1, 2 and 12 are "
                 "the ones running hot."),
        ("@Vera", "That is the wall account. Say it plainly."),
        ("@Kiro", "dT at the hot cells is 11.4C, which is the same magnitude as "
                  "before, on the other side of the pack."),
        ("@Ada", "This contradicts Lindqvist. Worth saying out loud."),
        ("@Nadia", "It does. Their pack is in a different enclosure — theirs is "
                   "liquid-jacketed, ours is air-gapped at the wall."),
        ("@Petra", "Then the wall is a radiative path for us and not for them, "
                   "and both results can be true."),
        ("@Vera", "I will take that, but it needs to be written down as a "
                  "difference in conditions, not as us being right."),
        ("@Sol", "Cycle 500. Separation is clear and it is location-fixed. "
                 "Ratio 1.94, overlapping the earlier 2.03."),
        ("@Kiro", "No instrumentation drift this run. Bath check at 500 is "
                  "within 0.06C."),
        ("@Nadia", "So the manifold swap would have told us very little."),
        ("@Kiro", "It would have told us the coolant path is not carrying it, "
                  "which we now know for two days less rig time."),
        ("@Sol", "Cycle 700. Fast cells at 82% and falling on the same curve "
                 "shape as runs 41-58."),
        ("@Ada", "Adding the enclosure difference to the sources note."),
        ("@Vera", "Before anyone writes 'wall proximity causes fade': it is "
                  "wall proximity OR tab length, and rotation moved both."),
        ("@Kiro", "Tab length did not move. The busbar is fixed to the pack, "
                  "not the enclosure."),
        ("@Vera", "Then I withdraw that. Rotation separated it cleanly."),
        ("@Nadia", "Recording it as a finding."),
        ("@Sol", "Cycle 900. Three fast cells at 78%, the rest above 94%."),
        ("@Petra", "Post-mortem on one fast cell would say whether it is "
                   "lithium plating or cathode. That is destructive."),
        ("@Nadia", "Not this week. Recording it as side work."),
        ("@Kiro", "Rig is free Friday if anyone wants the manifold swap "
                  "anyway, for completeness."),
        ("@Vera", "No. It answers a question we are no longer asking."),
        ("@Nadia", "Agreed, and that is a decision worth recording rather than "
                   "leaving in a thread."),
        ("@Sol", "Run complete at cycle 1000. Frames admitted."),
        ("@Ada", "I can draft the review section from this."),
        ("@Nadia", "Please. Keep the enclosure caveat prominent."),
        ("@Kiro", "Sending the thermal maps across as images."),
        ("@Sol", "Two plots attached to the main conversation, not here, so "
                 "they are findable."),
        ("@Petra", "The plating question is still open and I would like it on "
                   "the record as open rather than dropped."),
        ("@Nadia", "It is recorded. Nothing is caused by it yet, which is "
                   "exactly what 'deferred' means here."),
        ("@Vera", "Last challenge: our n is one pack. Everything above is one "
                  "pack rotated once."),
        ("@Nadia", "True and it goes in the caveat. A second pack is a "
                   "programme decision, not ours."),
        ("@Ada", "Draft is up in the review topic."),
        ("@Kiro", "Closing the rig out."),
    ]
    prev = big
    for speaker, line in thread_script:
        prev = cv.say(study, who[speaker], [part(line)], replies_to=prev,
                      written_by=f"claude/{speaker[1:].lower()}-1")

    # ---- what the rotation established ------------------------------------
    rex = cv.begin_execution(participant=who["@Nadia"], conversation=study,
                             persona=personas["Researcher"], runtime="claude")
    r0 = cv.record_act(actor=who["@Nadia"], act="execution-started",
                       conversation=study, turn=big, execution=rex.reference,
                       runtime="claude", because="the rotation run finished")
    a = r0
    for why in ["the rotation frames", "the bath checks either side",
                "the earlier runs, for the ratio"]:
        a = cv.record_act(actor=who["@Nadia"], act="records-read",
                          conversation=study, turn=big, execution=rex.reference,
                          runtime="claude", caused_by=a, because=why)
    rot_frames = corpus.admit(
        source="rig", locator="artifact:data/rotation-run-61.parquet",
        observed_at=_now(), content="external", payload=None,
        payload_type="application/vnd.apache.parquet",
        attributed_to=who["@Sol"], written_by="codex/sol-1")
    r_art = cv.record_act(actor=who["@Nadia"], act="artifact-produced",
                          conversation=study, turn=big, execution=rex.reference,
                          runtime="claude", caused_by=a,
                          about=["artifact:data/rotation-run-61.parquet", rot_frames],
                          because="the run this conclusion rests on")
    produced_link(corpus, r_art, rot_frames, "the rotation run wrote these")
    made.append(rot_frames)

    r_find = cv.record_act(actor=who["@Nadia"], act="finding-recorded",
                           conversation=study, turn=big, execution=rex.reference,
                           runtime="claude", caused_by=r_art,
                           about=[hyp, fade, prior],
                           because="the rotation separated it")
    wall = mint("finding", {"text":
                "Fade follows PHYSICAL LOCATION in the enclosure, not position "
                "index: rotating the pack moved the fast-fading cells with the "
                "wall. Tab length did not move under rotation, so it is "
                "separated. The effect is wall proximity, in an air-gapped "
                "enclosure."},
                "@Nadia", r_find)

    r_cons = cv.record_act(actor=who["@Nadia"], act="constraint-found",
                           conversation=study, turn=big, execution=rex.reference,
                           runtime="claude", caused_by=r_find,
                           because="it limits what we may claim")
    caveat = mint("constraint", {"limit":
                  "This result is one pack rotated once, in an air-gapped "
                  "enclosure. Lindqvist & Moreau found the coolant-path answer "
                  "in a liquid-jacketed enclosure; both can be true and "
                  "neither generalises without a second enclosure."},
                  "@Nadia", r_cons)

    r_les = cv.record_act(actor=who["@Nadia"], act="lesson-recorded",
                          conversation=study, turn=big, execution=rex.reference,
                          runtime="claude", caused_by=r_find,
                          because="this shape will arise again")
    lesson = mint("lesson", {"learned": LESSON_TEXT}, "@Nadia", r_les)

    # DEFERRED SIDE WORK: recorded, and nothing caused by it.
    cv.record_act(actor=who["@Petra"], act="problem-noticed", conversation=study,
                  turn=big, runtime="claude",
                  because="a post-mortem would say plating or cathode, and it "
                          "is destructive")

    # ---- SEMANTIC RELATIONS BETWEEN DURABLE OBJECTS -----------------------
    # These are the spine's OWN seeded relations (mentis/spine/seed.py) and
    # not one of them is invented here. Production code had never written a
    # single instance of any of them, so the vocabulary existed with nothing
    # in it and no view over it could be tested. A neighbourhood is only
    # worth drawing once there is something to draw.
    relate(wall, fade, "derived-from",
           "the rotation refined the position finding into a location one")
    relate(prior, hyp, "supports",
           "a published rotation supports running ours")
    relate(wall, prior, "disputes",
           "our rotation found the opposite of the published result; the "
           "enclosure differs, so both may hold")
    relate(lesson, wall, "derived-from",
           "the lesson was drawn from what the rotation established")
    relate(caveat, wall, "supports",
           "the caveat states the limit of that finding")
    relate(hyp, confound, "derived-from",
           "the hypothesis was put up to separate the confound")
    relate(rule, drift, "derived-from",
           "the rule came out of the drift going unnoticed", by="@Kiro")

    # A SUPERSESSION, which the engine actually reads by role. The first
    # ratio was computed across runs that crossed the instrumentation change;
    # the corrected one is not. The old measurement is not deleted — it is
    # superseded, and `stands()` will say so.
    c_meas = cv.record_act(actor=who["@Sol"], act="measurement-recorded",
                           conversation=study, turn=big, runtime="codex",
                           caused_by=r_art,
                           because="the first ratio crossed the tab "
                                   "instrumentation change at 4f2a1c7")
    ratio2 = mint("measurement", {"quantity": "fade ratio, fast positions to rest",
                                  "value": "1.94 (95% CI 1.81-2.08)",
                                  "conditions": "rotation run 61 only, 1C/1C to "
                                                "80%, 25C ambient, channels 3 "
                                                "and 7 re-seated"},
                  "@Sol", c_meas)
    relate(ratio2, ratio, "supersedes",
           "recomputed without crossing the instrumentation change", by="@Sol")

    r_risk = cv.record_act(actor=who["@Nadia"], act="risk-recorded",
                           conversation=study, turn=big, execution=rex.reference,
                           runtime="claude", caused_by=r_cons,
                           because="the review will read one pack as settled")
    risk = mint("risk", {"text": "The programme review may read this as a "
                                 "general result about pack geometry.",
                         "if_realised": "A second enclosure is never built and "
                                        "the air-gap caveat is lost."},
                "@Nadia", r_risk)
    cv.end_execution(rex.reference)

    n10 = say("@Nadia", "Rotation is done and it settles it: the effect is "
                        "wall proximity, not the coolant path. That is the "
                        "opposite of the published result, and the enclosure "
                        "difference explains why both can hold. Manifold swap "
                        "is not worth doing.",
              to=["@brian"], topic="Rotation experiment")
    cv.assign_topic(n10, t["Reporting"])

    # REFERENCE, NOT PRODUCTION: this act names the findings and mints nothing.
    cv.record_act(actor=who["@Nadia"], act="result-returned", conversation=study,
                  turn=n10, runtime="claude",
                  about=[wall, caveat, fade, lesson])

    # ---- ordinary conversation, after the dense stretch -------------------
    for author, body, tp in [
        ("@brian", "Good. Put the enclosure caveat in the first paragraph, not "
                   "the appendix.", "Reporting"),
        ("@Nadia", "It will be the second sentence.", "Reporting"),
        ("@Ada", "Draft section is up. It runs to about a page and a half with "
                 "the table.", "Reporting"),
        ("@brian", "Length is fine. Does it say what we would need to "
                   "generalise?", "Reporting"),
        ("@Ada", "Yes — a second enclosure, and it names the cost.", "Reporting"),
        ("@Kiro", "Rig is released. Channels 3 and 7 stay on the re-seat "
                  "schedule.", "Instrumentation"),
        ("@Petra", "Plating question is still open on the record.", "Task gravity"),
        ("@brian", "Leave it open.", "Task gravity"),
        ("@Sol", "Pipeline is tagged at the rotation run so the frames are "
                 "reproducible from the commit.", "Data pipeline"),
        ("@Vera", "I have nothing further to argue. The rotation was clean.",
         "Rotation experiment"),
        ("@Nadia", "Then we are done ahead of the review.", "Scheduling"),
        ("@brian", "Thanks. Keep the thread; I want to reread the prediction "
                   "exchange.", "Rotation experiment"),
    ]:
        say(author, body, topic=tp)

    # ---- a second work episode, so the conversation is not one arc --------
    p1 = say("@brian", "Separate question. Petra, is the B-221 lot actually "
                       "fine, or did we stop looking once position explained "
                       "the fade?",
             to=["@Petra"], topic="Cell lots")
    cv.expect(p1, of=who["@Petra"], kind="result", by=who["@brian"],
              because="the successor lot is being qualified on this assumption")

    pex = cv.begin_execution(participant=who["@Petra"], conversation=study,
                             persona=personas["Analyst"], runtime="claude")
    q = cv.record_act(actor=who["@Petra"], act="execution-started",
                      conversation=study, turn=p1, execution=pex.reference,
                      runtime="claude", because="the owner asked on Turn #17")
    for why in ["the B-221 incoming inspection records",
                "the B-219 records for comparison",
                "the formation data for both lots",
                "the impedance sweeps at receipt"]:
        q = cv.record_act(actor=who["@Petra"], act="records-read",
                          conversation=study, turn=p1, execution=pex.reference,
                          runtime="claude", caused_by=q, because=why)
    p_find = cv.record_act(actor=who["@Petra"], act="finding-recorded",
                           conversation=study, turn=p1, execution=pex.reference,
                           runtime="claude", caused_by=q, about=[fade],
                           because="the lots really are indistinguishable")
    lots = mint("finding", {"text":
                "B-221 and B-219 are indistinguishable at receipt on formation "
                "capacity, impedance and thickness. The supplier explanation "
                "for uneven fade is not merely unsupported by the cycling "
                "runs; it is contradicted by incoming inspection."},
                "@Petra", p_find)
    relate(lots, fade, "supports",
           "independent evidence that the effect is not the lot", by="@Petra")

    say("@Petra", REPORT_LOTS, to=["@brian"], topic="Cell lots")
    cv.record_act(actor=who["@Petra"], act="result-returned", conversation=study,
                  turn=p1, execution=pex.reference, runtime="claude",
                  caused_by=p_find, about=[lots])
    cv.end_execution(pex.reference)

    for author, body, tp in [
        ("@brian", "Good. Tell qualification.", "Cell lots"),
        ("@Petra", "Told. They were about to add a screen for something that "
                   "is not happening.", "Cell lots"),
        ("@Sol", "Pipeline question while I have it open: the parquet frames "
                 "are 2.1GB per run and we keep every cycle. We could keep "
                 "every tenth after a run closes and lose nothing we use.",
         "Data pipeline"),
        ("@brian", "What would we lose?", "Data pipeline"),
        ("@Sol", "Any future analysis that needs per-cycle resolution on a "
                 "closed run. I cannot name one we have wanted, which is not "
                 "the same as there being none.", "Data pipeline"),
        ("@brian", "Then keep everything. Storage is cheaper than a rerun.",
         "Data pipeline"),
        ("@Sol", "Keeping everything.", "Data pipeline"),
        ("@Ada", "Review draft is at `artifact:study/review-section.md` if "
                 "anyone wants to read it before Thursday. It cites 4f2a1c7 "
                 "for the instrumentation change.", "Reporting"),
        ("@Vera", "Read it. The enclosure caveat is in the second sentence as "
                  "promised. One quibble: it says 'the effect is wall "
                  "proximity' where it should say 'in this enclosure'.",
         "Reporting"),
        ("@Ada", "Changed.", "Reporting"),
        ("@Nadia", "Anything else before I close this out?", "Scheduling"),
        ("@Kiro", "The re-seat schedule for channels 3 and 7 needs an owner. "
                  "It is not mine after the rig is released.",
         "Instrumentation"),
        ("@brian", "Give it to qualification with the lot news.", "Instrumentation"),
        ("@Kiro", "Done.", "Instrumentation"),
    ]:
        say(author, body, topic=tp)

    # ---- media: a realistic spread of forms --------------------------------
    kit = [
        ("image", "image/png", "thermal-map-run58.png", "Thermal map, run 58"),
        ("image", "image/png", "thermal-map-run61.png", "Thermal map, rotation run 61"),
        ("image", "image/png", "fade-curves-by-position.png", "Fade curves by position"),
        ("image", "image/png", "pack-layout.png", "Mark-7 pack layout"),
        ("image", "image/jpeg", "rig-photo.jpg", "The rig, instrumented"),
        ("image", "image/png", "bath-check-3-7.png", "Bath check, channels 3 and 7"),
        ("diagram", "image/svg+xml", "coolant-path.svg", "Coolant path, as built"),
        ("diagram", "image/svg+xml", "busbar-geometry.svg", "Busbar geometry"),
        ("diagram", "image/svg+xml", "rotation-schematic.svg", "What rotation moves"),
        ("file", "application/pdf", "lindqvist-2023.pdf", "Lindqvist & Moreau 2023"),
        ("file", "application/pdf", "okonkwo-2021.pdf", "Okonkwo et al. 2021"),
        ("file", "application/pdf", "programme-review-draft.pdf", "Review draft"),
        ("file", "text/markdown", "method-notes.md", "Method notes"),
        ("file", "text/markdown", "review-section.md", "Draft review section"),
        ("file", "text/markdown", "rig-changelog.md", "Rig changelog"),
        ("file", "text/html", "run-61-report.html", "Run 61 generated report"),
        ("file", "text/html", "channel-map.html", "Thermocouple channel map"),
        ("file", "text/csv", "cycles-to-80.csv", "Cycles to 80% by position"),
        ("file", "text/csv", "dt-by-position.csv", "Mean dT by position"),
        ("file", "application/json", "run-61-manifest.json", "Run 61 manifest"),
        ("file", "text/x-python", "fade_by_position.py", "Analysis script"),
        ("file", "text/x-python", "cycles_to.py", "Cycle counting helper"),
    ]
    m1 = say("@Sol", "Everything from both runs, in one place so the review "
                     "can find it.",
             parts=[part("Everything from both runs, in one place so the "
                         "review can find it.")]
                   + [{"type": "image" if k in ("image", "diagram") else "file",
                       "ref": f"artifact:study/{f}", "media_type": mt, "alt": alt}
                      for k, mt, f, alt in kit],
             topic="Data pipeline")

    for form, of in [
        ("diagram", "the enclosure in section, showing the air gap"),
        ("map", "where each cell sits relative to the wall"),
        ("image", "the plating question, if we ever cut a cell open"),
    ]:
        cv.record_act(actor=who["@Sol"], act="media-marked", conversation=study,
                      turn=m1, because="the review will want this drawn",
                      detail={"of": of, "form": form, "ref": None,
                              "media_type": "image/png", "alt": of})

    # =======================================================================
    # ENOUGH OTHER CONVERSATIONS TO STRESS THE NAVIGATOR
    # =======================================================================
    others = [
        ("Saltmarsh", "the harbour campaign", "@Mira"),
        ("Pack thermal modelling", "simulation against the rig", "@Kiro"),
        ("Supplier qualification", "the B-221 lot and its successor", "@Petra"),
        ("Programme review", "what goes in front of the board", "@Nadia"),
        ("Rig scheduling", "who has the chamber and when", "@Kiro"),
        ("Data pipeline rewrite", "frames, parquet, reproducibility", "@Sol"),
        ("Literature sweep", "standing search across cell degradation", "@Ada"),
        ("Enclosure redesign", "if wall proximity is the mechanism", "@Kiro"),
        ("Cell post-mortem", "destructive analysis, held", "@Petra"),
        ("Instrumentation upgrade", "replacing contact thermocouples", "@Kiro"),
        ("Mark IV interface", "the first working web interface", "@Nadia"),
        # Named so the interface's configured defaults give it the image-based
        # atmosphere and one of the plain ones a neighbouring conversation, so
        # moving between them shows the canvas actually changing place.
        ("Tidewater array", "the offshore pack, and what the sea does to it",
         "@Kiro"),
    ]
    for name, about, lead in others:
        c = cv.open_conversation(name, about=about)
        cv.join(who["@brian"], c)
        cv.join(who[lead], c)
        o1 = cv.say(c, who["@brian"], [part(f"Opening {name}. {about.capitalize()}.")],
                    addressed_to=[who[lead]])
        cv.say(c, who[lead], [part("Noted. Nothing to report here yet.")],
               replies_to=o1, written_by=f"claude/{lead[1:].lower()}-1")

    # ---- brain scope: the assistant, joined to nothing --------------------
    jex = brain.begin_execution(participant=who["@Jarvis"],
                                persona=personas["Personal Assistant"],
                                runtime="claude")
    j1 = cv.record_act(actor=who["@Jarvis"], act="brain-oriented",
                       execution=jex.reference, runtime="claude",
                       because="a look across the brain")
    cv.record_act(actor=who["@Jarvis"], act="problem-noticed",
                  execution=jex.reference, caused_by=j1, about=[n9],
                  because="the owner has been asked to decide on Turn #9 of "
                          "Cell degradation study and has not answered")

    return dict(corpus=corpus, brain=brain, cv=cv, who=who, personas=personas,
                study=study, topics=t, big_thread=big, made=made,
                executions={"nadia": nex, "sol": sex, "ada": aex, "vera": vex,
                            "kiro": kex, "rotation": rex, "jarvis": jex})


def main(argv=None):
    root = (argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else "stress_corpus"
    w = build(root)
    cv = w["cv"]
    turns = cv.turns(w["study"])
    print(f"built {root}")
    print(f"  conversations {len(cv.all_conversations())}"
          f"  participants {len(cv.all_participants())}")
    print(f"  study turns {len(turns)}  topics {len(w['topics'])}")
    print(f"  operational acts {len(cv.history())}"
          f"  durable objects produced {len(w['made'])}")
    print(f"\nserve it:  python -m mentis.web {root} --demo-activity")


if __name__ == "__main__":
    main()
