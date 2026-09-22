"""Run the post-maturity resilience controls as one auditable batch campaign."""

from __future__ import annotations

import subprocess
import sys


CASES = (
    ("046-unmeasurable-resilience", "scripts/run_benchmark_046_unmeasurable_resilience.py"),
    ("047-duplicate-finding-resilience", "scripts/run_benchmark_047_duplicate_finding_resilience.py"),
    ("048-research-loop-duplicate-integration", "scripts/run_benchmark_048_research_loop_duplicate_integration.py"),
    ("048-unmeasurable-exhaustion", "scripts/run_benchmark_048_unmeasurable_exhaustion.py"),
)


def main() -> int:
    results: list[tuple[str, str]] = []
    for name, path in CASES:
        completed = subprocess.run(
            [sys.executable, path],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            results.append((name, "PASS"))
        else:
            print(completed.stdout, end="")
            print(completed.stderr, end="", file=sys.stderr)
            results.append((name, "FAIL"))

    print({"campaign": "049-post-maturity-hardening", "results": results})
    return 0 if all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
