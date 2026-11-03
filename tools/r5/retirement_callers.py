"""Every reference to R5.1's retirement candidates, with the function it is in.

The first half of the search in `docs/rust/R5.1-retirement-closure.md`. It follows module aliases
per scope (`from . import objects as _objects`, an import inside a function), which a text search
can't. It can't see code in a string or a call by route or op name: the document's `git grep` lines
are for those.

    python tools/r5/retirement_callers.py [checkout]
"""
import ast
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

MODULES = {
    "mentis.fluid.objects": "objects",
    "mentis.fluid.search": "search",
    "mentis.conversation.objectref": "objectref",
    "mentis.conversation.render_check": "render_check",
}


def python_files(root):
    listed = subprocess.run(
        ["git", "ls-files", "mentis", "tools", "tests", "apps"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split("\n")
    return [name for name in listed if name.endswith(".py")]


def absolute(rel, node):
    """The module a `from` import names, from the file it is in."""
    if not node.level:
        return node.module or ""
    package = rel[:-3].split("/")[:-1]
    package = package[: len(package) - (node.level - 1)]
    return ".".join(package + ([node.module] if node.module else []))


class Walk(ast.NodeVisitor):
    def __init__(self, rel, hits):
        self.rel, self.hits = rel, hits
        self.stack = []
        self.scopes = [{}]

    def where(self):
        return ".".join(self.stack) or "<module>"

    def bound(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in MODULES:
                self.scopes[-1][alias.asname or alias.name] = ("module", alias.name)
                self.hits[alias.name, "<import>"].append((self.rel, node.lineno, self.where()))

    def visit_ImportFrom(self, node):
        base = absolute(self.rel, node)
        for alias in node.names:
            full = f"{base}.{alias.name}" if base else alias.name
            name = alias.asname or alias.name
            if full in MODULES:
                self.scopes[-1][name] = ("module", full)
                self.hits[full, "<import>"].append((self.rel, node.lineno, self.where()))
            elif base in MODULES:
                self.scopes[-1][name] = ("attr", base, alias.name)
                self.hits[base, alias.name].append((self.rel, node.lineno, self.where()))

    def enter(self, node):
        self.stack.append(node.name)
        self.scopes.append({})
        for child in ast.iter_child_nodes(node):
            self.visit(child)
        self.scopes.pop()
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = enter

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name):
            bound = self.bound(node.value.id)
            if bound and bound[0] == "module":
                self.hits[bound[1], node.attr].append((self.rel, node.lineno, self.where()))
        self.generic_visit(node)

    def visit_Name(self, node):
        bound = self.bound(node.id)
        if bound and bound[0] == "attr" and isinstance(node.ctx, ast.Load):
            self.hits[bound[1], bound[2]].append((self.rel, node.lineno, self.where()))


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hits = defaultdict(list)
    for rel in python_files(root):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as why:
            print(f"NOT READ {rel}: {why}", file=sys.stderr)
            continue
        Walk(rel, hits).visit(tree)
    for (module, attr), sites in sorted(hits.items()):
        print(f"## {MODULES[module]}.{attr}")
        for rel, line, where in sorted(set(sites)):
            print(f"  {rel}:{line}  {where}")


if __name__ == "__main__":
    main()
