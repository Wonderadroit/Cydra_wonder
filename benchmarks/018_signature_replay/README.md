# Benchmark 018 — execution-domain authorization

This unfamiliar-target regression studies whether a signed authorization is bound to the execution domain. The blind reasoning target is a historical multi-deployment signature-verification flow. The causal fixture uses two otherwise equivalent deployments and checks that one authorization cannot be accepted by both when the signed context is intended to be deployment-specific.

The historical issue is used only for post-run corroboration. The blind hypothesis is generated from the target source before the fixture is executed.
