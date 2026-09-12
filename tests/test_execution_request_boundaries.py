import pytest
from cydra.execution_request import ExecutionRequest, foundry_request


def test_execution_request_exposes_read_only_parameters_and_stable_digest():
    request = foundry_request(execution_id="e1", project_dir="/tmp/p", command=("forge", "test"), project_fingerprint="fp", authorization_id="auth", test_filter="X")
    assert request.parameters["test_filter"] == "X"
    with pytest.raises(TypeError):
        request.parameters["test_filter"] = "Y"
    assert request.digest == request.digest


def test_execution_request_rejects_scalar_command_and_parameters():
    with pytest.raises(TypeError):
        foundry_request(execution_id="e1", project_dir="/tmp/p", command="forge test", project_fingerprint=None, authorization_id="auth")
    with pytest.raises(TypeError):
        ExecutionRequest("e1", "foundry", "/tmp/p", ("forge",), None, "auth", parameters=["bad"])


def test_canonical_payload_rejects_type_coercion():
    with pytest.raises(TypeError):
        ExecutionRequest.from_canonical_payload({"execution_id": 1, "adapter": "foundry", "target": "/tmp/p", "command": ["forge"], "authorization_id": "auth"})
    with pytest.raises(TypeError):
        ExecutionRequest.from_canonical_payload({"execution_id": "e1", "adapter": "foundry", "target": "/tmp/p", "command": "forge test", "authorization_id": "auth"})
