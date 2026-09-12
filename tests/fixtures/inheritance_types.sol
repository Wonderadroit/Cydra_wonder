interface IMinter {
    struct AirdropParams {
        address[] wallets;
    }
}

contract Minter is IMinter {
    function initialize(AirdropParams memory params) external {}
}
