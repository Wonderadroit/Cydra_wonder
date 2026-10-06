from cydra.web2_discovery import (
    Web2BundleAnalysis,
    Web2ResponseFingerprint,
    _detect_service_origin_resolution_gaps,
)
from cydra.web2_model import Web2TargetModel


def make_analysis(path, endpoints):
    return Web2BundleAnalysis(
        path=path,
        classification="application",
        endpoint_candidates=tuple(endpoints),
        request_methods=("GET",),
        unresolved_request_templates=("<dynamic-request-template>",),
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


def test_service_origin_gap_requires_corroborated_application_surface():
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

    assert gaps == ("SERVICE_ORIGIN_RESOLUTION",)


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
