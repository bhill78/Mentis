"""The starting Kind and Relation definitions, as DATA.

Nothing here is engine vocabulary. These are rows written into a fresh corpus,
and the engine would work identically with a completely different set. The only
strings the engine itself understands are the two substrate roles, and they are
properties a Relation definition declares about itself -- not names.

Deliberately small field sets: `b354bce` disproved the hypothesis that elaborate
per-Kind metadata helps.

`capturable` and `truth_apt` are the two exceptions, added from the Mark I-III
archaeology (`2e75388`). Both are DESCRIPTIVE. No engine code reads either one,
standing does not depend on them, and nothing enforces them. They record what a
Kind IS so that a reader years later is not left guessing.

`standing_apt` is a THIRD, AND IT IS A DIFFERENT SORT OF FACT -- read from the
CURRENT definition, never from the version an entry pinned. See its entry in
`KIND_PROPERTIES` below for why, and `docs/design/standing-apt.md` for the
classification in full.
"""

from __future__ import annotations

#: substrate roles the engine understands. Two, both from the frozen design.
ESTABLISHES = "establishes"
SUPERSEDES = "supersedes"

#: A RELATION MAY DECLARE THAT IT ONLY *PROPOSES* A ROLE, WHICH IS NOT THE
#: ROLE. `proposes_role` names a substrate role its links put FORWARD and do
#: not perform. The relation's own `substrate_role` stays None, so `stands`
#: treats it exactly as it treats every other ordinary relation -- reported
#: under its own label in `incoming`, conferring nothing, ending nothing.
#:
#: WHY IT IS DECLARED HERE AND NOT BRANCHED ON ANYWHERE. Mark III recorded
#: "this is meant to improve that" as `revises`, written on the PROPOSED act,
#: and said of it: *"The named item stays in force and stays in force until a
#: human approves this instead of it"* (`mentis3/operating.py:110`). But Mark
#: III then read that ONE fact twice -- `resolve.py:272` drops any item "a
#: successor has revised" from delivery the moment the successor is approved --
#: so the proposal and the supersession were the same row, told apart only by
#: whether somebody had approved. Mark II had already separated the general
#: case: *"Extraction and supersession are different relationships and are
#: recorded separately... they remain two acts so a reader can always tell
#: which they are looking at"* (`archive/mark-2/ARCHITECTURE.md`), which
#: MARK-3-CARRY-FORWARD C15 carried as an invariant. Here they are two facts:
#: the proposal is written when it is made and is never rewritten, and
#: approving writes a separate `supersedes` link.
#:
#: A reader finds the relation by this declaration rather than by its name, so
#: the engine holds no relation name and a record that calls it something else
#: is read correctly.
PROPOSES_ROLE = "proposes_role"

#: Every Kind definition carries these, over and above `kind` and `meaning`.
#:
#: fields     -- the body keys a node of this Kind may carry.
#: capturable -- may material legitimately ENTER Mentis already represented as
#:               this Kind, or does it only make sense as a conclusion drawn
#:               from something already held? This is the Ladder, described.
#:               Nothing enforces it; see `docs/archaeology/ladder-archaeology.md`.
#:               Whether RECORDING one needs a basis is `requires_basis`, a
#:               separate declaration, so that the owner's decision to require
#:               a basis did not turn this description into a rule.
#: truth_apt  -- is this the sort of thing that can meaningfully be true or
#:               false? A Decision is not false, it was made; a Rule is not
#:               false, it is unwise. Describing that prevents a category error;
#:               it is not a confidence score and it does not affect standing.
#: standing_apt -- do instances of this Kind participate meaningfully in the
#:               standing mechanism: may they acquire standing through
#:               `establishes` and lose it through `supersedes`? It says
#:               nothing about truth, capture, whether the material governs
#:               work, placement, or whether any particular entry stands.
#:
#:               *** CURRENT VOCABULARY CAPABILITY, NOT HISTORICAL ENTRY
#:               MEANING. *** Every other property here is read through
#:               `definition_for(entry)` -- the version the entry was written
#:               against -- because it says what that entry MEANT, and "a later
#:               version of the same definition never reinterprets it". This one
#:               is read through `current_definition(kind)` instead, because it
#:               says what the vocabulary CAN DO NOW. It belongs with
#:               `substrate_role` and a relation's `inverse`, which are already
#:               read currently for the same reason. There is exactly one source
#:               and no fallback: a pinned value is never consulted for it.
#:
#:               ABSENT IS NOT FALSE. `false` says standing is not meaningful
#:               for this Kind; absent says nobody has established the answer.
#:               Six Kinds are deliberately absent -- see the design note.
#:
#: NOTHING ENFORCES IT. `Corpus.establish`, `stands` and link writing are
#: unchanged and consult it nowhere; the engine still reads only `fields`.
#: Presentation may describe itself with it. Enforcement would be a separate
#: decision and is not this one.
#:
#: expects_falsifier -- DOES THIS KIND OWE A CHECK THAT COULD PROVE IT WRONG.
#:               Carried across from Mark III's `kinds.json` `_fields` in its
#:               own words: "does it owe a check that could prove it wrong.
#:               Declared, never inferred from truth_apt". That second sentence
#:               is the whole reason it is a property of its own. A Kind can be
#:               the sort of thing that is true or false and still owe nobody a
#:               way to find out which, so reading the obligation off
#:               `truth_apt` would be the engine answering a question nobody
#:               was ever asked.
#:
#:               THREE-VALUED, EXACTLY LIKE `standing_apt`. `true` says the
#:               Kind owes a falsifier, `false` says it owes none, and ABSENT
#:               says nobody has established the answer. Absent is not written
#:               into the definition at all, and ABSENT IS NOT FALSE -- "owes
#:               no check" and "nobody has said" are different facts, and a
#:               reader must be able to tell them apart.
#:
#:               THE ENGINE DOES NOT ENFORCE IT, AND DECLARING IT CHANGES NO
#:               BEHAVIOUR. The spine still reads only `fields`; `write`,
#:               `establish` and `stands` consult this nowhere. The refusal it
#:               exists for -- declining to record a hypothesis that names no
#:               falsifier -- lives in the web act layer and is a separate
#:               change by a separate builder. This is the declaration that
#:               refusal will read, and on its own it is a fact written down
#:               and nothing else.
#:
#: requires_basis -- MUST RECORDING ONE NAME WHAT IT WAS CONCLUDED FROM.
#:               `true` on finding, solution, hypothesis and lesson, by owner
#:               decision (Epistemic Ladder addendum 1, D1): recording one of
#:               those with no basis reference is refused, and the refusal
#:               says why. A shape check on the record, not a judgement of the
#:               material. ABSENT OR ANYTHING BUT `true` MEANS NOT REQUIRED.
#:               New recordings only: material already held without a basis
#:               is delivered, labelled "no basis recorded" (D6).
#:
#: knowing -- DOES MATERIAL OF THIS KIND STATE SOMETHING, OR DIRECT HOW WORK
#:            IS DONE. Two values and nothing else:
#:
#:              "that" -- propositional. It says something is so: an
#:                        observation, a finding, a lesson, a conclusion. Read
#:                        because it may be RELEVANT to a question.
#:              "how"  -- procedural. It directs how work is done: a rule, a
#:                        persona's behaviour, an instruction placed somewhere.
#:                        Read because it GOVERNS the work at hand.
#:
#: WHY THIS IS A KIND PROPERTY AND NOT A FLAG ON AN ENTRY. It is a fact about
#: what the Kind MEANS, so it is true of every instance and cannot drift
#: between two entries of one Kind. It is declared here for the same reason
#: `truth_apt` is: so that nothing reads a Kind's NAME and concludes anything.
#: Adding a peer Kind is a line in this list; no code learns its name.
#:
#: WHAT IT DOES NOT SAY. Not whether the material is true, not whether anybody
#: established it, not what may be done to it, and not a workflow. A Kind
#: defines what material means; the procedure for working with it lives in
#: procedural material, which is data, and may differ for the same Kind in two
#: places without either Kind changing.
#:
#: TWO THINGS READ IT, both of them small. Delivery reads it to know whether it
#: is supplying knowledge because it is relevant or governance because it
#: applies. The establish act reads it to know whether the act confers
#: behavioural control, which is the owner's to confer.
KNOWING_THAT = "that"
KNOWING_HOW = "how"

#: THE DECLARATIONS PRODUCTION BRANCHES ON, as opposed to the ones it only
#: shows. Dropping one of these from a redefinition does not make a Kind
#: slightly less described: it changes what the Kind DOES. `knowing` decides
#: which delivery channel a Kind's material travels, or neither; `requires_basis`
#: decides whether recording one without a basis is refused; `standing_apt`
#: decides whether a new version of it establishes itself and whether the
#: register treats it as governed; `expects_falsifier` decides whether
#: establishing it is refused without one.
#:
#: WHY THIS LIST EXISTS AND WHY IT IS SHORT. `define_kind` REPLACES a Kind's
#: properties rather than merging them -- deliberately, so that a definition is
#: a complete statement rather than an accumulation nobody can read whole. The
#: cost is that omission is indistinguishable from deletion, and for these four
#: that silently changes behaviour. `capturable`, `truth_apt` and `meaning` are
#: NOT here: nothing branches on them, so losing one costs a reader a sentence
#: and costs the system nothing. The list is what production reads, measured,
#: and it must shrink or grow with that rather than with what seems important.
BEHAVIOURAL_PROPERTIES = ("knowing", "standing_apt", "expects_falsifier",
                          "requires_basis")

#: authoring -- HOW AN OWNER'S GOVERNANCE SURFACE OFFERS TO WRITE ONE. A dict,
#:              every key optional except `section`:
#:
#:                section            which Governance tab it is authored under
#:                                   (a short slug; a new one is a new tab)
#:                section_label      that tab's words, where it is new
#:                door               "entry": written through the generic
#:                                   `POST /api/entries`. The only door a
#:                                   declaration may name; the instruction and
#:                                   Persona doors are their own routes.
#:                placeable          may it be placed in a Conversation
#:                                   (default true)
#:                persona_placeable  may it be placed on a Persona (default
#:                                   false). The place act already takes any
#:                                   destination; this only says to offer one.
#:                basis              offer "concluded from" supporting
#:                                   references (`derive-from`) (default false)
#:
#: form      -- HOW EACH FIELD IS ASKED FOR. `{field: {label, help, input,
#:              rows}}`, every key optional. `input` is one of "text" (a
#:              paragraph), "line" (one line), "capabilities" (a choice from
#:              the runtime Capability vocabulary, stored as a list), "refs"
#:              (held entry ids, stored as a list), "list" (one item per
#:              line, stored as a list), "participant" or "persona" (one
#:              Participant or Persona id, chosen from those held) or
#:              "activities" (a repeatable group of rows -- key, what, who,
#:              disciplines, done_when, coordinates -- stored as a list of
#:              objects). A field the form does not mention is asked for as a
#:              paragraph under its own name. The referencing inputs are
#:              checked against the record where a body is written
#:              (`mentis.conversation.reference_refusal`).
#:
#: BOTH ARE DESCRIPTIVE, AND DELIBERATELY NOT IN `BEHAVIOURAL_PROPERTIES`. No
#: engine code, no delivery and no act reads them; only the owner's authoring
#: surface does (`mentis.web.governance_ui`). A Kind without them is authored
#: exactly as before -- through the surface's own fallback for the Kinds it
#: has always known, or not offered a builder at all -- so a Brain whose
#: definitions predate them is unchanged. Losing one in a redefinition costs a
#: builder, never a behaviour.
KIND_PROPERTIES = ("fields", "capturable", "truth_apt", "meaning",
                   "standing_apt", "expects_falsifier", "requires_basis",
                   "knowing",
                   "authoring", "form")

#: The input kinds a `form` declaration may name. Anything else is asked for
#: as a paragraph, rather than refused: a form is a description.
FORM_INPUTS = ("text", "line", "capabilities", "refs", "list",
               "participant", "persona", "activities")

#: TWO FAMILIES, AND THE DIFFERENCE IS WHO SETTLES THE MATERIAL.
#:
#: The accepted vocabulary (Mark III's `kinds.json`, `_fields.adjudicated`)
#: divides what a Brain holds into material somebody ADJUDICATES -- a lesson, a
#: rule, a decision -- and UNGATED SUPPORTING MATERIAL, which nobody
#: adjudicates: a note, a finding, a problem. Standing is the adjudication
#: mechanism, so `standing_apt` follows that division and nothing else. It is
#: not a judgement about how useful the material is, and an ungated Kind is not
#: a lesser one: supporting material is how the adjudicated material came to be
#: argued for at all.
#:
#: DECLARED, NEVER INFERRED FROM THE NAME. The answers live here, in the Kind
#: definition, and every reader takes them from the current definition. Nothing
#: anywhere reads "finding" or "note" and concludes anything from the word.
KINDS = [
    {"kind": "source-material", "fields": ["text"],
     "standing_apt": False,
     "capturable": True, "truth_apt": False,
     "knowing": "that",  # what a connector or person observed
     "meaning": "What a connector or person actually observed, normalized for "
                "reading. Not a conclusion."},
    {"kind": "note", "fields": ["text"],
     # UNGATED SUPPORTING MATERIAL. Nothing adjudicates a note, so standing is
     # not the mechanism it lives by -- see the note under KINDS below.
     "standing_apt": False,
     "capturable": True, "truth_apt": False,
     "knowing": "that",  # somebody's own words about something
     "meaning": "Deliberately kept, in somebody's own words: understood well "
                "enough to be worth holding, and asserted as nothing more than "
                "that. Not an observation somebody made, and not a conclusion."},
    {"kind": "problem", "fields": ["text"],
     "standing_apt": False,
     "capturable": True, "truth_apt": False,
     "knowing": "that",  # something is wrong -- a state of the world
     "meaning": "Something is wrong with what we are working on."},
    # MARK III'S `solution` (`mentis3/kinds.json`), CARRIED AS MEANING AND NOT
    # AS MACHINERY. Its `derives_from: ["problem"]`, `next_actions:
    # ["attempt"]`, `terminal` and `adjudicated` are deliberately NOT ported as
    # fields: Mark IV has no transition engine and no edge-legality machinery
    # that could read them, and `docs/archaeology/ladder-archaeology.md`
    # records that decision. What `derives_from` said is said here by writing a
    # `derived-from` link instead -- an ordinary inert fact a reader can see,
    # rather than a legality the engine would have to police.
    {"kind": "solution", "fields": ["text"],
     # UNGATED SUPPORTING MATERIAL. The owner's two-axis decision lists
     # `solution` with the material nobody adjudicates, so standing is not the
     # mechanism it lives by. FALSE AND NOT ABSENT: that answer has been
     # established, which is a different fact from nobody having established it.
     "standing_apt": False,
     "requires_basis": True,
     "capturable": False, "truth_apt": False,
     "knowing": "that",  # an approach warranted for consideration; it states that this is worth trying, and it does not itself direct anybody to try it
     "meaning": "An approach warranted for consideration. NOT A DECLARATION "
                "THAT THE PROBLEM IS SOLVED, which is why it is not truth-apt "
                "-- an approach is worth trying or not worth trying, and only "
                "what happened when somebody ran it can be right or wrong. "
                "Several may hang off one problem at once and they do not "
                "compete. It does not replace its source: the problem stands, "
                "whatever is proposed for it."},
    {"kind": "hypothesis", "fields": ["text", "limits", "falsifier"],
     # THE APPROVAL WAS WITHHELD BY AN OMISSION, AND THIS GIVES IT BACK. Mark
     # III declared `hypothesis` both `adjudicated: true` and
     # `expects_falsifier: true`. Mark IV seeded it with no `standing_apt` at
     # all -- and `ui/src/surfaces/standing.ts` returns false for anything whose
     # `standing_apt` is not exactly `true`, so the single human approval never
     # reached a hypothesis. One could be recorded and then never settled, which
     # is precisely the dead end Mark III also had.
     #
     # ONE APPROVAL, AND RATIFICATION IS THAT APPROVAL. The owner's settled
     # decision is that claims and hypotheses get ONE human approval, and that
     # ratifying IS that approval: there is no separate ratify act and no
     # adjudication-plus-ratification. So the whole change is making the
     # approval that already exists reachable -- no new act, no new gate, no
     # queue, and nothing here that anything has to run.
     "standing_apt": True,
     "expects_falsifier": True,
     "requires_basis": True,
     "capturable": False, "truth_apt": True,
     "knowing": "that",  # a conjecture about what is so
     "meaning": "A conjecture put up to be settled. It can be true or false, "
                "and nothing yet says which."},
    {"kind": "finding", "fields": ["text"],
     # UNGATED SUPPORTING MATERIAL, like `note` and `problem`. A finding is
     # what looking turned up; nobody adjudicates it, and it is not the sort of
     # thing a person settles as true or false either -- what it reports either
     # happened or did not, and the looking is the evidence.
     "standing_apt": False,
     "requires_basis": True,
     "capturable": False, "truth_apt": False,
     "knowing": "that",  # what looking established
     "meaning": "What looking established, concluded from examining something."},
    {"kind": "outcome", "fields": ["text", "result", "attempted"],
     "standing_apt": False,
     # `attempted` IS ASKED OF THE FIELD, NEVER OF THE WORD. Mark III declared
     # it per outcome WORD in `mentis3/outcomes.json` and failed closed on any
     # word that file did not list. Mark IV decided the opposite, and decided it
     # LATER: the meaning below already says the engine checks `result` against
     # no list, "because an outcome vocabulary that cannot grow is a state
     # machine wearing a Kind". That later decision governs, so there is no list
     # to look a word up in and `attempted` CANNOT be derived from the word --
     # it has to be declared, per outcome, on the outcome. Mark III's own
     # wording required exactly this and said so: "Asked of this field, never of
     # the name." Nothing validates its values, for the same reason nothing
     # validates `result`.
     "capturable": True, "truth_apt": True,
     "knowing": "that",  # what happened when something was tried
     "meaning": "What happened when something was actually tried. `result` "
                "says which way it went -- worked, failed, partial, rejected, "
                "inconclusive were the values Marks I-III used -- and `text` "
                "says what happened. The engine does not check `result` "
                "against any list, because an outcome vocabulary that cannot "
                "grow is a state machine wearing a Kind. `attempted` says "
                "whether the thing was actually RUN, which is what keeps "
                "considered-and-rejected apart from attempted-and-failed -- "
                "two different things a single `failed` silently merges, "
                "losing the difference between `we tried it and it did not "
                "work` and `we looked at it and did not try it`. It is asked "
                "of this field and never of the name, because there is no list "
                "of names to ask."},
    {"kind": "lesson", "fields": ["text", "limits"],
     "standing_apt": True,
     "requires_basis": True,
     "capturable": False, "truth_apt": False,
     "knowing": "that",  # what went wrong and why; a conclusion, not an instruction -- a lesson may SUPPORT a rule without being one
     "meaning": "What went wrong and why. Concluded, never noticed directly."},
    # `about` IS THE SUBJECT IT SPEAKS TO, and it is what lets composition see
    # two pieces of procedural material saying different things about the same
    # thing (`conversation._conflicts`). A rule or decision without it is never
    # compared with anything, so a placed rule and a placed instruction could
    # contradict each other and nobody would be told. Optional: an empty
    # subject compares with nothing, exactly as before. An existing Brain gets
    # it from `tools/add_about_field.py`, deliberately, never by itself.
    {"kind": "rule", "fields": ["text", "about"],
     "standing_apt": True,
     "capturable": False, "truth_apt": False,
     "knowing": "how",  # a directive somebody wrote down: it says how work is to be done
     "meaning": "A directive somebody wrote down. It carries no authority by "
                "being a rule."},
    {"kind": "decision", "fields": ["text", "about"],
     "standing_apt": True,
     "capturable": False, "truth_apt": False,
     "knowing": "how",  # a question settled, and what it settled it to; it directs what happens next
     "meaning": "A question settled, and what it settled it to."},
]

RELATIONS = [
    {"relation": "establishes", "directed": True, "inverse": "established-by",
     "substrate_role": ESTABLISHES,
     "meaning": "An adjudication act conferring standing on its target. Says "
                "somebody established it; says nothing about whether it is true."},
    {"relation": "supersedes", "directed": True, "inverse": "superseded-by",
     "substrate_role": SUPERSEDES,
     "meaning": "This replaced that. Does NOT mean the predecessor was wrong, "
                "and never removes it. The reason belongs in this link's body, "
                "not in a rewrite of either object."},
    {"relation": "derived-from", "directed": True, "inverse": "gave-rise-to",
     "substrate_role": None,
     "meaning": "Concluded from another held object. Distinct from "
                "extracted-from, which crosses the admission boundary. Inert "
                "to the engine."},
    {"relation": "supports", "directed": True, "inverse": "supported-by",
     "substrate_role": None,
     "meaning": "Offered as evidence for. Not a claim that the target is true."},
    {"relation": "disputes", "directed": True, "inverse": "disputed-by",
     "substrate_role": None,
     "meaning": "A supported challenge to the target. Does NOT revoke it, does "
                "NOT supersede it, and does NOT make the challenger correct. "
                "Inert to the engine, which reports it and decides nothing."},
    {"relation": "extracted-from", "directed": True, "inverse": "yielded",
     "substrate_role": None,
     "meaning": "Drawn out of admitted material. Inert to the engine."},
    {"relation": "declines", "directed": True, "inverse": "declined-by",
     "substrate_role": None,
     "meaning": "Closes an adoption request. Says nothing about whether the "
                "material is true; the material stays recorded."},
    {"relation": "withdraws", "directed": True, "inverse": "withdrawn-by",
     "substrate_role": None,
     "meaning": "The challenger withdrew this challenge, and said why. The "
                "challenge and the withdrawal both stay in the record; it says "
                "nothing about whether the material was right."},
    {"relation": "proposes", "directed": True, "inverse": "proposed-by",
     "substrate_role": None,
     "meaning": "Puts its target forward for adjudication. Confers nothing."},
    {"relation": "proposes-to-supersede", "directed": True,
     "inverse": "proposed-to-be-superseded-by",
     # IT CONFERS NOTHING AND IT ENDS NOTHING. `substrate_role` is None, so the
     # engine is inert to it; `proposes_role` says which role it merely puts
     # forward, which is how a reader finds it without knowing its name.
     "substrate_role": None,
     "proposes_role": SUPERSEDES,
     "meaning": "This is PROPOSED as a replacement for that. It is not a "
                "replacement: every predecessor named here goes on standing "
                "exactly as it stood, nothing is ended, and nothing reaches "
                "anybody that did not reach them before. SEVERAL COMPETING "
                "PROPOSALS MAY NAME THE SAME PREDECESSOR and all of them "
                "remain readable, because four candidates may be put up for "
                "one post while the incumbent holds it. One proposal may name "
                "SEVERAL predecessors. Only an owner establishing the "
                "successor replaces anything, and that act writes `supersedes` "
                "-- a different fact, in its own link. Inert to the engine."},
    {"relation": "outcome-of", "directed": True, "inverse": "had-outcome",
     "substrate_role": None,
     "meaning": "From an outcome to the thing that was tried. Records that it "
                "WAS tried and how it went. It does not establish, supersede "
                "or refute the thing tried: a rule that failed once is still "
                "the rule somebody wrote. Inert to the engine."},
    {"relation": "in-context", "directed": True, "inverse": "context-of",
     # INERT TO THE ENGINE, and Mark III said as much in its own terms:
     # `lineage: false` and `asserts_cause: false` (`mentis3/relations.json`)
     # -- it makes nothing an ancestor and it claims nothing brought anything
     # about. In Mark IV terms that is `substrate_role: None`.
     #
     # THE INVERSE NAME IS MARK IV'S REQUIREMENT, NOT A MARK III FACT. Mark
     # III's file declares no inverses at all; every Mark IV relation declares
     # one so that direction survives a read. `context-of` is the natural
     # reading of the forward label, chosen here rather than carried across.
     "substrate_role": None,
     "meaning": "WHERE this happened -- the circumstances an outcome is true "
                "of. An outcome without one is the collapsed sentence `the "
                "approach works`, which is the thing the record exists to "
                "prevent. Naming the circumstances is not a claim that they "
                "caused anything, and it confers no standing on either end. "
                "Inert to the engine."},
    {"relation": "resembles", "directed": True, "inverse": "resembles",
     "substrate_role": None,
     "meaning": "LIKENESS IS NOT CAUSE. A resembles B, recorded because "
                "somebody or something noticed the likeness. It does NOT mean "
                "A derives from B, supports B, proves B, caused B or replaces "
                "B, and it confers no standing whatever. Its inverse is itself. "
                "A similarity score is not a resemblance -- a resemblance is an "
                "observation somebody is willing to put their name to. Inert "
                "to the engine."},
]
