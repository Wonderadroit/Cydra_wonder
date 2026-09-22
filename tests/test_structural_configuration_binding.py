from pathlib import Path

from cydra.configuration_binding_planning import plan_configuration_binding_experiment
from cydra.models import ContractModel, FunctionModel, Hypothesis
from cydra.structural_configuration_binding import (
    configuration_binding_invariant,
    generate_configuration_binding_hypotheses,
)


def _contract(tmp_path: Path, source: str) -> ContractModel:
    path = tmp_path / "Target.sol"
    path.write_text(source, encoding="utf-8")
    return ContractModel(
        name="Target",
        source=str(path),
        functions=(FunctionModel("claim", "external", (), (), (), 1),),
    )


def test_detects_unvalidated_keyed_configuration(tmp_path):
    contract = _contract(
        tmp_path,
        """
        struct Setting { uint8 split; bytes4 transfer; }
        struct State { mapping(address => Setting) settings; }
        library Target {
            function claim(State storage self, address revenue) external {
                uint256 amount = 100;
                uint256 owner = amount * self.settings[revenue].split / 100;
                if (owner != 0) revert("x");
            }
        }
        """,
    )
    invariant = configuration_binding_invariant(contract)
    hypotheses = generate_configuration_binding_hypotheses(contract)
    assert invariant is not None
    assert invariant.invariant_id == "INV-CONFIG-BINDING-001"
    assert len(hypotheses) == 1
    assert hypotheses[0].target_function == "claim"


def test_does_not_flag_guarded_keyed_configuration(tmp_path):
    contract = _contract(
        tmp_path,
        """
        struct Setting { uint8 split; bytes4 transfer; }
        struct State { mapping(address => Setting) settings; }
        library Target {
            function claim(State storage self, address revenue) external {
                require(self.settings[revenue].transfer != bytes4(0));
                uint256 amount = 100;
                uint256 owner = amount * self.settings[revenue].split / 100;
            }
        }
        """,
    )
    assert configuration_binding_invariant(contract) is None
    assert generate_configuration_binding_hypotheses(contract) == ()


def test_configuration_binding_planner_emits_structured_executable_step():
    hypothesis = Hypothesis(
        hypothesis_id="H-CONFIG-BINDING-claim-settings",
        invariant_id="INV-CONFIG-BINDING-001",
        target_function="claim",
        claim="unregistered configuration may be accepted",
        attacker_capability="choose an unregistered key",
        expected_impact="default configuration affects effectful execution",
    )
    experiment = plan_configuration_binding_experiment(hypothesis)
    assert len(experiment.steps) == 1
    assert experiment.steps[0].function == "claim"
    assert experiment.steps[0].arguments == ()
