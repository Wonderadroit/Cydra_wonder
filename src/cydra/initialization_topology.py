from __future__ import annotations

from pathlib import Path
import re


_PROXY_MARKER = "_disableInitializers()"
_INITIALIZABLE_MARKER = "Initializable"


def requires_proxy_initialization(contract_source: str | Path) -> bool:
    """Return true only when the implementation explicitly disables direct initialization."""
    if isinstance(contract_source, Path):
        try:
            source = contract_source.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False
    else:
        source = contract_source
    return _INITIALIZABLE_MARKER in source and _PROXY_MARKER in source


def adapt_generated_initialization_for_proxy(source: str, target_type: str, implementation_args: str = "") -> str:
    """Route initialization through a minimal delegate proxy while preserving msg.sender.

    The implementation contract remains the real target. The proxy owns the separate
    storage slot used by OpenZeppelin Initializable, so a constructor that calls
    _disableInitializers() does not make the intended proxy deployment untestable.
    """
    if "contract CydraDelegateProxy" in source:
        return source

    declaration = f"    {target_type} internal implementation;\n"
    if declaration not in source:
        anchor = f"    {target_type} internal target;\n"
        if anchor not in source:
            raise ValueError("generated initialization test has no target declaration")
        source = source.replace(anchor, anchor + declaration, 1)

    assignment = f"implementation = new {target_type}({implementation_args});\n        CydraDelegateProxy proxy = new CydraDelegateProxy(address(implementation));\n        target = {target_type}(address(proxy));"
    pattern = re.compile(rf"target\s*=\s*new\s+{re.escape(target_type)}\([^;]*\);")
    source, count = pattern.subn(assignment, source, count=1)
    if count != 1:
        raise ValueError("generated initialization test does not contain the expected direct target deployment")

    proxy = '''

contract CydraDelegateProxy {
    address public immutable implementation;

    constructor(address implementation_) {
        require(implementation_ != address(0), "proxy implementation is zero");
        implementation = implementation_;
    }

    fallback() external payable {
        address implementation_ = implementation;
        assembly {
            calldatacopy(0, 0, calldatasize())
            let ok := delegatecall(gas(), implementation_, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            switch ok
            case 0 { revert(0, returndatasize()) }
            default { return(0, returndatasize()) }
        }
    }

    receive() external payable {}
}
'''
    marker = "contract CydraInitializationInvariantTest is Test {"
    if marker not in source:
        raise ValueError("generated initialization test has no expected test contract")
    return source.replace(marker, proxy + "\n" + marker, 1)
