from __future__ import annotations

"""Safe, target-independent Web2 surface discovery.

Discovery is intentionally limited to caller-provided seed paths and
server-declared links/specs. It does not brute-force paths or treat discovery
output as a security finding.
"""

from dataclasses import dataclass
import hashlib
import heapq
import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

from .execution_adapter import AdapterObservation, AdapterRequest, AdapterStatus
from .web2_model import Web2EndpointModel, Web2IdentityModel, Web2TargetModel
from .web2_materialization import (
    Web2MaterializationPlan,
    Web2ResourceProvenance,
    extract_resource_identifiers,
    extract_template_parameters,
    materialize_endpoint,
)


@dataclass(frozen=True)
class Web2BundleAnalysis:
    path: str
    classification: str
    base_urls: tuple[str, ...] = ()
    service_origins: tuple[str, ...] = ()
    unauthorized_origins: tuple[str, ...] = ()
    request_methods: tuple[str, ...] = ()
    endpoint_candidates: tuple[str, ...] = ()
    unresolved_request_templates: tuple[str, ...] = ()
    # Concrete request -> service-origin provenance. This preserves the
    # relationship even when the origin is not authorized for execution.
    request_origins: tuple[tuple[str, str], ...] = ()
    request_endpoints: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Web2ResponseFingerprint:
    status_code: int | None
    content_type: str
    body_sha256: str
    body_length: int
    generic_negative: bool


@dataclass(frozen=True)
class Web2ServiceOriginRelation:
    source: str
    origin: str
    relation: str
    authorized_for_execution: bool


@dataclass(frozen=True)
class Web2DiscoveryResult:
    model: Web2TargetModel
    observations: tuple[AdapterObservation, ...]
    discovered_paths: tuple[str, ...]
    bundle_analyses: tuple[Web2BundleAnalysis, ...] = ()
    resource_provenance: tuple[Web2ResourceProvenance, ...] = ()
    materialization_plans: tuple[Web2MaterializationPlan, ...] = ()
    service_origin_relations: tuple[Web2ServiceOriginRelation, ...] = ()
    response_fingerprints: tuple[tuple[str, Web2ResponseFingerprint], ...] = ()
    capability_gaps: tuple[str, ...] = ()


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name not in {"a", "link", "form", "script"}:
            return
        for key, value in attrs:
            if not value:
                continue
            key_name = key.lower()
            if key_name == "href" and tag_name in {"a", "link"}:
                self.links.add(value)
            elif key_name == "action" and tag_name == "form":
                self.links.add(value)
            elif key_name == "src" and tag_name == "script":
                self.links.add(value)


def discover_web2_surface(
    adapter: Any,
    *,
    target: str,
    seeds: Iterable[str] = ("/",),
    identity_id: str | None = None,
    identity_authenticated: bool = False,
    max_paths: int = 50,
    max_js_bundles: int = 16,
) -> Web2DiscoveryResult:
    """Collect a bounded, read-only surface from explicit seed paths.

    Only GET requests are generated. Paths must resolve to the same target host
    as the adapter's configured target. Discovery metadata is planning input,
    never security evidence.

    The queue is priority-based: application bundles are scheduled before
    derived API/resource candidates so they can reveal service origins and
    request construction before the bounded request budget is consumed.
    Generic static assets remain low priority.
    """
    if max_paths < 1:
        raise ValueError("max_paths must be positive")
    if max_js_bundles < 0:
        raise ValueError("max_js_bundles must not be negative")

    model = Web2TargetModel(target=target)
    if identity_id is not None:
        # Preserve the caller identity in the target model so downstream
        # reasoning can distinguish an observed actor from an unmodeled one.
        # This records identity provenance only; it never infers ownership.
        model.add_identity(Web2IdentityModel(identity_id, identity_id, authenticated=identity_authenticated))
    queue: list[tuple[int, int, str]] = []
    queued: set[str] = set()
    seen: set[str] = set()
    deferred_templates: set[str] = set()
    sequence = 0

    for seed in _normalize_seeds(seeds):
        heapq.heappush(queue, (-_path_priority(seed), sequence, seed))
        queued.add(seed)
        sequence += 1

    observations: list[AdapterObservation] = []
    discovered: list[str] = []
    bundle_analyses: list[Web2BundleAnalysis] = []
    resource_provenance: list[Web2ResourceProvenance] = []
    analyzed_bundles: set[str] = set()
    response_fingerprints: dict[str, Web2ResponseFingerprint] = {}
    generic_negative_origins: set[str] = set()

    while queue and len(seen) < max_paths:
        _, _, path = heapq.heappop(queue)
        if path in seen:
            continue
        template_endpoint = Web2EndpointModel(f"GET {path}", "GET", path)
        execution_path = path
        if extract_template_parameters(path):
            plan = materialize_endpoint(
                template_endpoint, model.resources.values(), resource_provenance
            )
            if not plan.executable:
                # Keep the template in the modeled discovery surface, but do
                # not execute it or consume an execution slot.
                if path not in discovered:
                    discovered.append(path)
                deferred_templates.add(path)
                continue
            # The template is modeled separately from the concrete request.
            # Only the provenance-backed materialized path is executable.
            execution_path = plan.materialized_path
            if execution_path is None:
                raise RuntimeError("executable materialization must provide a concrete path")
        seen.add(path)
        request = AdapterRequest(
            action_id=f"discover:{len(seen)}",
            operation="http_request",
            inputs={"method": "GET", "path": execution_path, "identity_id": identity_id},
            metadata={"purpose": "surface_discovery"},
        )
        observation = adapter.execute(request)
        observations.append(observation)
        if observation.status != AdapterStatus.EXECUTED:
            continue

        payload = observation.value
        if not isinstance(payload, dict):
            continue
        fingerprint = _response_fingerprint(payload)
        if fingerprint is not None:
            response_fingerprints[path] = fingerprint
            if fingerprint.generic_negative:
                generic_negative_origins.add(_origin_for_path(path, target))
        body = payload.get("body", "")
        if not isinstance(body, str):
            continue

        endpoint_id = f"GET {path}"
        endpoint = Web2EndpointModel(endpoint_id, "GET", path)
        model.add_endpoint(endpoint)
        discovered.append(path)

        discovered_resources = extract_resource_identifiers(
            endpoint, body, observation.action_id
        )
        endpoint_resource_ids: list[str] = []
        for resource, provenance in discovered_resources:
            model.add_resource(resource)
            endpoint_resource_ids.append(resource.resource_id)
            resource_provenance.append(provenance)
        if endpoint_resource_ids:
            model.endpoints.pop(endpoint_id, None)
            endpoint = Web2EndpointModel(
                endpoint_id, "GET", path, tuple(dict.fromkeys(endpoint_resource_ids))
            )
            model.add_endpoint(endpoint)

        # A newly observed resource may make deferred templates executable.
        for deferred_path in tuple(deferred_templates):
            deferred_endpoint = Web2EndpointModel(
                f"GET {deferred_path}", "GET", deferred_path
            )
            deferred_plan = materialize_endpoint(
                deferred_endpoint, model.resources.values(), resource_provenance
            )
            if deferred_plan.executable:
                # A concrete resource has just unlocked this template.
                # Give the materialized dependent request a bounded readiness
                # boost so the capability chain completes before unrelated
                # frontier work consumes the execution budget.
                heapq.heappush(
                    queue,
                    (-(_path_priority(deferred_path) + 80), sequence, deferred_path),
                )
                sequence += 1
                deferred_templates.remove(deferred_path)

        content_type = str((payload.get("headers") or {}).get("Content-Type", "")).lower()
        links: dict[str, int] = {}

        def add_links(candidates: Iterable[str], *, boost: int = 0) -> None:
            for candidate in candidates:
                current = links.get(candidate)
                priority = _path_priority(candidate) + boost
                if current is None or priority > current:
                    links[candidate] = priority

        if "json" in content_type:
            add_links(_openapi_paths(body))
        if "html" in content_type or "<a" in body.lower() or "<form" in body.lower() or "<script" in body.lower():
            add_links(_html_paths(body))
            # Inline application code has already been recovered from the
            # current response, so its concrete requests should execute before
            # an external application bundle consumes the bounded budget.
            add_links(_inline_javascript_paths(body), boost=40)
            for inline_index, inline_body in enumerate(_inline_javascript_bodies(body), start=1):
                inline_analysis = _analyze_javascript_bundle(
                    f"{path}#inline-script-{inline_index}", inline_body, target
                )
                bundle_analyses.append(inline_analysis)
                add_links(inline_analysis.endpoint_candidates, boost=40)
            for origin in _runtime_configuration_origins(body):
                authorized_host = urlparse(target).hostname
                bundle_analyses.append(
                    Web2BundleAnalysis(
                        path=f"{path}#runtime-config",
                        classification="application",
                        service_origins=(origin,),
                        unauthorized_origins=(() if urlparse(origin).hostname == authorized_host else (origin,)),
                    )
                )
        if _looks_like_javascript(path, content_type):
            if path not in analyzed_bundles and len(analyzed_bundles) < max_js_bundles:
                analysis = _analyze_javascript_bundle(path, body, target)
                bundle_analyses.append(analysis)
                analyzed_bundles.add(path)
                # Endpoints recovered from an already-executed application
                # bundle outrank API/resource links that were merely present
                # in the surrounding HTML. Collection surfaces receive an
                # additional generic readiness boost because their observed
                # identifiers can unlock many dependent parameterized routes.
                add_links(analysis.endpoint_candidates, boost=20)
                add_links(
                    (
                        candidate
                        for candidate in analysis.endpoint_candidates
                        if _looks_like_resource_collection(candidate)
                    ),
                    boost=70,
                )
            add_links(_javascript_paths(body), boost=20)

        for candidate, priority in sorted(links.items()):
            normalized = _same_host_path(candidate, target)
            if not normalized or normalized in seen or normalized in queued:
                continue
            priority = max(priority, _path_priority(normalized))
            # Keep the frontier complete. max_paths bounds execution, while
            # priority decides which discovered work executes first. A queue
            # cap here would prevent an application bundle from running long
            # enough to reveal higher-priority API candidates.
            heapq.heappush(queue, (-priority, sequence, normalized))
            queued.add(normalized)
            # Preserve explicit application/API candidates in the target model
            # as planned surfaces even before execution. This separates
            # discovered/planned state from observed state: a missing response
            # must not erase a statically recovered endpoint.
            if priority >= 90:
                model.add_endpoint(
                    Web2EndpointModel(
                        f"GET {normalized}",
                        "GET",
                        normalized,
                    )
                )
            sequence += 1

    # Statically observed methods are planned surfaces; discovery remains
    # read-only GET execution and never turns method extraction into evidence.
    for analysis in bundle_analyses:
        for method, candidate in analysis.request_endpoints:
            normalized = _same_host_path(candidate, target)
            if normalized is None or method == "GET":
                continue
            model.add_endpoint(
                Web2EndpointModel(f"{method} {normalized}", method, normalized)
            )

    materialization_plans = tuple(
        materialize_endpoint(endpoint, model.resources.values(), resource_provenance)
        for endpoint in sorted(model.endpoints.values(), key=lambda item: item.endpoint_id)
    )
    authorized_host = urlparse(target).hostname
    origin_relations: set[Web2ServiceOriginRelation] = set()
    for analysis in bundle_analyses:
        for origin in analysis.service_origins:
            origin_relations.add(
                Web2ServiceOriginRelation(
                    source=analysis.path,
                    origin=origin,
                    relation="bundle_declares_service_origin",
                    authorized_for_execution=urlparse(origin).hostname == authorized_host,
                )
            )
        for request, origin in analysis.request_origins:
            origin_relations.add(
                Web2ServiceOriginRelation(
                    source=f"{analysis.path}:{request}",
                    origin=origin,
                    relation="request_targets_service_origin",
                    authorized_for_execution=urlparse(origin).hostname == authorized_host,
                )
            )
    capability_gaps = _detect_service_origin_resolution_gaps(
        target=target,
        bundle_analyses=bundle_analyses,
        response_fingerprints=response_fingerprints,
        model=model,
    )
    capability_gaps = tuple(dict.fromkeys((*capability_gaps, *_detect_resource_state_acquisition_gaps(
        response_fingerprints=response_fingerprints,
        model=model,
    ))))
    return Web2DiscoveryResult(
        model=model,
        observations=tuple(observations),
        discovered_paths=tuple(discovered),
        bundle_analyses=tuple(bundle_analyses),
        resource_provenance=tuple(resource_provenance),
        materialization_plans=materialization_plans,
        response_fingerprints=tuple(sorted(response_fingerprints.items(), key=lambda item: item[0])),
        service_origin_relations=tuple(
            sorted(
                origin_relations,
                key=lambda item: (item.source, item.origin, item.relation),
            )
        ),
        capability_gaps=capability_gaps,
    )


def _detect_resource_state_acquisition_gaps(
    *,
    response_fingerprints: dict[str, Web2ResponseFingerprint],
    model: Web2TargetModel,
) -> tuple[str, ...]:
    """Surface a generic resource-state boundary without inventing auth or IDs.

    Static API discovery can establish that resource-shaped endpoints exist, but
    repeated generic negative responses do not prove why the target returned
    them. When no resource identifiers are actually observed, preserve that
    boundary as a capability gap so planning does not silently stop with an
    empty model. Authentication state is intentionally not inferred here.
    """
    if model.resources:
        return ()
    if not model.identities or any(identity.authenticated for identity in model.identities.values()):
        return ()
    api_paths = tuple(
        path for path, fingerprint in response_fingerprints.items()
        if fingerprint.generic_negative and _looks_like_api_surface(path)
    )
    if len(api_paths) < 2:
        return ()
    if not any(_looks_like_api_surface(endpoint.path) for endpoint in model.endpoints.values()):
        return ()
    return ("RESOURCE_STATE_ACQUISITION",)


def _detect_service_origin_resolution_gaps(
    *,
    target: str,
    bundle_analyses: list[Web2BundleAnalysis],
    response_fingerprints: dict[str, Web2ResponseFingerprint],
    model: Web2TargetModel,
) -> tuple[str, ...]:
    """Identify an execution-readiness boundary without treating it as a finding.

    A service-origin gap is raised only when the application exposes API-like
    request construction, multiple same-origin API candidates return generic
    negative responses, and the bundle evidence does not establish an
    authorized service origin that explains those requests. External origins
    remain evidence only; CYDRA never probes them merely because they were
    recovered from JavaScript.
    """
    api_negative_paths = tuple(
        path for path, fingerprint in response_fingerprints.items()
        if fingerprint.generic_negative and _looks_like_api_surface(path)
    )
    if len(api_negative_paths) < 2:
        return ()

    application_analyses = [
        analysis for analysis in bundle_analyses
        if analysis.classification == "application"
    ]
    if not application_analyses:
        return ()

    has_request_construction = any(
        analysis.request_methods or analysis.endpoint_candidates or analysis.unresolved_request_templates
        for analysis in application_analyses
    )
    if not has_request_construction:
        return ()

    # A large cluster of concrete API routes recovered from application bundles
    # is stronger evidence than an isolated unresolved URL expression. When the
    # target origin returns generic negatives for several of those routes, and
    # no application-declared authorized service origin explains the requests,
    # the discovery model has reached a service-origin boundary. This remains a
    # capability gap, never security evidence: CYDRA must resolve the runtime
    # service before it can materialize identifiers or form authorization
    # experiments. The thresholds deliberately require corroboration across
    # bundles/routes so framework/vendor URL parsing does not recreate the old
    # false-positive path.
    # Distinguish an explicitly declared target service from a relative request
    # that merely defaults to the current web origin. Relative request primitives
    # are useful provenance, but they must not mask an external service-origin
    # declaration when the observed same-origin API candidates are all negative.
    authorized_origins = {
        origin
        for analysis in application_analyses
        for origin in analysis.service_origins
        if urlparse(origin).hostname == urlparse(target).hostname
        and (
            origin in {
                declared
                for value in analysis.base_urls
                for declared in (
                    f"{urlparse(value).scheme}://{urlparse(value).netloc}",
                )
                if urlparse(value).scheme in {"http", "https"} and urlparse(value).hostname
            }
            or analysis.path.endswith("#runtime-config")
        )
    }
    # An external origin is relevant to this capability only when it is
    # connected to actual request construction in the same bundle. Static
    # literals from vendor/dependency code (for example documentation URLs or
    # test fixtures) must not turn repeated same-origin API 404s into a false
    # execution-readiness gap.
    request_linked_origin_counts: dict[str, int] = {}
    for analysis in application_analyses:
        for _, origin in analysis.request_origins:
            if (
                urlparse(origin).hostname != urlparse(target).hostname
                and not _is_placeholder_service_origin(origin)
            ):
                request_linked_origin_counts[origin] = request_linked_origin_counts.get(origin, 0) + 1
    # Unresolved request expressions are intentionally not sufficient to
    # establish a service-origin gap. Bundled frameworks and vendor libraries
    # routinely contain dynamic URL construction that cannot be resolved
    # statically (often with one-character minified expressions). Treating any
    # such expression as an origin-resolution failure makes unrelated runtime
    # code causal evidence. The gap must instead be grounded in repeated,
    # concrete request-to-external-origin provenance.
    # One concrete request to an external origin is sufficient when it is
    # corroborated by repeated same-origin API negatives. Requiring two
    # external requests misses applications that centralize many routes behind
    # one API client/base URL while the static bundle only exposes one concrete
    # request at analysis time. The repeated negative responses provide the
    # independent corroboration; unrelated URL literals still do not qualify.
    repeated_request_linked_origins = {
        origin for origin, count in request_linked_origin_counts.items()
        if count >= 1
    }
    if authorized_origins:
        return ()

    # Preserve the strong pre-existing signal: one concrete, non-placeholder
    # request to an external origin is enough when repeated same-origin API
    # negatives corroborate it. This path is deliberately evaluated before the
    # broader multi-bundle fallback below so existing precise provenance remains
    # as sensitive as before.
    if repeated_request_linked_origins:
        return (
            "SERVICE_ORIGIN_RESOLUTION",
        )

    # Without concrete, non-placeholder request-to-external-origin provenance,
    # there is no evidence that the API service is distinct from the target web
    # origin. A large set of relative API routes returning 404s is not enough:
    # those routes may simply be stale, versioned, or protected application
    # paths. Do not manufacture a SERVICE_ORIGIN_RESOLUTION capability gap from
    # that absence of evidence. The gap is reserved for a concrete external
    # service dependency that CYDRA can name but is not authorized to execute.
    return ()

def _is_placeholder_service_origin(origin: str) -> bool:
    """Return whether an external origin is clearly a placeholder/non-service literal.

    Minified/vendor bundles frequently contain reserved example domains or tiny
    host literals as fixtures, documentation links, parser tests, or framework
    probes. They are useful lexical evidence, but cannot corroborate a real
    application service-origin resolution gap.
    """
    hostname = (urlparse(origin).hostname or "").lower().rstrip(".")
    if not hostname:
        return True
    if hostname in {
        "example.com", "example.net", "example.org",
        "localhost", "invalid", "test", "local",
    }:
        return True
    if hostname.endswith(".example") or hostname.endswith(".invalid") or hostname.endswith(".test"):
        return True
    # A one-label, one-character host such as https://a is not credible
    # service-origin evidence from a production application bundle.
    if re.fullmatch(r"[a-z]", hostname):
        return True
    return False


def _looks_like_api_surface(path: str) -> bool:
    lowered = path.lower().split("?", 1)[0]
    return bool(re.search(r"/(?:api|graphql|rpc|v[0-9]+)(?:/|$)", lowered))


def _origin_for_path(path: str, target: str) -> str:
    parsed = urlparse(urljoin(target.rstrip("/") + "/", path))
    return f"{parsed.scheme}://{parsed.netloc}"


def _response_fingerprint(payload: dict[str, Any]) -> Web2ResponseFingerprint | None:
    raw_body = payload.get("body", "")
    if not isinstance(raw_body, str):
        return None
    headers = payload.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}
    content_type = str(headers.get("Content-Type", headers.get("content-type", ""))).split(";", 1)[0].strip().lower()
    status_raw = payload.get("status_code")
    try:
        status_code = int(status_raw) if status_raw is not None else None
    except (TypeError, ValueError):
        status_code = None
    normalized = re.sub(r"\s+", " ", raw_body).strip()
    normalized = re.sub(r"\b(?:request[-_ ]?id|trace[-_ ]?id)\s*[:=]\s*[^\s<]+", "", normalized, flags=re.I)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    generic_negative = status_code in {400,401,403,404,405,410,422,429,500,502,503,504} and len(normalized) <= 8192
    return Web2ResponseFingerprint(status_code, content_type, digest, len(raw_body), generic_negative)


def _normalize_seeds(seeds: Iterable[str]) -> list[str]:
    result: list[str] = []
    for seed in seeds:
        parsed = urlparse(seed)
        if parsed.scheme or parsed.netloc:
            raise ValueError("discovery seeds must be relative paths")
        path = seed or "/"
        if not path.startswith("/"):
            path = "/" + path
        if path not in result:
            result.append(path)
    return result


def _canonicalize_discovery_candidate(value: str) -> str:
    """Normalize JS expression fragments before they enter the discovery frontier.

    Lexical extraction can see the literal prefix of a JavaScript expression such as
    `"/v1/items/{id}".replace("{id}", id)`. If the full request-construction
    expression was not statically resolvable, the fragment must not become a
    malformed executable path. Preserve only the explicit path literal.
    """
    candidate = value.strip()
    replace_marker = re.search(r'''[\"']\.replace\(\s*[\"']''', candidate)
    if replace_marker:
        candidate = candidate[:replace_marker.start()]
    return candidate.rstrip()


def _candidate_is_authorized(value: str, target: str) -> bool:
    """Return whether a concrete request candidate is already target-authorized.

    Relative paths are same-origin by construction. Absolute URLs must match
    the target host; discovering an external service origin is evidence only,
    not permission to execute or expose a concrete endpoint candidate.
    """
    parsed = urlparse(value)
    if not parsed.scheme and not parsed.netloc:
        return value.startswith("/")
    return parsed.scheme in {"http", "https"} and parsed.hostname == urlparse(target).hostname


def _same_host_path(value: str, target: str) -> str | None:
    value = _canonicalize_discovery_candidate(value)
    if not value:
        return None
    absolute = urljoin(target.rstrip("/") + "/", value)
    parsed = urlparse(absolute)
    target_parsed = urlparse(target)
    if parsed.hostname != target_parsed.hostname:
        return None
    path = parsed.path or "/"
    return path + (f"?{parsed.query}" if parsed.query else "")


def _looks_like_resource_collection(path: str) -> bool:
    """Recognize read-only collection surfaces that can yield concrete IDs.

    This is scheduling metadata only. The heuristic does not assert that a
    route is sensitive or exploitable; it only moves explicit collection-like
    GET surfaces ahead of unrelated static work so their observed identifiers
    can unlock dependent templates.
    """
    lowered = path.lower().split("?", 1)[0]
    if not lowered.startswith("/") or extract_template_parameters(lowered):
        return False
    segments = [segment for segment in lowered.split("/") if segment]
    if len(segments) < 2:
        return False
    terminal = segments[-1]
    if terminal in {
        "search", "stats", "status", "latest", "upcoming", "succeeded",
        "config", "limits", "metadata", "images", "index",
    }:
        return False
    return terminal.endswith("s")


def _path_priority(path: str) -> int:
    """Rank discovered surfaces by expected security value without guessing paths.

    The execution budget is finite, so candidates that expose object identity,
    account state, transactions, ownership, or mutable workflows outrank
    generic application/static resources. This is only scheduling metadata:
    it never turns a path into a finding.
    """
    lowered = path.lower().split("?", 1)[0]
    score = 50

    # Runtime/bootstrap configuration can reveal the actual service origin before application bundles do.
    # Prioritize it under the bounded execution budget; this is scheduling metadata only.
    if re.search(r"/(?:config|runtime-config|configuration)\.(?:js|json)(?:$|\?)", lowered) or lowered in {"/config.js", "/config.json"}:
        score = 145
    elif re.search(r"/_next/static/chunks/[^/]+\.(?:js|mjs)(?:$|\?)", lowered) or re.search(r"/(?:static|assets?)/[^/]*(?:app|main|index)[^/]*\.(?:js|mjs)(?:$|\?)", lowered) or re.search(r"/(?:chunks/app|chunks/pages|app|pages)(?:/|$)", lowered):
        score = 130
    elif re.search(r"/(?:api|graphql|rpc|v[0-9]+)(?:/|$)", lowered):
        score = 100
    elif re.search(
        r"/(?:auth|account|accounts|user|users|profile|profiles|inventory|shop|shops|player|players|resource|resources|wallet|wallets|token|tokens|item|items|pack|packs|exchange|exchanges)(?:/|$)",
        lowered,
    ):
        score = 95

    if re.search(r"(?:\{|\}|:id|:user|:wallet|:player|:account)", lowered):
        score += 12

    if re.search(
        r"/(?:admin|delete|remove|update|edit|create|purchase|purchases|buy|sell|transfer|trade|exchange|claim|redeem|favorite|favorites|equip|withdraw|deposit)(?:/|$)",
        lowered,
    ):
        score += 8

    if re.search(r"/(?:wallet|token|inventory|item|pack|order|payment|transaction|transactions)(?:/|$)", lowered):
        score += 5

    if re.search(r"/(?:framework|webpack|polyfills|vendor)(?:[-_/]|\.|$)", lowered):
        score = min(score, 65)
    elif lowered.endswith((".js", ".mjs")) or ".js/" in lowered or ".js?" in lowered:
        score = max(score, 80)
    elif lowered.endswith((".json", ".yaml", ".yml")):
        score = max(score, 70)
    elif lowered.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".css", ".woff", ".woff2")):
        score = 10

    return score

def _html_paths(body: str) -> set[str]:
    parser = _LinkParser()
    parser.feed(body)
    return {link for link in parser.links if link.startswith(("/", "?", "http://", "https://"))}


def _openapi_paths(body: str) -> set[str]:
    try:
        document = json.loads(body)
    except json.JSONDecodeError:
        return set()
    paths = document.get("paths") if isinstance(document, dict) else None
    if not isinstance(paths, dict):
        return set()
    return {str(path) for path in paths if str(path).startswith("/")}


def _looks_like_javascript(path: str, content_type: str) -> bool:
    lowered = path.lower()
    return (
        "javascript" in content_type
        or lowered.endswith(".js")
        or lowered.endswith(".mjs")
        or ".js?" in lowered
        or ".mjs?" in lowered
    )


def _inline_javascript_bodies(body: str) -> tuple[str, ...]:
    """Return only inline script bodies, never external ``src`` scripts.

    External script tags are bundle references and are analyzed after the
    corresponding resource is fetched. Treating their empty markup body as an
    inline bundle creates a false first analysis and can hide the real bundle
    analysis behind the bounded frontier.
    """
    bodies: list[str] = []
    for match in re.finditer(
        r"<script\b([^>]*)>(.*?)</script\s*>",
        body,
        re.IGNORECASE | re.DOTALL,
    ):
        attributes, script_body = match.group(1), match.group(2)
        if re.search(r"\bsrc\s*=", attributes, re.IGNORECASE):
            continue
        bodies.append(script_body)
    return tuple(bodies)


def _inline_javascript_paths(body: str) -> set[str]:
    """Extract URL-like literals only from inline ``<script>`` contents."""
    candidates: set[str] = set()
    for script in _inline_javascript_bodies(body):
        candidates.update(_javascript_paths(script))
    return candidates


def _runtime_configuration_origins(body: str) -> tuple[str, ...]:
    """Recover explicit service origins from HTML bootstrap/runtime config."""
    origin_key = r"(?:baseURL|baseUrl|apiBase|apiBaseUrl|API_BASE_URL|API_BASE|apiUrl|apiURL|API_URL|backendUrl|backendURL|BACKEND_URL|serviceUrl|serviceURL|SERVICE_URL|graphqlUrl|graphqlURL|GRAPHQL_URL|endpointUrl|ENDPOINT_URL)"
    origins: set[str] = set()
    pattern = re.compile(r"[\"'`]?" + origin_key + r"[\"'`]?\s*[:=]\s*[\"'`](https?://[^\"'`\s]+)", re.IGNORECASE)
    for match in pattern.finditer(body):
        parsed = urlparse(match.group(1))
        if parsed.hostname:
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
    return tuple(sorted(origins))

def _javascript_paths(body: str) -> set[str]:
    """Extract explicit URL-like path literals from downloaded JS.

    This is intentionally lexical rather than a JS interpreter: no execution,
    no guessing, and no path enumeration. Same-host absolute URLs are retained
    and later constrained by _same_host_path().
    """
    candidates: set[str] = set()
    pattern = r"""["'\x60]((?:/|https?://)[^"'\x60\\\s]+)["'\x60]"""
    for match in re.finditer(pattern, body):
        value = match.group(1)
        if value.startswith("/") and not value.startswith("//") and not any(char in value for char in "<>\\x00"):
            candidates.add(value)
        elif value.startswith(("http://", "https://")):
            candidates.add(value)
    return candidates



_JS_STRING = r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)"""
_IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"


def _decode_js_string(token: str) -> str | None:
    if len(token) < 2 or token[0] not in "\"'" + chr(96) or token[-1] != token[0]:
        return None
    value = token[1:-1]
    if token[0] == chr(96) and "$" + "{" in value:
        return None
    try:
        return bytes(value, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return value


def _javascript_runtime_config_aliases(body: str) -> dict[str, str]:
    """Resolve explicit URL values exposed through common runtime config objects."""
    aliases: dict[str, str] = {}
    origin_key = r"(?:baseURL|baseUrl|apiBase|apiBaseUrl|API_BASE_URL|API_BASE|apiUrl|apiURL|API_URL|backendUrl|backendURL|BACKEND_URL|serviceUrl|serviceURL|SERVICE_URL|graphqlUrl|graphqlURL|GRAPHQL_URL|endpointUrl|ENDPOINT_URL)"
    object_assignment = re.compile(
        rf"(?P<prefix>(?:window|globalThis|self)(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*)\s*=\s*\{{(?P<body>[^{{}}]*)\}}",
        re.DOTALL,
    )
    for match in object_assignment.finditer(body):
        prefix = match.group("prefix")
        for item in re.finditer(rf"\b({origin_key})\s*:\s*({_JS_STRING})", match.group("body")):
            value = _decode_js_string(item.group(2))
            if value:
                aliases[f"{prefix}.{item.group(1)}"] = value
    direct_assignment = re.compile(
        rf"(?P<name>(?:window|globalThis|self)(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+\.{origin_key})\s*=\s*({_JS_STRING})"
    )
    for match in direct_assignment.finditer(body):
        value = _decode_js_string(match.group(2))
        if value:
            aliases[match.group("name")] = value
    return aliases


def _javascript_constants(body: str, aliases: dict[str, str] | None = None) -> dict[str, str]:
    """Resolve simple JS constants, including references to earlier constants."""
    expressions: dict[str, str] = {}
    pattern = re.compile(rf"\b(?:const|let|var)\s+({_IDENT})\s*=\s*([^;\n]+)")
    for match in pattern.finditer(body):
        expressions[match.group(1)] = match.group(2).strip()

    constants: dict[str, str] = {}
    # Resolve in declaration order; a few passes also handle forward references
    # without attempting general JavaScript evaluation.
    for _ in range(max(1, len(expressions))):
        changed = False
        for name, expression in expressions.items():
            if name in constants:
                continue
            value = _resolve_js_expression(expression, constants, aliases)
            if value is not None:
                constants[name] = value
                changed = True
        if not changed:
            break
    return constants


def _resolve_js_expression(
    expression: str,
    constants: dict[str, str],
    aliases: dict[str, str] | None = None,
) -> str | None:
    expression = expression.strip()
    if not expression:
        return None
    if aliases and expression in aliases:
        return aliases[expression]

    # Minified application bundles commonly construct parameterized endpoints
    # as `"/v1/items/{id}".replace("{id}", id)`. The endpoint template is
    # already explicit in the first literal; the replacement merely fills its
    # placeholder at runtime. Preserve the canonical template rather than
    # leaking the JavaScript `.replace(...)` expression into the path model.
    replace_match = re.fullmatch(
        rf"({_JS_STRING})\.replace\(\s*({_JS_STRING})\s*,\s*{_IDENT}\s*\)",
        expression,
    )
    if replace_match:
        base = _decode_js_string(replace_match.group(1))
        marker = _decode_js_string(replace_match.group(2))
        if base is not None and marker is not None and marker.startswith("{") and marker.endswith("}") and marker in base:
            return base

    literal = _decode_js_string(expression)
    if literal is not None:
        return literal
    if re.fullmatch(_IDENT, expression):
        return constants.get(expression)
    parts = [part.strip() for part in re.split(r"\s*\+\s*", expression)]
    if len(parts) > 1:
        resolved = []
        for part in parts:
            value = _resolve_js_expression(part, constants, aliases)
            if value is None:
                return None
            resolved.append(value)
        return "".join(resolved)
    return None


def _request_method_from_context(context: str, default: str = "GET") -> str:
    match = re.search(r"""\bmethod\s*:\s*["']([A-Za-z]+)["']""", context, re.IGNORECASE)
    return match.group(1).upper() if match else default


def _analyze_javascript_bundle(path: str, body: str, target: str) -> Web2BundleAnalysis:
    """Recover statically-resolvable request construction without JS execution."""
    runtime_aliases = _javascript_runtime_config_aliases(body)
    constants = _javascript_constants(body, runtime_aliases)
    base_urls: set[str] = set()
    service_origins: set[str] = set()
    unauthorized_origins: set[str] = set()
    methods: set[str] = set()
    candidates: set[str] = set()
    unresolved: set[str] = set()
    request_origins: dict[str, str] = {}
    request_endpoints: set[tuple[str, str]] = set()

    # First pass: recover literal declarations with a normalized key set.
    # This intentionally does not depend on the general expression resolver;
    # service-origin provenance must survive harmless bundle/minifier changes.
    service_key_names = {
        "baseurl", "apibase", "apibaseurl", "api_base_url", "api_base",
        "apiurl", "backendurl", "backend_url", "serviceurl", "service_url",
        "graphqlurl", "graphql_url", "endpointurl", "endpoint_url",
    }
    # Service declarations are provenance-bearing evidence. Recover them with
    # a dedicated lexical parser so complex bundle expressions cannot hide the
    # application's declared origin.
    declaration_pattern = re.compile(
        # Keep this lexer deliberately simpler than the general JS-string
        # grammar. Service-origin declarations only need a concrete quoted
        # literal; using the literal capture directly makes provenance
        # independent of nested regex escaping in minified bundles.
        rf"(?<![A-Za-z0-9_$])(?:const|let|var)\s+({_IDENT})\s*=\s*(?:\"([^\"\\\\\r\\n]*)\"|'([^'\\\\\r\\n]*)'|\\x60([^\\x60\\\\\\r\\n]*)\\x60)",
        re.IGNORECASE,
    )
    for match in declaration_pattern.finditer(body):
        name = match.group(1)
        if name.lower() not in service_key_names:
            continue
        value = next((item for item in match.groups()[1:] if item is not None), None)
        if value is None:
            continue
        base_urls.add(value)
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            service_origins.add(f"{parsed.scheme}://{parsed.netloc}")

    # Resolve service origins only from application/config evidence. A URL is
    # not trusted merely because a route looks API-like: the surrounding config
    # key/property must establish that it is a service origin.
    origin_key = r"(?:baseURL|baseUrl|apiBase|apiBaseUrl|API_BASE_URL|API_BASE|apiUrl|apiURL|API_URL|backendUrl|backendURL|BACKEND_URL|serviceUrl|serviceURL|SERVICE_URL|graphqlUrl|graphqlURL|GRAPHQL_URL|endpointUrl|ENDPOINT_URL)"
    # Preserve resolved constant values directly. This is deliberately separate
    # from the lexical property matcher below so minified declarations such as
    # const API_BASE = "https://api.example" cannot be lost merely because
    # the declaration has no object/property syntax.
    for name, value in constants.items():
        if re.fullmatch(origin_key, name, re.IGNORECASE):
            base_urls.add(value)
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                service_origins.add(f"{parsed.scheme}://{parsed.netloc}")
    # Also retain literal origin/base declarations directly. This defensive
    # lexical pass makes provenance independent of the small constant resolver
    # when bundles are minified or declaration formatting changes.
    for match in re.finditer(
        rf"\b(?:const|let|var)\s+({origin_key})\s*=\s*({_JS_STRING})",
        body,
        re.IGNORECASE,
    ):
        value = _decode_js_string(match.group(2))
        if value is None:
            continue
        base_urls.add(value)
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            service_origins.add(f"{parsed.scheme}://{parsed.netloc}")
    for match in re.finditer(
        rf"\b{origin_key}\s*[:=]\s*({_JS_STRING}|{_IDENT})", body
    ):
        value = _resolve_js_expression(match.group(1), constants, runtime_aliases)
        if value is not None:
            base_urls.add(value)
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                service_origins.add(f"{parsed.scheme}://{parsed.netloc}")

    # Common runtime/bootstrap configuration shapes. These are intentionally
    # lexical: CYDRA records the origin only when the application itself
    # supplies a concrete URL. process.env/import.meta.env references remain
    # unresolved because their runtime value is not evidence in the bundle.
    config_property = rf"(?:window|globalThis|self)\s*(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[['\"][^'\"]+['\"]\])*\s*[.]?\s*{origin_key}"
    for match in re.finditer(rf"{config_property}\s*[:=]\s*({_JS_STRING})", body):
        value = _decode_js_string(match.group(1))
        if value:
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                service_origins.add(f"{parsed.scheme}://{parsed.netloc}")

    # Object/bootstrap literals such as { API_URL: "https://service.example" }
    # are also application-provided configuration evidence.
    for match in re.finditer(rf"\b{origin_key}\s*:\s*({_JS_STRING})", body):
        value = _decode_js_string(match.group(1))
        if value:
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                service_origins.add(f"{parsed.scheme}://{parsed.netloc}")

    patterns = (
        (rf"\bfetch\s*\(\s*([^,\)]+)([^\)]*)\)", "fetch"),
        (rf"\baxios\.(get|post|put|patch|delete|head|options)\s*\(\s*([^,\)]+)([^\)]*)\)", "axios"),
        (rf"\bnew\s+Request\s*\(\s*([^,\)]+)([^\)]*)\)", "request"),
        (rf"\.open\s*\(\s*['\"]([A-Za-z]+)['\"]\s*,\s*([^,\)]+)", "xhr"),
        # Minified clients commonly hide transport behind member methods such
        # as api.get("/v1/items") or client.post("/v1/..."). Recover only
        # concrete URL/path arguments; this is lexical evidence.
        (rf"\.\s*(get|post|put|patch|delete|head|options)\s*\(\s*([^,\)]+)([^\)]*)\)", "member_http"),
        (rf"\.\s*request\s*\(\s*([^,\)]+)([^\)]*)\)", "member_request"),
        (rf"\b(?:request|httpRequest)\s*\(\s*([^,\)]+)([^\)]*)\)", "request_function"),
    )
    for pattern, kind in patterns:
        for match in re.finditer(pattern, body, re.IGNORECASE | re.DOTALL):
            if kind in {"axios", "member_http"}:
                method = match.group(1).upper()
                expression = match.group(2)
            elif kind == "xhr":
                method = match.group(1).upper()
                expression = match.group(2)
            elif kind in {"member_request", "request_function"}:
                expression = match.group(1)
                method = _request_method_from_context(match.group(0))
            else:
                expression = match.group(1)
                method = _request_method_from_context(match.group(0))
            methods.add(method)
            value = _resolve_js_expression(expression, constants)
            if value is None:
                unresolved.add(expression.strip()[:200])
            else:
                # A concrete absolute URL used directly by a request primitive
                # is service-origin evidence even when the bundle does not label
                # it with API_BASE/baseURL/etc. Keep the origin as evidence, but
                # let the authorization filter below decide whether the concrete
                # request may enter the executable frontier.
                parsed_value = urlparse(value)
                if parsed_value.scheme in {"http", "https"} and parsed_value.hostname:
                    origin = f"{parsed_value.scheme}://{parsed_value.netloc}"
                    service_origins.add(origin)
                    request_origins[value] = origin
                elif value.startswith("/") and not value.startswith("//"):
                    # A root-relative request primitive is resolved by the browser
                    # against the application's current origin. Record that
                    # origin as service-origin provenance even when the bundle
                    # does not expose an explicit API_BASE/API_URL declaration.
                    target_parsed = urlparse(target)
                    if target_parsed.scheme in {"http", "https"} and target_parsed.hostname:
                        origin = f"{target_parsed.scheme}://{target_parsed.netloc}"
                        service_origins.add(origin)
                        request_origins[value] = origin
                candidates.add(value)
                request_endpoints.add((method, value))

    for match in re.finditer(
        rf"\b(?:url|endpoint)\s*:\s*({_JS_STRING}|{_IDENT})", body, re.IGNORECASE
    ):
        value = _resolve_js_expression(match.group(1), constants)
        if value is not None:
            candidates.add(value)
        else:
            unresolved.add(match.group(1)[:200])

    for match in re.finditer(
        rf"\bnew\s+URL\s*\(\s*([^,\)]+)\s*,\s*([^\)]+)\)", body
    ):
        first = _resolve_js_expression(match.group(1), constants)
        second = _resolve_js_expression(match.group(2), constants)
        if first is not None and second is not None:
            resolved = urljoin(second.rstrip("/") + "/", first)
            candidates.add(resolved)
            parsed_resolved = urlparse(resolved)
            if parsed_resolved.scheme in {"http", "https"} and parsed_resolved.hostname:
                request_origins[resolved] = f"{parsed_resolved.scheme}://{parsed_resolved.netloc}"
                service_origins.add(f"{parsed_resolved.scheme}://{parsed_resolved.netloc}")
        elif first is not None and first.startswith("/") and not first.startswith("//"):
            # The path literal is explicitly root-relative. Its meaning is
            # same-origin regardless of whether the base expression resolves.
            candidates.add(first)
        else:
            unresolved.add(match.group(0)[:200])

    if "$" + "{" in body and re.search(r"\b(?:fetch|Request|axios\.[A-Za-z]+)|\.open", body):
        unresolved.add("<dynamic-request-template>")
    candidates = {
        _canonicalize_discovery_candidate(candidate)
        for candidate in candidates
        if candidate and _candidate_is_authorized(candidate, target)
    }
    authorized_host = urlparse(target).hostname
    # Concrete service origins are evidence, not authorization. Only an origin
    # whose host is already the target host may enter the executable frontier;
    # external origins remain planned and explicitly unauthorized. In
    # particular, a resolved external base URL must not leak its concrete
    # request path into endpoint_candidates: the origin is evidence, while the
    # request remains non-executable until authorization exists.
    unauthorized_origins = {
        origin for origin in service_origins
        if urlparse(origin).hostname != authorized_host
    }
    classification = "application" if candidates or base_urls or service_origins or unresolved else "static_or_vendor"
    return Web2BundleAnalysis(
        path=path,
        classification=classification,
        base_urls=tuple(sorted(base_urls)),
        service_origins=tuple(sorted(service_origins)),
        unauthorized_origins=tuple(sorted(unauthorized_origins)),
        request_methods=tuple(sorted(methods)),
        endpoint_candidates=tuple(sorted(candidates)),
        unresolved_request_templates=tuple(sorted(unresolved)),
        request_origins=tuple(sorted(request_origins.items())),
        request_endpoints=tuple(sorted(request_endpoints)),
    )

def build_discovery_requests(
    paths: Iterable[str],
    *,
    identity_id: str | None = None,
) -> tuple[AdapterRequest, ...]:
    """Create explicit read-only requests without executing them."""
    return tuple(
        AdapterRequest(
            action_id=f"discover:{index}",
            operation="http_request",
            inputs={"method": "GET", "path": path, "identity_id": identity_id},
            metadata={"purpose": "surface_discovery"},
        )
        for index, path in enumerate(paths, start=1)
    )
