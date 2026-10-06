from cydra.web2_discovery import (
    Web2BundleAnalysis,
    Web2ResponseFingerprint,
    _detect_service_origin_resolution_gaps,
)
from cydra.web2_model import Web2TargetModel


def make_analysis(path, endpoints, *, request_origins=(), service_origins=()):
    return Web2BundleAnalysis(
        path=path,
        classification="application",
        endpoint_candidates=tuple(endpoints),
        service_origins=tuple(service_origins),
        request_methods=("GET",),
        unresolved_request_templates=("<dynamic-request-template>",),
        request_origins=tuple(request_origins),
    )


def make_negatives(paths):
    return {
        path: Web2ResponseFingerprint(
            status_code=404,
            content_type="text/html",
            body_sha256="deadbeef",
            body_length=100,
            generic_negative=True,
        )
        for path in paths
    }


def test_service_origin_gap_requires_concrete_external_request_provenance():
    analyses = [
        make_analysis(
            "bundle-a.js",
            ["/v1/items", "/v1/items/{id}", "/v1/inventories"],
            request_origins=(("https://api.example/v1/items", "https://api.example"),),
        ),
        make_analysis("bundle-b.js", ["/v1/matches", "/v1/matches/{match_id}", "/v2/items"]),
    ]
    negatives = make_negatives(
        ["/v1/items", "/v1/inventories", "/v1/matches", "/v2/items", "/v1/packs"]
    )

    gaps = _detect_service_origin_resolution_gaps(
        target="https://app.example",
        bundle_analyses=analyses,
        response_fingerprints=negatives,
        model=Web2TargetModel("https://app.example"),
    )

    assert gaps == ("SERVICE_ORIGIN_RESOLUTION",)


def test_service_origin_gap_ignores_placeholder_external_origins():
    analyses = [
        make_analysis(
            "bundle-a.js",
            ["/v1/items", "/v1/inventories", "/v1/packs"],
            request_origins=(("https://example.com/v1/items", "https://example.com"),),
        ),
        make_analysis("bundle-b.js", ["/v1/matches", "/v2/items", "/v1/challenges"]),
    ]
    negatives = make_negatives(
        ["/v1/items", "/v1/inventories", "/v1/packs", "/v1/matches", "/v2/items"]
    )

    gaps = _detect_service_origin_resolution_gaps(
        target="https://app.example",
        bundle_analyses=analyses,
        response_fingerprints=negatives,
        model=Web2TargetModel("https://app.example"),
    )

    assert gaps == ()


def test_service_origin_gap_does_not_trigger_for_large_relative_surface():
    analyses = [
        make_analysis("bundle-a.js", ["/v1/items", "/v1/items/{id}", "/v1/inventories"]),
        make_analysis("bundle-b.js", ["/v1/matches", "/v1/matches/{match_id}", "/v2/items"]),
    ]
    negatives = make_negatives(
        ["/v1/items", "/v1/inventories", "/v1/matches", "/v2/items", "/v1/packs"]
    )

    gaps = _detect_service_origin_resolution_gaps(
        target="https://app.example",
        bundle_analyses=analyses,
        response_fingerprints=negatives,
        model=Web2TargetModel("https://app.example"),
    )

    assert gaps == ()


def test_service_origin_gap_does_not_trigger_for_small_surface():
    analyses = [
        make_analysis("bundle-a.js", ["/v1/items"]),
        make_analysis("bundle-b.js", ["/v1/matches"]),
    ]
    negatives = make_negatives(["/v1/items", "/v1/matches"])

    gaps = _detect_service_origin_resolution_gaps(
        target="https://app.example",
        bundle_analyses=analyses,
        response_fingerprints=negatives,
        model=Web2TargetModel("https://app.example"),
    )

    assert gaps == ()


def test_service_origin_gap_correlates_declared_external_origin_with_relative_api_client():
    analyses = [
        make_analysis(
            "bundle-a.js",
            ["/v1/items", "/v1/items/{id}", "/v1/inventories"],
            service_origins=("https://api.testcorp.local",),
        ),
        make_analysis("bundle-b.js", ["/v1/matches", "/v2/items"]),
    ]
    negatives = make_negatives(
        ["/v1/items", "/v1/inventories", "/v1/matches", "/v2/items"]
    )

    gaps = _detect_service_origin_resolution_gaps(
        target="https://app.testcorp.local",
        bundle_analyses=analyses,
        response_fingerprints=negatives,
        model=Web2TargetModel("https://app.testcorp.local"),
    )

    assert gaps == ("SERVICE_ORIGIN_RESOLUTION",)
