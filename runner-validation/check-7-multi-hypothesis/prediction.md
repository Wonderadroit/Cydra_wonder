# Check 7 — Multi-Hypothesis Authorization Prediction

## Target

Repository:
https://github.com/Wonderadroit/Cydra_wonder

Target ref: `5786669ec73f44aa008b1706efd6677e43035bb8`

Target project:
benchmarks/check_7_multi_hypothesis

Target path:
src/MultiAuthorizationFixture.sol

Target contract:
MultiAuthorizationFixture

Class:
authorization

Patched counterpart:
none

## Pre-run prediction

The frozen runner is predicted to produce exactly two authorization
hypotheses from this single target path:

- H-AUTH-setOracle
- H-AUTH-updateFee

Both hypotheses are predicted to:

1. be extracted;
2. reach experiment planning;
3. reach Foundry test generation;
4. reach blind execution.

Because this is a blind target with no patched counterpart, both
hypotheses are predicted to have classification:

NOT_REACHED

with the existing authorization classification boundary:

authorization classifier requires patched counterpart; blind target has none

No prediction is made about whether either behavioral hypothesis is
actually confirmed as a vulnerability.

## Falsification criteria

- Fewer than two hypotheses: multiplicity fails at extraction.
- Two extracted but fewer than two planned: planning boundary.
- Two planned but fewer than two generated: generation boundary.
- Two generated but fewer than two executed: execution boundary.
- Two executed: end-to-end hypothesis multiplicity is demonstrated.

## Acceptance criterion

The frozen-run classification output must contain two per-hypothesis
records corresponding to H-AUTH-setOracle and H-AUTH-updateFee, with
both reaching blind execution.

This check validates hypothesis multiplicity through the frozen
pipeline. It does not establish a security finding.
