# Continue CYDRA

Continue CYDRA_wonder from the repository state, not from chat history.

Read first:

- `PROJECT_BIBLE.md`
- `AGENTS.md`
- `docs/AGENT_HANDOFF.md`
- `docs/LIVE_DOGFOOD_STATE.md`

## Mission

The only active objective is live-target dogfooding against the pinned authorized Hinkal target.

Do not reset or redesign CYDRA. Do not reopen the maturity gate. Do not add Benchmark 051 or other benchmark expansion. Do not perform unrelated cleanup.

## Operating loop

1. Inspect the current live state and latest artifact.
2. Identify the first demonstrated pipeline blocker.
3. Understand why it occurs.
4. Implement the smallest justified generic capability.
5. Add a regression for the failure.
6. Run the relevant tests.
7. Run the canonical Hinkal workflow against the same frozen target.
8. Update `docs/LIVE_DOGFOOD_STATE.md`.
9. Repeat.

Rule:

**Observed failure → understand missing general capability → implement generically → regression → rerun same experiment + broader validation.**

LLMs propose. Tools test. Evidence decides.

## Continuation requirement

Never assume an earlier chat message is authoritative. The latest repository checkpoint, workflow artifact, and commit history are authoritative.
