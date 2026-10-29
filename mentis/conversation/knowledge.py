"""Selecting propositional material because it may answer a question.

THE SECOND LADDER, AND WHY IT IS A SEPARATE ONE. Delivery already had a way of
choosing material: what somebody PLACED here and established, which reaches an
execution because it GOVERNS the work. That is the whole answer for procedural
material and it is the wrong question entirely for propositional material. A
finding is not placed at a Conversation and does not apply to it; it is either
relevant to what is being asked or it is not. So relevance is computed here,
against the question, and nothing about this read makes anything govern
anything.

TERM OVERLAP, AND NOT AN INDEX. Nothing here needs one yet: this Brain holds
thousands of entries, not millions, and the honest shape of the requirement is
"material whose words overlap the question's words". An embedding store, a
ranking model or an inverted index would each be a new mechanism carrying its
own failure modes, tuned against no measurement, to answer a question a `for`
loop answers. When a measurement says the loop is too slow, that measurement
is the warrant for an index -- and until then the loop is the honest
implementation and its limits are visible in it.

WHAT IS HANDED OVER AS WHAT, AND WHY THE LINE MOVED. This read used to say
that material nobody established must never be handed to an execution at all,
because handing it over as an answer would make writing something down the way
to be believed. The reason was right and the rule drawn from it was too wide.
What it protected against is material being BELIEVED -- delivered with the
force of something the Brain asserts -- and the owner's decisions on the
Epistemic Ladder (Turn #12 of "Epestemic Ladder", ent-5bfed2a54cda) keep
exactly that and no more:

  ADOPTED KNOWLEDGE is what stands: material of a `knowing: that` Kind the
  owner established and nothing superseded. `considered` selects it, and only
  it is ever delivered as knowledge, adopted, or anything a run may treat as
  the Brain's position.

  RELEVANT EXPERIENCE is what was recorded and not adopted. It MAY reach a
  run -- `recorded_matching` finds it and `ladder.experience_refusal` says
  which of it may -- but only under its own label, saying it was not adopted,
  with who recorded it, its basis, its limits, its outcomes and every open
  challenge beside it, and worded as evidence to weigh, never as instruction.
  Never as adopted, never as governing. Writing something down still makes
  nobody believe it; it makes it something the next run can CHECK.

Superseded and deleted material reaches nobody on either tier, for the reason
it always did: it was carried forward and is not any more.

AND THIS CONFERS NOTHING. It is knowledge selection. It decides no question,
settles nothing, gives nothing standing and directs nobody. What comes back is
material with the evidence of why it was thought relevant, for a reader to
weigh -- and which tier it is on is read from the record, not from this read.
"""

from __future__ import annotations

import math
import re

# THE VALUE THIS READ SELECTS ON, taken from the Conversation layer's own
# vocabulary rather than from the spine: this layer reaches the spine only
# through the public seam, and a literal here would be a third copy.
from . import KNOWING_THAT

#: WHY THREE. Shorter tokens are almost all function words -- "is", "a", "to",
#: "of" -- and a token that appears in most material is not evidence about any
#: of it. Three is the shortest length at which a token usually names
#: something, and it is a threshold rather than a stop-word list because a
#: curated list of English words is a small dictionary nobody maintains.
_SHORTEST_TOKEN = 3

#: HOW MUCH OF THE KNOWLEDGE CHANNEL ONE DELIVERY CARRIES. A bound, kept: a
#: question that happens to overlap four hundred standing findings must not put
#: four hundred of them in front of an execution, and "all of it" is not a
#: budget. Five is not measured and is not claimed to be optimal; what IS
#: claimed is that the cut is VISIBLE. Everything this bound excludes is named
#: in the composition's `withheld` with the bound stated, so the number can be
#: argued with from the record rather than guessed at from an empty answer.
#:
#: `compose` NOW HAS TWO BOUNDS, BY THE OWNER'S DECISION 4
#: (`ladder.ADOPTED_BOUND`, `ladder.EXPERIENCE_BOUND`): one for adopted
#: knowledge and one for relevant experience, so recorded material can never crowd adopted material
#: out of a delivery, nor the reverse. This stays the default for `answering`.
DELIVERY_LIMIT = 5

#: BM25's two constants, at their usual values: how quickly a further match
#: stops adding (k1) and how much an entry's length discounts its matches (b).
#: Used for ORDER only (`_matching`); nothing is cut by a score.
_K1 = 1.2
_B = 0.75

#: A MINIMUM RELEVANCE, FOR BOTH TIERS, said in words rather than as a score.
#: Material must match REAL OVERLAP with the question's CONTENT WORDS -- its
#: words less the function words below: two distinct content words of a
#: question that has three or more, one of a shorter question. Measured on
#: INTEGRATION: "Summarise the minutes of the budget committee and list the
#: three action items" reached a semver lesson on "the", "and" and "three" --
#: one content word, so it no longer does, while the semver task's own words
#: still reach it.
#:
#: AND HOW COMMON A WORD IS NEVER DECIDES WHETHER MATERIAL MATCHES. Rarity
#: ORDERS what matched and nothing else. The first repair also used it to
#: decide which words counted -- one in more than half the entries read was
#: treated as a function word -- and that made the subject of the work
#: ineligible exactly where the record knows most about it: thirty findings
#: on SQLite WAL checkpoints made "sqlite", "wal" and "checkpoints" common, and
#: the ADOPTED lesson on WAL checkpoints stopped reaching "Explain SQLite WAL
#: checkpoints", with nothing withheld (re-review adm-0ef8f1b6c273, R1). A
#: word being frequent says the record has a lot on it, not that it is not
#: about anything.
_REAL_OVERLAP = 2

#: THE FUNCTION WORDS. English grammatical words of three or more letters --
#: not a list of topics, and nothing here is ever a reason to deliver; a word
#: on it only stops counting as overlap or as weight. Measured on INTEGRATION:
#: in a record of 27 entries a garden welcome note reached a note on "note",
#: "for" and "the".
_FUNCTION_WORDS = frozenset("""
    the and for are but not nor yet you your yours our ours all any can could
    had has have having was were been being does did done will would shall
    should may might must one its his her hers him she they them their theirs
    this that these those there here then than when where which while who whom
    whose what why how with without within into onto from upon about above
    below over under after before again also just only some such each both
    very more most other others own too out off now yes because until unless
    since though although whether either neither per via
    """.split())

#: THE LENGTH FLOOR (`_matching`): words matched, discounted by length against
#: an ORDINARY STATEMENT of `_ORDINARY_CHARS`, must come to `_MIN_SHARE` of the
#: overlap such a statement needs. No word counts for less because it is
#: common. Absolute, not the median: in the day-to-day record the median
#: propositional entry IS a 7,000-character experiment log (measured on a
#: copy, 2026-10-24), so against the median those logs are "ordinary" and
#: nothing could tell three incidental words in one from a lesson's overlap.
#: A lesson or finding statement runs to a few hundred characters.
_ORDINARY_CHARS = 600
_MIN_SHARE = 0.5


def tokens_of(question: str) -> list[str]:
    """The question's words, lowercased, in the order they were said.

    NON-ALPHANUMERICS SEPARATE, so punctuation, paths and hyphenation split
    rather than being kept as part of a word. Distinct, because a token said
    twice is one term and counting it twice would weigh repetition.
    """
    seen, out = set(), []
    for t in re.split(r"[^0-9a-z]+", (question or "").lower()):
        if len(t) >= _SHORTEST_TOKEN and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def meets(question, text) -> list[str]:
    """The question's content words `text` contains, when they are REAL
    OVERLAP (`_REAL_OVERLAP`, by the same rule `_matching` holds material
    to); else empty.

    For a short statement of where something APPLIES -- a Discipline's or a
    Workflow's "When it applies" -- not for material that states something:
    no length floor and no ordering, because there is nothing here to rank
    and an applicability line is never a 7,000-character log. Deterministic,
    and the words returned are the evidence for why it was pointed to."""
    wanted = [t for t in tokens_of(question) if t not in _FUNCTION_WORDS]
    if not wanted or not isinstance(text, str):
        return []
    lowered = text.lower()
    found = [t for t in wanted if t in lowered]
    need = _REAL_OVERLAP if len(wanted) > _REAL_OVERLAP else 1
    return found if len(found) >= need else []


def considered(corpus, question) -> list[dict]:
    """Standing propositional material whose words overlap the question.

    WHAT IS CONSIDERED, and every part of it is a stated condition rather than
    a Kind name: an entry (not a link, not a definition), whose Kind's CURRENT
    definition declares `knowing == "that"`, and which stands. `knowing` is
    read from the current definition and nowhere else -- one source, no
    fallback -- because whether a Kind's material states something is a fact
    about the vocabulary NOW. ABSENT IS NOT A VALUE: a Kind that declares no
    `knowing` is in neither ladder and is delivered by neither channel, which
    is what keeps the record's own furniture out of both.

    THE WORDS OF AN ACT ARE NOT MATERIAL. A note that holds a challenge's
    objection, an adoption request's because or a decline's reason is
    established or recorded BY that act, and its words travel with the
    material the act was on (`ladder.is_act_words`). Offered on its own it
    would reach a run as adopted knowledge, which nobody adopted.

    ONLY `text` AND `limits` ARE MATCHED, AND THAT IS A REAL LIMIT. `limits`
    is matched because it says the circumstances the material holds in, which
    is exactly what a question about those circumstances is asking. An
    `outcome` carries `result` and `attempted` beside its `text` and neither
    is searched;
    a Persona's `behaviour` is not searched here at all (it is procedural, so
    it is not considered); and a Kind that declares no `text` field CANNOT
    MATCH ANYTHING, however relevant its material is. Matching every string
    field would mean this read deciding which of a Kind's fields carry its
    statement, which is a vocabulary question and not this function's. The
    limit is visible and narrow, which is better than a guess that is neither.

    ORDERED BY HOW MUCH OF THE QUESTION EACH ONE TOUCHES -- distinct tokens
    matched, descending -- and then by `recorded_at`, newest first. That is a
    sort key, NOT A SCORE: no number leaves this function. What leaves is
    `answered`, the tokens that actually matched, which is the evidence for why
    the material was offered and is something a reader can disagree with. A
    relevance float would be the same claim with the evidence thrown away.

    AND FINDING NOTHING IS AN ANSWER. A question no standing material speaks
    to returns `[]`, and so does a question with no usable tokens in it.
    Recent material is never substituted: "here is what this Brain knows about
    that" and "here is what it happened to write down lately" are different
    claims, and quietly making the second when the first is empty is how a
    record starts lying about what it knows.

    UNBOUNDED, AND THAT IS WHY IT IS A SEPARATE FUNCTION FROM `answering`.
    EVERYTHING this read considered relevant comes back, in order. The budget
    belongs to the caller, because the caller is the only thing that can SAY
    what it left out: this function cutting the list itself is how nine
    matching lessons became five delivered and four that nothing anywhere
    mentioned -- the exact "dropped three items without even being able to say
    which" that `compose`'s own docstring says Mark III did and this does not.
    """
    from .ladder import is_act_words
    return [_public(r) for r in _matching(corpus, question)
            if r["_stands"] and not is_act_words(corpus, r["entry"])]


def recorded_matching(corpus, question) -> list[dict]:
    """Recorded, unadopted propositional material whose words overlap the
    question: the CANDIDATES for Relevant experience, in the same order and
    with the same evidence `considered` gives.

    CANDIDATES, NOT DELIVERIES. What does not stand and was not superseded or
    deleted comes back here; whether each may actually reach a run -- the
    words of an act, a supersession or deletion -- is
    `ladder.experience_refusal`'s, so that the conditions live once, beside
    the rest of the Ladder's reads, and delivery can name what each one kept
    out rather than this read dropping it silently.
    """
    return [_public(r) for r in _matching(corpus, question)
            if not r["_stands"] and not r["_superseded"]]


def _public(row) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _matching(corpus, question) -> list[dict]:
    """Every propositional entry whose words overlap the question, ordered,
    with whether it stands and whether it was superseded kept privately.

    ONLY THE QUESTION'S CONTENT WORDS DECIDE: whether material matched, how
    much overlap it has and what it weighs are read from them alone, and a
    question of nothing but function words matches nothing. `answered` still
    says every word of the question the material contains, in the order it
    was said, because it is the evidence shown -- not the reason."""
    said = tokens_of(question)
    wanted = [t for t in said if t not in _FUNCTION_WORDS]
    if not wanted:
        return []

    knows = {}

    def propositional(kind):
        if kind not in knows:
            current = corpus.current_definition(kind) or {}
            knows[kind] = (current.get("body") or {}).get("knowing")
        return knows[kind] == KNOWING_THAT

    # ONLY THE PROPOSITIONAL KINDS' ENTRIES ARE READ. This loop used to decode
    # every entry in the corpus -- every link, every Source Admission -- to
    # throw away all but these: 0.003 s with no Sources, 0.1 s of reading
    # alone with 10k Admissions, on every dispatch (R2). Which Kinds those are
    # is the same question asked of the vocabulary first; the loop below is
    # unchanged, and so is what it keeps and in what order.
    #
    # AND NO KIND IS JUDGED OLDER THAN THE WHOLE-CORPUS READ JUDGED IT. That
    # read judged each Kind lazily, at its first entry in the loop, and asked
    # `stands` as it went; this judges every Kind before the entries are read
    # and keeps the judgement through the loop. So the WHOLE computation --
    # Kinds, entries and the loop -- is taken only if nothing was written
    # while it ran (`Corpus.settled`), and otherwise taken again; after a few
    # tries the whole-corpus read answers, exactly as it did. A Kind defined,
    # or redefined, at any point in the call is never judged on its old
    # definition (R2 re-review, adm-6a12b15130e0).
    def judged(entries):
        found = []
        # HOW MANY OF THE ENTRIES READ CONTAIN EACH WORD, for the ranking
        # below. Counted over every propositional entry with words, matched or
        # not, in this same pass.
        seen.clear()
        seen.update({t: 0 for t in wanted})
        lengths.clear()
        read = 0
        for e in entries:
            if e.get("family") != "entry" or e.get("link") is not None:
                continue
            kind = (e.get("definition") or {}).get("name")
            if not kind or not propositional(kind):
                continue
            text = (e.get("body") or {}).get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            limits = (e.get("body") or {}).get("limits")
            limits = limits if isinstance(limits, str) and limits.strip() \
                else None
            lowered = (text + " " + (limits or "")).lower()
            content = [t for t in wanted if t in lowered]
            read += 1
            lengths.append(len(lowered))
            for t in content:
                seen[t] += 1
            if not content:
                continue
            standing = corpus.stands(e["id"])
            found.append({"entry": e["id"], "kind": kind, "text": text,
                          **({"limits": limits} if limits else {}),
                          "answered": [t for t in said if t in lowered],
                          "_content": content,
                          "_stands": standing["stands"],
                          "_superseded": bool(standing["superseded_by"]),
                          "_len": len(lowered),
                          "_at": e.get("recorded_at") or 0.0})
        population[0] = read
        return found

    seen: dict[str, int] = {}
    population = [0]
    lengths: list[int] = []

    def indexed():
        knows.clear()
        kinds = sorted({k for k in (d["definition"]["name"]
                                    for d in corpus.definitions())
                        if propositional(k)})
        return judged(corpus.entries_of_kinds(kinds))

    def whole():
        knows.clear()
        return judged(corpus.all_entries())

    found = corpus.settled(indexed, whole)

    # MOST OF WHAT IS DISTINCTIVE IN THE QUESTION FIRST, then the most recent.
    # A word counts by how rare it is among the entries read (log of how many
    # entries there are over how many contain it), so a match on "the" -- which
    # is in nearly everything, and matches "these" and "there" as well -- is
    # worth almost nothing, and a match on the subject of the work is worth a
    # great deal. AND A LONG ENTRY'S MATCHES ARE DISCOUNTED: a word found
    # somewhere in a 7,000-character log is weaker evidence than the same word
    # in a 400-character lesson, because words are matched as substrings and a
    # long enough text contains nearly all of them. BM25's length
    # normalisation with presence-only term frequency (k1 1.2, b 0.75),
    # against the MEDIAN length -- the mean is dragged up by exactly the long
    # entries in question -- with the ratio rounded to a whole number and never
    # below one, so entries of ordinary length are equal, and two that answer
    # the same words still tie and the newer comes first, as it always did.
    # Measured on INTEGRATION: counted equally, a dispatched task's common
    # words let four unrelated 7,000-character experiment logs fill Relevant
    # experience ahead of the one lesson about the work. Equal weight still
    # orders newest first.
    # STABLE SORTS, WEAKEST KEY FIRST: newest first, then by words answered,
    # then by weight; each sort preserves the last among equals. `_at` and
    # `_weight` are sort keys and leave with nothing.
    n = population[0]
    need = _REAL_OVERLAP if len(wanted) > _REAL_OVERLAP else 1
    found = [r for r in found if len(r["_content"]) >= need]
    lens = sorted(lengths)
    median = float(lens[len(lens) // 2]) if lens else 1.0
    rarity = {t: math.log((n + 1) / (seen.get(t, 0) + 1)) for t in wanted}

    def norm_at(length, against):
        ratio = max(1, round(length / (against or 1.0)))
        return (_K1 + 1) / (1 + _K1 * (1 - _B + _B * ratio))

    for r in found:
        r["_weight"] = round(norm_at(r["_len"], median)
                             * sum(rarity[t] for t in r["_content"]), 9)
    # AND ENOUGH OF IT, FOR ITS LENGTH. Two words in common is real overlap
    # in a lesson and nothing in a 7,000-character log, which contains almost
    # any two words. So the words an entry matched are discounted by its
    # length against an ordinary statement (`_ORDINARY_CHARS`), with the same
    # normalisation as its weight, and must come to at least _MIN_SHARE of
    # `need`: anything up to three ordinary statements long is held only to
    # `need` (two words), and a 7,000-character log must match six. Matching
    # EVERY content word of the question is always enough. EVERY WORD COUNTS
    # ONE HERE, however common: this floor is
    # about length, and how often a word occurs in the record never makes
    # matching material ineligible (R1). Measured on a copy of the
    # day-to-day record: the budget-minutes control's only candidates were
    # four such logs on "budget", "list" and "items"; Task B's lesson matches
    # five of its five words in 330 characters.
    found = [r for r in found
             if len(r["_content"]) == len(wanted)
             or norm_at(r["_len"], _ORDINARY_CHARS) * len(r["_content"])
             >= _MIN_SHARE * need]
    # Newest first, then most content words, then by weight: stable sorts.
    found.sort(key=lambda r: r["_at"], reverse=True)
    found.sort(key=lambda r: len(r["_content"]), reverse=True)
    found.sort(key=lambda r: r["_weight"], reverse=True)
    return found


def answering(corpus, question, *, limit=DELIVERY_LIMIT) -> list[dict]:
    """The first `limit` of `considered`, for a caller that only wants those.

    THE BOUND LIVES WITH THE CALLER THAT CAN ACCOUNT FOR IT. `compose` does not
    use this: it reads `considered` and names the remainder in `withheld`,
    because a delivery that drops material has to be able to say what it
    dropped. This is the convenience for a reader asking "what would be
    delivered", and it is honest only because it is not the thing deciding.
    """
    return considered(corpus, question)[:limit]
