"""A realistic Brain to look at: research, a campaign, and an assistant.

    python -m mentis.web.fixture demo_corpus

Deliberately not a software-development demo. Two of the three worlds are a
literature review and a tabletop campaign, because a UI validated only against
development work narrows the same way Mark III narrowed.

The Designer Persona is created here through the ordinary Persona mechanism and
delivered to a real execution, so this task's own dogfooding is in the record.
"""

from __future__ import annotations
from mentis.corpus.store import (DAY_TO_DAY as _DAY_TO_DAY,
                                 role_at as _role_at)

import os
import sys

import time

import mentis.api as api
from mentis.conversation import text as part

DESIGNER = (
    "Design interfaces around what the user is trying to understand and do. "
    "Preserve product semantics while choosing clear information hierarchy, "
    "interaction, progressive disclosure, and visual organization. Prefer "
    "reusable semantic surfaces and adaptable presentation over hard-coded "
    "layouts. Show important state where it becomes relevant; keep deeper "
    "detail reachable without making it constantly visible.")


def produced_link(corpus, act_id, entry_id, why):
    """Say that this operational act brought this durable Entry into being.

    ONE ordinary, inert Relation, written the way anybody would write one.
    `about[]` means "this act concerned these things" and has never meant
    production, so nothing has to guess from a Kind name or an act name.
    """
    corpus.write(body={"reason": why}, attributed_to="human:brian",
                 link={"from": act_id, "to": entry_id, "relation": "produced"})


def _now():
    return time.time()


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
        ("@Mira", "durable game agent; runs scenes"),
        ("@Barkeep", "durable character agent; the Empty Net"),
        ("@Elena", "durable character agent; the harbourmaster's clerk"),
        ("@Jarvis", "durable assistant; works at brain scope, joins nothing"),
    ]}
    personas = {n: cv.define_persona(n, b) for n, b in [
        ("Designer", DESIGNER),
        ("Researcher", "Say what each source states before you say what you infer."),
        ("Challenger", "Argue the strongest case against the current conclusion."),
        ("Dungeon Master", "Run the scene. Never roll for a player."),
        ("NPC", "Stay in character and know only what your character could know."),
        ("Personal Assistant", "Report only what the record shows."),
    ]}

    # THE ONE RELATION THAT SAYS WHAT WORK LEFT BEHIND. Defined once, here,
    # because the design Conversation below is already the first work that
    # produces something durable. It is an ordinary Relation with an inverse
    # and no substrate role: the engine does nothing with it, and every reading
    # of production anywhere is a reading of these links.
    #
    # Every Brain now bootstraps it (`Conversations._ensure_vocabulary`), so
    # this only writes it for a corpus opened without that layer.
    if corpus.current_definition("produced") is None:
        corpus.define_relation(
            "produced", inverse="produced-by", attributed_to="human:brian",
            properties={"meaning": "This operational act brought this durable "
                                   "Entry into being as a result of the act."})

    # === this task's own work, done as the Designer ======================
    design = cv.open_conversation("Mark IV interface",
                                  about="the first working web interface")
    cv.join(who["@brian"], design)
    cv.join(who["@Nadia"], design)
    cv.instruct_conversation(
        design, "Surfaces are reusable; layouts decide where they appear.",
        about="architecture")
    d1 = cv.say(design, who["@brian"],
                [part("Build the first working Mark IV web interface, and use "
                      "a Designer Persona to do it.")],
                addressed_to=[who["@Nadia"]])
    cv.expect(d1, of=who["@Nadia"], kind="result", by=who["@brian"],
              because="I need to see and work with the substrate")
    dex = cv.begin_execution(participant=who["@Nadia"], conversation=design,
                             persona=personas["Designer"], runtime="claude")
    droot = cv.record_act(actor=who["@Nadia"], act="execution-started",
                          conversation=design, turn=d1, execution=dex.reference,
                          runtime="claude", because="the owner asked on Turn #1")
    cv.record_delivery(dex, cv.compose(conversation=design,
                                       participant=who["@Nadia"],
                                       persona=personas["Designer"]),
                       mechanism="SessionStart hook -> additionalContext",
                       entry_ids=[d1])
    d_art = cv.record_act(actor=who["@Nadia"], act="artifact-changed",
                          conversation=design, turn=d1, execution=dex.reference,
                          caused_by=droot, about=["artifact:ui/src/surfaces"],
                          because="built the surfaces the layouts compose")

    # A KIND THIS INTERFACE HAS NEVER HEARD OF, defined here through the same
    # public vocabulary mechanism anybody else would use. Nothing in the web
    # layer or the UI knows the word `constraint`, and nothing may be taught
    # it: if this renders, an arbitrary future Kind renders.
    #
    # Its one field is deliberately NOT called `text`. A reader that quietly
    # assumes `body.text` would show this Kind as blank, and would have been
    # keying on a convention rather than reading the declaration.
    corpus.define_kind(
        "constraint", fields=["limit"], attributed_to="human:brian",
        properties={"meaning": "A boundary the work must stay inside, found "
                               "by doing the work rather than chosen in "
                               "advance.", "truth_apt": True})
    bound = corpus.create_and_establish(
        kind="constraint", attributed_to=who["@Nadia"],
        written_by="claude/nadia-1",
        body={"limit": "A semantic surface may not read the atmosphere it is "
                       "being drawn in, so every product mark has to survive "
                       "all four without a special case."})
    d_bound = cv.record_act(actor=who["@Nadia"], act="constraint-found",
                            conversation=design, turn=d1,
                            execution=dex.reference, caused_by=d_art,
                            about=[bound],
                            because="building the surfaces established it")
    produced_link(corpus, d_bound, bound, "the build established this limit")

    # === research: parallel agents, clarification, owner decision =========
    research = cv.open_conversation(
        "Solid electrolytes", about="are they ready to build on this year")
    for a in ("@brian", "@Nadia", "@Vera", "@Ada"):
        cv.join(who[a], research)
    cv.instruct_conversation(
        research, "Distinguish observed evidence from inference, and label "
                  "every claim as one or the other.", about="evidence")
    t_sources = cv.open_topic(research, "Sources")
    t_risk = cv.open_topic(research, "Risks")

    r1 = cv.say(research, who["@brian"],
                [part("Are solid electrolytes ready for us to build on this "
                      "year? I want two independent investigations.")],
                addressed_to=[who["@Nadia"]])
    cv.expect(r1, of=who["@Nadia"], kind="result", by=who["@brian"],
              because="it decides the roadmap")
    rex = cv.begin_execution(participant=who["@Nadia"], conversation=research,
                             persona=personas["Researcher"], runtime="claude")
    rroot = cv.record_act(actor=who["@Nadia"], act="execution-started",
                          conversation=research, turn=r1,
                          execution=rex.reference, runtime="claude",
                          because="the owner asked on Turn #1")
    cv.record_delivery(rex, cv.compose(conversation=research,
                                       participant=who["@Nadia"],
                                       persona=personas["Researcher"]),
                       mechanism="SessionStart hook -> additionalContext",
                       entry_ids=[r1])

    r2 = cv.say(research, who["@Nadia"],
                [part("@Vera, take the failure modes. @Ada, take what is "
                      "actually purchasable today.")],
                addressed_to=[who["@Vera"], who["@Ada"]])
    cv.assign_topic(r2, t_sources)
    ask = cv.record_act(actor=who["@Nadia"], act="help-requested",
                        conversation=research, turn=r2, execution=rex.reference,
                        caused_by=rroot, about=[who["@Vera"], who["@Ada"]],
                        because="two independent readings, as asked")
    ev = cv.expect(r2, of=who["@Vera"], kind="result", by=who["@Nadia"])
    cv.expect(r2, of=who["@Ada"], kind="result", by=who["@Nadia"])

    vex = cv.begin_execution(participant=who["@Vera"], conversation=research,
                             persona=personas["Challenger"], runtime="claude")
    vstart = cv.record_act(actor=who["@Vera"], act="execution-started",
                           conversation=research, turn=r2,
                           execution=vex.reference, caused_by=ask)
    aex = cv.begin_execution(participant=who["@Ada"], conversation=research,
                             persona=personas["Researcher"], runtime="codex")
    astart = cv.record_act(actor=who["@Ada"], act="execution-started",
                           conversation=research, turn=r2,
                           execution=aex.reference, caused_by=ask)

    # a clarification, as an ordinary reply
    r3 = cv.say(research, who["@Ada"],
                [part("Purchasable by whom - us at prototype volume, or at "
                      "production volume? The answer changes completely.")],
                replies_to=r2, addressed_to=[who["@Nadia"]])
    cv.record_act(actor=who["@Ada"], act="clarification-requested",
                  conversation=research, turn=r3, execution=aex.reference,
                  caused_by=astart)
    cv.expect(r3, of=who["@Nadia"], kind="clarification", by=who["@Ada"],
              because="I cannot scope the search without it")
    r4 = cv.say(research, who["@Nadia"],
                [part("Prototype volume. Assume we buy tens, not thousands.")],
                replies_to=r3, addressed_to=[who["@Ada"]])
    cv.record_act(actor=who["@Nadia"], act="clarification-answered",
                  conversation=research, turn=r4, execution=rex.reference,
                  caused_by=ask)

    # Vera returns; a side issue is noticed and left
    r5 = cv.say(research, who["@Vera"],
                [part("[Observed] Dendrite growth still ends cells early at "
                      "the current-density we would need. [Inference] Not "
                      "ready for a product this year.")],
                replies_to=r2)
    cv.assign_topic(r5, t_risk)
    vres = cv.record_act(actor=who["@Vera"], act="result-returned",
                         conversation=research, turn=r5,
                         execution=vex.reference, caused_by=vstart)
    cv.record_act(actor=who["@Vera"], act="expectation-met",
                  conversation=research, turn=r5, caused_by=ev)
    cv.record_act(actor=who["@Vera"], act="problem-noticed",
                  conversation=research, turn=r2, execution=vex.reference,
                  caused_by=vstart, about=["artifact:lab/cycling-rig.md"],
                  because="the cycling rig logs temperature in two units in "
                          "the same file")
    cv.end_execution(vex.reference)

    # the owner is asked to decide; @Ada is still working
    r6 = cv.say(research, who["@Nadia"],
                [part("Vera says not this year on failure modes. Ada is still "
                      "on availability. Do you want the full answer, or is "
                      "'not this year' enough to plan around?")],
                addressed_to=[who["@brian"]])
    cv.expect(r6, of=who["@brian"], kind="decision", by=who["@Nadia"],
              because="I cannot finish without knowing how much you need")

    # === the campaign: separate NPC Participants, Topics, media ===========
    # One Turn, one execution, a pile of acts, and two DURABLE EPISTEMIC
    # PRODUCTS. This is the case a Conversation-local provenance spine has to
    # survive: the work is noisy, but what it LEFT BEHIND is small and worth
    # finding without opening a debugger.
    # CARRIED FORWARD DELIBERATELY. `define_kind` builds the new version's body
    # from what it is given, so a re-definition that omits a property DROPS it:
    # this one already loses `capturable` from the seeded v1, and omitting
    # `standing_apt` or `knowing` would make the fixture contradict the
    # vocabulary it is meant to demonstrate -- `knowing` decides which door
    # delivery reads this Kind through, so dropping it would silently take a
    # Kind out of both channels.
    corpus.define_kind("finding", fields=["text"], attributed_to="human:brian",
                       properties={"meaning": "What looking established, "
                                              "concluded from examining "
                                              "something.", "truth_apt": False,
                                   "standing_apt": False, "knowing": "that",
                                   "requires_basis": True})
    corpus.define_kind("problem", fields=["text"], attributed_to="human:brian",
                       properties={"meaning": "Something in the way, noticed "
                                              "and worth naming.",
                                   "truth_apt": False, "standing_apt": False, "knowing": "that"})
    def produced(act_id, entry_id, why):
        produced_link(corpus, act_id, entry_id, why)

    r7 = cv.say(research, who["@brian"],
                [part("Vera, run the cycling rig numbers properly and tell me "
                      "what they actually show.")],
                addressed_to=[who["@Vera"]])
    cv.assign_topic(r7, t_risk)
    cv.expect(r7, of=who["@Vera"], kind="result", by=who["@brian"])

    vex = cv.begin_execution(participant=who["@Vera"], conversation=research,
                             persona=personas["Researcher"], runtime="claude")
    a = cv.record_act(actor=who["@Vera"], act="execution-started",
                      conversation=research, turn=r7, execution=vex.reference,
                      runtime="claude", because="the owner asked for the numbers")
    for act, why in [
        ("consulted-mentis", "what is already known about the rig"),
        ("records-read", "the last four cycling runs"),
        ("records-read", "the temperature logs beside them"),
        ("measurement-taken", "current density at failure, per cell"),
        ("measurement-taken", "capacity retained after 200 cycles"),
        ("comparison-made", "this rig against the published figures"),
        ("artifact-changed", "the numbers, written down where they can be checked"),
    ]:
        a = cv.record_act(actor=who["@Vera"], act=act, conversation=research,
                          turn=r7, execution=vex.reference, runtime="claude",
                          caused_by=a, because=why)

    sheet = "artifact:lab/cycling-rig-analysis.csv"
    # Admitted material, not a claim: admitting a spreadsheet asserts nothing.
    sheet_entry = corpus.admit(
        source="lab", locator=sheet, observed_at=_now(), content="external",
        payload=None, payload_type="text/csv", attributed_to=who["@Vera"],
        written_by="claude/vera-1")
    a_art = cv.record_act(actor=who["@Vera"], act="artifact-produced",
                          conversation=research, turn=r7,
                          execution=vex.reference, runtime="claude",
                          caused_by=a, about=[sheet, sheet_entry],
                          because="so the working can be checked")
    produced(a_art, sheet_entry, "the run wrote this sheet")

    finding = corpus.create_and_establish(
        kind="finding", attributed_to=who["@Vera"], written_by="claude/vera-1",
        body={"text": "Dendrite growth ends cells at 3.1 mA/cm2, well under "
                      "the 5 mA/cm2 a product would need. The failure is the "
                      "current density, not the electrolyte chemistry."})
    a_find = cv.record_act(actor=who["@Vera"], act="finding-recorded",
                           conversation=research, turn=r7,
                           execution=vex.reference, runtime="claude",
                           caused_by=a_art, about=[finding, sheet],
                           because="this is what the numbers actually show")
    produced(a_find, finding, "the run concluded this")

    trouble = corpus.create_and_establish(
        kind="problem", attributed_to=who["@Vera"], written_by="claude/vera-1",
        body={"text": "The cycling rig logs temperature in two different "
                      "units in the same file, so older runs cannot be "
                      "compared without knowing which."})
    a_prob = cv.record_act(actor=who["@Vera"], act="problem-noticed",
                           conversation=research, turn=r7,
                           execution=vex.reference, runtime="claude",
                           caused_by=a_find, about=[trouble],
                           because="it will bite whoever reads the older runs")
    produced(a_prob, trouble, "the run named this problem")

    r8 = cv.say(research, who["@Vera"],
                [part("Ran it properly. It is the current density, not the "
                      "chemistry: cells end at 3.1 mA/cm2 against the 5 a "
                      "product needs. Numbers are in the sheet.")],
                replies_to=r7, written_by="claude/vera-1")
    cv.assign_topic(r8, t_risk)
    # NO `produced` link here on purpose: this act REFERENCED the finding that
    # an earlier act brought into being. A spine reading about[] would wrongly
    # report the finding as produced twice.
    cv.record_act(actor=who["@Vera"], act="result-returned", conversation=research,
                  turn=r8, execution=vex.reference, runtime="claude",
                  caused_by=a_find, about=[finding])
    cv.end_execution(vex.reference)

    tavern = cv.open_conversation("Saltmarsh", about="the harbour campaign")
    for a in ("@brian", "@Mira", "@Barkeep", "@Elena"):
        cv.join(who[a], tavern)
    cv.instruct_conversation(
        tavern, "Stay in character. Nobody narrates another character's "
                "actions.", about="narration")
    t_scene = cv.open_topic(tavern, "The Empty Net")
    t_ledger = cv.open_topic(tavern, "The missing ledger")

    g1 = cv.say(tavern, who["@brian"],
                [part("Day 12 of Flocktide. The party pushes into the Empty "
                      "Net, wet through. 'We're hunting the smugglers off the "
                      "old jetty.'")],
                addressed_to=[who["@Barkeep"]])
    cv.assign_topic(g1, t_scene)
    gex = cv.begin_execution(participant=who["@Barkeep"], conversation=tavern,
                             persona=personas["NPC"], runtime="claude")
    groot = cv.record_act(actor=who["@Barkeep"], act="execution-started",
                          conversation=tavern, turn=g1, execution=gex.reference,
                          runtime="claude", caused_by=None)
    cv.record_delivery(gex, cv.compose(conversation=tavern,
                                       participant=who["@Barkeep"],
                                       persona=personas["NPC"]),
                       mechanism="SessionStart hook -> additionalContext",
                       entry_ids=[g1])
    g2 = cv.say(tavern, who["@Barkeep"],
                [part("*sets down a tankard* 'Smugglers? I know nothing of "
                      "that. But the harbourmaster's ledger went missing last "
                      "month, and the constable's been grumbling in here "
                      "about it ever since.'")],
                replies_to=g1, written_by="claude/session-barkeep-1")
    cv.assign_topic(g2, t_scene)
    cv.assign_topic(g2, t_ledger)
    cv.record_act(actor=who["@Barkeep"], act="result-returned",
                  conversation=tavern, turn=g2, execution=gex.reference,
                  caused_by=groot)

    # --- A RICH REPLY, INSIDE A THREAD, ON PURPOSE -----------------------
    # Conversation and Thread shared no Turn renderer, so a reply carrying
    # anything beyond prose read as a rich record in one place and as a bare
    # paragraph in the other. Every existing reply in this corpus was plain
    # text, which is exactly why the divergence went unseen. This one is not:
    # it carries a marked span, an image part, a cited artifact, a topic and
    # an operational act of its own, so the two presentations can be compared
    # on something that would expose them.
    g2b = cv.say(tavern, who["@Mira"], [
        part("Here is the jetty the barkeep means, and the customs house "
             "behind it. The ledger pages are worth a look before anyone "
             "goes asking questions."),
        {"type": "image", "ref": "artifact:saltmarsh/jetty-approach.png",
         "media_type": "image/png", "alt": "The old jetty at dusk"},
        {"type": "reference", "ref": "artifact:saltmarsh/ledger-pages.pdf"},
    ], replies_to=g1, addressed_to=[who["@brian"]],
       written_by="claude/session-mira-1")
    cv.assign_topic(g2b, t_scene)
    cv.assign_topic(g2b, t_ledger)
    cv.record_act(
        actor=who["@Mira"], act="media-marked", conversation=tavern, turn=g2b,
        about=["artifact:saltmarsh/customs-house.png"],
        because="the customs house is the thing the party will actually look at",
        detail={"of": "the customs house", "form": "sketch",
                "ref": "artifact:saltmarsh/customs-house.png",
                "media_type": "image/png",
                "alt": "The customs house behind the jetty"})
    cv.record_act(actor=who["@Mira"], act="records-read", conversation=tavern,
                  turn=g2b, execution=gex.reference, runtime="claude",
                  caused_by=groot,
                  about=["artifact:saltmarsh/ledger-pages.pdf"],
                  because="the ledger is what the barkeep pointed at")

    cv.end_execution(gex.reference)

    g3 = cv.say(tavern, who["@Mira"],
                [part("The harbour, as the party would have seen it coming in.")],
                addressed_to=[who["@brian"]])
    cv.assign_topic(g3, t_scene)
    g4 = cv.say(tavern, who["@Mira"], [
        {"type": "image", "ref": "artifact:saltmarsh/harbour-map.png",
         "media_type": "image/png", "alt": "Hand-drawn map of Saltmarsh harbour"},
        {"type": "file", "ref": "artifact:saltmarsh/deck-plan.pdf",
         "media_type": "application/pdf"},
    ])
    cv.assign_topic(g4, t_scene)

    # --- media as a RECORDED INTENTION, not something inferred from prose ---
    # An agent marks a portion of a Turn as having a media representation.
    # `detail.ref` set  -> it names an artifact that already exists.
    # `detail.ref` None -> an intention; an agent/tool resolves it later with a
    # `media-generated` act caused_by this one. Nothing here infers anything
    # from the words, and Mentis generates nothing.
    cv.record_act(
        actor=who["@Mira"], act="media-marked", conversation=tavern, turn=g3,
        about=["artifact:saltmarsh/harbour-map.png"],
        because="the harbour is easier to see than to describe",
        detail={"of": "The harbour, as the party would have seen it coming in.",
                "form": "map", "ref": "artifact:saltmarsh/harbour-map.png",
                "media_type": "image/png",
                "alt": "Hand-drawn map of Saltmarsh harbour"})

    g6 = cv.say(tavern, who["@Mira"],
                [part("Out past the jetty the water lifts and a long shape "
                      "breaks it: a harbour dragon, barnacled and grey-green, "
                      "old as the seawall. It watches the party and does not "
                      "submerge.")],
                addressed_to=[who["@brian"]])
    cv.assign_topic(g6, t_scene)
    # marked, and deliberately NOT resolved: no artifact exists for this yet
    cv.record_act(
        actor=who["@Mira"], act="media-marked", conversation=tavern, turn=g6,
        because="the party will meet this again and should recognise it",
        detail={"of": "a harbour dragon, barnacled and grey-green, old as the "
                      "seawall", "form": "image", "ref": None,
                "media_type": "image/png",
                "alt": "The harbour dragon surfacing beyond the jetty"})

    g5 = cv.say(tavern, who["@brian"],
                [part("Who would have had the ledger last?")])
    # the same Turn, addressed to a second NPC LATER -- no new Turn, no mutation
    cv.address_turn(g5, who["@Elena"], by=who["@brian"],
                    because="Elena would know the clerk's routine")
    cv.expect(g5, of=who["@Elena"], kind="result", by=who["@brian"])

    # The ledger thread, so that Topic focus is actually EVALUABLE: with only
    # one Turn outside "The Empty Net", and that Turn last, focusing a Topic
    # changed nothing you could see without scrolling. A Topic worth looking
    # at needs enough of its own material to look different.
    g7 = cv.say(tavern, who["@brian"],
                [part("Forget the smugglers for a moment. Who reported the "
                      "ledger missing, and to whom?")],
                addressed_to=[who["@Barkeep"]])
    cv.assign_topic(g7, t_ledger)
    g8 = cv.say(tavern, who["@Barkeep"],
                [part("*wipes the bar* 'The harbourmaster's clerk did. Went "
                      "to the constable himself, white as a sheet. Then he "
                      "stopped coming in.'")],
                replies_to=g7, written_by="claude/session-barkeep-2")
    cv.assign_topic(g8, t_ledger)
    g9 = cv.say(tavern, who["@Mira"],
                [part("The constable keeps his own book of what was reported "
                      "and when. It is not a secret, but nobody has asked "
                      "him for it.")],
                addressed_to=[who["@brian"]])
    cv.assign_topic(g9, t_ledger)

    # A campaign accumulates material. Four artifacts cannot show whether a
    # media surface scales, so the table has a real pile of it: images that
    # exist, documents, and marks whose artifact has not been made yet.
    _kit = [
        ("map", "image/png", "harbour-map-night.png", "The harbour by night"),
        ("map", "image/png", "jetty-approach.png", "The old jetty, approach"),
        ("map", "image/png", "empty-net-interior.png", "Inside the Empty Net"),
        ("map", "image/png", "customs-house.png", "The customs house"),
        ("map", "image/png", "tide-caves.png", "The tide caves"),
        ("image", "image/png", "barkeep.png", "The barkeep"),
        ("image", "image/png", "constable-hale.png", "Constable Hale"),
        ("image", "image/png", "harbourmaster.png", "The harbourmaster"),
        ("image", "image/png", "elena.png", "Elena of the clerks"),
        ("image", "image/png", "smuggler-sigil.png", "A sigil cut into the jetty"),
        ("file", "application/pdf", "ledger-pages.pdf", "Pages torn from the ledger"),
        ("file", "application/pdf", "harbour-dues.pdf", "Harbour dues, last quarter"),
        ("file", "text/markdown", "session-12-notes.md", "Session 12 notes"),
        ("file", "text/markdown", "session-11-notes.md", "Session 11 notes"),
        ("file", "text/markdown", "npc-roster.md", "Who is in Saltmarsh"),
        ("file", "text/html", "tide-table.html", "Tide table for Flocktide"),
        ("file", "text/html", "manifest-index.html", "Manifest index"),
        ("diagram", "image/svg+xml", "smuggling-route.svg", "The route, as understood"),
        ("diagram", "image/svg+xml", "who-knew-what.svg", "Who knew what, and when"),
    ]
    _pending = [
        ("image", "the constable's book of reports, closed on the desk"),
        ("map", "the tide caves at low water, from the seaward side"),
        ("diagram", "the chain of custody for the ledger, as far as it is known"),
        ("image", "the harbourmaster's clerk, as the party last saw him"),
    ]
    m1 = cv.say(tavern, who["@Mira"],
                [part("Everything the table has seen so far, gathered in one "
                      "place.")]
                + [{"type": "image" if k in ("map", "image", "diagram") else "file",
                    "ref": f"artifact:saltmarsh/{f}", "media_type": mt, "alt": alt}
                   for k, mt, f, alt in _kit])
    cv.assign_topic(m1, t_scene)
    for form, of in _pending:
        cv.record_act(actor=who["@Mira"], act="media-marked", conversation=tavern,
                      turn=m1, because="the table will want to see this",
                      detail={"of": of, "form": form, "ref": None,
                              "media_type": "image/png", "alt": of})

    # === brain scope: the assistant, with no Conversation =================
    jex = brain.begin_execution(participant=who["@Jarvis"],
                                persona=personas["Personal Assistant"],
                                runtime="claude")
    j1 = cv.record_act(actor=who["@Jarvis"], act="brain-oriented",
                       execution=jex.reference, runtime="claude",
                       because="a look across the brain")
    j2 = cv.record_act(actor=who["@Jarvis"], act="consulted-mentis",
                       execution=jex.reference, caused_by=j1,
                       detail={"situation": "anything waiting on the owner"})
    cv.record_act(actor=who["@Jarvis"], act="problem-noticed",
                  execution=jex.reference, caused_by=j2,
                  about=[r6], because="the owner has been asked to decide on "
                                      "Turn #6 of Solid electrolytes and has "
                                      "not answered")

    return dict(corpus=corpus, brain=brain, cv=cv, who=who, personas=personas,
                design=design, research=research, tavern=tavern,
                executions={"designer": dex, "nadia": rex, "ada": aex,
                            "jarvis": jex})


def main(argv=None):
    root = (argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else "demo_corpus"
    w = build(root)
    cv = w["cv"]
    print(f"built {root}")
    print(f"  conversations {len(cv.all_conversations())}"
          f"  participants {len(cv.all_participants())}"
          f"  personas {len(w['corpus'].entries_of_kind('persona'))}")
    print(f"  operational acts {len(cv.history())}"
          f"  live executions {len(cv.active_executions())}")
    print(f"\nserve it:  python -m mentis.web {root}")


if __name__ == "__main__":
    main()
