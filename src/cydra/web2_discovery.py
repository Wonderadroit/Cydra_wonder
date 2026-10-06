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
    sequence = 0

    for seed in _normalize_seeds(seeds):
        heapq.heappush(queue, (-_path_priority(seed), sequence, seed))
        queued.add(seed)
        sequence += 1

    observations: list[AdapterObservation] = []
    discovered: list[str] = []
    bundle_analyses: list[Web2BundleAnalysis] = []
    analyzed_bundles: set[str] = set()

    while queue and len(seen) < max_paths:
        _, _, path = heapq.heappop(queue)
        if path in seen:
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
        model.add_endpoint(Web2EndpointModel(endpoint_id, "GET", path))
        discovered.append(path)

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
            if len(seen) + len(queue) >= max_paths:
                continue
            heapq.heappush(queue, (-_path_priority(normalized), sequence, normalized))
            queued.add(normalized)
            sequence += 1

    return Web2DiscoveryResult(
        model=model,
        observations=tuple(observations),
        discovered_paths=tuple(discovered),
        bundle_analyses=tuple(bundle_analyses),
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


def _same_host_path(value: str, target: str) -> str | None:
    absolute = urljoin(target.rstrip("/") + "/", value)
    parsed = urlparse(absolute)
    target_parsed = urlparse(target)
    if parsed.hostname != target_parsed.hostname:
        return None
    path = parsed.path or "/"
    return path + (f"?{parsed.query}" if parsed.query else "")


def _path_priority(path: str) -> int:
    """Rank known application surfaces without guessing new paths."""
    lowered = path.lower().split("?", 1)[0]
    if re.search(r"/(?:api|graphql|rpc|v[0-9]+)(?:/|$)", lowered):
        return 100
    if re.search(
        r"/(?:auth|account|accounts|user|users|profile|profiles|inventory|shop|shops|player|players|resource|resources)(?:/|$)",
        lowered,
    ):
        return 95
    if re.search(r"/(?:chunks/app|chunks/pages|app|pages)(?:/|$)", lowered):
        return 90
    if re.search(r"/(?:framework|webpack|polyfills|vendor)(?:[-_/]|\.|$)", lowered):
        return 65
    if lowered.endswith((".js", ".mjs")) or ".js/" in lowered or ".js?" in lowered:
        return 80
    if lowered.endswith((".json", ".yaml", ".yml")):
        return 70
    if lowered.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".css", ".woff", ".woff2")):
        return 10
    return 50


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
    for match in re.finditer(r"<script\\b[^>]*>(.*?)</script\\s*>", body, re.IGNORECASE | re.DOTALL):
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



_JS_STRING = r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\\x60(?:\\.|[^\\x60\\])*\\x60)"""
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
    constants: dict[str, str] = {}
    pattern = re.compile(rf"\b(?:const|let|var)\s+({_IDENT})\s*=\s*({_JS_STRING})")
    for match in pattern.finditer(body):
        value = _decode_js_string(match.group(2))
        if value is not None:
            constants[match.group(1)] = value
    return constants


def _resolve_js_expression(expression: str, constants: dict[str, str]) -> str | None:
    expression = expression.strip()
    if not expression:
        return None
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
        rf"\b(?:baseURL|baseUrl|apiBase|apiBaseUrl|API_BASE_URL)\s*[:=]\s*({_JS_STRING}|{_IDENT})",
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
        first_expression = match.group(1).strip()
        second_expression = match.group(2).strip()
        first = _resolve_js_expression(first_expression, constants)
        second = _resolve_js_expression(second_expression, constants)

        # Bundled clients commonly construct routes as
        # new URL("/v1/resource", apiBase), where apiBase is supplied by an
        # imported/runtime value that cannot be resolved lexically. The route
        # literal is still concrete enough to materialize as a same-host
        # discovery path without guessing the base URL.
        if first is not None and first.startswith("/"):
            candidates.add(first)
            if second is None:
                unresolved.add(match.group(0)[:200])
                continue

        if first is not None and second is not None:
            candidates.add(urljoin(second.rstrip("/") + "/", first))
        else:
            unresolved.add(match.group(0)[:200])

    if "$" + "{" in body and re.search(r"\b(?:fetch|Request|axios\.[A-Za-z]+)|\.open", body):
        unresolved.add("<dynamic-request-template>")
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
