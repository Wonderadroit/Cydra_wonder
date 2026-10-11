# CYDRA

**Evidence-first security research for explicitly authorized targets.**

> Understand systems rather than memorize vulnerabilities.
>
> **LLMs propose. Deterministic tools test. Evidence decides.**

## Current focus

CYDRA is prioritizing one narrow Web3 capability before expanding: **detecting missing or incorrect authorization on state-changing Solidity/EVM operations**.

The specialist reuses CYDRA's source model, authorization reasoning, Foundry execution, causal verification, and evidence gates. It must not promote a suspicious function, static warning, failed setup, or unsupported hypothesis into a finding.

### Current evidence (2026-10-11)

- Focused authorization controls and the historical external positive control passed their workflow.
- Two unfamiliar, program-linked source revisions compiled and produced state-effect evidence.
- Both unfamiliar runs ended `BLOCKED / NO_SUPPORTED_HYPOTHESIS / NOT_READY`; no authorization experiment was selected for those targets.
- **No novel, independently reproduced bounty finding has been established.** Green regression checks demonstrate engineering correctness, not bounty readiness.

See [the specialist plan](docs/WEB3_AUTHORIZATION_SPECIALIST.md) for the gates, evidence, and exact blockers.

## Quick start

```bash
python -m pip install -e . pytest
python -m pytest -q
```

Run the focused authorization tests:

```bash
python -m pytest -q \
  tests/test_blind_authorization.py \
  tests/test_authorization_reasoning.py \
  tests/test_authorization_invariant.py \
  tests/test_blind_auth_campaign_report.py
```

The specialist and unfamiliar-target workflows are deliberately manual campaigns; they should not run on every push. Review their YAML before dispatching because external source checkouts and long-running experiments may be involved.

## Repository map

| Path | Purpose |
|---|---|
| `src/cydra/` | Reusable models, reasoning, execution adapters, evidence, and finding gates |
| `tests/` | Unit and integration regressions, including authorization controls |
| `scripts/` | Reproducible entrypoints for the specialist, live intake, and historical campaigns |
| `benchmarks/` | Pinned historical/synthetic fixtures and their expected experimental boundaries |
| `.github/workflows/` | Fast regression checks and manually dispatched research campaigns |
| `targets/` | Target intake/configuration; scope and authorization must be verified before use |
| `docs/WEB3_AUTHORIZATION_SPECIALIST.md` | Current specialist decision, gates, and measurements |
| `docs/UNFAMILIAR_WEB3_AUTHORIZATION_GATE.md` | Rules for safe, blind unfamiliar-target validation |
| `docs/CYDRA_OPERATING_PROTOCOL.md` | Human/LLM/Actions operating and handoff contract |
| `PROJECT_BIBLE.md` | Long-form doctrine and design history |
| `ARCHITECTURE.md` | System boundaries and core objects |
| `DEVELOPMENT_PROTOCOL.md` | Engineering and validation rules |
| `AGENTS.md` | Active assignment and hard-stop rules |
| `ROADMAP.md` | Ordered completion gates |

## Research workflow

```text
authorized intake → immutable target snapshot → system model
→ authorization boundary → falsifiable hypothesis → safe experiment
→ execution evidence → causal verification → independent reproduction
→ human scope/novelty/impact review
```

A blocked or unmeasurable run is not a negative security result. Public source availability is not authorization. Production state-changing transactions are not part of the unfamiliar-target gate.

## Engineering rules

- Fix the first demonstrated blocker, not a speculative gap.
- Prefer a generic repair with a regression and replay against the same frozen target.
- Keep historical cases as evaluation assets; do not hard-code their answers into the detector.
- Keep long benchmark campaigns manual unless a narrow change specifically requires them.
- Do not claim a vulnerability, novelty, or bounty readiness without reproducible causal evidence and human review.
