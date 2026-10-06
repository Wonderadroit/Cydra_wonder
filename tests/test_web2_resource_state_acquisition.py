from cydra.execution_adapter import AdapterObservation, AdapterStatus
from cydra.web2_discovery import discover_web2_surface


class AuthorizedStateAdapter:
    """Generic stand-in for an already-authorized Web2 identity/session."""

    def __init__(self):
        self.requests = []

    def execute(self, request):
        path = request.inputs["path"]
        identity_id = request.inputs.get("identity_id")
        self.requests.append((identity_id, path))

        if path == "/":
            body = '<a href="/v1/items">items</a><a href="/v1/items/{id}">item</a>'
        elif path == "/v1/items":
            body = '{"items":[{"id":"observed-item-42","name":"publicly-observed"}]}'
        elif path == "/v1/items/observed-item-42":
            body = '{"id":"observed-item-42","name":"publicly-observed","state":"ready"}'
        else:
            body = "{}"

        return AdapterObservation(
            AdapterStatus.EXECUTED,
            request.action_id,
            value={
                "status_code": 200,
                "body": body,
                "headers": {"Content-Type": "application/json"},
                "identity_id": identity_id,
            },
            evidence=(body,),
        )


def test_authorized_resource_state_flows_to_identifier_provenance_and_dependent_execution():
    adapter = AuthorizedStateAdapter()

    result = discover_web2_surface(
        adapter,
        target="https://authorized.example",
        seeds=("/",),
        identity_id="authorized-owner",
        identity_authenticated=True,
        max_paths=3,
        max_js_bundles=0,
    )

    assert result.capability_gaps == ()
    assert len(result.model.resources) == 1

    resource = next(iter(result.model.resources.values()))
    assert resource.identifier == "observed-item-42"

    provenance = next(
        item for item in result.resource_provenance
        if item.resource_id == resource.resource_id
    )
    assert provenance.identifier == "observed-item-42"
    assert provenance.source_endpoint_id == "GET /v1/items"
    assert provenance.source_observation_id == "discover:2"
    assert provenance.field_path == "items[0].id"

    dependent = next(
        plan for plan in result.materialization_plans
        if plan.template == "/v1/items/{id}"
    )
    assert dependent.executable
    assert dependent.materialized_path == "/v1/items/observed-item-42"
    assert dependent.provenance[0].source_observation_id == "discover:2"

    assert adapter.requests == [
        ("authorized-owner", "/"),
        ("authorized-owner", "/v1/items"),
        ("authorized-owner", "/v1/items/observed-item-42"),
    ]


def test_missing_anonymous_resource_state_stays_fail_closed():
    class AnonymousAdapter(AuthorizedStateAdapter):
        def execute(self, request):
            path = request.inputs["path"]
            self.requests.append((request.inputs.get("identity_id"), path))
            body = (
                '<a href="/v1/items">items</a><a href="/v1/items/{id}">item</a>'
                if path == "/"
                else "{}"
            )
            status = 200
            if path == "/v1/items":
                status = 404
                body = "Not Found"
            return AdapterObservation(
                AdapterStatus.EXECUTED,
                request.action_id,
                value={
                    "status_code": status,
                    "body": body,
                    "headers": {"Content-Type": "application/json"},
                },
                evidence=(body,),
            )

    adapter = AnonymousAdapter()
    result = discover_web2_surface(
        adapter,
        target="https://authorized.example",
        seeds=("/",),
        identity_id="anonymous-owner",
        identity_authenticated=False,
        max_paths=3,
        max_js_bundles=0,
    )

    assert not result.model.resources
    assert "RESOURCE_STATE_ACQUISITION" in result.capability_gaps
    dependent = next(
        plan for plan in result.materialization_plans
        if plan.template == "/v1/items/{id}"
    )
    assert not dependent.executable
    assert dependent.materialized_path is None
    assert dependent.requirements[0].resource_id is None
