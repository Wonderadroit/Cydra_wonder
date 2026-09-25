from pathlib import Path

from cydra.initialization_deployment import inspect_deployment_surface


def test_explicit_proxy_implementation_and_initializer_forwarding_form_a_route(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "AccountV1.sol").write_text(
        "contract AccountV1 { function initialize(address owner) external {} }",
        encoding="utf-8",
    )
    (src / "Proxy.sol").write_text(
        """
contract AccountProxy {
    address public implementation;
    constructor(address implementation_) { implementation = implementation_; }
    fallback() external payable {
        assembly {
            calldatacopy(0, 0, calldatasize())
            let ok := delegatecall(gas(), implementation, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            if iszero(ok) { revert(0, returndatasize()) }
            return(0, returndatasize())
        }
    }
    function forward(bytes calldata data) external {
        (bool ok,) = implementation.delegatecall(data);
        require(ok);
    }
}
""",
        encoding="utf-8",
    )
    (src / "Factory.sol").write_text(
        """
contract Factory {
    function create() external returns (address) {
        AccountProxy proxy = new AccountProxy(address(accountImplementation));
        return address(proxy);
    }
    address accountImplementation;
}
""".replace("accountImplementation", "AccountV1"),
        encoding="utf-8",
    )

    surface = inspect_deployment_surface(tmp_path)

    assert surface.proxy_contracts == ("AccountProxy",)
    assert any(item.implementation_contract == "AccountV1" for item in surface.implementation_links)
    assert any(item.proxy_contract == "AccountProxy" for item in surface.initializer_forwarding)
    assert surface.has_explicit_route("AccountV1")


def test_proxy_without_explicit_implementation_link_is_not_a_route(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "AccountV1.sol").write_text(
        "contract AccountV1 { function initialize() external {} }",
        encoding="utf-8",
    )
    (src / "Proxy.sol").write_text(
        """
contract AccountProxy {
    address public implementation;
    fallback() external payable {
        (bool ok,) = implementation.delegatecall(msg.data);
        require(ok);
    }
}
""",
        encoding="utf-8",
    )

    surface = inspect_deployment_surface(tmp_path)

    assert surface.proxy_contracts == ("AccountProxy",)
    assert surface.implementation_links == ()
    assert not surface.has_explicit_route("AccountV1")


def test_ordinary_delegatecall_is_not_promoted_to_proxy_evidence(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Executor.sol").write_text(
        """
contract Executor {
    function execute(address target, bytes calldata data) external {
        (bool ok,) = target.delegatecall(data);
        require(ok);
    }
}
""",
        encoding="utf-8",
    )

    surface = inspect_deployment_surface(tmp_path)

    assert surface.evidence == ()
