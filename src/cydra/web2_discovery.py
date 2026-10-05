from __future__ import annotations

"""Safe, target-independent Web2 surface discovery.

Discovery is intentionally limited to caller-provided seed paths and
server-declared links/specs. It does not brute-force paths or treat discovery
output as a security finding.
"""

from dataclasses import dataclass
import json
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
        if tag.lower() not in {"a", "link", "form"}:
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.add(value)
            elif tag.lower() == "form" and key.lower() == "action" and value:
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
    """
    if max_paths < 1:
        raise ValueError("max_paths must be positive")

    model = Web2TargetModel(target=target)
    queue = _normalize_seeds(seeds)
    seen: set[str] = set()
    observations: list[AdapterObservation] = []
    discovered: list[str] = []

    while queue and len(seen) < max_paths:
        path = queue.pop(0)
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
        status = payload.get("status_code")
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
        if "html" in content_type or "<a" in body.lower() or "<form" in body.lower():
            links.update(_html_paths(body))

        for candidate in sorted(links):
            normalized = _same_host_path(candidate, target)
            if normalized and normalized not in seen and len(seen) + len(queue) < max_paths:
                queue.append(normalized)

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


def _html_paths(body: str) -> set[str]:
    parser = _LinkParser()
    parser.feed(body)
    return {link for link in parser.links if link.startswith(("/", "?"))}


def _openapi_paths(body: str) -> set[str]:
    try:
        document = json.loads(body)
    except json.JSONDecodeError:
        return set()
    paths = document.get("paths") if isinstance(document, dict) else None
    if not isinstance(paths, dict):
        return set()
    return {str(path) for path in paths if str(path).startswith("/")}


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
