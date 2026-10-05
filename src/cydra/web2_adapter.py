from __future__ import annotations

"""Authorized, allowlisted HTTP execution adapter for CYDRA."""

from dataclasses import dataclass, field
import hashlib
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from .execution_adapter import AdapterCapability, AdapterObservation, AdapterRequest, AdapterStatus


@dataclass(frozen=True)
class Web2Target:
    base_url: str
    allowed_hosts: tuple[str, ...]
    authorized: bool = False
    timeout_seconds: float = 15.0

    def validate(self) -> None:
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Web2 target must use an absolute HTTP(S) URL")
        if not self.authorized:
            raise PermissionError("Web2 active execution requires explicit authorization")
        if parsed.hostname not in self.allowed_hosts:
            raise PermissionError("Web2 target host is outside the adapter allowlist")


@dataclass
class Web2Identity:
    identity_id: str
    headers: dict[str, str] = field(default_factory=dict)


class Web2Adapter:
    adapter_id = "web2-http-v1"

    def __init__(self, target: Web2Target, *, identities: Mapping[str, Web2Identity] | None = None) -> None:
        target.validate()
        self.target = target
        self._identities = dict(identities or {})
        self._jars: dict[str, http.cookiejar.CookieJar] = {}

    def capabilities(self) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability("HTTP_REQUEST", True, "GET/POST/PUT/PATCH/DELETE"),
            AdapterCapability("IDENTITY_SWITCH", True, "isolated cookie jars and headers"),
            AdapterCapability("RESPONSE_OBSERVATION", True, "status, headers, body digest and body"),
            AdapterCapability("STATE_REPLAY", True, "repeat an identical request under an identity"),
        )

    def execute(self, request: AdapterRequest) -> AdapterObservation:
        if request.operation != "http_request":
            return AdapterObservation(AdapterStatus.UNAVAILABLE, request.action_id, error=f"unsupported Web2 operation: {request.operation}")
        try:
            observation = self.request(
                method=str(request.inputs.get("method", "GET")),
                path=str(request.inputs.get("path", "/")),
                identity_id=request.inputs.get("identity_id"),
                headers=request.inputs.get("headers") or {},
                body=request.inputs.get("body"),
            )
        except (OSError, ValueError, PermissionError) as error:
            return AdapterObservation(AdapterStatus.BLOCKED if isinstance(error, PermissionError) else AdapterStatus.FAILED, request.action_id, error=str(error))
        return AdapterObservation(AdapterStatus.EXECUTED, request.action_id, value=observation, evidence=(observation,))

    def request(self, *, method: str, path: str, identity_id: str | None = None,
                headers: Mapping[str, str] | None = None, body: Any = None) -> Mapping[str, Any]:
        url = urllib.parse.urljoin(self.target.base_url.rstrip("/") + "/", path.lstrip("/"))
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname not in self.target.allowed_hosts:
            raise PermissionError("request host is outside the Web2 target allowlist")
        identity = self._identities.get(identity_id) if identity_id else None
        jar = self._jars.setdefault(identity_id or "__anonymous__", http.cookiejar.CookieJar())
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        merged_headers = {"User-Agent": "CYDRA-Web2-Adapter/1.0"}
        if identity: merged_headers.update(identity.headers)
        merged_headers.update(dict(headers or {}))
        payload = None
        if body is not None:
            if isinstance(body, bytes): payload = body
            elif isinstance(body, str): payload = body.encode("utf-8")
            else:
                payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
                merged_headers.setdefault("Content-Type", "application/json")
        request_obj = urllib.request.Request(url, data=payload, headers=merged_headers, method=method.upper())
        try:
            response = opener.open(request_obj, timeout=self.target.timeout_seconds)
            status = response.status
            response_headers = dict(response.headers.items())
            raw_body = response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            response_headers = dict(error.headers.items())
            raw_body = error.read()
        except urllib.error.URLError as error:
            raise OSError(f"HTTP transport failed: {error.reason}") from error
        body_text = raw_body.decode("utf-8", errors="replace")
        return {"url": url, "method": method.upper(), "identity_id": identity_id,
                "status_code": status, "headers": response_headers, "body": body_text,
                "body_sha256": hashlib.sha256(raw_body).hexdigest()}

    def export_state(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps({"adapter": self.adapter_id, "target": self.target.base_url,
                                           "identities": sorted(self._identities)}, indent=2) + "
", encoding="utf-8")
