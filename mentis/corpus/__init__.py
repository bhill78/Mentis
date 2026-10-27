"""The user's portable corpus. Only this package resolves a path inside it."""
from .store import Corpus, machine_id, require

__all__ = ["Corpus", "machine_id", "require"]
