from importlib.util import module_from_spec, spec_from_file_location


def _runner_module():
    spec = spec_from_file_location("run_benchmark_005_blind", "scripts/run_benchmark_005_blind.py")
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Contract:
    def __init__(self, source):
        self.source = str(source)


def test_blind_initializer_replaces_address_zero_when_target_explicitly_rejects_it(tmp_path):
    runner = _runner_module()
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;\ncontract Target {\n"
        "function initialize(address _loanProtocol) external {\n"
        "if (_loanProtocol == address(0)) revert();\n"
        "}\n}\n""",
        encoding="utf-8",
    )
    generated = tmp_path / "generated.t.sol"
    generated.write_text("target.initialize(address(0));\n", encoding="utf-8")

    runner._harden_generated_initializer_arguments(generated, Contract(source), "initialize")

    assert "address(cydraDependency)" in generated.read_text(encoding="utf-8")


def test_blind_initializer_preserves_zero_when_no_explicit_zero_guard(tmp_path):
    runner = _runner_module()
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;\ncontract Target {\n"
        "function initialize(address _recipient) external { recipient = _recipient; }\n"
        "address recipient;\n}\n""",
        encoding="utf-8",
    )
    generated = tmp_path / "generated.t.sol"
    generated.write_text("target.initialize(address(0));\n", encoding="utf-8")

    runner._harden_generated_initializer_arguments(generated, Contract(source), "initialize")

    assert generated.read_text(encoding="utf-8") == "target.initialize(address(0));\n"

def test_blind_initializer_replaces_address_zero_when_common_nonzero_helper_is_used(tmp_path):
    runner = _runner_module()
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract Target {
    function initialize(address _staderConfig) external {
        UtilLib.checkNonZeroAddress(_staderConfig);
    }
}
library UtilLib {
    function checkNonZeroAddress(address value) internal pure {
        if (value == address(0)) revert();
    }
}
""",
        encoding="utf-8",
    )
    generated = tmp_path / "generated.t.sol"
    generated.write_text("target.initialize(address(0));\n", encoding="utf-8")

    runner._harden_generated_initializer_arguments(generated, Contract(source), "initialize")

    assert "address(cydraDependency)" in generated.read_text(encoding="utf-8")

def test_blind_initializer_adds_generic_dependency_probe_for_guarded_address(tmp_path):
    runner = _runner_module()
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract Target {
    address config;
    function initialise(address _staderConfig) external {
        UtilLib.checkNonZeroAddress(_staderConfig);
        config = _staderConfig;
    }
}
library UtilLib {
    function checkNonZeroAddress(address value) internal pure {
        if (value == address(0)) revert();
    }
}
""",
        encoding="utf-8",
    )
    generated = tmp_path / "generated.t.sol"
    generated.write_text(
        """contract CydraInitializationInvariantTest is Test {
    Target internal target;
    function setUp() public { target = new Target(); }
    function testInitializationInterfaceIsCallable() public {
        target.initialise(address(0));
    }
}
""",
        encoding="utf-8",
    )
    runner._harden_generated_initializer_arguments(generated, Contract(source), "initialise")
    rendered = generated.read_text(encoding="utf-8")
    assert "contract CydraInitializerDependencyProbe" in rendered
    assert "CydraInitializerDependencyProbe internal cydraDependency;" in rendered
    assert "cydraDependency = new CydraInitializerDependencyProbe();" in rendered
    assert "target.initialise(address(cydraDependency));" in rendered
