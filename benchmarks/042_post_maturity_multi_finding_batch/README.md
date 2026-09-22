# Benchmark 042 — Post-Maturity Multi-Finding Batch

This campaign tests the next capability boundary after Benchmark 041: whether CYDRA can discover and causally verify more than one distinct vulnerability on the same unfamiliar target.

The campaign is deliberately batch-shaped. Both independent findings are selected from one blind investigation before any historical answer, patch, exploit sequence, or finding identity is revealed to the reasoning engine. All causal controls are then executed in a batch so setup, representation, compiler, PoC, and classification failures accumulate in one artifact rather than being fixed one-at-a-time.

Target:
- code-423n4/2025-06-panoptic
- pinned ref eea2c931b1cbce1da01586e42ba298814de40d31
- source src/accountants/PanopticVaultAccountant.sol

Historical controls:
- H-01: paired premium subtraction order in `computeNAV`.
- H-02: per-pool non-linear clamping before a later underlying-balance addition.

The blind phase must discover both through the normal class-neutral reasoning surfaces:
- paired-output symmetry;
- aggregation-order reasoning.

The evaluator must then independently reproduce each finding against vulnerable and patched controls, plus independent vulnerable/patched reproductions.

Success requires:
1. at least two distinct blind hypotheses bind the two security-relevant computations;
2. each vulnerable control fails its independently authored invariant test;
3. each patched control passes;
4. independent reproductions agree for both findings;
5. the final artifact records two separate READY findings;
6. no historical finding details are available to the blind selector.

A single green CI result is insufficient. The batch is only READY when the evidence demonstrates two causally distinct findings on the same target.
