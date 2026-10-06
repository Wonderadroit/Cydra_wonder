from __future__ import annotations

"""Generic Web2 resource-identifier provenance and request materialization."""

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from .web2_model import Web2EndpointModel, Web2ResourceModel


_TEMPLATE_PARAMETER = re.compile(r"{([A-Za-z_][A-Za-z0-9_-]*)}|:([A-Za-z_][A-Za-z0-9_-]*)")
_IDENTIFIER_FIELD = re.compile(r"^(?:id|uuid|address|[A-Za-z][A-Za-z0-9]*(?:_id|_uuid|_address))$", re.I)


@dataclass(frozen=True)
class Web2ResourceProvenance:
    resource_id: str
    identifier: str
    source_endpoint_id: str
    source_observation_id: str
    field_path: str


@dataclass(frozen=True)
class Web2ParameterRequirement:
    endpoint_id: str
    parameter: str
    resource_id: str | None


@dataclass(frozen=True)
class Web2MaterializationPlan:
    endpoint_id: str
    template: str
    requirements: tuple[Web2ParameterRequirement, ...]
    materialized_path: str | None
    provenance: tuple[Web2ResourceProvenance, ...]
    executable: bool


def extract_template_parameters(path: str) -> tuple[str, ...]:
    """Return explicit path parameters without inventing values."""
    result: list[str] = []
    for match in _TEMPLATE_PARAMETER.finditer(path):
        name = match.group(1) or match.group(2)
        if name not in result:
            result.append(name)
    return tuple(result)


def extract_resource_identifiers(
    endpoint: Web2EndpointModel,
    body: str,
    observation_id: str,
) -> tuple[tuple[Web2ResourceModel, Web2ResourceProvenance], ...]:
    """Extract concrete identifiers from observed JSON with explicit provenance.

    Only identifier-shaped fields are accepted. Values are never guessed and
    the source endpoint/observation/field path is retained for replay.
    """
    try:
        payload = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return ()

    found: list[tuple[Web2ResourceModel, Web2ResourceProvenance]] = []

    def visit(value: Any, field_path: str = "") -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{field_path}.{key_text}" if field_path else key_text
                if _IDENTIFIER_FIELD.fullmatch(key_text) and isinstance(child, (str, int)):
                    identifier = str(child).strip()
                    if identifier:
                        digest = hashlib.sha256(
                            f"{key_text.lower()}|{identifier}".encode()
                        ).hexdigest()[:16]
                        resource_id = f"resource:{digest}"
                        resource = Web2ResourceModel(
                            resource_id=resource_id,
                            label=key_text,
                            identifier=identifier,
                        )
                        provenance = Web2ResourceProvenance(
                            resource_id=resource_id,
                            identifier=identifier,
                            source_endpoint_id=endpoint.endpoint_id,
                            source_observation_id=observation_id,
                            field_path=child_path,
                        )
                        found.append((resource, provenance))
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{field_path}[{index}]")

    visit(payload)
    return tuple(found)


def materialize_endpoint(
    endpoint: Web2EndpointModel,
    resources: Iterable[Web2ResourceModel],
    provenance: Iterable[Web2ResourceProvenance] = (),
) -> Web2MaterializationPlan:
    """Turn a template into an executable path only when provenance is sufficient.

    Ambiguous or missing identifiers remain unresolved. No synthetic values are
    ever inserted.
    """
    parameters = extract_template_parameters(endpoint.path)
    if not parameters:
        return Web2MaterializationPlan(
            endpoint.endpoint_id, endpoint.path, (), endpoint.path, (), True
        )

    resources_by_field: dict[str, list[Web2ResourceModel]] = {}
    for resource in resources:
        resources_by_field.setdefault(resource.label.lower(), []).append(resource)

    provenance_by_resource = {item.resource_id: item for item in provenance}
    values: dict[str, str] = {}
    requirements: list[Web2ParameterRequirement] = []
    selected_provenance: list[Web2ResourceProvenance] = []

    path_prefix = endpoint.path.split("?", 1)[0]
    segments = [segment for segment in path_prefix.split("/") if segment]
    for parameter in parameters:
        candidates = resources_by_field.get(parameter.lower(), [])
        if parameter.lower() == "id" and not candidates:
            previous = segments[segments.index("{" + parameter + "}") - 1] if "{" + parameter + "}" in segments and segments.index("{" + parameter + "}") > 0 else None
            if previous:
                candidates = resources_by_field.get(previous.rstrip("s").lower() + "_id", [])
        unique = {item.resource_id: item for item in candidates if item.identifier is not None}
        selected = next(iter(unique.values())) if len(unique) == 1 else None
        requirements.append(Web2ParameterRequirement(endpoint.endpoint_id, parameter, selected.resource_id if selected else None))
        if selected is None:
            continue
        values[parameter] = selected.identifier  # type: ignore[assignment]
        item = provenance_by_resource.get(selected.resource_id)
        if item is not None:
            selected_provenance.append(item)

    if len(values) != len(parameters):
        return Web2MaterializationPlan(
            endpoint.endpoint_id,
            endpoint.path,
            tuple(requirements),
            None,
            tuple(selected_provenance),
            False,
        )

    materialized = endpoint.path
    for parameter, value in values.items():
        materialized = re.sub(
            r"{" + re.escape(parameter) + r"}|:" + re.escape(parameter) + r"\\b",
            value,
            materialized,
        )
    return Web2MaterializationPlan(
        endpoint.endpoint_id,
        endpoint.path,
        tuple(requirements),
        materialized,
        tuple(selected_provenance),
        True,
    )
