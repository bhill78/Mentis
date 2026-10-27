"""The connector registry: what each kind of source is, and one door to all.

WHY A REGISTRY AND NOT A SECOND CONNECTOR. Everything about Bulk Source that
is not about folders -- declaration, scope and its revision, diff, the one
write path, absence, the reads, references and provenance -- is written once.
What differs per source is described here, as data the owner's interface
renders and the reads route by: how a source is bound, what its scope form
asks for, whether its preview is exact, how it can stay current, how it links
back to the live thing, how it is browsed, and what an object key is and how
it reads to a person.

THE FILESYSTEM AND GIT ARE AVAILABLE. Git is a repository on this machine,
read at a ref and never changed (`mentis.sources.git`). Slack, Jira, Confluence, Gmail, an HTTP
API, the Web and RSS/Atom are registered as UNAVAILABLE descriptors (owner
decision 5 added Web and RSS/Atom): listed so the choice and its shape can be
seen, refused if anything is asked of them, and promising nothing.

THE FACADE (`Sources`) is what `mentis.api.sources` hands a client. It routes
by a collection's DECLARED connector, so nothing above it names a connector
it does not have to; the filesystem `Connector` keeps its own behaviour.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from mentis.sources import (Refused, declaration, declarations,
                            effective_scope, source_id)


def _path_key(key) -> str:
    """A folder object's key: an NFC relative path with `/` separators."""
    return unicodedata.normalize(
        "NFC", str(key or "").replace("\\", "/").strip("/"))


def _path_label(key: str, observation: dict | None = None) -> str:
    """A folder object reads as its relative path."""
    return key


def _opaque_key(key) -> str:
    return str(key or "").strip()


def _native_label(key: str, observation: dict | None = None) -> str:
    native = (observation or {}).get("native") or {}
    return native.get("label") or key


@dataclass(frozen=True)
class Descriptor:
    id: str
    label: str
    available: bool
    #: `local-folder` | `account` | `endpoint`
    binding: str
    #: what the scope form asks for, as a schema the interface renders
    scope_fields: list = field(default_factory=list)
    presets: list = field(default_factory=list)
    #: `exact` | `bounded`
    preview: str = "exact"
    modes: tuple = ("one-time",)
    #: `local-reveal` | `permalink` | None
    live: str | None = None
    #: `hierarchy` | `channel-thread` | `chronology` | `issues` | ...
    browse: str = "hierarchy"
    #: what an object key is, said, and the two hooks that make it one
    key: str = "an opaque key"
    summary: str = ""
    connect: str = ""
    normalise: Callable = _opaque_key
    labelled: Callable = _native_label
    #: WHERE A COLLECTION OF THIS KIND CAN BE: `local-folder` (chosen on
    #: this machine) and/or `address` (a location elsewhere, typed). The
    #: interface draws a folder chooser or an address field from this, and
    #: never from which connector it is. Empty means just `binding`.
    locations: tuple = ()
    #: EVIDENCE CATEGORIES a scope form shows as visible toggles: each is a
    #: named set of exclude patterns, "off" while they are in the exclude
    #: list. Acquiring any of it newly needs a category decision (K5).
    categories: list = field(default_factory=list)

    def public(self) -> dict:
        return {"id": self.id, "label": self.label,
                "available": self.available, "binding": self.binding,
                "locations": list(self.locations or (self.binding,)),
                "scope_fields": self.scope_fields, "presets": self.presets,
                "preview": self.preview, "modes": list(self.modes),
                "live": self.live, "browse": self.browse,
                "key": self.key, "connect": self.connect, "summary": self.summary,
                **({"categories": self.categories} if self.categories
                   else {}),
                **({} if self.available else
                   {"why_not": "not available yet: described so its shape "
                               "can be seen, not promised"})}


_PATTERNS = [
    {"name": "include", "type": "patterns", "label": "Include",
     "default": ["*"],
     "help": "globs over relative paths; `*` crosses folders"},
    {"name": "exclude", "type": "patterns", "label": "Exclude",
     "default": [], "help": "globs; an excluded folder is never entered"},
]

from mentis.sources.sensitive import CATEGORIES, REPOSITORY_PRESET_EXCLUDES

#: K3, RECORDED WHERE PATTERNS ARE EXPLAINED: exclude always wins, so nothing
#: inside an excluded folder can be brought back by an include.
_FOLDER_FIELDS = [
    _PATTERNS[0],
    {**_PATTERNS[1],
     "help": "globs; an excluded folder is never entered, and nothing inside "
             "it can be re-included: exclude the narrower folder instead"},
]

_FOLDER_CATEGORIES = [
    {"id": c, "label": d["label"], "patterns": d["patterns"],
     "default": "off",
     "help": "off: these patterns are excluded, and what they match is "
             "reported as not selected. On: a preview lists what would be "
             "newly acquired and asks for your decision for the whole "
             "category. Not a check for secrets: no file is examined for "
             "them"}
    for c, d in CATEGORIES.items()]

#: THE FOLDER PRESETS. `Notes & documents` is what the owner chose for the
#: worked example; its patterns are exactly what the preview shows.

_FOLDER_PRESETS = [
    {"id": "everything", "label": "Everything", "include": ["*"],
     "exclude": []},
    {"id": "repository", "label": "Repository", "include": ["*"],
     "exclude": REPOSITORY_PRESET_EXCLUDES},
    {"id": "notes", "label": "Notes & documents",
     "include": ["*.md", "*.csv", "*.pdf"], "exclude": []},
    {"id": "custom", "label": "Custom", "include": None, "exclude": None},
]

#: THE REPOSITORY'S SCOPE: the folder's two pattern lists over paths, and the
#: two things only a repository has -- which ref it follows and how many
#: recent commits on that ref to take. `option: True` marks a field that is
#: not a pattern list: it travels as the scope's `options`, which the generic
#: code carries and compares and never interprets. Drawn by the same form.
_GIT_FIELDS = _PATTERNS + [
    {"name": "ref", "type": "text", "label": "Branch, tag or commit",
     "default": "", "option": True,
     "help": "what the collection follows; empty takes the repository's "
             "current branch, and that name is what is recorded"},
    {"name": "commits", "type": "number", "label": "Recent commits",
     "default": 10, "min": 0, "max": 1000, "option": True,
     "help": "newest first on that ref; 0 takes none. Older commits are not "
             "observed, and never called missing"},
]

_GIT_PRESETS = [
    {"id": "everything", "label": "Everything", "include": ["*"],
     "exclude": []},
    {"id": "docs", "label": "Documentation",
     "include": ["*.md", "*.markdown", "*.rst", "*.txt", "docs", "doc"],
     "exclude": []},
    {"id": "custom", "label": "Custom", "include": None, "exclude": None},
]


REGISTRY: dict[str, Descriptor] = {d.id: d for d in [
    Descriptor(
        summary="Files under a folder you choose",
        id="filesystem", label="Folder on this machine", available=True,
        binding="local-folder", scope_fields=_FOLDER_FIELDS,
        presets=_FOLDER_PRESETS, categories=_FOLDER_CATEGORIES,
        preview="exact",
        modes=("one-time", "manual-refresh"), live="local-reveal",
        browse="hierarchy", key="a relative path (NFC, `/`)",
        connect="choose a folder on this machine; the path stays here",
        normalise=_path_key, labelled=_path_label),
    Descriptor(
        summary="A repository on this machine, or its https or ssh address",
        id="git", label="Git repository", available=True,
        binding="local-folder", locations=("local-folder", "address"),
        scope_fields=_GIT_FIELDS,
        presets=_GIT_PRESETS, preview="exact",
        modes=("one-time", "manual-refresh"), live=None,
        browse="hierarchy",
        key="a path in the tree (NFC, `/`), or `.git/commits/<sha>`",
        connect="choose a repository on this machine, or give the https or "
                "ssh address of one elsewhere. A path stays on this machine; "
                "an address is fetched into this machine's own copy only when "
                "you preview, using the credentials Git on this machine "
                "already has. No credential is ever kept in the Brain, and "
                "the repository is only read",
        normalise=_path_key, labelled=_native_label),
    Descriptor(
        summary="Tables from a .db / .sqlite file, opened read-only",
        id="sqlite", label="SQLite database file", available=True,
        binding="local-file", scope_fields=[
            {**_PATTERNS[0], "help": "globs over percent-encoded table names"},
            {**_PATTERNS[1], "help": "excluded tables are never read"},
            {"name": "tables", "type": "sqlite-tables", "label": "Table rules", "default": {}, "option": True,
             "help": "per table: columns left out and row rules joined by AND; compiled to parameterised SQL, never typed SQL"}],
        presets=[{"id": "everything", "label": "All tables", "include": ["*"], "exclude": []}],
        modes=("one-time", "manual-refresh"), browse="hierarchy",
        key="table / injective typed primary or valid unique key; keyless table snapshot",
        connect="choose an absolute SQLite file path on this machine; only an atomic private snapshot is acquired",
        normalise=_opaque_key, labelled=_native_label),
    Descriptor(
        id="slack", label="Slack", available=False, binding="account",
        scope_fields=[
            {"name": "channels", "type": "list", "label": "Channels"},
            {"name": "since", "type": "date", "label": "From"},
            {"name": "threads", "type": "bool", "label": "Threads"},
            {"name": "files", "type": "bool", "label": "Files"}],
        preview="bounded", modes=("one-time", "connected"),
        live="permalink", browse="channel-thread",
        key="channel / message timestamp",
        connect="sign in (OAuth)"),
    Descriptor(
        id="jira", label="Jira", available=False, binding="account",
        scope_fields=[{"name": "projects", "type": "list", "label": "Projects"},
                      {"name": "jql", "type": "text", "label": "JQL"}],
        preview="bounded", modes=("one-time", "connected"),
        live="permalink", browse="issues", key="issue key",
        connect="site and API token"),
    Descriptor(
        id="confluence", label="Confluence", available=False,
        binding="account",
        scope_fields=[{"name": "spaces", "type": "list", "label": "Spaces"},
                      {"name": "subtrees", "type": "list",
                       "label": "Page subtrees"}],
        preview="bounded", modes=("one-time", "connected"),
        live="permalink", browse="hierarchy", key="page id",
        connect="site and OAuth"),
    Descriptor(
        id="gmail", label="Gmail", available=False, binding="account",
        scope_fields=[{"name": "labels", "type": "list", "label": "Labels"},
                      {"name": "query", "type": "text", "label": "Search"},
                      {"name": "since", "type": "date", "label": "From"}],
        preview="bounded", modes=("one-time", "connected"),
        live="permalink", browse="chronology", key="message id",
        connect="Google sign-in"),
    Descriptor(
        id="http-api", label="HTTP API", available=False, binding="endpoint",
        scope_fields=[{"name": "endpoint", "type": "text", "label": "Endpoint"},
                      {"name": "query", "type": "text", "label": "Query"},
                      {"name": "identity", "type": "text",
                       "label": "Identity field"}],
        preview="bounded", modes=("one-time", "connected"),
        live="permalink", browse="chronology",
        key="a field you name", connect="base URL and credential"),
    Descriptor(
        id="web", label="Web", available=False, binding="endpoint",
        scope_fields=[{"name": "urls", "type": "list", "label": "Pages"},
                      {"name": "depth", "type": "number",
                       "label": "Follow links to depth"}],
        preview="bounded", modes=("one-time", "manual-refresh"),
        live="permalink", browse="hierarchy", key="URL",
        connect="addresses to fetch"),
    Descriptor(
        id="rss-atom", label="RSS / Atom", available=False,
        binding="endpoint",
        scope_fields=[{"name": "feeds", "type": "list", "label": "Feeds"},
                      {"name": "since", "type": "date", "label": "From"}],
        preview="bounded", modes=("one-time", "connected"),
        live="permalink", browse="chronology", key="entry id",
        connect="feed addresses"),
]}


def descriptor(connector: str) -> Descriptor:
    d = REGISTRY.get(connector)
    if d is None:
        raise Refused(f"{connector!r} is not a connector Mentis knows")
    return d


def descriptors() -> list[dict]:
    return [d.public() for d in REGISTRY.values()]


def _module(connector: str):
    """The implementation of an AVAILABLE connector. Unavailable ones refuse
    here, so a descriptor can never be mistaken for a working connector."""
    d = descriptor(connector)
    if not d.available:
        raise Refused(f"the {d.label} connector is not available yet")
    if connector == "filesystem":
        from mentis.sources import filesystem
        return filesystem
    if connector == "git":
        from mentis.sources import git
        return git
    if connector == "sqlite":
        from mentis.sources import sqlite
        return sqlite
    raise Refused(f"{connector!r} has no implementation")  # pragma: no cover


def connector_of(corpus, collection: str) -> str:
    d = declaration(corpus, collection)
    if d is None:
        raise Refused(f"{collection!r} is not a collection declared in this "
                      "corpus")
    return d["connector"]


def normalise(connector: str, key) -> str:
    return descriptor(connector).normalise(key)


def label(connector: str, key: str, observation: dict | None = None) -> str:
    return descriptor(connector).labelled(key, observation)


def source_of(decl: dict) -> str:
    return source_id(decl["connector"], decl["collection"])


def _extract_after(corpus, result) -> None:
    """EXTRACTION IN THE BACKGROUND AFTER A SWEEP (Sources C, C2), for each
    newly present source with a current extractor -- whatever the
    connector. Writes nothing to the record, and never fails the sweep."""
    try:
        from mentis.sources.extract import engine
        engine.after_sweep(corpus, (result or {}).get("admitted") or ())
    except Exception:                                      # noqa: BLE001
        pass


#: WHICH CONNECTOR PREVIEWED EACH DRAFT. Confirming a draft names only the
#: draft (`POST /api/sources/sweep {draft, plan}`), and the draft lives in
#: the connector that made it, so the facade remembers which one that was --
#: a second connector's draft was otherwise confirmed against the folder
#: connector and refused as unknown. Process memory only, like the drafts
#: themselves, and bounded the same way.
_DRAFTED: dict[str, str] = {}
_DRAFTED_CAP = 64


def _drafted(draft, connector) -> None:
    if not draft:
        return
    _DRAFTED.pop(draft, None)
    _DRAFTED[draft] = connector
    while len(_DRAFTED) > _DRAFTED_CAP:
        _DRAFTED.pop(next(iter(_DRAFTED)))


def _address(connector: str, remote) -> dict:
    """`remote` for a connector whose collections can be at an address;
    refused, never dropped, for one whose cannot."""
    if remote is None:
        return {}
    d = descriptor(connector)
    if "address" not in (d.locations or (d.binding,)):
        raise Refused(f"the {d.label} connector takes a folder on this "
                      "machine, not an address")
    return {"remote": remote}


def _options(connector: str, options) -> dict:
    """`options` for a connector that declares option fields; refused, never
    dropped, for one that does not -- a scope field the owner filled in that
    nothing recorded would be a silent loss. An empty or absent one is
    nothing to pass."""
    d = descriptor(connector)
    named = {f["name"] for f in d.scope_fields if f.get("option")}
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise Refused("options are an object of the connector's own scope "
                      "fields")
    if not named:
        if options:
            raise Refused(f"the {d.label} connector has no scope options")
        return {}
    unknown = sorted(set(options) - named)
    if unknown:
        raise Refused(f"{unknown[0]!r} is not one of the {d.label} "
                      "connector's scope options")
    for f in d.scope_fields:
        value = options.get(f['name'])
        if f.get('option') and f['type'] in ('text', 'number') and isinstance(value, (dict, list)):
            raise Refused(f"options.{f['name']} must be text or a whole number")
    return {"options": options}


def _sensitive(connector, value, categories=None, decision_plan=None):
    if connector == "sqlite":
        return {"sensitive_decisions": value, "category_decisions": categories,
                "decision_plan": decision_plan}
    if value is None and categories is None:
        return {}
    if connector != "filesystem":
        raise Refused("sensitive and category decisions apply to folder "
                      "previews only")
    return {**({"sensitive_decisions": value} if value is not None else {}),
            **({"category_decisions": categories}
               if categories is not None else {})}


class Sources:
    """Every collection, every connector: one door. Routes owner operations
    by the collection's declared connector; the reads are generic."""

    def __init__(self, corpus, cv):
        self.corpus, self.cv = corpus, cv

    # -- what there is ------------------------------------------------------
    def descriptors(self):
        return descriptors()

    def check_options(self, connector, options):
        """Refuse malformed descriptor fields before starting background work."""
        return _options(connector, options)

    def _conn(self, collection):
        return _module(connector_of(self.corpus, collection)).Connector(
            self.corpus, self.cv)

    def _named(self, connector):
        return _module(connector).Connector(self.corpus, self.cv)

    def sqlite_inspect(self, root=None, *, collection=None, progress=None):
        module = _module("sqlite")
        if collection is not None:
            if connector_of(self.corpus, collection) != "sqlite":
                raise Refused("choose a SQLite collection")
            _, binding = module._ready(self.corpus, collection)
            root = binding["root"]
        return module.inspect(self.corpus, root, progress=progress)

    def sqlite_find(self, folder):
        return _module("sqlite").find(self.corpus, folder)

    def sqlite_sample(self, plan, table, rules=None):
        return _module("sqlite").sample(self.corpus, plan, table, rules)

    # -- owner operations -----------------------------------------------------
    def declare(self, name, *, connector="filesystem", include=None,
                exclude=None, declarer="human", written_by=None,
                options=None):
        return self._named(connector).declare(
            name, include=include, exclude=exclude, declarer=declarer,
            written_by=written_by, **_options(connector, options))

    def bind(self, collection, root=None, written_by=None, remote=None):
        return self._conn(collection).bind(
            collection, root, written_by=written_by,
            **_address(connector_of(self.corpus, collection), remote))

    def unbind(self, collection, written_by=None):
        return self._conn(collection).unbind(collection,
                                             written_by=written_by)

    def _scope_options(self, collection, scope) -> None:
        """A proposed scope's `options` are checked here, for EVERY path that
        proposes one -- plan, revise-and-sweep and plain revise alike -- so a
        connector with none refuses them rather than its `_proposed` quietly
        dropping them (independent review, F4)."""
        if isinstance(scope, dict) and scope.get("options") is not None:
            _options(connector_of(self.corpus, collection), scope["options"])

    def plan(self, collection, *, within=None, scope=None, progress=None,
             sensitive_decisions=None, category_decisions=None, decision_plan=None):
        self._scope_options(collection, scope)
        return self._conn(collection).plan(collection, within=within,
                                           scope=scope, progress=progress,
                                           **_sensitive(connector_of(self.corpus, collection), sensitive_decisions,
                                                        category_decisions, decision_plan))

    def sweep(self, collection, plan_id, *, within=None,
              acknowledge_binding_change=False, actor="human", scope=None,
              because=None, progress=None, sensitive_decisions=None,
              category_decisions=None, **written):
        self._scope_options(collection, scope)
        out = self._conn(collection).sweep(
            collection, plan_id, within=within,
            acknowledge_binding_change=acknowledge_binding_change,
            actor=actor, scope=scope, because=because, progress=progress,
            **_sensitive(connector_of(self.corpus, collection), sensitive_decisions,
                         category_decisions), **written)
        _extract_after(self.corpus, out)
        return out

    def revise_scope(self, collection, *, include, exclude, by,
                     because=None, written_by=None, options=None):
        """Record a revision without sweeping (the next plan uses it)."""
        from mentis.sources import record_revision
        conn = connector_of(self.corpus, collection)
        mod = _module(conn)
        inc = mod._patterns(include, ["*"])
        exc = mod._patterns(exclude, [])
        opts = _options(conn, options).get("options")
        if opts is not None:
            opts = mod.checked_options(
                opts, base=effective_scope(self.corpus, collection)["options"])
        act = record_revision(self.corpus, self.cv, collection, include=inc,
                              exclude=exc, by=by, because=because,
                              written_by=written_by, options=opts)
        return {"collection": collection, "revision": act,
                "scope": effective_scope(self.corpus, collection)}

    def preview_new(self, *, connector="filesystem", name, root=None,
                    include=None, exclude=None, progress=None, options=None,
                    remote=None, sensitive_decisions=None,
                    category_decisions=None, decision_plan=None):
        out = self._named(connector).preview_new(
            name=name, root=root, include=include, exclude=exclude,
            progress=progress, **_options(connector, options),
            **_address(connector, remote),
            **_sensitive(connector, sensitive_decisions, category_decisions, decision_plan))
        _drafted(out.get("draft"), connector)
        return out

    def acquire_new(self, draft, plan_id, *, connector=None,
                    actor="human", progress=None, **written):
        connector = connector or _DRAFTED.get(draft) or "filesystem"
        out = self._named(connector).acquire_new(draft, plan_id, actor=actor,
                                                 progress=progress, **written)
        _extract_after(self.corpus, out)
        return out

    def binding_state(self, collection):
        return self._conn(collection).binding_state(collection)

    def reveal(self, collection, obj):
        d = descriptor(connector_of(self.corpus, collection))
        if d.live != "local-reveal":
            raise Refused(f"a {d.label} object is not shown on this machine")
        return self._conn(collection).reveal(collection, obj)

    def folders(self, path=None):
        return self._named("filesystem").folders(path)

    def effective_scope(self, collection):
        return effective_scope(self.corpus, collection)

    # -- reads (generic) -------------------------------------------------------
    def collections(self):
        from mentis.sources import reading
        return reading.collections(self.corpus)

    def objects(self, collection, **kw):
        from mentis.sources import reading
        return reading.objects(self.corpus, collection, **kw)

    def history(self, collection, path):
        from mentis.sources import reading
        return reading.history(self.corpus, collection, path)

    def links(self, collection, path, *, ref=None):
        from mentis.sources import reading
        return reading.links(self.corpus, collection, path, ref=ref)

    def read(self, **kw):
        from mentis.sources import reading
        return reading.read(self.corpus, **kw)

    def search(self, q, **kw):
        from mentis.sources import search
        return search.search(self.corpus, q, **kw)

    def provenance(self, ref):
        from mentis.sources import reading
        return reading.provenance(self.corpus, ref)

    def compare(self, a, b):
        from mentis.sources import reading
        return reading.compare(self.corpus, a, b)

    def declarations(self):
        return declarations(self.corpus)
