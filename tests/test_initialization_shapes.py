import logging

from cydra.initialization_shapes import render_initialization_test_body
from cydra.models import FunctionModel


def _function(*, authorization=(), state=()):
    return FunctionModel(
        name="initialize",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=1,
        authorization_predicates=authorization,
        state_predicates=state,
    )


def test_caller_only_uses_unauthorized_caller_shape():
    body = render_initialization_test_body(
        _function(authorization=("msg.sender != owner",)),
        "target",
        "address(0xA11CE)",
        "tokenStub, false",
    )
    assert "vm.prank(unauthorized);" in body
    assert "vm.expectRevert();" in body
    assert "target.initialize(tokenStub, false);" in body


def test_state_only_uses_lifecycle_shape():
    body = render_initialization_test_body(
        _function(state=("factory != address(0)",)),
        "target",
        "address(0xA11CE)",
        "tokenStub, tokenStub, false",
    )
    assert body.count("target.initialize(tokenStub, tokenStub, false);") == 2
    first, second = body.split("target.initialize(tokenStub, tokenStub, false);")[:2]
    assert "vm.expectRevert();" not in first
    assert "vm.expectRevert();" in second
    assert "vm.prank" not in body


def test_neither_uses_direct_fallback_and_logs_undetermined(caplog):
    with caplog.at_level(logging.WARNING, logger="cydra.initialization_shapes"):
        body = render_initialization_test_body(
            _function(),
            "target",
            "address(0xA11CE)",
            "params",
        )
    assert "target.initialize(params);" in body
    assert "vm.prank" not in body
    assert "vm.expectRevert" not in body
    assert "shape undetermined" in caplog.text


def test_both_prioritizes_unauthorized_caller_shape():
    body = render_initialization_test_body(
        _function(
            authorization=("msg.sender != owner",),
            state=("factory != address(0)",),
        ),
        "target",
        "address(0xA11CE)",
        "tokenStub",
    )
    assert "vm.prank(unauthorized);" in body
    assert "vm.expectRevert();" in body
    assert body.count("target.initialize(tokenStub);") == 1
