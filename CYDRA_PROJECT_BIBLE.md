# CYDRA — PROJECT BIBLE

**Status:** Constitutional / governing document  
**Purpose:** Defines what CYDRA is, what it is not, how it reasons, and how every future change must be evaluated.

---

# 1. CYDRA'S PURPOSE

CYDRA is a **security reasoning engine for authorized security research**.

Its purpose is not primarily to recognize known vulnerability patterns.

Its purpose is to:

> **Understand a system deeply enough to identify potentially violated behavioral invariants, construct competing explanations, design information-gain experiments, establish causality where possible, preserve uncertainty where causality cannot be established, and produce reproducible security findings.**

CYDRA exists to help a researcher understand **why a system behaves the way it does**, not merely identify that a piece of code resembles a known vulnerability.

# 2. THE CENTRAL PHILOSOPHY

## Understand systems rather than memorize vulnerabilities.

A vulnerability class is not the system.

A pattern is not a finding.

A suspicious function is not a vulnerability.

A failing test is not automatically a vulnerability.

A passing test is not automatically proof of safety.

CYDRA must reason from:

**system behavior → evidence → relationships → invariants → hypotheses → experiments → observations → causal explanation → finding**

rather than:

**known vulnerability → pattern match → assertion → finding**

# 3. WHAT CYDRA IS NOT

CYDRA is not:

- a conventional static vulnerability scanner;
- a collection of vulnerability signatures;
- an audit/compliance checklist;
- an oracle that matches benchmark answers;
- a system that assumes every anomaly is exploitable;
- a system that treats a suspicious signal as proof of a root cause;
- a system that treats code style or naming conventions as security truth;
- a system that equates test failure with vulnerability confirmation;
- a system that equates test success with security confirmation;
- a system that requires a patched counterpart before it can reason;
- a system that hides uncertainty behind binary classifications;
- a system whose architecture is optimized merely to pass synthetic benchmarks.

Benchmarks are evidence about CYDRA.

They are not CYDRA's identity.

# 4. AUTHORIZED USE ONLY

CYDRA is for authorized security research, including bug-bounty programs, authorized assessments, controlled research targets, local reproductions, historical vulnerability datasets, and synthetic fixtures used to validate CYDRA itself.

# 5. THE CYDRA REASONING MODEL

The canonical reasoning architecture is:

```text
EVIDENCE
   ↓
CORRELATION
   ↓
UNCERTAINTY
   ↓
CAUSALITY
   ↓
TEST PLANNING
   ↓
HYPOTHESIS UPDATING
   ↓
SYSTEM MODEL
   ↓
FINDING
```

This defines how CYDRA is supposed to think.

# 6. EVIDENCE

CYDRA begins with evidence: source code, structure, call relationships, state transitions, modifiers, storage relationships, control flow, external calls, configuration, historical behavior, execution traces, generated tests, runtime behavior, build information, historical findings, negative controls, and regression results.

Evidence must retain provenance. CYDRA must distinguish **observed evidence** from **inferred interpretation** and never silently convert inference into fact.

# 7. CORRELATION IS NOT CAUSATION

CYDRA must distinguish “these things are related” from “this mechanism caused this behavior.” Relationships generate hypotheses. Experiments establish causality.

# 8. SYSTEM MODEL

The most important internal object in CYDRA is the **system model**.

CYDRA should reconstruct what the system is intended to do, which actors exist, what authority each actor has, which state each actor can change, how state changes propagate, which invariants connect those states, which mechanisms enforce them, which assumptions exist, and where evidence conflicts with those assumptions.

The system model must remain revisable.

# 9. INVARIANTS

An invariant expresses a behavioral or structural property CYDRA believes should hold. It must have a clear statement, supporting evidence, provenance, confidence/uncertainty, and a relationship to relevant system behavior.

An invariant is a proposition to be tested and potentially falsified, not an automatically true fact.

CYDRA should prefer **system-derived invariants** over hard-coded vulnerability-class rules.

# 10. HYPOTHESES

A hypothesis is a falsifiable explanation. It should identify the suspected mechanism, relevant state, actor/capability, expected behavior, suspected deviation, related invariant, supporting evidence, and alternative explanations where relevant.

A hypothesis remains a hypothesis until evidence supports an upgrade in confidence.

# 11. COMPETING HYPOTHESES

CYDRA should preserve multiple explanations when the evidence permits them rather than committing to the first plausible explanation.

# 12. INFORMATION-GAIN TESTING

CYDRA should choose experiments because they reduce uncertainty.

The question is not “What test can I generate?” but **“What experiment most efficiently distinguishes the competing explanations?”**

A useful experiment has a hypothesis, expected observations, competing outcomes, a reason it is informative, and a clear interpretation boundary.

# 13. CAUSAL VERIFICATION

CYDRA should seek a chain from system condition → specific mechanism → actor/action → state transition → security-relevant consequence.

Where possible it should establish the triggering condition, causal mechanism, resulting state change, security impact, and reproducibility.

# 14. EXECUTION IS EVIDENCE, NOT TRUTH

Foundry or other execution infrastructure is an experimental instrument.

**PASS ≠ secure** and **FAIL ≠ vulnerable**.

A result must be interpreted in the context of the experiment that produced it. A generated test that does not exercise the hypothesized mechanism is not valid causal evidence even if it passes.

# 15. EXECUTION FAILURE MUST PRESERVE KNOWLEDGE

Compiler incompatibility, missing dependencies, environment failure, unsupported targets, infrastructure failure, or incomplete instrumentation mean **“the hypothesis could not be tested,”** not “the hypothesis is false” or “the system is safe.”

Execution failure creates an epistemic boundary. It must not erase valid model-level evidence.

# 16. UNCERTAINTY IS A FIRST-CLASS OUTPUT

CYDRA must be comfortable saying unknown, not tested, insufficient evidence, execution blocked, competing hypotheses remain, or causality not established.

**Unsupported certainty is worse than uncertainty.**

# 17. CLASSIFICATION

Classification is a conclusion produced after evidence has been evaluated. It must not reduce to test-pass/test-fail semantics.

A useful conceptual progression is:

**PROPOSED → SUPPORTED → EXPERIMENTALLY SUPPORTED → CAUSALLY ESTABLISHED → FINDING**

The exact implementation may evolve, but the epistemic distinction must remain.

# 18. PATCHED VERSIONS

A patched counterpart is useful differential and regression evidence, but it is **not a prerequisite for reasoning**. CYDRA must be able to investigate a blind target and clearly state when available evidence is insufficient for final classification.

# 19. HISTORICAL BENCHMARKS

Historical vulnerabilities are used to test CYDRA's reasoning, not to memorize answers.

The benchmark is an external reference against which independently derived reasoning is compared. CYDRA must not be built to reproduce benchmark labels by pattern matching.

# 20. NEGATIVE CONTROLS

Negative controls test whether CYDRA distinguishes suspicion from security-relevant causality. A system that reports every suspicious pattern is not reasoning correctly.

# 21. REGRESSION

Meaningful improvements must preserve previously established behavior unless an intentional philosophical change is made. Test positive cases, negative controls, execution-blocked cases, competing-hypothesis cases, historical benchmarks, and determinism where applicable.

# 22. ADVERSARIAL SELF-TESTING

CYDRA must ask how it could fool itself: naming-based false hypotheses, bypassed authorization paths, tests exercising the wrong state, benchmark leakage, suppressed alternatives, erased static understanding, compatibility fixtures becoming accidental subjects, and classifier assumptions about patches.

# 23. MULTI-HYPOTHESIS REASONING

One target may produce multiple hypotheses. Each retains its own evidence, invariant, experiment, execution, observations, confidence, and classification state.

Multiplicity is not the philosophical goal; preserving multiple plausible explanations when warranted is.

# 24. VULNERABILITY CLASSES ARE LENSES, NOT THE ONTOLOGY

Authorization, initialization, arithmetic, accounting, reentrancy, oracle manipulation, and other categories are research lenses, not CYDRA's fundamental ontology.

The system model comes first. A real vulnerability may cross categories or fit none cleanly.

# 25. SYNTHETIC FIXTURES

Synthetic fixtures may validate infrastructure such as multi-hypothesis handling, evidence preservation, competing-hypothesis representation, and execution association. They must not be treated as evidence that CYDRA understands real-world security behavior.

# 26. BENCHMARK ACCEPTANCE

Every benchmark must define its research question, prediction, available evidence, legitimate hypotheses, falsifying observations, uncertainty conditions, finding criteria, and what would falsify CYDRA's reasoning. Predictions must be written before the relevant run.

# 27. PROVENANCE

Important results must identify target, target revision, CYDRA revision, runner revision where relevant, configuration, generated artifacts, experiment identity, execution environment, and relevant evidence.

Behavioral evidence and provenance metadata must be distinguished.

# 28. FROZEN VALIDATION INFRASTRUCTURE

When a runner or harness is frozen, it is the experimental instrument. Do not casually modify it during an experiment designed to measure it. Record gaps, classify them, preserve evidence, decide whether they are runner or reasoning issues, and repair separately if justified.

# 29. ENGINEERING PRIORITY

Every new component must answer:

> **Which part of CYDRA's reasoning does this improve?**

If the answer is unclear, do not build it.

Priority:

1. preserve the philosophy;
2. establish real evidence;
3. improve reasoning quality;
4. improve causal verification;
5. preserve uncertainty;
6. validate against real historical cases;
7. improve reproducibility;
8. optimize architecture and convenience.

# 30. THE CYDRA DEVELOPMENT LOOP

```text
1. STATE THE QUESTION
        ↓
2. STATE THE PREDICTION
        ↓
3. IDENTIFY AVAILABLE EVIDENCE
        ↓
4. RUN CYDRA
        ↓
5. OBSERVE WHAT CYDRA ACTUALLY DID
        ↓
6. COMPARE AGAINST THE PREDICTION
        ↓
7. IDENTIFY WHAT WAS LEARNED
        ↓
8. IDENTIFY WHAT REMAINS UNKNOWN
        ↓
9. UPDATE THE SYSTEM MODEL
        ↓
10. DECIDE THE NEXT INFORMATION-GAIN ACTION
```

The next action follows from what was learned, not from a desire to keep adding features.

# 31. THE MOST IMPORTANT RULE

Before implementing any proposed change, ask:

> **Does this make CYDRA better at understanding systems and establishing causal security claims, or does it merely make CYDRA better at passing tests?**

If it is only the latter, it is not automatically worth doing.

# 32. DECISION HIERARCHY

When there is a conflict:

**CYDRA philosophy → epistemic correctness → research question → evidence integrity → causal validity → reproducibility → engineering convenience**

Engineering convenience never overrides epistemic correctness. Benchmark convenience never overrides the research question. A passing test never overrides evidence provenance. A known vulnerability pattern never overrides system understanding.

# 33. CURRENT INTERPRETATION OF THE PROJECT

CYDRA should ultimately behave like a researcher who can say:

> “Here is what I know.”
>
> “Here is how those observations relate.”
>
> “Here is the invariant I believe should hold.”
>
> “Here are the explanations consistent with the evidence.”
>
> “Here is the experiment that best distinguishes them.”
>
> “Here is what happened.”
>
> “This evidence supports this explanation.”
>
> “This alternative explanation is now less likely.”
>
> “This remains uncertain because I could not establish causality.”
>
> “Here is the reproducible security consequence.”

That is CYDRA: **a security reasoning engine, not a scanner, oracle, or benchmark-answer matcher.**

# 34. GOVERNANCE RULE

This Bible is the governing reference for CYDRA development.

Before any future feature, refactor, benchmark, experiment, architecture change, classifier, generator, heuristic, or validation check, ask:

### “Which part of the CYDRA Project Bible justifies this?”

If there is no clear answer, stop and reassess.

If an implementation contradicts the Bible, **the implementation is presumed wrong until the philosophy itself is deliberately reconsidered.**

The project must never silently drift again.

# CYDRA'S ONE-SENTENCE DEFINITION

> **CYDRA is an authorized security-research reasoning engine that reconstructs system behavior, preserves uncertainty, generates and tests competing causal hypotheses, and produces reproducible security findings only when the evidence justifies them.**
