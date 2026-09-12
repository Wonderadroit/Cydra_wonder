"""Canonical external-execution request identity and digesting."""
from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from typing import Mapping, Optional, Sequence

_MAPPING_TAG = "__cydra_mapping__"
_SEQUENCE_TAG = "__cydra_sequence__"

def _freeze(value):
    if isinstance(value, Mapping):
        items = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("execution request mapping keys must be strings")
            items.append((key, _freeze(item)))
        return (_MAPPING_TAG, tuple(sorted(items)))
    if isinstance(value, (list, tuple)):
        return (_SEQUENCE_TAG, tuple(_freeze(item) for item in value))
    if isinstance(value, float) and not math.isfinite(value):
        raise TypeError("execution request parameters must contain only finite numbers")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"execution request parameters must be JSON-compatible, got {type(value).__name__}")

def _thaw(value):
    if isinstance(value, tuple) and len(value) == 2 and value[0] == _MAPPING_TAG:
        return {key: _thaw(item) for key, item in value[1]}
    if isinstance(value, tuple) and len(value) == 2 and value[0] == _SEQUENCE_TAG:
        return [_thaw(item) for item in value[1]]
    return value


def _argv(value: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of argv strings, not a scalar string")
    items = tuple(value)
    if not items or any(not isinstance(item, str) or not item for item in items):
        raise TypeError(f"{field_name} must contain only non-empty strings")
    return items

@dataclass(frozen=True)
class ExecutionRequest:
    execution_id: str
    adapter: str
    target: str
    command: tuple[str, ...]
    project_fingerprint: Optional[str]
    authorization_id: str
    scope_status: str = "AUTHORIZED_EXECUTION"
    parameters: Mapping[str, object] = None
    _parameters_frozen: object = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("execution_id", "adapter", "target", "authorization_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        object.__setattr__(self, "command", _argv(self.command, "command"))
        if self.project_fingerprint is not None and not isinstance(self.project_fingerprint, str):
            raise TypeError("project_fingerprint must be a string or None")
        if self.scope_status != "AUTHORIZED_EXECUTION":
            raise ValueError("execution request requires AUTHORIZED_EXECUTION scope status")
        parameters = {} if self.parameters is None else self.parameters
        if not isinstance(parameters, Mapping):
            raise TypeError("execution request parameters must be a mapping")
        frozen = _freeze(parameters)
        object.__setattr__(self, "parameters", dict(parameters))
        object.__setattr__(self, "_parameters_frozen", frozen)

    def canonical_payload(self) -> dict:
        return {"execution_id": self.execution_id, "adapter": self.adapter, "target": self.target,
                "command": list(self.command), "project_fingerprint": self.project_fingerprint,
                "authorization_id": self.authorization_id, "scope_status": self.scope_status,
                "parameters": _thaw(self._parameters_frozen)}

    @property
    def digest(self) -> str:
        encoded = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
        return f"execution-request:{sha256(encoded).hexdigest()}"

    @classmethod
    def from_canonical_payload(cls, payload: Mapping[str, object], expected_digest: Optional[str] = None):
        if not isinstance(payload, Mapping):
            raise TypeError("canonical execution request payload must be a mapping")
        required_strings = ("execution_id", "adapter", "target", "authorization_id")
        for name in required_strings:
            if not isinstance(payload.get(name), str):
                raise TypeError(f"canonical execution request field {name} must be a string")
        command = payload.get("command")
        if not isinstance(command, (list, tuple)) or isinstance(command, str):
            raise TypeError("canonical execution request command must be an argv sequence")
        if any(not isinstance(item, str) or not item for item in command):
            raise TypeError("canonical execution request command entries must be non-empty strings")
        parameters = payload.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise TypeError("canonical execution request parameters must be a mapping")
        scope_status = payload.get("scope_status", "AUTHORIZED_EXECUTION")
        if not isinstance(scope_status, str):
            raise TypeError("canonical execution request scope_status must be a string")
        fingerprint = payload.get("project_fingerprint")
        if fingerprint is not None and not isinstance(fingerprint, str):
            raise TypeError("canonical execution request project_fingerprint must be a string or None")
        request = cls(payload["execution_id"], payload["adapter"], payload["target"], tuple(command), fingerprint,
                      payload["authorization_id"], scope_status, parameters)
        if expected_digest is not None and request.digest != expected_digest:
            raise ValueError("persisted execution request digest does not match canonical request")
        return request

def foundry_request(*, execution_id: str, project_dir: str, command: Sequence[str],
                    project_fingerprint: Optional[str], authorization_id: str,
                    scope_status: str = "AUTHORIZED_EXECUTION", test_filter: Optional[str] = None,
                    extra_args: Sequence[str] = ()) -> ExecutionRequest:
    return ExecutionRequest(execution_id=execution_id, adapter="foundry", target=project_dir,
                            command=_argv(command, "command"), project_fingerprint=project_fingerprint,
                            authorization_id=authorization_id, scope_status=scope_status,
                            parameters={"test_filter": test_filter, "extra_args": list(_argv(extra_args, "extra_args")) if extra_args else []})
