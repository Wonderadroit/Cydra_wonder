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


def test_unresolved_templates_do_not_consume_discovery_budget():
    from cydra.execution_adapter import AdapterObservation, AdapterStatus
    from cydra.web2_discovery import discover_web2_surface

    class FakeAdapter:
        def __init__(self):
            self.paths = []

        def execute(self, request):
            path = request.inputs["path"]
            self.paths.append(path)
            if path == "/":
                body = '<a href="/v1/items">items</a><a href="/v1/items/{id}">item</a>'
            elif path == "/v1/items":
                body = '{"items":[{"id":"item-42"}]}'
            elif path == "/v1/items/item-42":
                body = '{"id":"item-42","name":"observed"}'
            else:
                body = "{}"
            return AdapterObservation(
                AdapterStatus.EXECUTED,
                request.action_id,
                {"status_code": 200, "body": body, "headers": {"Content-Type": "application/json"}},
            )

    adapter = FakeAdapter()
    result = discover_web2_surface(
        adapter, target="https://authorized.example", seeds=("/",), max_paths=3
    )
    assert adapter.paths == ["/", "/v1/items", "/v1/items/item-42"]
    assert all("{id}" not in path for path in adapter.paths)
    assert any(plan.materialized_path == "/v1/items/item-42" for plan in result.materialization_plans)


def test_endpoint_resource_relation_materializes_generic_id():
    from cydra.web2_model import Web2ResourceModel

    resource = Web2ResourceModel("resource:1", "Alice record", "alice", "record-42")
    endpoint = Web2EndpointModel(
        "endpoint:get-record", "GET", "/records/{id}", ("resource:1",)
    )
    plan = materialize_endpoint(endpoint, (resource,), ())
    assert plan.executable
    assert plan.materialized_path == "/records/record-42"
    assert plan.requirements[0].resource_id == "resource:1"


def test_extracts_resource_identifiers_from_observed_json_script_state():
    endpoint = Web2EndpointModel("GET /", "GET", "/")
    observed = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"items":[{"itemId":"item-99"}]}}}'
        '</script></html>'
    )
    found = extract_resource_identifiers(endpoint, observed, "obs-html")
    assert [item[0].identifier for item in found] == ["item-99"]
    assert found[0][1].field_path == "props.pageProps.items[0].itemId"
    assert found[0][1].source_observation_id == "obs-html"
