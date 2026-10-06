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
class Web2DiscoveryResult:
    model: Web2TargetModel
    observations: tuple[AdapterObservation, ...]
    discovered_paths: tuple[str, ...]


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
