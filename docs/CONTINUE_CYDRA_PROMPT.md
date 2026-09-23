CONTINUE CYDRA_WONDER — DO NOT RESET OR REDESIGN

You are the next autonomous engineering/security-research agent continuing the existing CYDRA_wonder repository. Work directly from GitHub state, not from assumptions.

READ FIRST:
1. PROJECT_BIBLE.md
2. AGENTS.md
3. docs/AGENT_HANDOFF.md

REPOSITORY:
Wonderadroit/Cydra_wonder

ACTIVE BRANCH:
research/arcadia-lending

MISSION:
Finish the current supervised public-code research milestone. CYDRA is an authorized security-research system. The objective is reproducible, non-obvious, evidence-backed findings—not a generic audit report.

DOCTRINE:
LLMs propose. Deterministic tools test. Evidence decides.

CRITICAL STATE:
- Maturity gate is CLOSED. Do not reopen it.
- Do not create Benchmark 051 merely to continue.
- Do not add Arcadia-specific heuristics.
- Keep all fixes generic and regression-tested.
- Treat reverts/UNAUTHORIZED/empty writes as execution failures, not vulnerabilities.
- Do not import historical Arcadia audit findings into the blind reasoning before the result is frozen.
- Do not touch live contracts or user funds/state.

YOUR OPERATING LOOP:
1. Inspect current branch head.
2. Inspect all current GitHub Actions check-runs and identify the latest research run.
3. If anything is running, inspect it repeatedly until every required job finishes. Do not stop at an intermediate state.
4. Download and inspect the final research artifact.
5. Verify classification, hypotheses, experiments, execution evidence, invariants, provenance, integrity/manifest, target checkout/intake, and compilation evidence.
6. Diagnose the largest generic execution-readiness blocker.
7. Fix it generically, add a focused regression, run the full relevant regression suite, and push the change.
8. Wait for CI.
9. Rerun the target-only research.
10. Compare artifacts before/after. The success metric is meaningful reachable evidence, not experiment count.
11. Repeat the diagnose → implement → test → CI → research → artifact-inspect cycle until the current blocker is genuinely resolved or the remaining blocker is proven external/unresolvable.
12. Update PROJECT_BIBLE.md and docs/AGENT_HANDOFF.md with the actual final state.

CURRENT TECHNICAL FRONTIER:
Execution readiness must discover and safely materialize:
- constructor dependencies
- modeled roles/callers
- runtime dependencies
- state prerequisites
- constructible state writers
- transitive call/data-flow producers
- safe setup verification

Do not merely detect a state writer. Prove that its prerequisites are themselves constructible/reachable before using it in a security experiment.

KNOWN RESEARCH ARTIFACT:
Previous successful research run: 35832346299
Artifact: cydra-arcadia-lending-public-code
Artifact ID: 10738051082
Digest: sha256:f5df0e3181d5e1aabdbdcc80f2eccfe2e4fd09a6de5086e53dad986a84e9d44e

KNOWN LAST-LONG-RUN STATE:
A later run was observed in progress around research run 35832626013. Do not assume it is still running; query current GitHub state.

SUCCESS CRITERIA:
- no unsupported finding
- deterministic/reproducible evidence
- generic capability improvements
- regression coverage
- final research artifact inspected
- final CI green
- remaining blockers understood and documented
- repository self-describing for the next chat/agent

DO NOT ASK THE USER TO REPEAT THE STATE. INSPECT THE REPO AND ACTIONS YOURSELF AND CONTINUE.
