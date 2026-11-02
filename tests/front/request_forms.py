"""Request forms where the front and Python could read one request two ways, with what Python's own
parse makes of each target. Row A's parser cases, `test_front_forms.py` and the front's unit test all
take them from here, so what is claimed is Python's and not a copy of the front's reasoning.

    python tests/front/request_forms.py --write    rewrites crates/mentis-server/tests/python_targets.tsv
"""

from __future__ import annotations

import pathlib
import re
import sys
import urllib.parse

#: `/private/` to Python, and so the front's own on the public port.
PRIVATE_TARGETS = [
    "/private/live", "/private/", "/private/stop?x=1", "/private/live;x", "/private/live#f",
    "//private/live", "///private/live", "http://host/private/live", "HTTP://host/private/live",
    "http:/private/live", "http:///private/live", "weird:/private/live", "mailto:/private/live",
    "a+b.c-d:/private/live", "\x01/private/live", "\x01///private/live",
    "http://[::1]/private/live", "http://u@[::1]:1/private/live", "http://[v1.a]/private/live",
]
#: Not `/private/` to Python, however much they look it: its normal answer.
ELSEWHERE_TARGETS = [
    "x/private/live", "mailto:x/private/live", "/private", "/privateer/x", "/fluid/private/x",
    "/%70rivate/live", "/PRIVATE/live", "1x:/private/live", "a_b:/private/live", ":/private/live",
    "a:b:/private/live", "http:http://h/private/live", "//h/private/live", "http://private/live",
    "\x01//private/live", "http://////private/live", "?/private/live", "#/private/live",
    "/x?/private/live", "/x#/private/live", "http://h?/private/live", "http://h#/private/live",
]
#: `urlparse` raises on these, so Python's handler dies and it closes without a word, and the front
#: must too. Each has `/private/` where its path would be, so if it did parse it would be under there.
RAISING_TARGETS = [
    "http://[/private/live", "http://]/private/live", "http://[x]/private/live",
    "http://[1.2.3.4]/private/live", "http://a[::1]/private/live",
]
#: In HTTP/0.9's form, `GET <target>`: some under `/private/`, and two that aren't.
BARE_PRIVATE_TARGETS = ["/private/live", "/private/x", "//private/live", "http://host/private/live"]
BARE_ELSEWHERE_TARGETS = ["/", "x/private/live"]
#: A request line Python refuses before anything is routed, with `/private/` in it.
ODD_LINES = ["G'T /private/live HTTP/1.1", "GET /private/live HTTP/2.0", "GET /private/live HTTP/x",
             "GET /private/live extra HTTP/1.1"]
#: Python can't hold a body this big, so a route that reads one closes without a word. Where that
#: starts depends on the machine's memory (2^38 where this was measured, as `read` raises
#: MemoryError, and OverflowError from 2^63), and each of these is far past it.
ENORMOUS_LENGTHS = ["9223372036854775807", "9223372036854775808", "18446744073709551615",
                    "18446744073709551616", "99999999999999999999999"]


def python_reads(target: str) -> str:
    """`private`, `elsewhere` or `raises`, by `parse_request`'s `//` and then `urlparse`. `raises` is
    only said of a target whose path would have been under `/private/`: for any other, whether it
    raises makes no difference to what it may carry."""
    path = "/" + target.lstrip("/") if target.startswith("//") else target
    try:
        return "private" if urllib.parse.urlparse(path).path.startswith("/private/") else "elsewhere"
    except ValueError:
        # Only the brackets of a netloc raise, and it starts at the first `//`.
        unbracketed = re.sub(r"^(.*?//)([^/?#]*)",
                             lambda m: m[1] + m[2].replace("[", "").replace("]", ""), path, count=1)
        would_be = urllib.parse.urlparse(unbracketed).path
        return "raises" if would_be.startswith("/private/") else "elsewhere"


_PREFIXES = [
    "", "/", "//", "///", "////", "\x01", "\x1b/", "\x00", "http:", "http://", "http:///",
    "HTTP://h", "http://h", "x:", "x:/", "x://", "1x:", "a_b:", ":", "a:b:", "mailto:", "mailto:x",
    "\xe9:", "a\xe9:", "a+b.c-d:", "http://[", "http://]", "http://[::1]", "http://[::1]:80",
    "http://u@[::1]", "http://[1.2.3.4]", "http://[v1.a]", "http://[v.a]", "http://[fe80::1%25]",
    "http://[fe80::1%x%y]", "http://[fe80::1%]", "http://[::1]x", "http://a[::1]", "http://[a]@b",
    "http://\xbc", "//[", "\x01//", "\x01///", "?", "#", "x?", "x#", "http://h?", "http://h#", ";",
]
_BODIES = ["private/live", "/private/live", "private/", "/private/", "/private", "/private;x/live",
           "/private/;x", "/privateer/x", "/PRIVATE/x", "/%70rivate/x", "/x/private/y"]
_SUFFIXES = ["", "?x", "#x"]

TSV = pathlib.Path(__file__).resolve().parents[2] / "crates/mentis-server/tests/python_targets.tsv"


def all_targets() -> list[str]:
    made = {prefix + body + suffix for prefix in _PREFIXES for body in _BODIES for suffix in _SUFFIXES}
    return sorted(made | set(PRIVATE_TARGETS + ELSEWHERE_TARGETS + RAISING_TARGETS))


def table() -> str:
    """Hex of each target as sent, a tab, and what Python reads it as. Hex, since many aren't text."""
    return "".join(f"{target.encode('latin-1').hex()}\t{python_reads(target)}\n"
                   for target in all_targets())


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit(__doc__)
    TSV.write_text(table(), encoding="ascii", newline="\n")
    print(f"{TSV}: {len(all_targets())} targets")
