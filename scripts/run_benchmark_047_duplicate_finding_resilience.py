from dataclasses import dataclass

from cydra.impact_priority import FindingCollection


@dataclass(frozen=True)
class Finding:
    finding_id: str
    detail: str


def main() -> None:
    finding = Finding("F-047-1", "same evidence-backed finding")
    collection = FindingCollection("benchmark-047")
    collection = collection.add(finding)
    collection = collection.add(finding)
    assert len(collection.findings) == 1
    assert collection.findings[0] == finding

    try:
        collection.add(Finding("F-047-1", "conflicting content"))
    except ValueError as exc:
        assert "conflicting finding" in str(exc)
    else:
        raise AssertionError("conflicting finding identity must fail closed")

    print("Benchmark 047: PASS")
    print("exact_duplicate_count=1")
    print("conflicting_identity=rejected")


if __name__ == "__main__":
    main()
