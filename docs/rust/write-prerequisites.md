# What a Rust write needs first

Section 6 of `adm-56082aa297b0`. **Not R1 work.** R1 adds nothing that depends on these. No Rust write happens until all four pass and the owner approves W0 and the recovery rule (r2, section 7).

1. **Cross-process semantic-operation lock.** Held around the whole production command, from its first check through commit or rollback, not just inside `Store.write()`. Check-then-append paths such as `conversation/__init__.py:2927-2948` are the proof cases.
2. **Memo invalidation.** On taking the lock, Python compares a durable position and invalidates every affected memo, revision and shared answer **before checking anything**. Consumers are inventoried first (`spine/store.py:223-256`, `spine/seam.py:420-509`).
3. **Chain head and `seq`.** Read inside the transaction on both sides, with any in-memory state in Python found and handled.
4. **Proof on a Brain copy under load.** No race, correct memos, both verifiers accept.

If W0 fails, writes become one flip, and the plan says so. W0 can start after R1, on a copy only, and deploys nothing.
