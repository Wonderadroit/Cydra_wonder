# Benchmark 027 — iterative strict-blind control-flow research loop

This benchmark tests the missing generic research-loop behavior exposed by Benchmark 026.

The first selection is performed by the normal class-neutral selector with no vulnerability class, target function, state surface, reasoning injection, exploit sequence, or answer. CYDRA executes the hypothesis it selected. If the measured initialization experiment does not confirm that hypothesis, the hypothesis is excluded through the generic reselection API and CYDRA selects the next hypothesis.

The second selection must independently reach the control-flow hypothesis. Only after that blind selection does the benchmark execute the real pinned Venus target, an isolated causal control, and independent vulnerable/patched reproductions.

This benchmark therefore tests:
1. blind hypothesis selection;
2. execution of the selected hypothesis;
3. evidence-driven rejection of a non-confirming candidate;
4. generic reselection;
5. causal verification of the newly selected hypothesis;
6. independent reproduction and finding-gate promotion.

A failure to reach the control-flow hypothesis after the measured first-round rejection is a research-loop failure, not a reason to add target-specific ranking.
