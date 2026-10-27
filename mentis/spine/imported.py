"""The import door's rules: what another Brain's rows may become here.

Design adm-6cebfabd6e9c, slice 2 (§3, §6, O5). `Store.append_imported` is the
ONLY write path an import has, and this module is everything it decides. It
is kept apart from the store so the rules can be read in one place, and so
nothing above the spine can widen them: the door asks `check` and writes
exactly what it answers, whatever its caller wanted.

WHAT IS REFUSED, WITH NOTHING WRITTEN (`ImportRefused`, every problem named):

  * `definition` rows. A Kind or Relation is matched to a version here with
    an identical body, by whoever builds the batch; it is never appended
    from another Brain, because a foreign "v5" can be a different body from
    this Brain's "v5" (finding 6).
  * links that put things in force: the relation carrying the establishing
    role, `scoped-to` placements and `carries-intake` designations
    (finding 3). Standing does not travel; `evidence.json` says where it
    stood.
  * delivery rows, in either list: what Foundation put in front of an
    execution is this Brain's own observation, and no semantic path reaches
    that table.
  * acts outside `ALLOWED_ACTS`, and any act that names an execution (run
    and dispatch acts would make this Brain act: finding 2) other than the
    two decision-form acts, which are inert here (`EXECUTION_INERT_ACTS`) --
    and those too when that execution has any act here, or when an
    attachment attaches a form that is not in the batch.
  * ANYTHING THAT WOULD CHANGE THE STATE OF WORK HERE (review
    ent-cca01f8347bb, finding 1; ent-8b37c98bb8d5). An `expectation-recorded`
    is allowed only as a question of a decision form in the same batch,
    closed in the same batch, carrying no `review` or `review_of`: open, it
    would be a decision owed here. An answer act (`decision-answered`,
    `expectation-met`) is allowed only of such a question: of an expectation
    here, it would answer, meet or withdraw work this Brain holds and let
    what waits on it resume. And a reply by an expectation's carrier that
    would answer an expectation open here is refused with it.
  * an id already here -- checked before anything is written, never by
    trying, because a present id aborts the whole transaction at the
    UNIQUE constraint -- and an id named twice in one batch.
  * a reference to an id that is neither here nor in the batch: a link's
    two ends, an act's Conversation, Turn, cause and `about`, and the
    definition version an entry names. References inside BODIES are not
    checked: those are the stubs an export lists, and they read as "not in
    this Brain" (§2).
  * rows that are not rows: a missing id, actor or time, a link whose
    relation is not the definition it names, an id with `/` in it.
  * a HELD Admission whose bytes are not already in this Brain's byte store:
    possession comes before the record of it, as `admit` requires, so the
    bytes are put here first (`mentis.spine.held`) and the row after.

WHAT IS REWRITTEN, never refused: a foreign `supersedes` link whose target is
already here and STANDS -- or is itself a link here that carries a
substrate role and still counts -- would end, or change, standing on this
Brain. That is a governance effect, so it is written as the relation that
PROPOSES the superseding role (`proposes-to-supersede`), which `stands()`
ignores (§6). Supersession among rows that only exist because of this batch
ends nothing that stood here and is written as given. The door does the
rewrite; its answer lists each one, so the import act can record it.

STRUCTURAL STANDING (O5) is `establish_structural`: the owner of THIS Brain
establishing imported Conversations, Topics and Participants in one act.
Never copied from the origin, and never for anything else.
"""

from __future__ import annotations

import json

from mentis.spine import held, seed

#: What every Admission names: the spine's own, not a definition row.
ADMISSION_DEFINITION = ("admission", 1)
#: The meaning-giving acts an export may carry (§2). Everything else is
#: refused, whatever the caller asks.
ALLOWED_ACTS = frozenset({
    "conversation-renamed",
    "participant-renamed",
    "conversation-named-provisionally",
    "turn-addressed",
    "decision-form",
    "decision-form-attached",
    "decision-answered",
    "expectation-recorded",     # only a decision form's question
    "expectation-met",          # only of such a question
})

#: THE ONLY ACTS THAT MAY NAME AN EXECUTION, and they keep it as recorded. A
#: decision form is asked by a run and attached to its answer post by that
#: run, so both acts always name it; without them no question reads as a
#: form. Naming an execution that never started HERE is inert here (package
#: C, gap 2): the wake check examines only `execution-started` acts nothing
#: ended (`Conversations.open_runs`), a run's liveness is read only from its
#: start and end acts (`expectation_state`), pending forms are attached only
#: when a run of that execution writes its answer post here
#: (`attach_pending_forms`), resumption is asked only when a run ends or a
#: lost continuation is closed (`dispatch.resume_if_ready`,
#: `wakecheck.after_restart`), and what is owed is the questions'
#: expectations, not the form's acts (`operational.work.owed_by`). Every
#: other act naming an execution is still refused.
EXECUTION_INERT_ACTS = frozenset({"decision-form", "decision-form-attached"})

#: The acts that answer, meet or withdraw an expectation.
ANSWER_ACTS = frozenset({"decision-answered", "expectation-met"})

#: What the wake check reads as its own review of a run (`wakecheck`): a
#: question carrying either is never imported.
REVIEW_KEYS = frozenset({"review", "review_of"})

#: The relation a reply is written with (`conversation.REPLIES_TO`).
REPLIES_TO = "replies-to"

#: Placement and intake. The establishing relation is found by its ROLE, in
#: the definitions, so a Brain that named it differently is covered too.
REFUSED_RELATIONS = frozenset({"scoped-to", "carries-intake"})

#: The families an imported entry may be. `definition` never is.
ALLOWED_FAMILIES = frozenset({"entry", "admission"})

#: The columns of a delivery row that no entry or act has. A row carrying
#: any of them is a delivery, whichever list it came in.
DELIVERY_SHAPE = frozenset({"mechanism", "material", "behavioural_sources",
                            "operation_ok"})

#: The Kinds whose standing an import may give, as the owner's own act here
#: (O5). Rules, decisions, procedures and everything else are not among them.
STRUCTURAL_KINDS = ("conversation", "topic", "participant")

#: The act `establish_structural` writes.
STRUCTURAL_ACT = "import-established"


class ImportRefused(ValueError):
    """The batch was refused and nothing was written. `problems` names each
    reason, one line per row it concerns."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("import refused, nothing written: "
                         + "; ".join(self.problems))


class _Vocabulary:
    """This Brain's definitions, read once inside the door's transaction."""

    def __init__(self, store):
        self.bodies = {}
        self.proposing = None
        self.roles = {}
        for e in store.by_family("definition"):
            d = e["definition"]
            self.bodies[(d["name"], d["version"])] = e["body"]
            b = e["body"]
            if b.get("relation") and b.get("substrate_role"):
                self.roles[b["relation"]] = b["substrate_role"]
            if b.get(seed.PROPOSES_ROLE) == seed.SUPERSEDES:
                if self.proposing is None or d["version"] > self.proposing[1]:
                    self.proposing = (b["relation"], d["version"])

    def role(self, relation, version):
        body = self.bodies.get((relation, version)) or {}
        return body.get("substrate_role")

    def establishing(self, relation) -> bool:
        return self.roles.get(relation) == seed.ESTABLISHES


def _link_role(vocab, row) -> str | None:
    link = row.get("link") or {}
    return vocab.role(link.get("relation"), link.get("relation_version"))


def _counts(store, vocab, link_id, memo) -> bool:
    """Is this link HERE still in force: not itself superseded by a link that
    is? `Corpus._superseded`, read through the store, as of now."""
    if link_id in memo:
        return memo[link_id]
    memo[link_id] = True                      # guards a cycle
    for other in store.links(to=link_id):
        if _link_role(vocab, other) != seed.SUPERSEDES:
            continue
        if _counts(store, vocab, other["id"], memo):
            memo[link_id] = False
            break
    return memo[link_id]


def stands_here(store, vocab, entry_id) -> bool:
    """`Corpus.stands(entry_id)["stands"]`, read through the store: an
    establishing link that counts, and no superseding link that does."""
    memo, established, superseded = {}, False, False
    for link in store.links(to=entry_id):
        if not _counts(store, vocab, link["id"], memo):
            continue
        role = _link_role(vocab, link)
        if role == seed.ESTABLISHES:
            established = True
        elif role == seed.SUPERSEDES:
            superseded = True
    return established and not superseded


def _present(store, entry_ids, act_ids) -> tuple[set, set]:
    entries = {e["id"] for k in range(0, len(entry_ids), 500)
               for e in store.by_ids(entry_ids[k:k + 500])}
    acts = set(store.operational_order(act_ids))
    return entries, acts


def check(store, entries, acts) -> dict:
    """What the door may write of this batch, or `ImportRefused`.

    Read-only. Called by `Store.append_imported` inside its own write
    transaction, so nothing can be appended between this answer and the
    rows it allows. Returns {"entries", "acts", "rewritten"}: the rows to
    write, in the order given, with each rewritten supersession already
    rewritten and listed."""
    entries, acts = list(entries), list(acts)
    problems = []
    vocab = _Vocabulary(store)

    # -- the rows as rows ---------------------------------------------------
    seen = {}
    for kind, rows in (("entry", entries), ("act", acts)):
        for i, row in enumerate(rows):
            where = f"{kind} {i}"
            if not isinstance(row, dict):
                problems.append(f"{where}: not a row")
                continue
            rid = row.get("id")
            if not isinstance(rid, str) or not rid or "/" in rid:
                problems.append(f"{where}: no usable id ({rid!r})")
                continue
            if (kind, rid) in seen:
                problems.append(f"{kind} {rid}: named twice in this batch")
            seen[(kind, rid)] = row
            if DELIVERY_SHAPE & set(row):
                problems.append(f"{kind} {rid}: a delivery row; what was "
                                "delivered to an execution never travels")
    if problems:
        raise ImportRefused(problems)

    entry_ids = [r["id"] for r in entries]
    act_ids = [r["id"] for r in acts]
    here_e, here_a = _present(store, entry_ids, act_ids)
    for rid in entry_ids:
        if rid in here_e:
            problems.append(f"entry {rid}: already in this Brain")
    for rid in act_ids:
        if rid in here_a:
            problems.append(f"act {rid}: already in this Brain")

    # every id a row may point at: here, or in this batch
    batch_e, batch_a = set(entry_ids), set(act_ids)
    wanted = set()
    for row in entries:
        link = row.get("link") or {}
        wanted |= {link.get("from"), link.get("to")} - {None}
    for row in acts:
        wanted |= {row.get("conversation"), row.get("turn"),
                   row.get("caused_by")} - {None}
        wanted |= {a for a in (row.get("about") or ()) if isinstance(a, str)}
    wanted -= batch_e | batch_a
    wanted = sorted(w for w in wanted if isinstance(w, str))
    found_e, found_a = _present(store, wanted, wanted)
    known = batch_e | batch_a | found_e | found_a

    def refer(where, ref):
        if ref is not None and ref not in known:
            problems.append(f"{where}: names {ref!r}, which is neither in "
                            "this Brain nor in this batch")

    # -- entries --------------------------------------------------------------
    out_entries, rewritten = [], []
    for row in entries:
        rid = row["id"]
        where = f"entry {rid}"
        family = row.get("family")
        if family == "definition":
            problems.append(f"{where}: a definition; Kinds and Relations are "
                            "matched to a version here, never imported")
            continue
        if family not in ALLOWED_FAMILIES:
            problems.append(f"{where}: family {family!r} is not importable")
            continue
        if not row.get("attributed_to"):
            problems.append(f"{where}: attributed to nobody")
        if not isinstance(row.get("recorded_at"), (int, float)) \
                or isinstance(row.get("recorded_at"), bool):
            problems.append(f"{where}: no recorded_at")
        try:
            json.dumps(row.get("body"))
        except (TypeError, ValueError):
            problems.append(f"{where}: its body is not JSON")
        d = row.get("definition") or {}
        key = (d.get("name"), d.get("version"))
        if family == "admission":
            # the spine's own definition, never a row (`Corpus._admission`)
            if key != ADMISSION_DEFINITION or row.get("link"):
                problems.append(f"{where}: an Admission names "
                                f"{ADMISSION_DEFINITION}, not {key}")
                continue
            body = row.get("body") or {}
            if body.get("content") == "held":
                # POSSESSION BEFORE THE RECORD OF IT, as `admit` requires:
                # the bytes are put here first, then the Admission
                digest = held.digest_of(body.get("locator"))
                if digest is None or not held.has(store.root, digest):
                    problems.append(f"{where}: holds {body.get('locator')!r}, "
                                    "and those bytes are not in this Brain")
            out_entries.append(row)
            continue
        if key not in vocab.bodies:
            problems.append(f"{where}: names definition {key[0]!r} version "
                            f"{key[1]!r}, which this Brain does not hold")
        link = row.get("link")
        if link:
            rel = link.get("relation")
            if (rel, link.get("relation_version")) != key:
                problems.append(f"{where}: its link names {rel!r} version "
                                f"{link.get('relation_version')!r} but the "
                                f"row names {key[0]!r} version {key[1]!r}")
                continue
            if vocab.establishing(rel) or \
                    vocab.role(*key) == seed.ESTABLISHES:
                problems.append(f"{where}: an establishing link; standing "
                                "does not travel")
                continue
            if rel in REFUSED_RELATIONS:
                problems.append(f"{where}: a {rel} link; placement and "
                                "intake do not travel")
                continue
            refer(where, link.get("from"))
            refer(where, link.get("to"))
            target = link.get("to")
            if (vocab.role(*key) == seed.SUPERSEDES and target in found_e
                    and _ends_standing_here(store, vocab, target)):
                if vocab.proposing is None:
                    problems.append(f"{where}: supersedes {target}, which "
                                    "stands here, and this Brain declares no "
                                    "relation that proposes it instead")
                    continue
                name, version = vocab.proposing
                row = {**row, "definition": {"name": name, "version": version},
                       "link": {**link, "relation": name,
                                "relation_version": version}}
                rewritten.append({"id": rid, "target": target,
                                  "was": rel, "written_as": name})
        out_entries.append(row)

    # -- replies that would answer work here (ent-8b37c98bb8d5, R1) -----------
    problems += [f"entry {rid}: {why}" for rid, why in
                 _replies_closing_work_here(store, entries, found_e).items()]

    # -- response-set entries that would answer work here (R2) ----------------
    problems += [f"entry {rid}: {why}" for rid, why in
                 _responses_closing_work_here(store, entries, found_e).items()]

    # -- acts -----------------------------------------------------------------
    by_id = {row["id"]: row for row in acts}
    forms = {rid for rid, row in by_id.items()
             if row.get("act") == "decision-form"}
    form_questions = set()
    for row in acts:
        if (row.get("act") == "expectation-recorded"
                and (row.get("detail") or {}).get("form")):
            form_questions.add(row["id"])
    closers = {}
    for row in acts:
        if row.get("act") in ANSWER_ACTS and row.get("caused_by") in by_id:
            closers.setdefault(row["caused_by"], []).append(row)
    out_acts = []
    for row in acts:
        rid, act = row["id"], row.get("act")
        where = f"act {rid}"
        if act not in ALLOWED_ACTS:
            problems.append(f"{where}: {act!r} is not an act an import "
                            "carries")
            continue
        if row.get("execution") and act not in EXECUTION_INERT_ACTS:
            problems.append(f"{where}: names execution "
                            f"{row['execution']!r}; run and dispatch acts "
                            "would make this Brain act")
            continue
        if not row.get("actor") or row.get("at") is None:
            problems.append(f"{where}: no actor or time")
            continue
        if act in EXECUTION_INERT_ACTS and row.get("execution") \
                and store.operational(execution=row["execution"], limit=1):
            # inert ONLY because that execution never ran here
            problems.append(f"{where}: names execution "
                            f"{row['execution']!r}, which has acts in this "
                            "Brain; a form of a run here is not imported")
            continue
        if act == "decision-form-attached" and \
                row.get("caused_by") not in forms:
            problems.append(f"{where}: attaches {row.get('caused_by')!r}, "
                            "which is not a decision form in this batch; a "
                            "form here is attached only by its own run")
            continue
        if act == "expectation-recorded":
            why = _question_problem(row, forms, closers.get(rid, ()))
            if why:
                problems.append(f"{where}: {why}")
                continue
        if act in ANSWER_ACTS:
            cause = row.get("caused_by")
            if cause not in form_questions:
                if cause is not None and cause in found_a:
                    # NOTHING IMPORTED CHANGES THE STATE OF WORK HERE: an
                    # answer, a fulfilment or a withdrawal of an expectation
                    # this Brain holds would close it, or let the work
                    # waiting on it resume (review ent-cca01f8347bb, D3)
                    problems.append(f"{where}: would answer, meet or withdraw "
                                    f"{cause!r}, an expectation of this "
                                    "Brain; the state of work here is never "
                                    "imported")
                else:
                    problems.append(f"{where}: answers {cause!r}, which is "
                                    "not a decision form's question in this "
                                    "batch")
                continue
        for col in ("conversation", "turn", "caused_by"):
            refer(where, row.get(col))
        for a in row.get("about") or ():
            refer(where, a)
        try:
            json.dumps(row.get("detail") or {})
        except (TypeError, ValueError):
            problems.append(f"{where}: its detail is not JSON")
        out_acts.append(row)

    if problems:
        raise ImportRefused(problems)
    pre_open = _capture_open_work(store)
    return {"entries": out_entries, "acts": out_acts, "rewritten": rewritten,
            "_pre_open": pre_open}


def _ends_standing_here(store, vocab, target) -> bool:
    """Would superseding `target`, which is here, change standing here?

    It would if `target` stands. It would too if `target` is a link that
    carries a substrate role and still counts: superseding an establishing
    link withdraws what it established, and superseding a superseding link
    reinstates what it ended."""
    if stands_here(store, vocab, target):
        return True
    rows = store.by_ids([target])
    if rows and rows[0].get("link") and _link_role(vocab, rows[0]) in (
            seed.ESTABLISHES, seed.SUPERSEDES):
        return _counts(store, vocab, target, {})
    return False


def _closes(answer, question) -> bool:
    """Does this answer act close this question, as `expectation_state`
    reads it? Its carrier is `about[0]`: no assignment act is importable."""
    d, qd = answer.get("detail") or {}, question.get("detail") or {}
    carrier = (question.get("about") or [None])[0]
    by_carrier = carrier is not None and answer.get("actor") == carrier
    if qd.get("reconsideration"):
        return (answer["act"] == "expectation-met" and by_carrier
                and (bool(d.get("withdrawn")) or "selections" in d))
    if qd.get("expects") == "input":
        return (answer["act"] == "expectation-met" and by_carrier
                and bool(d.get("withdrawn")))
    if answer["act"] == "expectation-met":
        return True
    return by_carrier                         # decision-answered


def _question_problem(row, forms, closers) -> str | None:
    """Why this `expectation-recorded` may not be written here, or None.

    A question is an expectation of somebody, so written OPEN it would be
    work owed on this Brain (review ent-cca01f8347bb, D1). It arrives only
    as a question of a decision form in this same batch, closed in this
    same batch, and never carrying what the wake check reads as its own
    review of a run (D2)."""
    detail = row.get("detail") or {}
    if not detail.get("form"):
        return "an expectation that is not a decision form's question"
    if REVIEW_KEYS & set(detail):
        return ("a question carrying "
                f"{', '.join(sorted(REVIEW_KEYS & set(detail)))}; reviews of "
                "work are this Brain's own and never imported")
    if detail["form"] not in forms:
        return (f"a question of form {detail['form']!r}, which is not a "
                "decision form in this batch")
    if not any(_closes(a, row) for a in closers):
        return ("a decision form's question that this batch does not close; "
                "written open it would be a decision owed on this Brain")
    return None


def replies_closing_work_here(store, entries) -> dict:
    """{link id: reason} for each reply link in `entries` that would answer
    an expectation open HERE (ent-8b37c98bb8d5). Read-only.

    THE ONE RULE: `check` refuses these, and the exchange's selection
    (`mentis.exchange._select`) holds them back, so a preview and an apply
    never hand the door a batch it refuses for this."""
    entries = list(entries)
    batch = {r["id"] for r in entries}
    targets = sorted({(r.get("link") or {}).get("to") for r in entries
                      if (r.get("link") or {}).get("relation") == REPLIES_TO}
                     - batch - {None})
    found_e, _ = _present(store, targets, [])
    return _replies_closing_work_here(store, entries, found_e)


def _replies_closing_work_here(store, entries, found_e) -> dict:
    """The reply links in this batch that would answer an expectation that
    is open HERE (ent-8b37c98bb8d5), each with why.

    An expectation that is not a decision form's question, an input or a
    reconsideration is answered by a reply its carrier writes to its Turn
    -- to ANY Turn when it names none (`expectation_state`). So a reply
    from the carrier would close work this Brain holds, whatever runs of it
    are open, and is refused."""
    links = [r for r in entries
             if (r.get("link") or {}).get("relation") == REPLIES_TO]
    if not links:
        return {}
    batch = {r["id"]: r for r in entries}
    froms = sorted({r["link"]["from"] for r in links} - set(batch))
    author = {rid: r.get("attributed_to") for rid, r in batch.items()}
    author.update(_authors(store, froms))
    turns = sorted({r["link"]["to"] for r in links} & set(found_e))
    asked = [a for t in turns
             for a in store.operational(turn=t, act="expectation-recorded")]
    asked += [a for a in store.operational(act="expectation-recorded")
              if a.get("turn") is None]
    problems, memo = {}, {}
    for exp in asked:
        d = exp.get("detail") or {}
        if d.get("form") or d.get("reconsideration") \
                or d.get("expects") == "input":
            continue
        carrier = _carrier_here(store, exp)
        if carrier is None:
            continue
        hits = [r for r in links
                if (r.get("attributed_to") == carrier
                    or author.get(r["link"]["from"]) == carrier)
                and (exp.get("turn") is None
                     or r["link"]["to"] == exp["turn"])]
        if hits and _open_here(store, exp, carrier, memo):
            for r in hits:
                problems.setdefault(
                    r["id"],
                    f"a reply by {carrier!r} that would answer "
                    f"{exp['id']!r}, which is open on this Brain; the state "
                    "of work here is never imported")
    return problems


def _authors(store, ids) -> dict:
    ids = sorted(ids)
    return {e["id"]: e.get("attributed_to") for k in range(0, len(ids), 500)
            for e in store.by_ids(ids[k:k + 500])}


def _carrier_here(store, exp):
    """`assigned_carrier`: the latest assignment, else who it was asked of."""
    assigned = [a for a in store.operational(caused_by=exp["id"],
                                             act="expectation-assigned")
                if a.get("about")]
    if assigned:
        return max(assigned, key=lambda a: a["at"])["about"][0]
    return (exp.get("about") or [None])[0]


def _open_here(store, exp, carrier, memo) -> bool:
    """Is this expectation here still unanswered: none of its own acts (the
    walk stops at each child expectation, `_own_acts`) meets it, and no
    reply by its carrier answers it?"""
    frontier, seen = [exp["id"]], {exp["id"]}
    while frontier:
        nxt = []
        for _, a in store.operational_under(frontier):
            if a["id"] in seen:
                continue
            seen.add(a["id"])
            if a["act"] == "expectation-met":
                return False
            if a["act"] != "expectation-recorded":
                nxt.append(a["id"])
        frontier = nxt
    key = exp.get("turn")
    if key not in memo:
        memo[key] = (store.links(relation=REPLIES_TO, to=key)
                     if key is not None else store.links(relation=REPLIES_TO))
    replies = memo[key]
    authors = _authors(store, {r["link"]["from"] for r in replies})
    return not any(r.get("attributed_to") == carrier
                   or authors.get(r["link"]["from"]) == carrier
                   for r in replies)


# -- structural standing (O5) --------------------------------------------------

def establish_structural(corpus, ids, *, owner, caused_by=None,
                         because=None) -> dict:
    """Establish imported Conversations, Topics and Participants as ONE act
    by `owner`, this Brain's owner, on this Brain.

    Each gets one establishing link attributed to the owner, and one
    `import-established` act names them all, in one transaction. Nothing
    is copied from the origin: its establishing links never travel, and
    `evidence.json` is evidence. Anything that is not a node of one of
    `STRUCTURAL_KINDS` -- a rule, a decision, a procedure, a placement, an
    intake designation, any link -- is refused, the whole call with it, and
    nothing is written. What is established is each one's CURRENT version
    (`history`'s newest), as a rename here establishes its new version; one
    that already stands is left as it is and listed under `already`.
    `established` maps each version established to its establishing link.
    """
    if not owner:
        raise ImportRefused(["structural standing is given by this Brain's "
                             "owner, and none was named"])
    ids = list(dict.fromkeys(ids))
    rows = {e["id"]: e for e in corpus.read(ids)}
    problems = []
    for eid in ids:
        e = rows.get(eid)
        if e is None:
            problems.append(f"{eid}: not in this Brain")
            continue
        kind = (e.get("definition") or {}).get("name")
        if e.get("family") != "entry" or e.get("link") \
                or kind not in STRUCTURAL_KINDS:
            problems.append(
                f"{eid}: a {kind or e.get('family')!r}"
                f"{' link' if e.get('link') else ''}; only "
                f"{', '.join(STRUCTURAL_KINDS)} are established by an import, "
                "and rules, decisions, procedures, placements and intake "
                "designations never are")
    if problems:
        raise ImportRefused(problems)
    made, already = {}, []
    with corpus.atomic():
        for eid in ids:
            # THE CURRENT VERSION, as a rename here establishes it: a
            # Conversation imported with its renames is established under its
            # latest name, and its root stays superseded by it
            head = corpus.history(eid)[-1]
            kind = ((corpus.read([head]) or [{}])[0].get("definition")
                    or {}).get("name")
            if kind not in STRUCTURAL_KINDS:
                raise ImportRefused([f"{eid}: its current version {head} is "
                                     f"a {kind!r}"])
            if corpus.stands(head)["stands"]:
                already.append(head)
                continue
            made[head] = corpus.establish(
                head, attributed_to=owner,
                reason="established on import into this Brain, by its owner; "
                       "the other Brain's standing did not travel")
        act = None
        if made:
            act = corpus.record_operational(
                actor=owner, act=STRUCTURAL_ACT, caused_by=caused_by,
                because=because or "imported structure, established here",
                about=list(made), detail={"established": made})
    return {"act": act, "established": made, "already": already}


def open_response_sets_here(store) -> dict[str, dict]:
    """sid -> {'expectation': exp_id, 'carrier': carrier} for every response set
    belonging to an open input expectation on this Brain."""
    open_sets = {}
    try:
        cv = _conversations_over_store(store)
    except Exception:
        return {}
    for a in store.operational(act="expectation-recorded"):
        d = a.get("detail") or {}
        if d.get("expects") == "input" or d.get("response_set"):
            sid = d.get("response_set")
            if not sid:
                continue
            st = cv.expectation_state(a["id"])
            if not st.get("response_present") and not st.get("withdrawn"):
                open_sets[sid] = {
                    "expectation": a["id"],
                    "carrier": st.get("expected_of"),
                }
    return open_sets


def responses_closing_work_here(store, entries) -> dict:
    """The public selection rule for response-set entries (R2)."""
    batch = {r["id"] for r in entries}
    targets = sorted({(r.get("link") or {}).get("to") for r in entries}
                     - batch - {None})
    found_e, _ = _present(store, targets, [])
    return _responses_closing_work_here(store, entries, found_e)


def _responses_closing_work_here(store, entries, found_e) -> dict:
    """The response-set entries (marked-ready, answers) in this batch that
    would answer or attach to an input or response set open HERE (R2),
    each with why."""
    open_sets = open_response_sets_here(store)
    if not open_sets:
        return {}
    problems = {}
    for r in entries:
        link = r.get("link") or {}
        to = link.get("to")
        if to in open_sets:
            info = open_sets[to]
            problems[r["id"]] = (
                f"a response-set entry for {to!r} that would answer "
                f"{info['expectation']!r}, which is open on this Brain; the state "
                "of work here is never imported")

    for r in entries:
        if r.get("id") in problems:
            continue
        body = r.get("body") or {}
        sid = body.get("set")
        if sid in open_sets:
            info = open_sets[sid]
            problems[r["id"]] = (
                f"a response-set entry for {sid!r} that would answer "
                f"{info['expectation']!r}, which is open on this Brain; the state "
                "of work here is never imported")
            continue
        link = r.get("link") or {}
        if link:
            from_id = link.get("from")
            to_id = link.get("to")
            if from_id in problems:
                problems[r["id"]] = problems[from_id]
            elif to_id in problems and to_id in open_sets:
                info = open_sets[to_id]
                problems[r["id"]] = (
                    f"a response-set entry for {to_id!r} that would answer "
                    f"{info['expectation']!r}, which is open on this Brain; the state "
                    "of work here is never imported")

    return problems


def _conversations_over_store(store):
    from mentis.spine.seam import Corpus
    from mentis.conversation import Conversations
    c = Corpus.__new__(Corpus)
    c.root = store.root
    c._store = store
    c._pinned = {}
    c._role_cache = {}
    c._proposing_cache = {}
    return Conversations(c)


def _capture_open_work(store) -> dict:
    try:
        cv = _conversations_over_store(store)
    except Exception:
        return {}
    from mentis.operational.work import owed_by
    open_exps = {}
    try:
        open_states = cv.expectations(open_only=True)
    except Exception:
        return {}
    for st in open_states:
        eid = st["expectation"]
        carrier = st.get("expected_of")
        was_owed = False
        if carrier:
            try:
                was_owed = any(o["expectation"] == eid
                               for o in owed_by(cv, carrier, limit=1000)["owed"])
            except Exception:
                was_owed = True
        open_exps[eid] = {
            "expectation": eid,
            "carrier": carrier,
            "was_owed": was_owed,
            "turn": st.get("turn"),
            "conversation": st.get("conversation"),
            "expects": st.get("expects"),
        }
    return open_exps


def verify_work_invariants(store, allowed, entries, acts):
    pre_open = (allowed or {}).get("_pre_open") or {}
    if not pre_open:
        return
    cv = _conversations_over_store(store)
    from mentis.operational.work import owed_by
    problems = []
    affected_rows = [r["id"] for r in entries] + [r["id"] for r in acts]
    affected_str = ", ".join(affected_rows[:5])
    if len(affected_rows) > 5:
        affected_str += f" (and {len(affected_rows) - 5} more)"

    for eid, pre in pre_open.items():
        try:
            st = cv.expectation_state(eid)
        except Exception:
            problems.append(
                f"expectation {eid!r} was open before import but cannot be read "
                f"after import (rows: {affected_str})")
            continue

        carrier = pre.get("carrier")
        is_closed = False
        reason = None

        if st.get("response_present"):
            is_closed = True
            reason = "its response is now present"
        elif st.get("satisfied_by"):
            is_closed = True
            reason = "it has been satisfied/met"
        elif st.get("withdrawn"):
            is_closed = True
            reason = "it was withdrawn"
        elif st.get("replies_from_expected"):
            is_closed = True
            reason = "a reply from the expected carrier was recorded"
        elif (pre.get("expects") == "input"
              and st.get("input", {}).get("ready")):
            is_closed = True
            reason = "its response set was marked ready"
        elif pre.get("was_owed") and carrier:
            try:
                owed_now = any(o["expectation"] == eid
                               for o in owed_by(cv, carrier, limit=1000)["owed"])
                if not owed_now:
                    is_closed = True
                    reason = "it stopped being owed"
            except Exception:
                pass

        if is_closed:
            problems.append(
                f"import would close work on this Brain: expectation {eid!r} "
                f"was open before import but {reason} (rows: {affected_str})")

    if problems:
        raise ImportRefused(problems)
