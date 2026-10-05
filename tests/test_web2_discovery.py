from cydra.execution_adapter import AdapterObservation, AdapterStatus
from cydra.web2_discovery import build_discovery_requests, discover_web2_surface


class FakeAdapter:
    def __init__(self, responses):
        self.responses = responses

    def execute(self, request):
        value = self.responses.get(request.inputs["path"])
        if value is None:
            return AdapterObservation(AdapterStatus.UNAVAILABLE, request.action_id, error="not found")
        return AdapterObservation(AdapterStatus.EXECUTED, request.action_id, value=value, evidence=(value,))


def test_discovery_follows_same_host_html_links_and_scripts():
    adapter = FakeAdapter({
        "/": {
            "status_code": 200,
            "headers": {"Content-Type": "text/html"},
            "body": (
                '<a href="/account">account</a>'
                '<script src="/static/app.js"></script>'
                '<a href="https://evil.example/x">bad</a>'
            ),
        },
        "/account": {
            "status_code": 200,
            "headers": {"Content-Type": "text/html"},
            "body": "<h1>account</h1>",
        },
        "/static/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": 'fetch("/api/users/me"); fetch("https://evil.example/secret");',
        },
        "/api/users/me": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
    })

    result = discover_web2_surface(adapter, target="https://app.example", max_paths=10)

    assert result.discovered_paths == ("/", "/account", "/static/app.js", "/api/users/me")
    assert "GET /api/users/me" in result.model.endpoints


def test_discovery_extracts_openapi_paths_without_treating_them_as_findings():
    adapter = FakeAdapter({
        "/openapi.json": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": '{"paths": {"/users": {}, "/users/{id}": {}}}',
        },
        "/users": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
        "/users/{id}": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
    })

    result = discover_web2_surface(
        adapter,
        target="https://app.example",
        seeds=("/openapi.json",),
        max_paths=5,
    )

    assert "/users" in result.discovered_paths
    assert "/users/{id}" in result.discovered_paths


def test_discovery_rejects_absolute_seed_urls():
    adapter = FakeAdapter({})
    try:
        discover_web2_surface(adapter, target="https://app.example", seeds=("https://evil.example",))
    except ValueError:
        pass
    else:
        raise AssertionError("absolute discovery seed must be rejected")


def test_build_requests_is_read_only_and_explicit():
    requests = build_discovery_requests(("/", "/account"), identity_id="owner")
    assert [r.inputs["method"] for r in requests] == ["GET", "GET"]
    assert all(r.metadata["purpose"] == "surface_discovery" for r in requests)
