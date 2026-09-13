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
