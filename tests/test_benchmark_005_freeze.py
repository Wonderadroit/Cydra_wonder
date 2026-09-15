from pathlib import Path

from scripts.run_benchmark_005_blind import FREEZE_FILES, GENERATED_MANIFEST, manifest


def test_compilation_log_is_part_of_frozen_integrity_manifest(tmp_path: Path):
    for name in FREEZE_FILES:
        if name != GENERATED_MANIFEST:
            (tmp_path / name).write_text(name, encoding="utf-8")
    entries = manifest(tmp_path)
    assert "compilation.log" in {entry.split("  ", 1)[1] for entry in entries}
