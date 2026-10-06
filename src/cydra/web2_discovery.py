from __future__ import annotations

"""Safe, target-independent Web2 surface discovery.

Discovery is intentionally limited to caller-provided seed paths and
server-declared links/specs. It does not brute-force paths or treat discovery
output as a security finding.
"""

from dataclasses import dataclass
import heapq
import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

from .execution_adapter import AdapterObservation, AdapterRequest, AdapterStatus
from .web2_model import Web2EndpointModel, Web2TargetModel
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


@dataclass(frozen=True)
class Web2DiscoveryResult:
    model: Web2TargetModel
    observations: tuple[AdapterObservation, ...]
    discovered_paths: tuple[str, ...]
    bundle_analyses: tuple[Web2BundleAnalysis, ...] = ()
    resource_provenance: tuple[Web2ResourceProvenance, ...] = ()
    materialization_plans: tuple[Web2MaterializationPlan, ...] = ()


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
                heapq.heappush(
                    queue,
                    (-_path_priority(deferred_path), sequence, deferred_path),
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
                # in the surrounding HTML.
                add_links(analysis.endpoint_candidates, boost=20)
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
