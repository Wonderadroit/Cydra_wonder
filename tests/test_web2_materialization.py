from cydra.web2_materialization import (
    extract_template_parameters,
    extract_resource_identifiers,
    materialize_endpoint,
)
from cydra.web2_model import Web2EndpointModel


def test_extracts_explicit_resource_identifiers_with_provenance():
    endpoint = Web2EndpointModel("GET /v1/items", "GET", "/v1/items")
    observed = '{"items":[{"id":"item-42","owner_id":"wallet-7"}]}'
    found = extract_resource_identifiers(endpoint, observed, "obs-1")
    assert {item[0].identifier for item in found} == {"item-42", "wallet-7"}
    provenance = {item[1].field_path: item[1].source_observation_id for item in found}
    assert provenance["items[0].id"] == "obs-1"


def test_materializes_template_only_from_observed_identifier():
    source = Web2EndpointModel("GET /v1/items", "GET", "/v1/items")
    resources_and_provenance = extract_resource_identifiers(
        source, '{"items":[{"id":"item-42"}]}', "obs-1"
    )
    resources = [item[0] for item in resources_and_provenance]
    provenance = [item[1] for item in resources_and_provenance]

    endpoint = Web2EndpointModel("GET /v1/items/{id}", "GET", "/v1/items/{id}")
    plan = materialize_endpoint(endpoint, resources, provenance)
    assert plan.executable
    assert plan.materialized_path == "/v1/items/item-42"
    assert plan.provenance[0].source_observation_id == "obs-1"


def test_unresolved_parameter_stays_unresolved():
    endpoint = Web2EndpointModel("GET /v1/items/{id}", "GET", "/v1/items/{id}")
    plan = materialize_endpoint(endpoint, (), ())
    assert not plan.executable
    assert plan.materialized_path is None
    assert plan.requirements[0].resource_id is None


def test_ambiguous_identifiers_do_not_create_executable_request():
    source = Web2EndpointModel("GET /v1/items", "GET", "/v1/items")
    pairs = extract_resource_identifiers(
        source, '{"items":[{"id":"item-1"},{"id":"item-2"}]}', "obs-1"
    )
    endpoint = Web2EndpointModel("GET /v1/items/{id}", "GET", "/v1/items/{id}")
    plan = materialize_endpoint(endpoint, [item[0] for item in pairs], [item[1] for item in pairs])
    assert not plan.executable
