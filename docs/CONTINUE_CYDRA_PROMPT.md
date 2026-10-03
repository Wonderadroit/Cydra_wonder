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


## Current architectural direction: recursive exploration

The next generic capability is recursive target exploration built on the existing model/reasoning/evidence machinery.

Use `src/cydra/exploration.py` as the current boundary:
- derive frontier questions from the existing investigation result;
- prefer unresolved hypotheses with executable experiments;
- retain uncovered functions/state surfaces as explicit exploration questions;
- enforce an investigation budget;
- never invent target facts or bypass readiness.

The intended loop is **model → frontier → test → evidence → updated model/frontier → repeat**. Connect this to the canonical live orchestration before adding more individual detectors.

### Current continuation boundary
The next generic orchestration capability is bounded recursive exploration via run_bounded_exploration. It must delegate execution to the existing canonical path, feed returned evidence into the investigation model, refresh the frontier, and stop on budget/frontier exhaustion. Do not invent target facts or create a second execution engine.