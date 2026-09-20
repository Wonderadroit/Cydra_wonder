// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
contract FeeTransferToken {
    mapping(address=>uint256) public balanceOf;
    uint256 public constant FEE_BPS=1000;
    constructor(){balanceOf[msg.sender]=1_000_000;}
    function mint(address to,uint256 amount) external {balanceOf[to]+=amount;}
    function transferFrom(address from,address to,uint256 amount) external returns(bool){
        require(balanceOf[from]>=amount,"balance"); balanceOf[from]-=amount;
        uint256 fee=amount*FEE_BPS/10_000; balanceOf[to]+=amount-fee; return true;
    }
}
contract FeeTransferAccountingTargetPatched {
    FeeTransferToken public immutable token;
    mapping(address=>uint256) public credits;
    constructor(address token_){token=FeeTransferToken(token_);}
    function deposit(uint256 amount) external {
        uint256 beforeBalance=token.balanceOf(address(this));
        require(token.transferFrom(msg.sender,address(this),amount),"transfer");
        uint256 received=token.balanceOf(address(this))-beforeBalance;
        credits[msg.sender]+=received;
    }
    function assetBalance() external view returns(uint256){return token.balanceOf(address(this));}
}
