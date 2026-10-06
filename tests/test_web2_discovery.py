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
            "body": 'fetch("/api/users/me"); fetch("https://app.example/api/profile/me"); fetch("https://evil.example/secret");',
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
    assert "GET /api/profile/me" in result.model.endpoints


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


def test_api_candidates_survive_bounded_queue_pressure():
    static_links = "".join(f'<img src="/assets/icon-{index}.png">' for index in range(80))
    adapter = FakeAdapter({
        "/": {
            "status_code": 200,
            "headers": {"Content-Type": "text/html"},
            "body": static_links + '<script src="/app.js"></script><a href="/v1/items">items</a>',
        },
        "/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": 'fetch("/v1/inventories");',
        },
        "/v1/items": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
        "/v1/inventories": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
    })

    result = discover_web2_surface(adapter, target="https://app.example", max_paths=4)

    assert result.discovered_paths == ("/", "/v1/items", "/app.js", "/v1/inventories")
    assert not any(path.endswith(".png") for path in result.discovered_paths)


def test_bundle_analysis_materializes_root_relative_new_url_with_unresolved_base():
    adapter = FakeAdapter({
        "/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": 'const endpoint = new URL("/v1/items", o); fetch(endpoint);',
        },
        "/v1/items": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
    })

    result = discover_web2_surface(
        adapter,
        target="https://app.example",
        seeds=("/app.js",),
        max_paths=2,
        max_js_bundles=1,
    )

    analysis = result.bundle_analyses[0]
    assert "/v1/items" in analysis.endpoint_candidates
    assert "new URL(\"/v1/items\", o)" not in analysis.unresolved_request_templates
    assert "/v1/items" in result.discovered_paths


def test_discovery_extracts_inline_javascript_before_bundle_budget():
    adapter = FakeAdapter({
        "/": {
            "status_code": 200,
            "headers": {"Content-Type": "text/html"},
            "body": '<script>fetch("/api/session");</script><script src="/_next/static/chunks/app.js"></script>',
        },
        "/api/session": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
        "/_next/static/chunks/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": "fetch('/api/from-bundle');",
        },
    })

    result = discover_web2_surface(
        adapter,
        target="https://app.example",
        max_paths=2,
    )

    assert result.discovered_paths == ("/", "/api/session")


def test_discovery_does_not_turn_html_bootstrap_markup_into_paths():
    adapter = FakeAdapter({
        "/": {
            "status_code": 200,
            "headers": {"Content-Type": "text/html"},
            "body": '<div><!--$--></div><script>$RC("b","c");</script><script src="/_next/static/chunks/app.js"></script>',
        },
        "/_next/static/chunks/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": "fetch('/api/session');",
        },
    })

    result = discover_web2_surface(adapter, target="https://app.example", max_paths=3)

    assert "/$" not in result.discovered_paths
    assert "/&" not in result.discovered_paths
    assert all(">" not in path and "<" not in path for path in result.discovered_paths)


def test_bundle_analysis_resolves_base_url_and_request_construction():
    adapter = FakeAdapter({
        "/": {
            "status_code": 200,
            "headers": {"Content-Type": "text/html"},
            "body": '<script src="/static/app.js"></script>',
        },
        "/static/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": (
                'const API_BASE = "/api";'
                'const users = API_BASE + "/users";'
                'fetch(users);'
                'axios.post(API_BASE + "/session");'
                'const xhr = new XMLHttpRequest(); xhr.open("GET", API_BASE + "/profile");'
            ),
        },
        "/api/users": {"status_code": 200, "headers": {"Content-Type": "application/json"}, "body": "{}"},
        "/api/session": {"status_code": 200, "headers": {"Content-Type": "application/json"}, "body": "{}"},
        "/api/profile": {"status_code": 200, "headers": {"Content-Type": "application/json"}, "body": "{}"},
    })

    result = discover_web2_surface(adapter, target="https://app.example", max_paths=6, max_js_bundles=2)
    analysis = result.bundle_analyses[0]
    assert analysis.classification == "application"
    assert analysis.base_urls == ("/api",)
    assert "GET" in analysis.request_methods
    assert "POST" in analysis.request_methods
    assert "/api/users" in analysis.endpoint_candidates
    assert "/api/session" in analysis.endpoint_candidates
    assert "/api/profile" in analysis.endpoint_candidates


def test_bundle_analysis_keeps_dynamic_requests_unresolved():
    dynamic = 'fetch(' + chr(96) + '/api/player/$' + '{playerId}' + chr(96) + '); fetch(API_BASE + path);'
    adapter = FakeAdapter({
        "/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": dynamic,
        },
    })
    result = discover_web2_surface(adapter, target="https://app.example", seeds=("/app.js",), max_paths=1, max_js_bundles=1)
    analysis = result.bundle_analyses[0]
    assert analysis.classification == "application"
    assert analysis.endpoint_candidates == ()
    assert analysis.unresolved_request_templates


def test_bundle_analysis_does_not_authorize_external_hosts():
    adapter = FakeAdapter({
        "/": {
            "status_code": 200,
            "headers": {"Content-Type": "text/html"},
            "body": '<script src="/app.js"></script>',
        },
        "/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": 'const API_BASE = "https://api.example.net"; fetch(API_BASE + "/private");',
        },
    })
    result = discover_web2_surface(adapter, target="https://app.example", max_paths=2, max_js_bundles=1)
    assert "/private" not in result.discovered_paths
    assert any(item == "https://api.example.net" for item in result.bundle_analyses[0].base_urls)


def test_bundle_analysis_normalizes_replace_built_endpoint_templates():
    adapter = FakeAdapter({
        "/app.js": {
            "status_code": 200,
            "headers": {"Content-Type": "application/javascript"},
            "body": (
                'fetch("/v1/items/{id}".replace("{id}", id));'
                'fetch("/v1/wallets/{wallet}/tokens".replace("{wallet}", wallet));'
            ),
        },
        "/v1/items/{id}": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
        "/v1/wallets/{wallet}/tokens": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
        },
    })

    result = discover_web2_surface(
        adapter,
        target="https://app.example",
        seeds=("/app.js",),
        max_paths=3,
        max_js_bundles=1,
    )

    analysis = result.bundle_analyses[0]
    assert "/v1/items/{id}" in analysis.endpoint_candidates
    assert "/v1/wallets/{wallet}/tokens" in analysis.endpoint_candidates
    assert not any(".replace(" in candidate for candidate in analysis.endpoint_candidates)
    assert "/v1/items/{id}" in result.discovered_paths
    assert "/v1/wallets/{wallet}/tokens" in result.discovered_paths
    assert not any('.replace(' in path for path in result.discovered_paths)
    assert not any('.replace(' in endpoint for endpoint in result.model.endpoints)
