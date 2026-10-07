from __future__ import annotations

"""Capture a browser-authenticated Web2 session for explicit handoff to CYDRA.

Run locally. The generated JSON is a credential file: keep it outside the
repository and never upload it as an artifact.
"""

import argparse
import json
from pathlib import Path
import urllib.parse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Authorized Web2 target origin.")
    parser.add_argument("--identity-id", default="owner")
    parser.add_argument("--output", default=".cydra/web2-session.json")
    parser.add_argument(
        "--header",
        action="append",
        default=["authorization"],
        help="Request header name to capture from browser traffic; repeatable.",
    )
    parser.add_argument("--headed", action="store_true", default=True)
    args = parser.parse_args()

    origin = urllib.parse.urlparse(args.target)
    if origin.scheme not in {"http", "https"} or not origin.hostname:
        raise SystemExit("--target must be an absolute HTTP(S) URL")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise SystemExit(
            "Playwright is required for local browser capture. Install it separately "
            "with 'pip install playwright' and 'playwright install chromium'."
        ) from error

    captured_headers: dict[str, str] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)

        def observe_request(request) -> None:
            parsed = urllib.parse.urlparse(request.url)
            if parsed.hostname != origin.hostname:
                return
            wanted = {name.lower() for name in args.header}
            for name, value in request.headers.items():
                if name.lower() in wanted and value:
                    captured_headers[name] = value

        context = browser.new_context()
        page = context.new_page()
        page.on("request", observe_request)
        page.goto(args.target, wait_until="domcontentloaded")
        print("Browser opened. Log in to the authorized target, then return here.")
        input("Press Enter after authentication is complete... ")

        cookies = context.cookies()
        browser.close()

    normalized_cookies = [
        {
            "name": item["name"],
            "value": item["value"],
            "domain": item["domain"],
            "path": item.get("path", "/"),
            "secure": bool(item.get("secure", True)),
            "http_only": bool(item.get("httpOnly", False)),
        }
        for item in cookies
        if urllib.parse.urlparse(args.target).hostname == item["domain"].lstrip(".")
        or urllib.parse.urlparse(args.target).hostname.endswith("." + item["domain"].lstrip("."))
    ]

    payload = {
        "version": 1,
        "session_id": args.identity_id,
        "target_origin": f"{origin.scheme}://{origin.hostname}",
        "headers": captured_headers,
        "cookies": normalized_cookies,
        "source": "playwright-local-browser",
    }

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    destination.chmod(0o600)
    print(f"Captured authenticated session to {destination}")
    print("Do not commit or upload this file. Treat it as a live credential.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
