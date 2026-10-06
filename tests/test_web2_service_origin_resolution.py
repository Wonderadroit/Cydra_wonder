from cydra.execution_adapter import AdapterObservation, AdapterStatus
from cydra.web2_discovery import discover_web2_surface


class ServiceOriginAdapter:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        path = request.inputs["path"]
        self.requests.append(path)
        if path == "/":
            body = """<html>
<script>
const API_BASE_URL = "https://api.testcorp.local";
fetch(API_BASE_URL + "/v1/items");
</script>
<a href="/v1/items">items</a>
<a href="/v1/inventories">inventories</a>
</html>"""
            content_type = "text/html"
            status = 200
        elif path in {"/v1/items", "/v1/inventories"}:
            body = "Not Found"
            content_type = "text/plain"
            status = 404
        else:
            body = "{}"
            content_type = "application/json"
            status = 200
        return AdapterObservation(
            AdapterStatus.EXECUTED,
            request.action_id,
            value={
                "status_code": status,
                "body": body,
                "headers": {"Content-Type": content_type},
            },
            evidence=(body,),
        )


def test_external_service_origin_is_modeled_without_being_executed():
    adapter = ServiceOriginAdapter()
    result = discover_web2_surface(
        adapter,
        target="https://app.testcorp.local",
        seeds=("/",),
        identity_id="bugcrowd-authorized",
        identity_authenticated=True,
        max_paths=3,
        max_js_bundles=4,
    )

    relations = result.service_origin_relations
    assert any(
        relation.origin == "https://api.testcorp.local"
        and relation.authorized_for_execution is False
        for relation in relations
    )
    assert "https://api.testcorp.local/v1/items" not in adapter.requests
    assert "https://api.testcorp.local/v1/items" not in result.discovered_paths
    assert all(path.startswith("/") for path in adapter.requests)


def test_external_service_origin_gap_requires_concrete_request_provenance():
    adapter = ServiceOriginAdapter()
    result = discover_web2_surface(
        adapter,
        target="https://app.testcorp.local",
        seeds=("/",),
        identity_id=None,
        identity_authenticated=False,
        max_paths=3,
        max_js_bundles=4,
    )

    assert "SERVICE_ORIGIN_RESOLUTION" in result.capability_gaps
    assert all(path.startswith("/") for path in adapter.requests)



def test_placeholder_external_origins_do_not_create_service_origin_gap():
    class PlaceholderAdapter(ServiceOriginAdapter):
        def execute(self, request):
            path = request.inputs["path"]
            self.requests.append(path)
            if path == "/":
                body = '''<html><script>
const fixture = "https://example.com";
const tiny = "https://a";
fetch("/v1/items");
</script><a href="/v1/items">items</a><a href="/v1/inventories">inventories</a></html>'''
                return AdapterObservation(AdapterStatus.EXECUTED, request.action_id, value={"status_code": 200, "body": body, "headers": {"Content-Type": "text/html"}}, evidence=(body,))
            body = "Not Found"
            return AdapterObservation(AdapterStatus.EXECUTED, request.action_id, value={"status_code": 404, "body": body, "headers": {"Content-Type": "text/plain"}}, evidence=(body,))

    adapter = PlaceholderAdapter()
    result = discover_web2_surface(adapter, target="https://app.testcorp.local", seeds=("/",), identity_id=None, identity_authenticated=False, max_paths=3, max_js_bundles=4)
    assert "SERVICE_ORIGIN_RESOLUTION" not in result.capability_gaps
    assert all(path.startswith("/") for path in adapter.requests)


def test_placeholder_origin_is_never_executable_service_target():
    class PlaceholderRequestAdapter(ServiceOriginAdapter):
        def execute(self, request):
            path = request.inputs["path"]
            self.requests.append(path)
            if path == "/":
                body = '''<script>fetch("https://example.com/v1/items");</script>'''
                return AdapterObservation(AdapterStatus.EXECUTED, request.action_id, value={"status_code": 200, "body": body, "headers": {"Content-Type": "text/html"}}, evidence=(body,))
            return AdapterObservation(AdapterStatus.EXECUTED, request.action_id, value={"status_code": 404, "body": "Not Found", "headers": {"Content-Type": "text/plain"}}, evidence=("Not Found",))

    adapter = PlaceholderRequestAdapter()
    discover_web2_surface(adapter, target="https://app.testcorp.local", seeds=("/",), identity_id="anonymous", identity_authenticated=False, max_paths=2, max_js_bundles=2)
    assert "https://example.com/v1/items" not in adapter.requests
    assert all(path.startswith("/") for path in adapter.requests)
