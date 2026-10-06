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

    The queue is priority-based: explicit application/API references are
    preferred over code bundles, and code bundles over static assets. This
    makes the bounded budget useful without guessing or brute-forcing paths.
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
        if extract_template_parameters(path):
            plan = materialize_endpoint(template_endpoint, model.resources.values(), resource_provenance)
            if not plan.executable:
                # Keep the template in the modeled discovery surface, but do
                # not execute it or consume an execution slot.
                if path not in discovered:
                    discovered.append(path)
                deferred_templates.add(path)
                continue
        seen.add(path)
        request = AdapterRequest(
            action_id=f"discover:{len(seen)}",
            operation="http_request",
            inputs={"method": "GET", "path": path, "identity_id": identity_id},
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
        links: set[str] = set()
        if "json" in content_type:
            links.update(_openapi_paths(body))
        if "html" in content_type or "<a" in body.lower() or "<form" in body.lower() or "<script" in body.lower():
            links.update(_html_paths(body))
            # Modern SPA/Next.js pages often embed route/API literals in inline
            # bootstrap JavaScript. Extract those before spending the bounded
            # request budget on static bundles.
            links.update(_inline_javascript_paths(body))
        if _looks_like_javascript(path, content_type):
            if path not in analyzed_bundles and len(analyzed_bundles) < max_js_bundles:
                analysis = _analyze_javascript_bundle(path, body)
                bundle_analyses.append(analysis)
                analyzed_bundles.add(path)
                links.update(analysis.endpoint_candidates)
            links.update(_javascript_paths(body))

        for candidate in sorted(links):
            normalized = _same_host_path(candidate, target)
            if not normalized or normalized in seen or normalized in queued:
                continue
            priority = _path_priority(normalized)
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

    materialization_plans = tuple(
        materialize_endpoint(endpoint, model.resources.values(), resource_provenance)
        for endpoint in sorted(model.endpoints.values(), key=lambda item: item.endpoint_id)
    )
    return Web2DiscoveryResult(
        model=model,
        observations=tuple(observations),
        discovered_paths=tuple(discovered),
        bundle_analyses=tuple(bundle_analyses),
        resource_provenance=tuple(resource_provenance),
        materialization_plans=materialization_plans,
    )


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


def _path_priority(path: str) -> int:
    """Rank discovered surfaces by expected security value without guessing paths.

    The execution budget is finite, so candidates that expose object identity,
    account state, transactions, ownership, or mutable workflows outrank
    generic application/static resources. This is only scheduling metadata:
    it never turns a path into a finding.
    """
    lowered = path.lower().split("?", 1)[0]
    score = 50

    if re.search(r"/(?:api|graphql|rpc|v[0-9]+)(?:/|$)", lowered):
        score = 100
    elif re.search(
        r"/(?:auth|account|accounts|user|users|profile|profiles|inventory|shop|shops|player|players|resource|resources|wallet|wallets|token|tokens|item|items|pack|packs|exchange|exchanges)(?:/|$)",
        lowered,
    ):
        score = 95
    elif re.search(r"/(?:chunks/app|chunks/pages|app|pages)(?:/|$)", lowered):
        score = 90

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


def _inline_javascript_paths(body: str) -> set[str]:
    """Extract URL-like literals only from inline ``<script>`` contents."""
    candidates: set[str] = set()
    for match in re.finditer(r"<script\b[^>]*>(.*?)</script\s*>", body, re.IGNORECASE | re.DOTALL):
        candidates.update(_javascript_paths(match.group(1)))
    return candidates


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


def _javascript_constants(body: str) -> dict[str, str]:
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
            value = _resolve_js_expression(expression, constants)
            if value is not None:
                constants[name] = value
                changed = True
        if not changed:
            break
    return constants


def _resolve_js_expression(expression: str, constants: dict[str, str]) -> str | None:
    expression = expression.strip()
    if not expression:
        return None

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
            value = _resolve_js_expression(part, constants)
            if value is None:
                return None
            resolved.append(value)
        return "".join(resolved)
    return None


def _request_method_from_context(context: str, default: str = "GET") -> str:
    match = re.search(r"""\bmethod\s*:\s*["']([A-Za-z]+)["']""", context, re.IGNORECASE)
    return match.group(1).upper() if match else default


def _analyze_javascript_bundle(path: str, body: str) -> Web2BundleAnalysis:
    """Recover statically-resolvable request construction without JS execution."""
    constants = _javascript_constants(body)
    base_urls: set[str] = set()
    methods: set[str] = set()
    candidates: set[str] = set()
    unresolved: set[str] = set()

    for match in re.finditer(
        rf"\b(?:baseURL|baseUrl|apiBase|apiBaseUrl|API_BASE_URL|API_BASE)\s*[:=]\s*({_JS_STRING}|{_IDENT})",
        body,
    ):
        value = _resolve_js_expression(match.group(1), constants)
        if value is not None:
            base_urls.add(value)

    patterns = (
        (rf"\bfetch\s*\(\s*([^,\)]+)([^\)]*)\)", "fetch"),
        (rf"\baxios\.(get|post|put|patch|delete|head|options)\s*\(\s*([^,\)]+)([^\)]*)\)", "axios"),
        (rf"\bnew\s+Request\s*\(\s*([^,\)]+)([^\)]*)\)", "request"),
        (rf"\.open\s*\(\s*['\"]([A-Za-z]+)['\"]\s*,\s*([^,\)]+)", "xhr"),
    )
    for pattern, kind in patterns:
        for match in re.finditer(pattern, body, re.IGNORECASE | re.DOTALL):
            if kind == "axios":
                method = match.group(1).upper()
                expression = match.group(2)
            elif kind == "xhr":
                method = match.group(1).upper()
                expression = match.group(2)
            else:
                expression = match.group(1)
                method = _request_method_from_context(match.group(0))
            methods.add(method)
            value = _resolve_js_expression(expression, constants)
            if value is None:
                unresolved.add(expression.strip()[:200])
            else:
                candidates.add(value)

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
            candidates.add(urljoin(second.rstrip("/") + "/", first))
        elif first is not None and first.startswith("/") and not first.startswith("//"):
            # The path literal is explicitly root-relative. Its meaning is
            # same-origin regardless of whether the base expression resolves.
            candidates.add(first)
        else:
            unresolved.add(match.group(0)[:200])

    if "$" + "{" in body and re.search(r"\b(?:fetch|Request|axios\.[A-Za-z]+)|\.open", body):
        unresolved.add("<dynamic-request-template>")
    candidates = {_canonicalize_discovery_candidate(candidate) for candidate in candidates if candidate}
    classification = "application" if candidates or base_urls or unresolved else "static_or_vendor"
    return Web2BundleAnalysis(
        path=path,
        classification=classification,
        base_urls=tuple(sorted(base_urls)),
        request_methods=tuple(sorted(methods)),
        endpoint_candidates=tuple(sorted(candidates)),
        unresolved_request_templates=tuple(sorted(unresolved)),
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
