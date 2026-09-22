# Benchmark 044 — Post-Maturity Negative-Control Campaign

This campaign validates that evidence-backed execution does not promote structurally plausible but safe behavior into confirmed findings.

The controls are deliberately safe targets:
- authorization: a privileged-looking whitelist mutation is permanently blocked by target state;
- initialization: the deployment claims the privileged state before arbitrary initialization;
- temporal precondition: the patched target establishes the precondition before the external state-changing call.

Each control is investigated through the normal reasoning surface, rendered by the generic Foundry generators, and executed. A safe control must produce an executed PASS result for the security assertion. No benchmark answer, exploit sequence, or target-specific selector is supplied to the reasoning engine.

The campaign is a false-positive resistance gate, not a discovery benchmark. A failure is evidence that CYDRA needs diagnosis before production readiness can advance.
