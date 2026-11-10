"""Masking credentials in what the record keeps of a command or a tool call
(WS-A: `operation-answered`, `operations-observed`, a run's end act).

CONSERVATIVE BY DESIGN. Only HIGH-CONFIDENCE secret VALUES are masked, each
replaced by `***`; the syntax around them -- names, quotes, flags, URLs -- is
left exactly as it was, and any text no rule matches is returned
byte-identical. A commit message that says "auth", a search for `token: `,
`auth=None` in code: none is touched. Something unusual may get through; that
is the price of never damaging ordinary text.

What is masked:
  * the value of an assignment whose NAME, in capitals, contains KEY, TOKEN,
    SECRET, PASSWORD, PASSWD, PWD or CREDENTIAL (`X=..`, `export X=..`,
    `set X=..`, `$env:X = ..`, any case after `$env:`);
  * the value of an Authorization / API-key / token header (`-H`/`--header`),
    and a value after `Bearer`;
  * a URL's userinfo password (`https://user:PASS@host`);
  * `curl -u user:PASS`, `mysql -pPASS`, `--password=PASS`,
    `ConvertTo-SecureString 'PASS'`;
  * well-known token shapes: GitHub (ghp_, gho_, ghs_, ghu_, ghr_,
    github_pat_), GitLab (glpat-), OpenAI/Anthropic (sk-, sk-ant-), Slack
    (xoxb-, xoxp-, xoxa-, xoxs-), AWS access key ids (AKIA...), npm (npm_),
    and three-part JWTs (eyJ...).
"""

from __future__ import annotations

import re

MASK = "***"

_NAME = r"(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL)"
_VALUE = r"""(?:"(?P<dq>[^"\n]+)"|'(?P<sq>[^'\n]+)'|(?P<bare>[^\s"';&|)]+))"""

#: (pattern, the named groups holding the secret). Every other part of a
#: match is written back as it was.
_RULES = [
    # NAME=VALUE: env, export, set; capitals in the name (an env variable)
    (re.compile(r"(?:(?<=^)|(?<=[\s;&|(]))(?:export\s+|set\s+)?"
                r"[A-Z0-9_]*" + _NAME + r"[A-Z0-9_]*=" + _VALUE),
     ("dq", "sq", "bare")),
    # $env:NAME = VALUE: PowerShell, any case
    (re.compile(r"(?i)\$env:[A-Za-z0-9_]*" + _NAME + r"[A-Za-z0-9_]*\s*=\s*" + _VALUE),
     ("dq", "sq", "bare")),
    # -H 'Authorization: Bearer|token|Basic VALUE', -H 'X-Api-Key: VALUE'
    (re.compile(r"(?i)(?:-H|--header)\s+['\"]?[A-Za-z-]*(?:authorization|api-?key|token|secret)"
                r"\s*:\s*(?:(?:bearer|token|basic)\s+)?(?P<v>[^\s'\"]+)"),
     ("v",)),
    (re.compile(r"(?i)\bbearer\s+(?P<v>[A-Za-z0-9._~+/=-]{8,})"), ("v",)),
    # https://user:PASS@host
    (re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@'\"]+:(?P<v>[^@\s/'\"]+)@"), ("v",)),
    # curl -u user:PASS
    (re.compile(r"(?:(?<=^)|(?<=\s))(?:-u|--user)\s+['\"]?[^\s:'\"]+:(?P<v>[^\s'\"]+)"), ("v",)),
    # mysql -pPASS (the attached form only), --password=PASS
    (re.compile(r"\bmysql(?:dump|admin)?\b[^\n;|&]*?\s-p(?P<v>[^\s'\"]+)"), ("v",)),
    (re.compile(r"--password=" + _VALUE), ("dq", "sq", "bare")),
    # ConvertTo-SecureString 'PASS'
    (re.compile(r"(?i)ConvertTo-SecureString\s+(?:-String\s+)?" + _VALUE), ("dq", "sq", "bare")),
    # token shapes
    (re.compile(r"\b(?P<v>(?:gh[opsur]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}"
                r"|glpat-[A-Za-z0-9_-]{16,}|sk-ant-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{20,}"
                r"|xox[bpas]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|npm_[A-Za-z0-9]{20,}"
                r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+))"), ("v",)),
]


def redact_flag(text):
    """(`text` with secret values masked, whether anything was)."""
    if not isinstance(text, str) or not text:
        return text, False
    spans = []
    for rx, groups in _RULES:
        for m in rx.finditer(text):
            for g in groups:
                if m.group(g) is not None and m.group(g) != MASK:
                    spans.append(m.span(g))
    if not spans:
        return text, False
    spans.sort()
    out, at = [], 0
    for a, b in spans:
        if a < at:                      # overlapping: already masked
            a = at
            if a >= b:
                continue
        out.append(text[at:a])
        out.append(MASK)
        at = b
    out.append(text[at:])
    return "".join(out), True


def redact(text):
    return redact_flag(text)[0]


def redact_call(call: dict) -> dict:
    """A tool call as recorded: its title (and raw command) masked, marked
    `redacted: true` when anything was."""
    if not isinstance(call, dict):
        return call
    out, hit = dict(call), False
    for k in ("title", "command"):
        if isinstance(out.get(k), str):
            out[k], h = redact_flag(out[k])
            hit = hit or h
    if hit:
        out["redacted"] = True
    return out
