# Benchmark 044 — Post-Maturity Negative Controls

Benchmark 044 stress-tests the finding boundary after maturity closure.

The campaign uses the same two unfamiliar-target mechanisms exercised by Benchmark 043, but executes the selected hypotheses only against their patched counterfactual controls:

- RabbitHole Quest Protocol — authorization boundary on `mint`;
- Debt DAO Line of Credit — keyed configuration binding on `claimRevenue`.

The blind stage is still run without a vulnerability class, target function, exploit sequence, patch, historical answer, or selector override. The known mechanism is used only after blind selection to bind the selected hypothesis to its safe counterfactual.

Acceptance requires:

1. blind selection completes;
2. the selected hypothesis is the expected blind hypothesis;
3. the patched control executes successfully;
4. the patched control does not reproduce the vulnerable differential;
5. the finding gate remains `NOT_READY`;
6. no causal verification is claimed;
7. the blind boundary remains preserved.

This is a false-positive/negative-control campaign, not a new vulnerability claim. A passing result means CYDRA did **not** promote the patched counterfactual to a finding under this campaign.

The maturity/generalization gate remains closed.
