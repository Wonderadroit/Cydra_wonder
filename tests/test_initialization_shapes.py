import logging

from cydra.initialization_shapes import render_initialization_test_body
from cydra.models import FunctionModel


def _function(*, name="initialize", authorization=(), state=()):
    return FunctionModel(
        name=name,
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
        "0xA11CE",
        "tokenStub, false",
    )
    assert "address unauthorized = address(0xA11CE);" in body
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


def test_unclassified_initializer_uses_generic_mutation_probe(caplog):
    with caplog.at_level(logging.WARNING, logger="cydra.initialization_shapes"):
        body = render_initialization_test_body(
            _function(name="initialise"),
            "target",
            "0xA11CE",
            "false, 0, 0, address(0xCAFE)",
        )
    assert "address unauthorized = address(0xA11CE);" in body
    assert "vm.record();" in body
    assert "vm.prank(unauthorized);" in body
    assert "try target.initialise(false, 0, 0, address(0xCAFE));" in body
    assert "vm.accesses(address(target))" in body
    assert "assertEq(writes.length, 0" in body
    assert "shape undetermined; using generic mutation probe" in caplog.text


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


def test_initialise_spelling_is_preserved():
    body = render_initialization_test_body(
        _function(name="initialise", authorization=("msg.sender != owner",)),
        "target",
        "0xA11CE",
        "false, 0, 0, address(0xCAFE)",
    )
    assert "target.initialise(false, 0, 0, address(0xCAFE));" in body
