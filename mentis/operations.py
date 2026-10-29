"""What an agent's permission request would DO, in words, and whether it is
inside the task it was authorised for (docs/run-consent.md, section 3).

A backend asks permission with a tool call: a kind (`read`, `edit`,
`execute`, ...), a title -- for a shell tool, the command itself -- its raw
input and the paths it names. Mentis used to put that title in front of the
owner as the question. This reads it instead, as ONE OPERATION: what it does
(`category`), what it touches (`resources`), which tool it is for "allow
this tool for this run" (`tool`), and whether it stays inside the task's
boundary (`within`, with `outside` saying why not, in words).

CLASSIFIED OR NOT ROUTINE. A shell command is split into its simple commands
(`;`, `&&`, `||`, `|`, newlines, braces, loop keywords) and every one of them
must be recognised: a known read-only program, a write whose target can be
resolved, a test or build tool, local Git. Anything not recognised --
an unknown program, inline code (`python -c`, `node -e`, `bash -c`),
command substitution, a write to a path held in a variable -- is `other` and
never routine: it is asked, unless the owner allowed that tool for the run.

THIS GRANTS NOTHING. It describes; `mentis.web.permissions` decides, under
the run's grant and the consent the owner gave. A description that is wrong
in the safe direction (asks when it need not) costs a question; this is
written to be wrong only that way.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

#: Categories routine work is made of, permitted by default under consent.
DEFAULT_CATEGORIES = ("read", "edit", "test", "build", "run", "git")
#: Categories the owner may add; outside the task otherwise.
OPTIONAL_CATEGORIES = ("delete", "git-remote", "network", "install")
CATEGORIES = DEFAULT_CATEGORIES + OPTIONAL_CATEGORIES

#: Inside a workspace, files that become commands or grant permissions are
#: the owner's all the same: Git's hooks and config, agent and editor
#: settings. Writing one would run code, or widen an agent's authority, later.
GUARDED = {".git", ".claude", ".codex", ".gemini", ".kimi", ".agents",
           ".vscode", ".idea", ".mcp.json", ".gitmodules", ".gitattributes",
           ".husky", ".github"}

#: Programs that only read (or only print), whatever their arguments, apart
#: from the exceptions `_simple` checks (sed -i, find -delete, ...).
READERS = {
    "ls", "dir", "cat", "head", "tail", "less", "more", "wc", "grep", "egrep",
    "fgrep", "rg", "ag", "find", "fd", "tree", "stat", "file", "du", "df",
    "sort", "uniq", "cut", "tr", "column", "diff", "cmp", "comm", "jq", "yq",
    "sed", "awk", "basename", "dirname", "realpath", "readlink", "pwd", "echo",
    "printf", "true", "false", "test", "[", "which", "where", "type",
    "command", "date", "env", "printenv", "whoami", "hostname", "uname",
    "sleep", "nl", "od", "hexdump", "xxd", "md5sum", "sha1sum", "sha256sum",
    "cd", "pushd", "popd", "seq", "tac", "rev", "fold", "fmt", "paste",
    "join", "expand", "tee",  # tee: its file arguments are writes (_simple)
    # PowerShell, by its own names and aliases
    "get-content", "gc", "get-childitem", "gci", "get-item", "gi",
    "get-itemproperty", "select-string", "sls", "test-path", "resolve-path",
    "get-location", "gl", "set-location", "sl", "push-location",
    "pop-location", "measure-object", "measure", "select-object", "select",
    "sort-object", "sort", "where-object", "where", "?", "foreach-object",
    "foreach", "%", "format-table", "ft", "format-list", "fl", "out-string",
    "out-null", "write-output", "write", "write-host", "get-date",
    "start-sleep", "get-command", "gcm", "get-filehash", "compare-object",
    "group-object", "convertfrom-json", "convertto-json", "get-process",
    "gps", "get-member", "gm", "get-help", "join-path", "split-path",
    "get-psdrive", "get-variable", "get-acl", "get-itempropertyvalue",
}
#: Programs whose file arguments are written.
WRITERS = {
    "mkdir", "md", "touch", "cp", "copy", "mv", "move", "rm", "del", "erase",
    "rmdir", "rd", "ln", "chmod", "unlink", "truncate", "patch",
    "set-content", "sc", "add-content", "ac", "out-file", "new-item", "ni",
    "remove-item", "ri", "copy-item", "cpi", "move-item", "mi",
    "rename-item", "rni", "clear-content", "clc", "expand-archive",
    "compress-archive",
}
#: Test, lint and type-check tools; run inside the workspace.
TESTERS = {"pytest", "py.test", "tox", "nox", "ruff", "mypy", "pyright",
           "flake8", "pylint", "black", "isort", "vitest", "jest", "mocha",
           "eslint", "prettier", "tsc", "ctest"}
BUILDERS = {"make", "cmake", "ninja", "msbuild", "vite", "esbuild", "webpack",
            "rollup", "gradle", "mvn"}
NETWORK = {"curl", "wget", "invoke-webrequest", "iwr", "invoke-restmethod",
           "irm", "gh", "ssh", "scp", "sftp", "ftp", "telnet", "nc", "ncat",
           "start-bitstransfer", "rsync"}
#: Programs that run whatever they are given: inline code, another shell.
RUNNERS_OF_ANYTHING = {"bash", "sh", "zsh", "pwsh", "powershell",
                       "powershell.exe", "pwsh.exe", "cmd", "cmd.exe", "eval",
                       "exec", "invoke-expression", "iex", "start-process",
                       "saps", "start", "xargs", "sudo", "runas", "nohup",
                       "invoke-command", "icm", "source", "."}
PYTHONS = {"python", "python3", "py", "python.exe", "python3.exe"}
NODES = {"node", "node.exe", "deno", "bun"}
PACKAGERS = {"npm", "npx", "pnpm", "yarn"}

_GIT_READ = {"status", "log", "diff", "show", "rev-parse", "merge-base",
             "ls-files", "ls-tree", "blame", "describe", "shortlog",
             "cat-file", "grep", "reflog", "rev-list", "for-each-ref",
             "name-rev", "whatchanged", "count-objects", "check-ignore",
             "show-ref", "help", "version", "--version"}
_GIT_LOCAL = {"add", "commit", "checkout", "switch", "restore", "merge",
              "rebase", "stash", "cherry-pick", "revert", "mv", "rm", "apply",
              "am", "init", "notes", "bisect", "format-patch", "worktree",
              "branch", "tag", "reset", "clean", "gc", "prune", "maintenance",
              "update-index", "commit-tree", "read-tree", "write-tree",
              "symbolic-ref", "update-ref", "mergetool", "range-diff"}
_GIT_REMOTE = {"fetch", "pull", "push", "clone", "ls-remote", "submodule",
               "remote", "lfs", "archive", "send-email", "request-pull"}

_NEUTRAL_REDIRECT = {"/dev/null", "nul", "$null", "&1", "&2"}
_SEPARATORS = {";", "&&", "||", "|", "&", "\n", "{", "}", "(", ")"}
_KEYWORDS = {"for", "in", "do", "done", "if", "then", "else", "elif", "fi",
             "while", "until", "case", "esac", "function", "foreach",
             "try", "catch", "finally", "!", "time"}


@dataclass
class Operation:
    summary: str
    action: str
    category: str
    kind: str | None = None
    resources: list[str] = field(default_factory=list)
    workspace: str | None = None
    tool: str = ""
    tool_label: str = ""
    within: bool = False
    outside: list[str] = field(default_factory=list)
    command: str | None = None
    cwd: str | None = None
    agent_says: str | None = None
    why: str | None = None
    #: every simple command's own category, for the log and the tests
    parts: list[str] = field(default_factory=list)
    #: True when every path it writes or runs in was resolved and is inside
    #: the workspaces; computed against `workspaces` given to `describe`
    in_workspaces: bool = False
    #: the directory to offer adding to the task's workspaces, when the
    #: operation is outside only because of where it works
    offer_workspace: str | None = None
    #: tools (programs) it uses, for "allow this tool for this run"
    tools: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("parts", None)
        if d.get("command") and len(d["command"]) > 4000:
            d["command"] = d["command"][:4000] + " …"
        return d


# ---------------------------------------------------------------------------
# paths


def protected_roots() -> list[str]:
    """Locations no consent reaches, read or write: Brains, MARS's data and
    credential stores. Anything under one is outside every task."""
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    roots = [os.path.join(local, "Mentis"), os.path.join(local, "mars"),
             os.environ.get("MARS_DATA_DIR") or "",
             *(os.path.join(home, d) for d in (
                 ".ssh", ".codex", ".claude", ".gemini", ".kimi", ".aws",
                 ".azure", ".gnupg", ".docker", ".kube", ".config\\gh",
                 ".config/gh", ".git-credentials", ".npmrc", ".pypirc",
                 ".netrc", "_netrc", ".mentis-ambient-backup"))]
    extra = os.environ.get("MENTIS_PROTECTED_PATHS") or ""
    roots += [p for p in extra.split(os.pathsep) if p]
    return [norm(r) for r in roots if r]


_SECRET_NAMES = re.compile(
    r"(^|[\\/])(\.env(\.[^\\/]*)?|auth\.json|credentials(\.[^\\/]*)?|"
    r"id_(rsa|ed25519|ecdsa|dsa)(\.pub)?|[^\\/]*\.pem|[^\\/]*\.pfx|"
    r"[^\\/]*\.key)$", re.I)


def norm(path: str) -> str:
    try:
        return os.path.normcase(os.path.realpath(path))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(path))


def inside(path: str, root: str) -> bool:
    try:
        p, r = norm(path), norm(root)
        return os.path.commonpath([p, r]) == r
    except (ValueError, OSError):
        return False


def is_protected(path: str, roots: list[str] | None = None) -> bool:
    if _SECRET_NAMES.search(path.replace("/", os.sep)):
        return True
    return any(inside(path, r) for r in (roots if roots is not None
                                         else protected_roots()))


def is_guarded(path: str, root: str) -> bool:
    try:
        rel = os.path.relpath(norm(path), norm(root))
    except ValueError:
        return False
    parts = [x.casefold() for x in rel.replace("\\", "/").split("/")]
    return any(p in {g.casefold() for g in GUARDED} for p in parts)


def _msys(path: str) -> str:
    """`/c/Work/x` (Git Bash) as `C:\\Work\\x`; others unchanged."""
    m = re.match(r"^/([a-zA-Z])(/.*)?$", path)
    if m and os.name == "nt":
        return f"{m.group(1).upper()}:{(m.group(2) or '/').replace('/', os.sep)}"
    return path


def resolve(token: str, cwd: str | None) -> str | None:
    """A path token as an absolute path, or None when it cannot be known
    (a variable, a glob root that is not a directory, no cwd)."""
    t = token.strip().strip("'\"")
    if not t or "$" in t or "`" in t or "%" in t and re.search(r"%\w+%", t):
        return None
    if t.lower() in _NEUTRAL_REDIRECT:
        return None
    if t.startswith("~"):
        t = os.path.expanduser(t)
    t = _msys(t)
    # A glob names files under its fixed part; that part is what is touched.
    if any(c in t for c in "*?["):
        t = re.split(r"[*?\[]", t, 1)[0] or "."
    if not os.path.isabs(t):
        if not cwd:
            return None
        t = os.path.join(cwd, t)
    return os.path.normpath(t)


def _looks_like_path(token: str) -> bool:
    t = token.strip("'\"")
    if not t or t.startswith("-") and not t.startswith("-/"):
        return False
    if re.match(r"^[a-z][a-z0-9+.-]*://", t, re.I):
        return False
    return ("/" in t or "\\" in t or t.startswith(".") or t.startswith("~")
            or bool(re.match(r"^[a-zA-Z]:", t)))


def repository_root(path: str) -> str | None:
    """The Git work tree holding `path`, or its directory: what to offer
    adding to a task's workspaces."""
    p = path if os.path.isdir(path) else os.path.dirname(path)
    cur = p
    for _ in range(40):
        if os.path.exists(os.path.join(cur, ".git")):
            return os.path.normpath(cur)
        up = os.path.dirname(cur)
        if up == cur:
            break
        cur = up
    return os.path.normpath(p) if p and os.path.isdir(p) else None


# ---------------------------------------------------------------------------
# shell


def tokens(command: str, powershell: bool = False) -> list[str] | None:
    """Words and operators, quotes kept on words. None for what cannot be
    read safely: command substitution, process substitution, a here-doc.
    In PowerShell a backtick escapes the next character; in Bash it is
    command substitution."""
    out, i, n = [], 0, len(command)
    word = ""

    def push():
        nonlocal word
        if word:
            out.append(word)
            word = ""

    while i < n:
        c = command[i]
        if c in "'\"":
            j = i + 1
            while j < n and command[j] != c:
                if c == '"' and command[j] == "\\" and j + 1 < n:
                    j += 1
                j += 1
            if j >= n:
                return None                       # unbalanced quote
            inner = command[i + 1:j]
            if c == '"' and ("$(" in inner or "`" in inner and not powershell):
                return None
            word += command[i:j + 1]
            i = j + 1
            continue
        if command.startswith("$(", i):
            return None
        if c == "`":
            if not powershell:
                return None
            word += command[i:i + 2]
            i += 2
            continue
        if command.startswith("<(", i) or command.startswith(">(", i) \
                or command.startswith("<<", i):
            return None
        if c == "\\" and not powershell and i + 1 < n and command[i + 1] != "\n":
            word += command[i:i + 2]           # `\(` is a word, not a group
            i += 2
            continue
        if c in " \t\r":
            push()
            i += 1
            continue
        if c == "#" and not word:
            # a comment runs to the end of the line
            j = command.find("\n", i)
            i = n if j < 0 else j
            continue
        two = command[i:i + 2]
        if two in ("&&", "||", "2>", ">>"):
            if two == "2>":
                push()
                j = i + 2
                if command.startswith("&1", j):
                    out.append("2>&1")
                    i = j + 2
                    continue
                out.append("2>")
                i = j
                continue
            push()
            out.append(two)
            i += 2
            continue
        if c in ";|&\n{}()<>":
            push()
            out.append(c)
            i += 1
            continue
        word += c
        i += 1
    push()
    return out


def statements(toks: list[str]) -> list[list[str]]:
    """The simple commands in a token list, with redirections kept on the
    command they belong to and loop keywords stripped."""
    out, cur = [], []
    for t in toks:
        if t in _SEPARATORS:
            if cur:
                out.append(cur)
            cur = []
            continue
        if not cur and t.lower() in _KEYWORDS:
            continue
        cur.append(t)
    if cur:
        out.append(cur)
    # `for x in a b c` leaves `x in a b c`; `in` lists are values, not commands
    cleaned = []
    for s in out:
        if len(s) >= 2 and s[1] == "in" and re.match(r"^\$?\w+$", s[0]):
            continue
        cleaned.append(s)
    return cleaned


def _unwrap(raw) -> str | None:
    """The command a request runs, as one string: Codex sends argv, often
    `["powershell.exe", "-Command", "<script>"]` or `["bash", "-lc", "<script>"]`."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (list, tuple)) and raw and all(isinstance(x, str) for x in raw):
        prog = os.path.basename(raw[0]).lower()
        if prog in {"bash", "sh", "zsh", "bash.exe", "sh.exe"} and len(raw) >= 3 \
                and raw[1] in ("-c", "-lc", "-ic"):
            return raw[2]
        if prog in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
            rest = [x for x in raw[1:] if x.lower() not in (
                "-noprofile", "-nologo", "-noninteractive", "-nop")]
            if len(rest) >= 2 and rest[0].lower() in ("-command", "-c"):
                return " ".join(rest[1:])
        if prog in {"cmd", "cmd.exe"} and len(raw) >= 3 and raw[1].lower() == "/c":
            return None
        return " ".join(_quote(x) for x in raw)
    return None


def _quote(x: str) -> str:
    return x if re.match(r"^[\w@%+=:,./\\-]+$", x) else '"' + x.replace('"', '\\"') + '"'


@dataclass
class _Part:
    category: str
    program: str
    writes: list[str] = field(default_factory=list)      # resolved
    unknown_writes: int = 0                               # unresolvable targets
    reads: list[str] = field(default_factory=list)       # resolved
    runs_in: str | None = None                           # cwd it runs code in
    why: str | None = None                               # why `other`
    #: it reads where the shell is, and where that is is not reported
    reads_unplaced: bool = False


def _test_location(args: list[str], cwd: str | None) -> str | None:
    """Where a test command runs. An explicit absolute test target is enough
    when no shell cwd was reported; option parsing remains deliberately
    conservative."""
    if cwd:
        return cwd
    targets = [a for a in args if not a.startswith("-")]
    resolved = [resolve(a, None) for a in targets]
    return resolved[0] if resolved and all(resolved) else None


def _simple(words: list[str], cwd: str | None) -> tuple[_Part, str | None]:
    """One simple command: what it is, and the cwd after it (for `cd`).
    A reader whose output is redirected into a file is a write."""
    p, after = _simple_unredirected(words, cwd)
    if p.category == "read" and (p.writes or p.unknown_writes):
        p.category = "edit"
    # WHAT MENTIS CANNOT CLASSIFY RUNS WHERE IT IS RUN, and is checked there.
    if p.category in ("other", "run", "test", "build") and p.runs_in is None:
        p.runs_in = cwd
    return p, after


def _simple_unredirected(words: list[str], cwd: str | None) -> tuple[_Part, str | None]:
    # redirections first: `> f`, `>> f`, `2> f`, `2>&1`, `< f`
    args, writes, unknown, reads = [], [], 0, []
    i = 0
    while i < len(words):
        w = words[i]
        if w in (">", ">>", "2>"):
            target = words[i + 1] if i + 1 < len(words) else ""
            i += 2
            if target.lower() in _NEUTRAL_REDIRECT or target.startswith("&"):
                continue
            r = resolve(target, cwd)
            if r is None:
                unknown += 1
            else:
                writes.append(r)
            continue
        if w == "2>&1":
            i += 1
            continue
        if w == "<":
            r = resolve(words[i + 1], cwd) if i + 1 < len(words) else None
            if r:
                reads.append(r)
            i += 2
            continue
        args.append(w)
        i += 1
    # environment assignments in front (`FOO=1 cmd`)
    while args and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", args[0]):
        args.pop(0)
    if not args:
        return _Part("read", "", writes, unknown, reads), cwd
    prog_raw = args[0].strip("'\"")
    if prog_raw.startswith("&") and len(prog_raw) > 1:
        prog_raw = prog_raw[1:]
    if prog_raw == "&" and len(args) > 1:                # PowerShell call operator
        args = args[1:]
        prog_raw = args[0].strip("'\"")
    prog = os.path.basename(prog_raw.replace("\\", "/")).lower()
    if prog.endswith(".exe"):
        prog = prog[:-4]
    rest = args[1:]
    paths = [a for a in rest if _looks_like_path(a)]

    def part(cat, **kw):
        kw.setdefault("reads", list(reads))
        return _Part(cat, prog, list(writes), unknown, **kw)

    # A POWERSHELL EXPRESSION, not a command: `$?`, `$LASTEXITCODE -eq 0`
    # (what `if (...)` leaves), or `$out = <command>`, which is that command.
    if prog_raw.startswith("$") and re.match(r"^\$[\w?:]+$", prog_raw):
        if rest[:1] == ["="] and len(rest) > 1:
            return _simple(rest[1:], cwd)
        if all(re.match(r"^(\$[\w?:]+|-[a-z]+|\d+|'[^']*'|\"[^\"$`]*\"|\$true|\$false|\$null)$",
                        a, re.I) for a in rest):
            return part("read"), cwd
    if "$" in prog_raw or prog_raw.startswith("("):
        return part("other", why="the program is held in a variable", runs_in=cwd), cwd

    # cd / Set-Location move the cwd for what follows
    if prog in {"cd", "pushd", "set-location", "sl", "push-location", "chdir"}:
        target = next((a for a in rest if not a.startswith("-")), None)
        new = resolve(target, cwd) if target else cwd
        return part("read"), (new if target else cwd)

    if prog in RUNNERS_OF_ANYTHING:
        return part("other", why=f"`{prog}` runs whatever it is given"), cwd

    if prog == "git":
        return _git(rest, cwd, part), cwd

    if prog in PYTHONS:
        flags = [a for a in rest if a.startswith("-")]
        if "-c" in flags or "-" in rest:
            return part("other", why="inline Python code"), cwd
        if "-m" in rest:
            mod = rest[rest.index("-m") + 1] if rest.index("-m") + 1 < len(rest) else ""
            mod = mod.split(".")[0].lower()
            if mod in {"pytest", "unittest", "doctest", "ruff", "mypy", "pyflakes",
                       "pylint", "black", "isort", "compileall", "py_compile",
                       "tox", "nox", "coverage"}:
                after_mod = rest[rest.index("-m") + 2:]
                return part("test", runs_in=_test_location(after_mod, cwd)), cwd
            if mod in {"pip", "pipx", "uv", "poetry", "ensurepip"}:
                return part("install"), cwd
            if mod in {"json.tool", "json", "tabnanny", "this", "site",
                       "platform", "sysconfig"}:
                return part("read"), cwd
            if mod in {"http", "venv", "virtualenv", "build", "twine", "webbrowser"}:
                return part("other", why=f"`python -m {mod}`"), cwd
            return part("run", runs_in=cwd), cwd
        script = next((a for a in rest if not a.startswith("-")), None)
        if script is None:
            return part("other", why="an interactive interpreter"), cwd
        if script in ("--version", "-V"):
            return part("read"), cwd
        r = resolve(script, cwd)
        if r is None:
            return part("other", why="the script's path is not known"), cwd
        return part("run", runs_in=cwd, reads=[*reads, r]), cwd

    if prog in NODES:
        if any(a in ("-e", "-p", "--eval", "--print") for a in rest):
            return part("other", why="inline JavaScript"), cwd
        if "--test" in rest:
            return part("test", runs_in=cwd), cwd
        if rest and rest[0] in ("--version", "-v"):
            return part("read"), cwd
        script = next((a for a in rest if not a.startswith("-")), None)
        if script is None:
            return part("other", why="an interactive interpreter"), cwd
        return part("run", runs_in=cwd), cwd

    if prog in PACKAGERS:
        sub = next((a for a in rest if not a.startswith("-")), "")
        if prog == "npx":
            tool = sub.split("@")[0].lower()
            if tool in TESTERS:
                return part("test", runs_in=cwd), cwd
            if tool in BUILDERS:
                return part("build", runs_in=cwd), cwd
            return part("other", why=f"`npx {sub}` may download and run a package"), cwd
        if sub in ("test", "t", "tst"):
            return part("test", runs_in=cwd), cwd
        if sub in ("run", "run-script"):
            script = next((a for a in rest[rest.index(sub) + 1:]
                           if not a.startswith("-")), "")
            cat = "build" if script.startswith("build") else "test"
            return part(cat, runs_in=cwd), cwd
        if sub in ("ls", "list", "outdated", "view", "why", "explain",
                   "--version", "-v", "config"):
            return part("read") if sub != "config" else part("other", why="npm config"), cwd
        if sub in ("install", "i", "ci", "add", "update", "upgrade", "remove",
                   "uninstall", "rm", "dedupe", "audit", "link"):
            return part("install"), cwd
        if sub in ("exec", "x", "dlx", "publish", "login", "adduser"):
            return part("other", why=f"`{prog} {sub}`"), cwd
        return part("build", runs_in=cwd), cwd

    if prog in {"pip", "pip3", "uv", "poetry", "pipx", "conda", "choco",
                "winget", "scoop", "apt", "apt-get", "brew", "cargo-install"}:
        if prog in {"uv", "poetry"} and rest[:1] == ["run"]:
            return _simple(rest[1:], cwd)
        if rest[:1] in (["list"], ["show"], ["freeze"], ["--version"]):
            return part("read"), cwd
        return part("install"), cwd

    if prog in {"cargo", "go", "dotnet"}:
        sub = rest[0] if rest else ""
        if sub in ("test", "check", "vet", "clippy", "fmt"):
            return part("test", runs_in=cwd), cwd
        if sub in ("build", "run"):
            return part("build", runs_in=cwd), cwd
        if sub in ("install", "get", "add", "restore"):
            return part("install"), cwd
        return part("other", why=f"`{prog} {sub}`"), cwd

    if prog in TESTERS:
        return part("test", runs_in=_test_location(rest, cwd)), cwd
    if prog in BUILDERS:
        return part("build", runs_in=cwd), cwd
    if prog in NETWORK:
        return part("network"), cwd

    if prog in WRITERS:
        targets = [a for a in rest if not a.startswith("-") or _looks_like_path(a)]
        # PowerShell named parameters: the value after -Path/-Destination/...
        if prog not in {"mkdir", "touch", "cp", "mv", "rm", "rmdir", "ln", "chmod",
                        "unlink", "truncate", "patch"}:
            targets = []
            j = 0
            while j < len(rest):
                a = rest[j]
                if a.startswith("-"):
                    name = a.lower().lstrip("-")
                    if name in ("path", "literalpath", "filepath", "destination",
                                "newname", "target", "destinationpath", "lp", "pspath"):
                        if j + 1 < len(rest):
                            targets.append(rest[j + 1])
                        j += 2
                        continue
                    j += 2 if name in ("value", "encoding", "itemtype", "type",
                                       "name", "include", "exclude", "filter") else 1
                    continue
                if not targets:
                    targets.append(a)         # the first positional is the path
                j += 1
            if prog in {"new-item", "ni"}:
                name_i = next((k for k, a in enumerate(rest)
                               if a.lower() == "-name"), None)
                if name_i is not None and name_i + 1 < len(rest) and targets:
                    targets = [os.path.join(targets[0].strip("'\""),
                                            rest[name_i + 1].strip("'\""))]
        if prog in {"rename-item", "rni"} and len(targets) > 1:
            targets = targets[:1]
        recursive = any(a.lower() in ("-r", "-rf", "-fr", "-recurse", "/s", "-force",
                                      "--recursive") or re.match(r"^-[a-z]*r", a.lower())
                        for a in rest if a.startswith("-") or a.startswith("/s"))
        res, unk = list(writes), unknown
        for t in targets:
            r = resolve(t, cwd)
            if r is None:
                unk += 1
            else:
                res.append(r)
        if not targets:
            unk += 1
        deleting = prog in {"rm", "del", "erase", "rmdir", "rd", "remove-item", "ri"}
        cat = "delete" if deleting and recursive else "edit"
        return _Part(cat, prog, res, unk, list(reads)), cwd

    if prog in READERS:
        lower = [a.lower() for a in rest]
        if prog == "sed" and any(a == "-i" or a.startswith("-i") or a == "--in-place"
                                 for a in lower):
            files = [a for a in rest if not a.startswith("-")][1:]
            res, unk = list(writes), unknown
            for f in files:
                r = resolve(f, cwd)
                if r is None:
                    unk += 1
                else:
                    res.append(r)
            return _Part("edit", prog, res, unk or (0 if files else 1), list(reads)), cwd
        if prog in ("find",) and any(a in ("-delete", "-exec", "-execdir", "-ok",
                                           "-okdir", "-fprint", "-fls")
                                     for a in lower):
            return part("other", why="`find` with an action"), cwd
        if prog == "awk" and any("system(" in a or re.search(r">\s*\"", a)
                                 or "getline" in a for a in rest):
            return part("other", why="an awk program that runs or writes"), cwd
        if prog in ("foreach-object", "foreach", "%", "where-object", "where", "?") \
                and any("{" in a for a in rest):
            pass                    # the block's commands are their own statements
        if prog in ("env", "command", "time") and rest and not rest[0].startswith("-"):
            return _simple(rest, cwd)
        if prog == "tee":
            res, unk = list(writes), unknown
            for f in (a for a in rest if not a.startswith("-")):
                r = resolve(f, cwd)
                if r is None:
                    unk += 1
                else:
                    res.append(r)
            return _Part("edit", prog, res, unk, list(reads)), cwd
        if prog in ("out-file",):
            pass
        # A SEARCH'S FIRST POSITIONAL IS ITS PATTERN, not a file to read.
        if prog in {"grep", "egrep", "fgrep", "rg", "ag", "sed", "awk",
                    "select-string", "sls"} and not any(
                        a in ("-e", "-f", "--regexp", "-pattern") for a in lower):
            pos = [a for a in rest if not a.startswith("-")]
            paths = [a for a in paths if not pos or a != pos[0]]
        rp = [r for r in (resolve(a, cwd) for a in paths) if r]
        p = part("read")
        p.reads += rp
        # A READ OF THE SHELL'S OWN DIRECTORY, or of a relative path, with
        # that directory not reported: what it reads cannot be checked.
        p.reads_unplaced = cwd is None and (not paths or len(rp) < len(paths))
        return p, cwd

    return part("other", why=f"`{prog}` is not a program Mentis recognises"), cwd


def _git(rest, cwd, part) -> _Part:
    # `git -C <dir>` and other global options before the subcommand
    where = cwd
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        if rest[i] == "-C" and i + 1 < len(rest):
            where = resolve(rest[i + 1], cwd)
            i += 2
            continue
        if rest[i] in ("-c",) and i + 1 < len(rest):
            # WHO A COMMIT IS BY is routine; any other setting can run code
            # (`core.pager`, `core.sshCommand`, hooks paths) and is not.
            key = rest[i + 1].strip("'\"").split("=", 1)[0].lower()
            if key not in ("user.name", "user.email", "commit.gpgsign",
                           "core.autocrlf", "color.ui", "advice.detachedhead"):
                return part("other", why="`git -c` sets configuration for the command")
            i += 2
            continue
        i += 1
    sub = rest[i] if i < len(rest) else ""
    args = rest[i + 1:]
    p = part("read")
    p.program = "git"
    p.runs_in = where
    if sub in _GIT_REMOTE:
        if sub == "remote" and (not args or args[0] in ("-v", "show", "get-url")):
            p.category = "read"
        elif sub == "submodule" and args[:1] == ["status"]:
            p.category = "read"
        else:
            p.category = "git-remote"
        return p
    if sub == "config":
        p.category = ("read" if any(a in ("--get", "--list", "-l", "--get-all",
                                          "--show-origin") for a in args)
                      else "other")
        p.why = None if p.category == "read" else "`git config` changes settings"
        return p
    if sub in ("branch", "tag", "stash", "worktree") and (
            not args or args[0] in ("--list", "-l", "-a", "-r", "-v", "-vv", "list",
                                    "show", "--show-current", "--contains",
                                    "--merged", "--no-merged")):
        return p
    if sub in _GIT_READ:
        return p
    if sub in _GIT_LOCAL:
        destructive = (sub == "reset" and "--hard" in args) or sub == "clean" \
            or (sub == "branch" and any(a in ("-D", "--delete --force") for a in args)) \
            or (sub == "checkout" and ("--" in args or "." in args)) \
            or (sub == "restore") or (sub == "stash" and args[:1] in (["drop"], ["clear"])) \
            or (sub == "worktree" and args[:1] == ["remove"] and "--force" in args)
        p.category = "delete" if destructive else "git"
        p.runs_in = where
        if where is None:
            p.unknown_writes += 1
        else:
            p.writes.append(where)
        if sub == "worktree" and args[:1] == ["add"]:
            dest = next((a for a in args[1:] if not a.startswith("-")), None)
            r = resolve(dest, where) if dest else None
            if r is None:
                p.unknown_writes += 1
            else:
                p.writes.append(r)
        return p
    p.category = "other"
    p.why = f"`git {sub}` is not a subcommand Mentis recognises"
    return p


# ---------------------------------------------------------------------------
# a request, described


#: A READ-ONLY PUBLIC WEB OPERATION through the runtime's own web tool: a
#: search query, or a public page fetched by URL (docs/run-consent.md,
#: "Research"). Allowed only by a request that asks for research; never by a
#: category of consent, and never for a shell command (`curl` stays
#: `network`).
RESEARCH = "research"
_MAX_QUERY = 400
_MAX_URL = 2048
#: what a query or URL must not carry: a local path or a share, so a search
#: is not a way to send local files or Brain content out
_LOCAL = re.compile(r"(?i)(\b[a-z]:[\\/]|\\\\|(?<![\w.])/[a-z]/|file:|appdata|\.ssh|corpus\.db|mentis-corpus)")


def research_of(raw: dict, title: str) -> tuple[str, str] | None:
    """("search", query) or ("page", url) when a fetch is a read-only public
    web operation, else None (it stays `network`). Fails closed: anything
    that could carry local data, credentials, a write or a non-public host
    is not research."""
    import ipaddress
    from urllib.parse import urlsplit
    if any(k in raw for k in ("body", "data", "headers", "files", "upload", "json")):
        return None
    method = str(raw.get("method") or "GET").upper()
    if method not in ("GET", "HEAD"):
        return None
    url = raw.get("url") if isinstance(raw.get("url"), str) else None
    query = raw.get("query") if isinstance(raw.get("query"), str) else None
    if url is None and query is None:
        m = re.match(r'^(?:Search|Web search)\s*:?\s*"(.+)"$', title or "", re.S)
        if m:
            query = m.group(1)
    if query is not None and url is None:
        q = query.strip()
        if not q or len(q) > _MAX_QUERY or _LOCAL.search(q):
            return None
        return ("search", q)
    if url is None or len(url) > _MAX_URL or _LOCAL.search(url.split("?", 1)[0]) \
            or (len(url.split("?", 1)) > 1 and _LOCAL.search(url.split("?", 1)[1])):
        return None
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    host = parts.hostname.lower()
    if host in ("localhost",) or host.endswith((".local", ".localhost", ".internal", ".lan")):
        return None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        return None
    if "." not in host and ip is None:
        return None
    return ("page", url)


def describe(request: dict, *, cwd: str | None, workspaces: list[str],
             categories=DEFAULT_CATEGORIES, protected: list[str] | None = None,
             run_workspace: str | None = None,
             shell: str | None = None) -> Operation:
    """One permission request as an operation, checked against these
    workspaces and permitted categories."""
    tool = request.get("tool_call") or {}
    kind = tool.get("kind")
    title = " ".join(str(tool.get("title") or "").split())
    raw = tool.get("raw_input")
    if raw is None:
        raw = tool.get("rawInput")
    raw = raw if isinstance(raw, dict) else ({"command": raw} if isinstance(raw, (str, list)) else {})
    tool_metas = [m for m in (tool.get("field_meta"), tool.get("_meta"))
                  if isinstance(m, dict)]
    request_metas = [m for m in (request.get("field_meta"), request.get("_meta"))
                     if isinstance(m, dict)]
    observed_shell = next((mars_tool.get("shell") for meta in tool_metas
                           if isinstance((mars_tool := meta.get("mars/tool")), dict)
                           and mars_tool.get("shell") in ("powershell", "bash")), None)
    claude_name = next(((meta.get("claudeCode") or {}).get("toolName")
                        for meta in [*tool_metas, *request_metas]
                        if isinstance(meta.get("claudeCode"), dict)), None)
    if claude_name is None and isinstance(tool.get("claudeCode"), dict):
        claude_name = tool["claudeCode"].get("toolName")
    if claude_name is None and isinstance(request.get("claudeCode"), dict):
        claude_name = request["claudeCode"].get("toolName")
    claude_shell = (claude_name.lower() if isinstance(claude_name, str)
                    and claude_name.lower() in ("powershell", "bash") else None)
    command_shell = observed_shell or claude_shell or shell
    tool_name = claude_name or tool.get("name")
    says = raw.get("description") if isinstance(raw.get("description"), str) else None
    declared_cwd = request.get("shell_cwd") if "shell_cwd" in request else cwd
    here = (raw.get("cwd") if isinstance(raw.get("cwd"), str)
            and os.path.isabs(raw["cwd"]) else declared_cwd)
    roots = protected if protected is not None else protected_roots()
    locs = [loc.get("path") for loc in tool.get("locations") or ()
            if isinstance(loc, dict) and isinstance(loc.get("path"), str)]

    # THE RUN'S OWN MENTIS TOOLS. Every one is checked again by `/api/worker`
    # against the run's grant; asking the owner first adds nothing.
    mcp_name = tool_name or title
    if isinstance(mcp_name, str) and mcp_name.startswith("mcp__mentis__"):
        op = Operation(summary=f"Use its Mentis tool {mcp_name[len('mcp__mentis__'):]}",
                       action="mentis", category="mentis", kind=kind,
                       tool=mcp_name, tool_label=mcp_name[len("mcp__mentis__"):],
                       agent_says=says, within=True, in_workspaces=True,
                       tools=[mcp_name])
        return op

    command = _unwrap(raw.get("command")) if raw.get("command") is not None else None
    if command is None and kind == "execute" and title:
        command = title
    if command is not None:
        return _describe_command(command, kind=kind, cwd=here, says=says,
                                 workspaces=workspaces, categories=categories,
                                 roots=roots, shell=command_shell,
                                 run_workspace=run_workspace)

    # A FILE TOOL: read, edit, delete, move, search -- by its locations
    paths = [p for p in (locs or [raw.get("file_path") or raw.get("path") or raw.get("notebook_path")])
             if isinstance(p, str) and p]
    paths = [os.path.normpath(p if os.path.isabs(p) else os.path.join(here or "", p))
             for p in paths] if paths else []
    label = (tool_name or kind or "tool")
    if kind in ("read", "search", "think"):
        op = Operation(summary=_files_summary("Read", paths, here) if paths else
                       f"{'Search' if kind == 'search' else 'Read'} files",
                       action="read", category="read", kind=kind, resources=paths,
                       tool=f"{label}".lower(), tool_label=label, agent_says=says,
                       tools=[label.lower()])
        _check(op, writes=[], unknown=0, runs_in=None, reads=paths,
               workspaces=workspaces, categories=categories, roots=roots)
        return op
    if kind in ("edit", "delete", "move"):
        verb = {"edit": "Edit", "delete": "Delete", "move": "Move"}[kind]
        op = Operation(summary=_files_summary(verb, paths, here) if paths else f"{verb} a file",
                       action=kind, category="edit", kind=kind, resources=paths,
                       tool=label.lower(), tool_label=label, agent_says=says,
                       tools=[label.lower()])
        _check(op, writes=paths, unknown=0 if paths else 1, runs_in=None, reads=[],
               workspaces=workspaces, categories=categories, roots=roots)
        return op
    if kind == "fetch":
        found = research_of(raw, title)
        if found is not None:
            what, target = found
            summary = (f'Search the web for "{target}"' if what == "search"
                       else f"Read the public page {target}")
            op = Operation(summary=summary, action=what, category=RESEARCH, kind=kind,
                           resources=[target], tool=label.lower(), tool_label=label,
                           agent_says=says, tools=[label.lower()])
            op.outside = ["web research is not part of this request"]
            return op
        url = raw.get("url") or title
        op = Operation(summary=f"Fetch {url}" if url else "Fetch from the network",
                       action="fetch", category="network", kind=kind,
                       resources=[str(url)] if url else [], tool=label.lower(),
                       tool_label=label, agent_says=says, tools=[label.lower()])
        _check(op, writes=[], unknown=0, runs_in=None, reads=[],
               workspaces=workspaces, categories=categories, roots=roots)
        return op
    op = Operation(summary=f"Use {title or label}", action="other", category="other",
                   kind=kind, resources=paths, tool=(tool_name or title or kind or "tool").lower(),
                   tool_label=tool_name or title or kind or "a tool", agent_says=says,
                   tools=[(tool_name or title or kind or "tool").lower()])
    op.outside = ["Mentis does not recognise this kind of operation"]
    return op


def _files_summary(verb: str, paths: list[str], cwd: str | None) -> str:
    shown = [_short(p, cwd) for p in paths[:3]]
    more = f" and {len(paths) - 3} more" if len(paths) > 3 else ""
    return f"{verb} {', '.join(shown)}{more}"


def _short(path: str, cwd: str | None) -> str:
    if cwd and inside(path, cwd):
        rel = os.path.relpath(path, cwd)
        return rel if rel != "." else os.path.basename(path) or path
    return path


_VERBS = {"read": "Read", "edit": "Edit", "delete": "Delete", "test": "Run tests",
          "build": "Build", "run": "Run", "git": "Git", "git-remote": "Git (remote)",
          "network": "Network", "install": "Install packages", "other": "Run"}


def _describe_command(command, *, kind, cwd, says, workspaces, categories, roots,
                      shell, run_workspace) -> Operation:
    if shell is None:
        bash = _describe_command_as(command, kind=kind, cwd=cwd, says=says,
                                    workspaces=workspaces, categories=categories,
                                    roots=roots, shell_name="bash",
                                    run_workspace=run_workspace)
        powershell = _describe_command_as(
            command, kind=kind, cwd=cwd, says=says, workspaces=workspaces,
            categories=categories, roots=roots, shell_name="PowerShell",
            run_workspace=run_workspace)
        agreed = (bash.category, bash.within, bash.outside, bash.in_workspaces) == (
            powershell.category, powershell.within, powershell.outside,
            powershell.in_workspaces)
        if agreed and not (_unreadable(bash) or _unreadable(powershell)):
            bash.tool = bash.tool.replace("bash", "shell", 1)
            bash.tools = ["shell" if p == "bash" else p for p in bash.tools]
            bash.summary = bash.summary.replace("bash", "shell")
            return bash
        return _cannot_read(command, kind=kind, cwd=cwd, says=says,
                            shell_name="shell")
    shell_name = "PowerShell" if shell.lower() == "powershell" else "bash"
    return _describe_command_as(command, kind=kind, cwd=cwd, says=says,
                                workspaces=workspaces, categories=categories,
                                roots=roots, shell_name=shell_name,
                                run_workspace=run_workspace)


def _cannot_read(command, *, kind, cwd, says, shell_name) -> Operation:
    op = Operation(summary=f"Run a {shell_name} command Mentis cannot read safely",
                   action="run", category="other", kind=kind, command=command,
                   cwd=cwd, agent_says=says, tool=shell_name.lower(),
                   tool_label=shell_name, tools=[shell_name.lower()])
    op.outside = ["it uses shell syntax whose meaning is not reported or cannot "
                  "be read safely"]
    return op


def _unreadable(op: Operation) -> bool:
    return op.category == "other" and any("cannot be read" in reason for reason in op.outside)


def _describe_command_as(command, *, kind, cwd, says, workspaces, categories, roots,
                         shell_name, run_workspace) -> Operation:
    toks = tokens(command, powershell=shell_name.lower() == "powershell")
    if toks is None:
        return _cannot_read(command, kind=kind, cwd=cwd, says=says,
                            shell_name=shell_name)
    parts, here = [], cwd
    for words in statements(toks):
        p, here = _simple(words, here)
        parts.append(p)
    if not parts:
        parts = [_Part("read", "")]
    rank = ["other", "delete", "network", "install", "git-remote", "edit", "git",
            "run", "build", "test", RESEARCH, "read"]
    cats = [p.category for p in parts]
    main = min(cats, key=rank.index)
    # THE TOOL IS THE ONE DOING WHAT THE OPERATION IS NAMED FOR, first.
    ordered = sorted(parts, key=lambda p: p.category != main)
    programs = list(dict.fromkeys(p.program for p in ordered if p.program
                                  and not (p.category == "read" and p.program in READERS)))
    if not programs:
        programs = list(dict.fromkeys(p.program for p in parts if p.program)) or [shell_name.lower()]
    writes = [w for p in parts for w in p.writes]
    unknown = sum(p.unknown_writes for p in parts)
    reads = [r for p in parts for r in p.reads]
    runs_in = [p.runs_in for p in parts
               if p.category in ("test", "build", "run", "git", "other")
               or p.program == "git"] + [None for p in parts if p.reads_unplaced]
    resources = list(dict.fromkeys(writes or reads or [r for r in runs_in if r]))
    op = Operation(summary="", action=main, category=main, kind=kind,
                   resources=resources, command=command, cwd=cwd, agent_says=says,
                   tool=":".join([shell_name.lower(), programs[0]]) if programs else shell_name.lower(),
                   tool_label=programs[0] if programs else shell_name, parts=cats,
                   tools=programs)
    # WHERE THE PART THAT DECIDES IT RUNS, not where the command started: a
    # command that sets its own directory (`Set-Location C:\repo; pytest`)
    # runs there, and the question names it.
    deciding = [p.runs_in for p in parts if p.category == main and p.runs_in]
    summary_cwd = (deciding[-1] if deciding else
                   cwd or next((p.runs_in for p in parts if p.runs_in), None))
    op.summary = _command_summary(op, parts, summary_cwd, shell_name)
    _check(op, writes=writes, unknown=unknown,
           runs_in=runs_in, reads=reads, workspaces=workspaces,
           categories=categories, roots=roots, cwd=cwd, parts=parts)
    return op


def _command_summary(op: Operation, parts: list[_Part], cwd, shell_name) -> str:
    cat = op.category
    where = (f" in {_short(cwd, None)}" if cwd else
             " in its shell's current directory (not reported)")
    if cat == "read":
        shown = [_short(r, cwd) for r in op.resources[:2]]
        return (f"Read {', '.join(shown)}" + (" and more" if len(op.resources) > 2 else "")
                if shown else f"Look at files{where}") + f" ({', '.join(op.tools[:3]) or shell_name})"
    if cat in ("edit", "delete"):
        targets = [_short(w, cwd) for w in op.resources[:3]]
        verb = "Delete" if cat == "delete" else "Write"
        if targets:
            return f"{verb} {', '.join(targets)}" + (" and more" if len(op.resources) > 3 else "") \
                + f" with {op.tool_label}"
        return f"{verb} files with {op.tool_label} (the target is not known until it runs)"
    if cat == "test":
        return f"Run tests or checks with {op.tool_label}{where}"
    if cat == "build":
        return f"Build with {op.tool_label}{where}"
    if cat == "run":
        script = next((r for p in parts for r in p.reads if p.category == "run"), None)
        return f"Run {_short(script, cwd) if script else op.tool_label}{where}"
    if cat == "git":
        return f"Change the Git repository{where} ({' '.join(op.tools[:2])})"
    if cat == "git-remote":
        return f"Talk to a Git remote{where} (fetch, pull or push)"
    if cat == "network":
        return f"Reach the network with {op.tool_label}"
    if cat == "install":
        return f"Install or change packages with {op.tool_label}{where}"
    why = next((p.why for p in parts if p.category == "other" and p.why), None)
    return f"Run {op.tool_label}{where}" + (f" ({why})" if why else "")


def _check(op: Operation, *, writes, unknown, runs_in, reads, workspaces, categories,
           roots, cwd=None, parts=None) -> None:
    """Fill `within`, `outside`, `in_workspaces`, `workspace`, `offer_workspace`."""
    outside: list[str] = []
    ws = [w for w in workspaces if w]
    touched = list(writes) + [r for r in (runs_in or []) if r]
    protected_hit = [p for p in [*touched, *reads] if is_protected(p, roots)]
    if protected_hit:
        outside.append(f"it touches a protected location ({protected_hit[0]}): "
                       f"Brains, MARS data and credentials are never part of a task")
    # paths written or run in must be inside a workspace
    not_in = [p for p in touched if not any(inside(p, w) for w in ws)]
    if runs_in is not None and None in runs_in:
        outside.append("where it runs is not reported (start the command by setting "
                       "an absolute directory)")
    if unknown:
        outside.append("what it writes is held in a variable or not named, so it "
                       "cannot be checked")
    if not_in:
        outside.append(f"it works outside the approved workspaces ({not_in[0]})")
    guarded = [p for p in writes for w in ws if inside(p, w) and is_guarded(p, w)]
    if guarded:
        outside.append(f"it changes {guarded[0]}, which can run code or change "
                       f"permissions later")
    cats = list(dict.fromkeys(parts and [p.category for p in parts] or [op.category]))
    blocked = [c for c in cats if c not in ("read", "mentis") and c not in categories]
    other_parts = [p for p in (parts or []) if p.category == "other"]
    if op.category == "other" and not other_parts and not outside:
        outside.append("Mentis does not recognise what this does")
    op.in_workspaces = not (protected_hit or not_in or unknown or guarded
                            or (runs_in is not None and None in runs_in))
    if blocked:
        names = ", ".join(c for c in blocked if c != "other")
        if names:
            outside.append(f"its kind of operation ({names}) is not permitted for this task")
        if "other" in blocked:
            whys = [p.why for p in other_parts if p.why]
            outside.append("it does something Mentis cannot classify"
                           + (f": {whys[0]}" if whys else ""))
    op.outside = outside
    op.within = not outside
    home = next((w for w in ws if any(inside(p, w) for p in touched)), None) \
        or next((w for w in ws if cwd and inside(cwd, w)), None)
    op.workspace = home
    # OFFER A WORKSPACE only when where it works is the one thing wrong
    if not_in and not (protected_hit or unknown or guarded or blocked):
        roots_of = {repository_root(p) for p in not_in}
        roots_of.discard(None)
        if len(roots_of) == 1:
            cand = roots_of.pop()
            if cand and not is_protected(cand, roots) and len(cand) > 3 \
                    and os.path.normcase(cand) != os.path.normcase(os.path.expanduser("~")):
                op.offer_workspace = cand


def read_only(op: Operation) -> bool:
    """Wholly a read of nothing protected: what the run's grant already covers."""
    if op.category not in ("read",):
        return False
    return not any("protected" in o or "where it runs is not reported" in o
                   for o in op.outside)
