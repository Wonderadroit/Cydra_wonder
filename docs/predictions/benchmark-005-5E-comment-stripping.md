# Prediction 5E — Comment-stripping pre-pass for Solidity source

## Prediction

Adding a comment-stripping pre-pass to `solidity_model.py`, applied before `_CONTRACT_RE` and the function regex, will eliminate the phantom `contract address` match in `Voter.sol` while preserving the correct contract boundaries in `Pool.sol` and `Minter.sol`.

On the frozen LiquidClaw target:

- Voter functions will contain `initialize`.
- Pool functions and Minter functions will be unchanged.
- Benchmarks 001, 002, and 003 outputs will be unchanged.
- The compile gate will reach Foundry compilation for all three initializer tests.

## Falsification conditions

- Phantom `address` contract still appears in Voter parse output → comment stripping did not remove the offending comment, or the pre-pass is not applied before the regex.
- Voter functions present but Pool or Minter functions changed → comment stripping damaged legitimate source.
- Line numbers or function attribution spans shift incorrectly → comment stripping replaced content without preserving offsets.
- Any of 001/002/003 produce different hypotheses, experiments, or classifications → regression; stop and inspect what the comment stripper did to the fixture sources.
- Compile gate fails after parse succeeds → a different boundary was hiding behind this one; capture and classify separately.

## Regression precondition

Before running LiquidClaw, Benchmarks 001, 002, and their negative controls must produce identical output, and Benchmark 003 must reach its previous harness boundary unchanged. Any divergence is a regression and must be investigated before continuing.

## Scope

Only `src/cydra/solidity_model.py` is to be changed. The helper may be named `_strip_comments(source: str) -> str` and must be applied at the top of `parse_solidity()` before `_CONTRACT_RE`, `_FUNCTION_RE`, and `_CONSTRUCTOR_RE` are iterated.

Comment rules:

1. Remove single-line comments beginning with `//`, including `///` and `//!`, through the newline.
2. Remove block comments from `/*` through `*/`, including multi-line NatSpec.
3. Preserve line numbers and source offsets by replacing removed comment characters with whitespace while retaining newlines.
4. Do not remove string literals in this change; string handling is a separate failure mode/prediction.

The contract regex remains unchanged. No changes are permitted to `foundry.py`, `reasoning.py`, `models.py`, benchmark fixtures, or classifier logic.
