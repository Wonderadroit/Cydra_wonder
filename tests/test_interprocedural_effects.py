from pathlib import Path

from cydra.solidity_model import parse_solidity
from cydra.solidity_system_model import project_contracts


def test_internal_call_and_effective_write_composition(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        contract Target {
            uint256 counter;
            uint256 other;

            function entry() external {
                _mutate();
            }

            function _mutate() internal {
                counter += 1;
            }

            function unrelated() external {
                other = 1;
            }
        }
        """,
        encoding="utf-8",
    )

    contract = parse_solidity(source)[0]
    entry = next(f for f in contract.functions if f.name == "entry")
    mutate = next(f for f in contract.functions if f.name == "_mutate")

    assert entry.internal_calls == ("_mutate",)
    assert mutate.internal_calls == ()
    assert entry.writes == ()
    assert mutate.writes == ("counter",)
    assert entry.effective_writes == ("counter",)
    assert mutate.effective_writes == ("counter",)

    system = project_contracts((contract,))
    entry_id = f"function:{contract.source}:{contract.name}:entry()"
    mutate_id = f"function:{contract.source}:{contract.name}:_mutate()"
    counter_id = f"state:{contract.source}:{contract.name}:counter"
    assert any(
        edge.source == entry_id and edge.relation == "internal_call" and edge.target == mutate_id
        for edge in system.edges
    )
    assert any(
        edge.source == entry_id and edge.relation == "writes" and edge.target == counter_id
        for edge in system.edges
    )


def test_internal_effect_summary_is_cycle_safe(tmp_path: Path):
    source = tmp_path / "Cycle.sol"
    source.write_text(
        """
        contract Cycle {
            uint256 a;
            uint256 b;

            function first() external {
                second();
                a = 1;
            }

            function second() internal {
                b = 1;
                first();
            }
        }
        """,
        encoding="utf-8",
    )

    contract = parse_solidity(source)[0]
    first = next(f for f in contract.functions if f.name == "first")
    second = next(f for f in contract.functions if f.name == "second")

    assert first.internal_calls == ("second",)
    assert second.internal_calls == ("first",)
    assert first.effective_writes == ("a", "b")
    assert second.effective_writes == ("a", "b")


def test_member_calls_do_not_become_internal_edges(tmp_path: Path):
    source = tmp_path / "Boundary.sol"
    source.write_text(
        """
        contract Boundary {
            uint256 value;

            function transfer() internal {
                value = 1;
            }

            function run(address token) external {
                token.transfer();
            }
        }
        """,
        encoding="utf-8",
    )

    contract = parse_solidity(source)[0]
    run = next(f for f in contract.functions if f.name == "run")

    assert run.internal_calls == ()
    assert run.external_calls == (("token", "transfer"),)
    assert run.effective_writes == ()
