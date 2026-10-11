from scripts.run_benchmark_006_blind_auth import _auth_modifier


def test_causal_auth_control_prefers_owner_guard_over_frequent_role_guard():
    source = """
    contract Fixture {
        address public owner;
        address public router;

        modifier onlyRouter() {
            require(msg.sender == router);
            _;
        }

        modifier onlyOwner {
            require(msg.sender == owner);
            _;
        }

        function mint(address to) public onlyRouter {}
        function burn(address from) public onlyRouter {}
        function mintByOwner(address to) public onlyOwner {}
        function burnByOwner(address from) public onlyOwner {}
        function setRouter(address next) public { router = next; }
    }
    """
    assert _auth_modifier(source) == "onlyOwner"


def test_causal_auth_control_fails_closed_without_owner_or_admin_guard():
    source = """
    contract Fixture {
        address public router;

        modifier onlyRouter() {
            require(msg.sender == router);
            _;
        }

        function mint(address to) public onlyRouter {}
        function burn(address from) public onlyRouter {}
        function setRouter(address next) public { router = next; }
    }
    """
    assert _auth_modifier(source) is None



def test_causal_auth_control_recognizes_delegated_owner_check():
    source = """
    contract Fixture {
        address public owner;
        address public router;

        modifier onlyRouter() {
            require(msg.sender == router);
            _;
        }

        modifier onlyOwner {
            _checkOwner();
            _;
        }

        function _checkOwner() internal view {
            require(msg.sender == owner);
        }

        function mint(address to) public onlyRouter {}
        function burnByOwner(address from) public onlyOwner {}
        function setRouter(address next) public { router = next; }
    }
    """
    assert _auth_modifier(source) == "onlyOwner"
