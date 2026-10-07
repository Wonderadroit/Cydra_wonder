from __future__ import annotations

"""Generic authenticated Web2 session handoff.

The session is an execution credential, not evidence. It is accepted only from
an explicit local file or environment variable and is never serialized by the
discovery artifact layer.
"""

from dataclasses import dataclass, field
import base64
import json
from pathlib import Path
from typing import Any, Mapping
import urllib.parse


@dataclass(frozen=True)
class Web2Cookie:
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = True
    http_only: bool = False


@dataclass(frozen=True)
class Web2Session:
    session_id: str
    target_origin: str
    headers: Mapping[str, str] = field(default_factory=dict)
    cookies: tuple[Web2Cookie, ...] = ()
    source: str = "external"

    @property
    def authenticated(self) -> bool:
        return bool(self.headers or self.cookies)

    def validate_for(self, target_origin: str, allowed_hosts: tuple[str, ...]) -> None:
        requested = urllib.parse.urlparse(target_origin)
        captured = urllib.parse.urlparse(self.target_origin)
        if requested.scheme not in {"http", "https"} or not requested.hostname:
            raise ValueError("target origin must be an absolute HTTP(S) URL")
        if requested.hostname not in allowed_hosts:
            raise PermissionError("session target host is outside the Web2 target allowlist")
        if captured.scheme and captured.scheme != requested.scheme:
            raise PermissionError("session scheme does not match the Web2 target")
        if captured.hostname and captured.hostname != requested.hostname:
            raise PermissionError("session target host does not match the Web2 target")

        for cookie in self.cookies:
            if not cookie.name or not cookie.domain:
                raise ValueError("session cookie must have a name and domain")
            if not _cookie_domain_matches(cookie.domain, requested.hostname):
                raise PermissionError("session cookie domain is outside the Web2 target host")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, default_target_origin: str) -> "Web2Session":
        version = payload.get("version", 1)
        if version != 1:
            raise ValueError(f"unsupported Web2 session version: {version}")

        target_origin = str(payload.get("target_origin") or default_target_origin).strip()
        session_id = str(payload.get("session_id") or "owner").strip()
        if not session_id:
            raise ValueError("session_id must not be empty")

        headers_raw = payload.get("headers") or {}
        if not isinstance(headers_raw, Mapping):
            raise ValueError("session headers must be an object")
        headers = {str(k): str(v) for k, v in headers_raw.items() if str(k).strip()}

        cookies: list[Web2Cookie] = []
        raw_cookies = payload.get("cookies") or []
        if not isinstance(raw_cookies, list):
            raise ValueError("session cookies must be an array")
        for raw in raw_cookies:
            if not isinstance(raw, Mapping):
                raise ValueError("each session cookie must be an object")
            cookies.append(
                Web2Cookie(
                    name=str(raw.get("name") or ""),
                    value=str(raw.get("value") or ""),
                    domain=str(raw.get("domain") or ""),
                    path=str(raw.get("path") or "/"),
                    secure=bool(raw.get("secure", True)),
                    http_only=bool(raw.get("http_only", raw.get("httpOnly", False))),
                )
            )

        return cls(
            session_id=session_id,
            target_origin=target_origin,
            headers=headers,
            cookies=tuple(cookies),
            source=str(payload.get("source") or "external"),
        )

    @classmethod
    def from_file(cls, path: str | Path, *, default_target_origin: str) -> "Web2Session":
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"Web2 session file not found: {source}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("Web2 session file must contain a JSON object")
        return cls.from_mapping(payload, default_target_origin=default_target_origin)

    @classmethod
    def from_base64(cls, encoded: str, *, default_target_origin: str) -> "Web2Session":
        if not encoded.strip():
            raise ValueError("empty Web2 session secret")
        try:
            raw = base64.b64decode(encoded, validate=True)
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid base64-encoded Web2 session JSON") from error
        if not isinstance(payload, Mapping):
            raise ValueError("Web2 session secret must contain a JSON object")
        return cls.from_mapping(payload, default_target_origin=default_target_origin)

    def to_identity_kwargs(self) -> dict[str, Any]:
        return {
            "identity_id": self.session_id,
            "headers": dict(self.headers),
            "cookies": self.cookies,
            "authenticated": self.authenticated,
        }


def _cookie_domain_matches(cookie_domain: str, hostname: str) -> bool:
    domain = cookie_domain.lstrip(".").lower()
    host = hostname.lower()
    return host == domain or host.endswith("." + domain)
