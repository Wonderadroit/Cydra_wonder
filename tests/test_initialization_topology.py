from cydra.initialization_topology import adapt_generated_initialization_for_proxy, requires_proxy_initialization


IMPLEMENTATION = '''
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
contract ListingService is Initializable {
    constructor() { _disableInitializers(); }
    function initialize(address _loanProtocol) external initializer {}
}
'''


def test_requires_proxy_only_when_implementation_disables_initializers():
    assert requires_proxy_initialization(IMPLEMENTATION)
    assert not requires_proxy_initialization('contract Safe { function initialize() external {} }')


def test_adaptation_preserves_constructor_arguments_and_proxy_storage_boundary():
    generated = '''
import {Test} from "forge-std/Test.sol";
contract CydraInitializationInvariantTest is Test {
    ListingService internal target;
    function setUp() public {
        target = new ListingService(address(0x1234));
    }
    function testInitializationInterfaceIsCallable() public {
        target.initialize(address(0x1234));
    }
}
'''
    adapted = adapt_generated_initialization_for_proxy(generated, "ListingService")
    assert "ListingService internal implementation;" in adapted
    assert "implementation = new ListingService(address(0x1234));" in adapted
    assert "target = ListingService(address(proxy));" in adapted
    assert "contract CydraDelegateProxy" in adapted
    assert "delegatecall(gas(), implementation_" in adapted
    assert "target = new ListingService(address(0x1234));" not in adapted


def test_adaptation_is_idempotent():
    generated = '''
contract CydraInitializationInvariantTest is Test {
    ListingService internal target;
    function setUp() public { target = new ListingService(address(0x1234)); }
}
'''
    once = adapt_generated_initialization_for_proxy(generated, "ListingService")
    twice = adapt_generated_initialization_for_proxy(once, "ListingService")
    assert twice == once


def test_requires_proxy_follows_imported_base_constructor(tmp_path):
    root = tmp_path / "target"
    contracts = root / "contracts"
    lib = root / "lib" / "openzeppelin-contracts-upgradeable" / "contracts" / "proxy" / "utils"
    contracts.mkdir(parents=True)
    lib.mkdir(parents=True)
    (contracts / "LoanProtocol.sol").write_text(
        'import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";\n'
        'contract LoanProtocol is Initializable { function initialize() external initializer {} }\n',
        encoding="utf-8",
    )
    (lib / "Initializable.sol").write_text(
        "abstract contract Initializable {\n"
        "    function _disableInitializers() internal {}\n"
        "    constructor() { _disableInitializers(); }\n"
        "}\n",
        encoding="utf-8",
    )
    assert requires_proxy_initialization(contracts / "LoanProtocol.sol")


def test_requires_proxy_does_not_treat_library_function_definition_as_disable_signal(tmp_path):
    root = tmp_path / "target"
    contracts = root / "contracts"
    lib = root / "lib" / "openzeppelin-contracts-upgradeable" / "contracts" / "proxy" / "utils"
    contracts.mkdir(parents=True)
    lib.mkdir(parents=True)
    (contracts / "Safe.sol").write_text(
        'import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";\n'
        'contract Safe is Initializable { function initialize() external initializer {} }\n',
        encoding="utf-8",
    )
    (lib / "Initializable.sol").write_text(
        "abstract contract Initializable {\n"
        "    function _disableInitializers() internal {}\n"
        "}\n",
        encoding="utf-8",
    )
    assert not requires_proxy_initialization(contracts / "Safe.sol")



def test_supports_initializer_disable_follows_reachable_definition(tmp_path):
    root = tmp_path / "target"
    contracts = root / "contracts"
    lib = root / "lib" / "openzeppelin-contracts-upgradeable" / "contracts" / "proxy" / "utils"
    contracts.mkdir(parents=True)
    lib.mkdir(parents=True)
    (contracts / "LoanProtocol.sol").write_text(
        'import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";\n'
        'contract LoanProtocol is Initializable { function initialize() external initializer {} }\n',
        encoding="utf-8",
    )
    (lib / "Initializable.sol").write_text(
        "abstract contract Initializable {\n"
        "    function _disableInitializers() internal {}\n"
        "}\n",
        encoding="utf-8",
    )
    from cydra.initialization_topology import supports_initializer_disable
    assert supports_initializer_disable(contracts / "LoanProtocol.sol")



def test_requires_proxy_resolves_openzeppelin_from_node_modules(tmp_path):
    root = tmp_path / "target"
    contracts = root / "contracts"
    lib = root / "node_modules" / "@openzeppelin" / "contracts-upgradeable" / "proxy" / "utils"
    contracts.mkdir(parents=True)
    lib.mkdir(parents=True)
    (contracts / "LoanProtocol.sol").write_text(
        'import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";\n'
        'contract LoanProtocol is Initializable { function initialize() external initializer {} }\n',
        encoding="utf-8",
    )
    (lib / "Initializable.sol").write_text(
        "abstract contract Initializable {\n"
        "    function _disableInitializers() internal {}\n"
        "}\n",
        encoding="utf-8",
    )
    from cydra.initialization_topology import supports_initializer_disable
    assert supports_initializer_disable(contracts / "LoanProtocol.sol")
