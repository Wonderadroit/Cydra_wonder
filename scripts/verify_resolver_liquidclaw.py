from __future__ import annotations

from pathlib import Path
import re
import sys

from cydra.interface_resolver import resolve_interface


IMPORT_RE = re.compile(
    r'\bimport\s+(?:\{([^}]+)\}\s+from\s+)?"([^"]+)"\s*;',
    re.MULTILINE,
)


def imported_interfaces(source: Path) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for symbols, import_path in IMPORT_RE.findall(source.read_text(encoding="utf-8")):
        if not symbols:
            continue
        for symbol in symbols.split(","):
            name = symbol.strip().split(" as ", 1)[0].strip()
            if name.startswith("I"):
                result.append((name, import_path))
    return result


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "liquidclaw").resolve()
    targets = (
        "contracts/Pool.sol",
        "contracts/Minter.sol",
        "contracts/Voter.sol",
    )

    print(f"LIQUIDCLAW ROOT: {root}")
    print("FROZEN REF: 58bed220236e8cdd8d279ef7259b3298a71aac0b")

    failures = 0
    for relative in targets:
        target = root / relative
        print(f"\nTARGET: {relative}")
        imports = imported_interfaces(target)
        seen: set[str] = set()
        for name, import_path in imports:
            if name in seen:
                continue
            seen.add(name)
            print(f"IMPORT: {name} <- {import_path}")
            try:
                resolved = resolve_interface(root, target, name)
            except Exception as exc:
                failures += 1
                print(f"RESOLUTION ERROR: {type(exc).__name__}: {exc}")
                continue

            print(f"{resolved.name}:")
            print(f"  source: {resolved.source_path}")
            print(f"  method: {resolved.resolution_method}")
            print("  methods:")
            for method in resolved.methods:
                parameters = ", ".join(method.parameters)
                returns = ", ".join(method.returns)
                print(f"    {method.name}({parameters}) -> ({returns})")

    print(f"\nRESOLVER VERIFICATION: {'PASS' if failures == 0 else 'FAIL'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
