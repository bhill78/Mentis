"""A recursive text search over a directory that holds secret files.

Round 2 (Builder A; docs/modernization/CONTRACT.md "Round 2 — A"). A shell
command such as `grep -r TOKEN .` reads only a directory by its path, so a
path check sees nothing protected -- yet its output prints the lines of every
`.env`, key or credentials file beneath it (live: Grep over a workspace
printed `.env`). This module says, for ONE simple command, whether it is such a
search and which secret files (`operations._SECRET_NAMES`) it would read. The
policy then treats the command as touching a protected location: asked of the
owner, refused under `deny`, allowed only under Approve All.

WHAT IS RECOGNISED, and nothing else:
  grep / egrep / fgrep   with -r, -R, --recursive, --dereference-recursive or
                         -d recurse. Every GNU grep option is known with its
                         value (-m 5, -A 2, -e PAT, --max-count=5, -rm5 ...) and
                         unique long-option prefixes are resolved as grep does.
                         Limits honoured: --include, --exclude (the last
                         matching one wins; with none matching a file is
                         searched unless the first is --include), --exclude-dir.
  rg                     always recursive. Every ripgrep option is known with
                         its value. Limits honoured: -g/--glob/--iglob (positive
                         and '!' negative, the later one wins, any positive glob
                         makes it a whitelist), -t/--type and -T/--type-not for
                         the common built-in types (and --type-add NAME:GLOB),
                         hidden files skipped unless --hidden/-./-uu or a glob or
                         type names them.
  findstr                with /s; only the files its masks name (or /D: dirs).

NOT CONFIDENT = PROTECTED. When the command cannot be read with confidence --
an option this module does not know, an ambiguous long-option prefix, a target
that does not exist or is not literal (a variable), no known directory to
search, a file list read from a file (--exclude-from, findstr /F:) -- the
answer is `unclear`, and the policy treats it exactly like touching a protected
location. An unknown `-t TYPE` makes every file count as named by the type.
A search with no path searches the current directory.

Not recognised (said in the contract): Select-String, `git grep`, ack/ag, a
search inside an interpreter. rg's .gitignore handling is not modelled: a
gitignored secret still counts (conservative). An explicitly named file is
always counted as read, whatever the limits.

BOUNDED WALK. Dependency trees (`node_modules`, `.venv`, `venv`,
`site-packages`, `.git`, `__pycache__`) are not walked -- their `*.pem` /
`*.key` files are package data, and walking them would make every search of a
repository an owner question -- and at most `MAX_ENTRIES` entries are looked
at; past that, what was found so far decides.
"""

from __future__ import annotations

import fnmatch
import glob as _glob
import os
import re
from dataclasses import dataclass, field

#: Directories not walked (package data, not the owner's secrets).
SKIP_DIRS = frozenset({"node_modules", ".venv", "venv", "site-packages", ".git",
                       "__pycache__", ".tox", ".mypy_cache"})
MAX_ENTRIES = 20000


@dataclass
class Found:
    """What one recognised recursive search would read."""
    secrets: list[str] = field(default_factory=list)
    #: Why the command cannot be read with confidence (None when it can).
    unclear: str | None = None


class _Unclear(Exception):
    pass


def _name(word: str) -> str:
    return os.path.basename(word.strip("'\"").replace("\\", "/")).lower()


def _secret(name: str) -> bool:
    from mentis.operations import _SECRET_NAMES
    return bool(_SECRET_NAMES.search(os.sep + name))


def _unq(word: str) -> str:
    return word.strip("'\"")


def _rel(rel: str) -> str:
    return rel.replace("\\", "/")


# ---------------------------------------------------------------------------
# option tables

_GREP_SHORT_VALUE = set("ABCDdefmX")
_GREP_SHORT_FLAG = set("EFGPiyvwxcLloqsbHhnTZzUuaIrRV0123456789")
_GREP_LONG_VALUE = {
    "regexp", "file", "max-count", "after-context", "before-context", "context",
    "directories", "devices", "binary-files", "include", "exclude", "exclude-from",
    "exclude-dir", "label", "group-separator"}
_GREP_LONG_OPTIONAL = {"color", "colour"}            # a value only with '='
_GREP_LONG_FLAG = {
    "extended-regexp", "fixed-strings", "basic-regexp", "perl-regexp", "ignore-case",
    "no-ignore-case", "invert-match", "word-regexp", "line-regexp", "count",
    "files-without-match", "files-with-matches", "only-matching", "quiet", "silent",
    "no-messages", "byte-offset", "with-filename", "no-filename", "line-number",
    "no-line-number", "initial-tab", "null", "null-data", "binary", "text", "recursive",
    "dereference-recursive", "line-buffered", "version", "help", "unix-byte-offsets",
    "no-group-separator", "fixed-regexp"}

_RG_SHORT_VALUE = set("ABCEMTdefgjmrt")
_RG_SHORT_FLAG = set("FHILNPSUVabchilnopqsuvwxz0.")
_RG_LONG_VALUE = {
    "after-context", "before-context", "context", "regexp", "file", "glob", "iglob",
    "max-count", "type", "type-not", "type-add", "type-clear", "encoding", "threads",
    "max-columns", "replace", "max-depth", "maxdepth", "max-filesize", "colors", "color",
    "context-separator", "field-context-separator", "field-match-separator",
    "path-separator", "sort", "sortr", "dfa-size-limit", "regex-size-limit", "engine",
    "ignore-file", "pre", "pre-glob", "hostname-bin", "hyperlink-format", "generate",
    "max-columns-preview-length"}
_RG_LONG_FLAG = {
    "hidden", "no-hidden", "no-ignore", "ignore", "no-ignore-dot", "no-ignore-exclude",
    "no-ignore-files", "no-ignore-global", "no-ignore-parent", "no-ignore-vcs",
    "no-ignore-messages", "ignore-messages", "no-require-git", "require-git",
    "ignore-file-case-insensitive", "no-ignore-file-case-insensitive", "follow",
    "no-follow", "count", "count-matches", "files", "files-with-matches",
    "files-without-match", "fixed-strings", "no-fixed-strings", "ignore-case",
    "smart-case", "case-sensitive", "invert-match", "no-invert-match", "word-regexp",
    "line-regexp", "line-number", "no-line-number", "only-matching", "pretty", "quiet",
    "search-zip", "no-search-zip", "text", "no-text", "json", "no-json", "messages",
    "no-messages", "null", "null-data", "trim", "no-trim", "vimgrep", "with-filename",
    "no-filename", "heading", "no-heading", "column", "no-column", "byte-offset",
    "no-byte-offset", "multiline", "no-multiline", "multiline-dotall",
    "no-multiline-dotall", "pcre2", "no-pcre2", "unrestricted", "stats", "no-stats",
    "debug", "trace", "binary", "no-binary", "block-buffered", "no-block-buffered",
    "line-buffered", "no-line-buffered", "crlf", "no-crlf", "passthru", "passthrough",
    "one-file-system", "no-one-file-system", "no-config", "sort-files",
    "no-sort-files", "max-columns-preview", "no-max-columns-preview", "unicode",
    "no-unicode", "pcre2-unicode", "no-pcre2-unicode", "auto-hybrid-regex",
    "no-auto-hybrid-regex", "include-zero", "no-include-zero", "mmap", "no-mmap",
    "type-list", "version", "help", "glob-case-insensitive",
    "no-glob-case-insensitive", "no-context-separator", "pcre2-version", "list-file-types",
    "no-encoding", "no-pre", "fixed-strings", "no-column", "quiet"}

#: ripgrep's built-in types for the common languages (`rg --type-list`).
_RG_TYPES = {
    "py": ["*.py", "*.pyi"], "python": ["*.py", "*.pyi"],
    "js": ["*.js", "*.jsx", "*.mjs", "*.cjs", "*.vue"],
    "ts": ["*.ts", "*.tsx", "*.mts", "*.cts"], "typescript": ["*.ts", "*.tsx", "*.mts", "*.cts"],
    "rust": ["*.rs"], "go": ["*.go"], "java": ["*.java", "*.jsp", "*.jspx", "*.properties"],
    "c": ["*.c", "*.h", "*.H", "*.cats"], "cpp": ["*.C", "*.cc", "*.cpp", "*.cxx", "*.h",
                                                   "*.hh", "*.hpp", "*.hxx", "*.inl"],
    "cs": ["*.cs"], "csharp": ["*.cs"], "css": ["*.css", "*.scss"],
    "html": ["*.htm", "*.html", "*.ejs"], "md": ["*.markdown", "*.md", "*.mdown",
                                                   "*.mdwn", "*.mkd", "*.mkdn", "*.mdx"],
    "markdown": ["*.markdown", "*.md", "*.mdown", "*.mdwn", "*.mkd", "*.mkdn", "*.mdx"],
    "json": ["*.json", "composer.lock", "*.sarif"], "yaml": ["*.yaml", "*.yml"],
    "toml": ["*.toml", "Cargo.lock"], "txt": ["*.txt"], "sql": ["*.sql", "*.psql"],
    "ps": ["*.cdxml", "*.ps1", "*.ps1xml", "*.psd1", "*.psm1"],
    "powershell": ["*.cdxml", "*.ps1", "*.ps1xml", "*.psd1", "*.psm1"],
    "rst": ["*.rst"], "xml": ["*.xml", "*.xml.dist", "*.xsd", "*.xsl", "*.xslt", "*.xsl"],
    "svelte": ["*.svelte"], "vue": ["*.vue"], "kotlin": ["*.kt", "*.kts"],
    "ruby": ["*.rb", "Gemfile", "*.gemspec", ".irbrc", "Rakefile"],
    "sh": ["*.bash", "*.bashrc", ".bashrc", ".bash_profile", ".bash_login", ".bash_logout",
           "*.sh", "*.zsh", ".zshrc", ".zprofile", ".profile"],
}

_FINDSTR_FLAGS = {"s", "i", "b", "e", "l", "r", "x", "v", "n", "m", "o", "p"}


def _long(a: str, known_value: set, known_flag: set, optional: set, *, prefixes: bool):
    """`--name[=value]` as (canonical name, inline value or None, takes value)."""
    name, eq, value = a[2:].partition("=")
    every = known_value | known_flag | optional
    if name not in every:
        if not prefixes:
            raise _Unclear(f"it uses an option Mentis does not know ({a})")
        hits = [n for n in every if n.startswith(name)] if name else []
        if len(hits) != 1:
            raise _Unclear(f"it uses an option Mentis does not know or cannot "
                           f"resolve ({a})")
        name = hits[0]
    takes = name in known_value
    if name in known_flag and eq:
        raise _Unclear(f"it gives a value to an option that takes none ({a})")
    return name, (value if eq else None), takes


def _options(args, *, short_value, short_flag, long_value, long_flag, long_optional=(),
             prefixes=False):
    """Split one command's arguments into ordered options [(name, value)] and
    operands. Raises _Unclear on anything not known."""
    opts, operands, i = [], [], 0
    long_optional = set(long_optional)
    while i < len(args):
        raw = args[i]
        a = _unq(raw)
        if a == "--":
            operands += [_unq(x) for x in args[i + 1:]]
            break
        if a.startswith("--"):
            name, value, takes = _long(a, long_value, long_flag, long_optional,
                                       prefixes=prefixes)
            if takes and value is None:
                if i + 1 >= len(args):
                    raise _Unclear(f"option {a} has no value")
                i += 1
                value = _unq(args[i])
            opts.append((name, value))
        elif a.startswith("-") and len(a) > 1:
            letters, j = a[1:], 0
            while j < len(letters):
                ch = letters[j]
                if ch in short_value:
                    rest = letters[j + 1:]
                    if rest:
                        value = rest
                    else:
                        if i + 1 >= len(args):
                            raise _Unclear(f"option -{ch} has no value")
                        i += 1
                        value = _unq(args[i])
                    opts.append((ch, value))
                    break
                if ch in short_flag:
                    opts.append((ch, None))
                    j += 1
                    continue
                raise _Unclear(f"it uses an option Mentis does not know (-{ch})")
        else:
            operands.append(a)
        i += 1
    return opts, operands


# ---------------------------------------------------------------------------
# what each search reads


@dataclass
class _Search:
    targets: list[str]
    #: file decision: (rel, base) -> searched?
    file_ok: object
    #: directory decision: (rel, base) -> walked?
    dir_ok: object
    #: files read besides the search itself (a pattern file)
    also: list[str] = field(default_factory=list)
    #: findstr: masks per target (a file-name glob), else None
    masks: list[str] | None = None


def _grep(args):
    opts, operands = _options(args, short_value=_GREP_SHORT_VALUE,
                              short_flag=_GREP_SHORT_FLAG, long_value=_GREP_LONG_VALUE,
                              long_flag=_GREP_LONG_FLAG, long_optional=_GREP_LONG_OPTIONAL,
                              prefixes=True)
    recursive, pattern_given, also = False, False, []
    rules, dir_excl = [], []       # rules: ("include"|"exclude", glob), in order
    for name, value in opts:
        if name in ("r", "R", "recursive", "dereference-recursive"):
            recursive = True
        elif name in ("d", "directories"):
            recursive = recursive or value == "recurse"
        elif name in ("e", "regexp"):
            pattern_given = True
        elif name in ("f", "file"):
            pattern_given = True
            also.append(value)
        elif name == "include":
            rules.append(("include", value))
        elif name == "exclude":
            rules.append(("exclude", value))
        elif name == "exclude-dir":
            dir_excl.append(value)
        elif name == "exclude-from":
            raise _Unclear("it reads the files to skip from another file (--exclude-from)")
    if not recursive:
        return None
    targets = operands if pattern_given else operands[1:]
    if not pattern_given and not operands:
        raise _Unclear("it gives no pattern Mentis can place")

    def file_ok(rel, base):
        # GNU grep: the last matching --include/--exclude wins; with none
        # matching, a file is searched unless the first one is --include.
        # An include matches loosely (more is searched), an exclude exactly.
        last = None
        for kind, g in rules:
            hit = (fnmatch.fnmatch(base.lower(), g.lower()) if kind == "include"
                   else fnmatch.fnmatchcase(base, g) or fnmatch.fnmatchcase(_rel(rel), g))
            if hit:
                last = kind
        if last is not None:
            return last == "include"
        return not (rules and rules[0][0] == "include")

    def dir_ok(rel, base):
        return not any(fnmatch.fnmatchcase(base, g) for g in dir_excl)

    return _Search(targets or ["."], file_ok, dir_ok, also)


def _rg_glob_hit(g: str, rel: str, base: str, *, insensitive: bool) -> bool:
    rel = _rel(rel)
    if not insensitive:
        m = fnmatch.fnmatchcase
    else:
        def m(s, p):
            return fnmatch.fnmatch(s.lower(), p.lower())
    g = g.replace("\\", "/")
    anchored = g.startswith("/")
    g = g.lstrip("/")
    if g.endswith("/"):
        g = g.rstrip("/")
    if "/" not in g:
        return m(base, g)
    g2 = g[3:] if g.startswith("**/") else g
    return m(rel, g) or (not anchored and m(rel, "*/" + g2)) or m(rel, g2)


def _rg(args):
    opts, operands = _options(args, short_value=_RG_SHORT_VALUE, short_flag=_RG_SHORT_FLAG,
                              long_value=_RG_LONG_VALUE, long_flag=_RG_LONG_FLAG)
    hidden, pattern_given, u, also = False, False, 0, []
    globs = []          # (positive, glob, insensitive), in order
    gci = False
    types = dict(_RG_TYPES)
    selected, negated, unknown_type = [], [], False
    for name, value in opts:
        if name in ("hidden", "."):
            hidden = True
        elif name == "no-hidden":
            hidden = False
        elif name in ("u", "unrestricted"):
            u += 1
        elif name in ("e", "regexp"):
            pattern_given = True
        elif name in ("f", "file"):
            pattern_given = True
            also.append(value)
        elif name in ("g", "glob", "iglob"):
            pos = not value.startswith("!")
            globs.append((pos, value[1:] if not pos else value, name == "iglob"))
        elif name == "glob-case-insensitive":
            gci = True
        elif name == "type-add":
            tname, _, spec = value.partition(":")
            if not spec or spec.startswith("include:"):
                unknown_type = True
            else:
                types.setdefault(tname, [])
                types[tname] = types[tname] + spec.split(",")
        elif name == "type-clear":
            types[value] = []
        elif name in ("t", "type"):
            if value == "all":
                continue
            selected.append(value)
        elif name in ("T", "type-not"):
            negated.append(value)
    if u >= 2:
        hidden = True
    if not pattern_given:
        if not operands and not any(n in ("files", "type-list") for n, _ in opts):
            raise _Unclear("it gives no pattern Mentis can place")
        targets = operands[1:] if not any(n == "files" for n, _ in opts) else operands
    else:
        targets = operands
    if any(t not in types for t in selected):
        unknown_type = True
    positives = any(p for p, _, _ in globs)

    def _glob_match(rel, base, is_dir):
        """None (no glob decides), True (whitelisted), False (ignored)."""
        last = None
        for pos, g, ins in globs:
            # a positive glob matches loosely, a negative one as given
            if _rg_glob_hit(g, rel, base, insensitive=(True if pos else (ins or gci))):
                last = pos
        if last is not None:
            return last
        if positives and not is_dir:
            return False
        return None

    def _type_match(base):
        if any(fnmatch.fnmatch(base.lower(), g.lower())
               for t in negated for g in types.get(t, [])):
            return False
        if unknown_type:
            return True
        if selected:
            return any(fnmatch.fnmatch(base.lower(), g.lower())
                       for t in selected for g in types.get(t, []))
        return None

    def file_ok(rel, base):
        m = _glob_match(rel, base, False)
        if m is None:
            m = _type_match(base)
        if m is None:
            return hidden or not base.startswith(".")
        return m

    def dir_ok(rel, base):
        m = _glob_match(rel, base, True)
        if m is None:
            return hidden or not base.startswith(".")
        return m

    return _Search(targets or ["."], file_ok, dir_ok, also)


def _findstr(args):
    recursive, strings_given, dirs = False, False, None
    rest = []
    for raw in args:
        a = _unq(raw)
        if re.match(r"^/[A-Za-z]+(:.*)?$", a, re.S):
            body = a[1:]
            key, colon, value = body.partition(":")
            k = key.lower()
            if colon:
                if k == "c":
                    strings_given = True
                elif k == "g":
                    strings_given = True
                elif k == "f":
                    raise _Unclear("it reads the files to search from another file (/F:)")
                elif k == "d":
                    dirs = [d for d in value.split(";") if d]
                elif k == "a":
                    pass
                else:
                    raise _Unclear(f"it uses an option Mentis does not know ({a})")
            elif k in ("off", "offline"):
                pass
            elif k and set(k) <= _FINDSTR_FLAGS:
                recursive = recursive or "s" in k
            else:
                raise _Unclear(f"it uses an option Mentis does not know ({a})")
        else:
            rest.append(a)
    if not recursive:
        return None
    files = rest if strings_given else rest[1:]
    if not strings_given and not rest:
        raise _Unclear("it gives no search string Mentis can place")
    files = files or ["*"]
    targets, masks = [], []
    for f in files:
        d, m = os.path.dirname(f.replace("/", os.sep)), os.path.basename(f.replace("/", os.sep)) or "*"
        for root in (dirs or ["."]):
            targets.append(os.path.join(root, d) if d and not os.path.isabs(d) else (d or root))
            masks.append(m)

    def file_ok(rel, base):
        return True

    def dir_ok(rel, base):
        return True

    return _Search(targets, file_ok, dir_ok, [], masks)


SEARCHERS = {"grep": _grep, "egrep": _grep, "fgrep": _grep, "rg": _rg,
             "rg.exe": _rg, "grep.exe": _grep, "findstr": _findstr, "findstr.exe": _findstr}


# ---------------------------------------------------------------------------
# the walk


def _walk(root: str, s: _Search, mask: str | None) -> list[str]:
    found, seen = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in dirnames:
            rel = os.path.relpath(os.path.join(dirpath, d), root)
            if d.lower() not in SKIP_DIRS and s.dir_ok(rel, d):
                keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            seen += 1
            if seen > MAX_ENTRIES:
                return found
            if not _secret(f):
                continue
            if mask is not None and not fnmatch.fnmatch(f.lower(), mask.lower()):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            if s.file_ok(rel, f):
                found.append(os.path.join(dirpath, f))
    return found


def _expand(path: str) -> list[str] | None:
    """A target as the paths it names: a glob as what the shell expands it to
    (not dotfiles for '*'), else itself. None when nothing is there."""
    if any(c in path for c in "*?["):
        got = _glob.glob(path)
        return got or None
    return [path] if os.path.exists(path) else None


def search(words: list[str], cwd: str | None) -> Found | None:
    """For one simple command: None when it is not a recognised recursive
    search; else the secret files it would read and, when it cannot be read
    with confidence, why (`unclear`)."""
    if not words:
        return None
    reader = SEARCHERS.get(_name(words[0]))
    if reader is None:
        return None
    try:
        s = reader(words[1:])
    except _Unclear as e:
        # Only a search can be unclear: an unknown option on a command that
        # might be recursive (grep/rg/findstr) is not read as harmless.
        return Found(unclear=str(e))
    if s is None:
        return None
    from mentis.operations import _msys, resolve
    found = Found()
    for p in s.also:
        if p and _secret(_name(p)):
            found.secrets.append(resolve(p, cwd) or p)
    masks = s.masks or [None] * len(s.targets)
    for t, mask in zip(s.targets, masks):
        if not t or "$" in t or "`" in t or (t.startswith("%") and t.endswith("%")):
            return Found(found.secrets, f"it searches {t or 'a path'} which is not literal")
        if not os.path.isabs(_msys(os.path.expanduser(t))) and not cwd:
            return Found(found.secrets, "it searches its shell's current directory, "
                                        "which is not reported")
        base = os.path.expanduser(_msys(t))
        full = os.path.normpath(base if os.path.isabs(base) else os.path.join(cwd, base))
        paths = _expand(full)
        if paths is None:
            return Found(found.secrets, f"it searches {t}, which does not exist")
        for path in paths:
            if os.path.isfile(path):
                # a file named on the command line is read whatever the limits
                if _secret(os.path.basename(path)) and (
                        mask is None or fnmatch.fnmatch(os.path.basename(path).lower(),
                                                        mask.lower())):
                    found.secrets.append(path)
            else:
                found.secrets += _walk(path, s, mask)
    return found


def secrets_searched(words: list[str], cwd: str | None) -> list[str] | None:
    """Compatibility: the secret files a recursive search would read ([] when
    none), or None when the command is not a recognised recursive search.
    Callers deciding policy use `search`, which also reports `unclear`."""
    got = search(words, cwd)
    return None if got is None else got.secrets
