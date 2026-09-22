# Benchmark 048 — post-maturity research-loop duplicate integration

This benchmark exercises duplicate finding handling through the real generic research loop rather than calling the collection primitive directly.

The loop emits the same finding identity on two confirmed observations. Acceptance requires one retained finding and no orchestration exception.

This validates that repeated identical evidence-backed promotion is safe at the loop boundary. It does not classify a vulnerability or encode a target-specific answer.
