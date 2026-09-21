    return tuple(names)


def _project_root(path: Path) -> Path:
    """Find the project root used by interface resolution.

    A repository remappings file is authoritative when present. Small
    standalone fixtures without remappings use the directory containing the
    Solidity file, preserving the existing parser call shape.
    """
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / "remappings.txt").is_file() or (parent / "foundry.toml").is_file():
            return parent
    return resolved.parent


def _constructor_interface_casts(
    body: str,
    parameters: tuple[ParameterModel, ...],
    *,
    importer: Path,
    root: Path,
) -> tuple[
    tuple[tuple[str, str], ...],
    tuple[tuple[str, ResolvedInterface], ...],