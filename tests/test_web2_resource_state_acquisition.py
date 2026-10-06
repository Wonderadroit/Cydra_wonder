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
                '<a href="/v1/items">items</a>'
                '<a href="/v1/inventories">inventories</a>'
                '<a href="/v1/items/{id}">item</a>'
                if path == "/"
                else "{}"
            )
            status = 200
            if path in {"/v1/items", "/v1/inventories"}:
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


def test_resource_state_capability_is_classified_instead_of_repaired_blindly():
    class FrontierAdapter(AuthorizedStateAdapter):
        def execute(self, request):
            path = request.inputs["path"]
            self.requests.append((request.inputs.get("identity_id"), path))
            if path == "/":
                body = (
                    '<script src="/app.js"></script>'
                    '<a href="/v1/items">items</a>'
                    '<a href="/v1/items/{id}">item</a>'
                )
            elif path == "/app.js":
                body = 'fetch("/v1/items");'
            elif path == "/v1/items":
                body = "Not Found"
            else:
                body = "{}"
            return AdapterObservation(
                AdapterStatus.EXECUTED,
                request.action_id,
                value={
                    "status_code": 404 if path == "/v1/items" else 200,
                    "body": body,
                    "headers": {"Content-Type": "application/javascript" if path == "/app.js" else "text/html"},
                },
                evidence=(body,),
            )

    result = discover_web2_surface(
        FrontierAdapter(),
        target="https://authorized.example",
        seeds=("/",),
        identity_id="anonymous-owner",
        identity_authenticated=False,
        max_paths=10,
        max_js_bundles=0,
    )
    state = next(item for item in result.capability_states if item.capability == "RESOURCE_STATE_ACQUISITION")
    assert state.status in {"BLOCKED_CONTEXT", "INCOMPLETE_FRONTIER", "EXHAUSTED"}
    assert state.status != "RESOLVED"


def test_nextjs_serialized_response_state_provides_resource_provenance():
    class NextJsAdapter:
        def execute(self, request):
            path = request.inputs["path"]
            if path == "/":
                body = (
                    '<script>self.__next_f.push([1,"{\\"items\\":[{\\"id\\":\\"next-item-7\\"}]}"])</script>'
                    '<a href="/v1/items/{id}">item</a>'
                )
            elif path == "/v1/items/next-item-7":
                body = '{"id":"next-item-7","state":"ready"}'
            else:
                body = "{}"
            return AdapterObservation(
                AdapterStatus.EXECUTED,
                request.action_id,
                value={
                    "status_code": 200,
                    "body": body,
                    "headers": {"Content-Type": "text/html"},
                },
                evidence=(body,),
            )

    result = discover_web2_surface(
        NextJsAdapter(),
        target="https://authorized.example",
        seeds=("/",),
        identity_id="authorized-owner",
        identity_authenticated=True,
        max_paths=2,
        max_js_bundles=0,
    )

    resource = next(iter(result.model.resources.values()))
    assert resource.identifier == "next-item-7"
    provenance = next(
        item for item in result.resource_provenance
        if item.resource_id == resource.resource_id
    )
    assert provenance.field_path == "items[0].id"
    dependent = next(
        plan for plan in result.materialization_plans
        if plan.template == "/v1/items/{id}"
    )
    assert dependent.executable
    assert dependent.materialized_path == "/v1/items/next-item-7"
