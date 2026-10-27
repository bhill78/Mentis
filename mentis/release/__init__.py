"""Mentis release packages: build them from a commit, verify them.

    python -m mentis.release build  --version 1.0.0-rc.1 [--commit REF] [--repo R] [--out DIR]
    python -m mentis.release verify <package.zip | release dir | wheel bundle>
    python -m mentis.release wheels <package.zip> [--platform TAG ...]
    python -m mentis.release lock   [--repo R]

See `build.py` for the package contract.
"""
