"""Folder acquisition policy: names only, never content classification."""

from fnmatch import fnmatchcase

from mentis.sources import Refused

#: THE REPOSITORY PRESET EXCLUDES REPRODUCIBLE MATERIAL ONLY (owner, K1/K2):
#: Git metadata and copies, dependencies and environments, and caches named
#: as caches. A cache is excluded by ITS OWN folder, never by its parent
#: (K3): `.turbo/cache` (Oatmeal: 23.9 GiB) goes, `.turbo/*.log` task logs
#: stay reachable; `.next/cache` goes, the rest of `.next` is build output.
#: Logs and build output are evidence, so they are not here: they are the
#: CATEGORIES below, visible and off by default.
REPOSITORY_FOLDERS = (
    '.git', '.worktrees', 'node_modules', '.venv', 'venv', '__pycache__',
    '.pytest_cache', '.mypy_cache', '.cache', '.turbo/cache',
    '.angular/cache', '.next/cache',
)


def _anywhere(folders):
    """At the root and at any depth. `*` crosses `/`."""
    return [p for folder in folders for p in (folder, '*/' + folder)]


REPOSITORY_EXCLUDES = _anywhere(REPOSITORY_FOLDERS)

#: EVIDENCE CATEGORIES (owner, K1/K2/K5). Material that is evidence but may
#: carry what a filename cannot reveal, so acquiring any of it that would be
#: newly acquired needs an explicit, recorded, category-level decision.
#: "Off" is these patterns as visible excludes in the scope; "on" removes
#: them. `*.log` also covers Turborepo task logs (`<pkg>/.turbo/*.log`).
CATEGORIES = {
    'logs': {'label': 'Logs', 'patterns': _anywhere(('logs',)) + ['*.log']},
    'build': {'label': 'Build output',
              'patterns': _anywhere(('dist', 'build', 'out', 'coverage',
                                     'target', '.next'))},
}

#: What the Repository preset puts in the exclude list: the reproducible
#: material, then both categories, off.
REPOSITORY_PRESET_EXCLUDES = REPOSITORY_EXCLUDES + [
    p for c in CATEGORIES.values() for p in c['patterns']]

#: What category consent never means, said wherever it is given or recorded.
CONSENT_NOTE = ('category consent is the owner choosing to acquire this kind '
                'of material; it is not evidence that the files contain no '
                'secrets, and no file was examined for secrets')


def _under(patterns, path):
    parts = path.split('/')
    return any(fnmatchcase('/'.join(parts[:i]), p) for p in patterns
               for i in range(1, len(parts) + 1))


def categories_of(path):
    """Every category a relative path belongs to, by name, never by content."""
    return [c for c, d in CATEGORIES.items() if _under(d['patterns'], path)]


def category_decisions(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or any(
            c not in CATEGORIES or choice not in ('include', 'exclude')
            for c, choice in value.items()):
        raise Refused('category decisions map ' + ' or '.join(CATEGORIES)
                      + ' to include or exclude')
    return dict(sorted(value.items()))


def category_label(c):
    return CATEGORIES[c]['label']


RULES = (
    '.env*', '*.pem', '*.key', '*.p12', '*.pfx', 'id_rsa*',
    'id_ed25519*', '*credential*', '*secret*', '.npmrc', '.netrc',
    '.pgpass', '*.kdbx', '*service*account*.json',
)


def rule(path):
    name = path.rsplit('/', 1)[-1].casefold()
    return next((p for p in RULES if fnmatchcase(name, p)), None)


def decisions(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise Refused('sensitive decisions must map exact paths to include or exclude')
    for path, choice in value.items():
        if (not isinstance(path, str) or not path or '\\' in path
                or path.startswith('/') or ':' in path
                or any(p in ('', '.', '..') for p in path.split('/'))
                or not rule(path) or choice not in ('include', 'exclude')):
            raise Refused('each sensitive decision needs a credential-like relative path and include or exclude')
    return dict(sorted(value.items()))


def literal_pattern(path):
    # fnmatch's literal escapes, including filenames containing glob syntax.
    return ''.join({'[': '[[]', '*': '[*]', '?': '[?]'}.get(c, c) for c in path)


def scope_with_decisions(scope, choices, categories=None):
    """Exclusions become explicit, visible scope patterns: a flagged file's
    literal path, and a declined category's own patterns."""
    out = {**scope, 'exclude': list(scope['exclude'])}
    patterns = [literal_pattern(p) for p, c in choices.items() if c == 'exclude']
    for c, choice in (categories or {}).items():
        if choice == 'exclude':
            patterns += CATEGORIES[c]['patterns']
    for pattern in patterns:
        if pattern not in out['exclude']:
            out['exclude'].append(pattern)
    return out
