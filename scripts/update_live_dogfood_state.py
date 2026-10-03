#!/usr/bin/env python3
"""Refresh the durable live-dogfood checkpoint from a GitHub Actions run.

The script is intentionally dependency-light so the canonical workflow can run it
after the research artifact is produced. It preserves the diagnosis written by
the researcher and only refreshes machine-verifiable run metadata.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "docs" / "LIVE_DOGFOOD_STATE.md"


def gh_api(path: str) -> dict:
    token = os.environ["GITHUB_TOKEN"]
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "cydra-live-dogfood-checkpoint",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def replace_line(text: str, prefix: str, value: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            return "\n".join(lines) + "\n"
    return text


def main() -> None:
    run_id = os.environ["GITHUB_RUN_ID"]
    sha = os.environ["GITHUB_SHA"]
    run = gh_api(f"/repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}")
    artifacts = gh_api(
        f"/repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}/artifacts"
    ).get("artifacts", [])

    text = STATE.read_text(encoding="utf-8")
    text = replace_line(text, "- Branch: ", f"`{run.get('head_branch') or os.environ.get('GITHUB_REF_NAME', '')}`")
    text = replace_line(text, "- Current checkpoint commit: ", f"`{sha}`")
    text = replace_line(text, "- Workflow: ", f"`{run.get('name', 'unknown')}`")
    text = replace_line(text, "- Run: ", f"`{run_id}`")

    if artifacts:
        artifact = artifacts[0]
        artifact_id = artifact.get("id")
        artifact_name = artifact.get("name", "unknown")
        digest = artifact.get("digest") or "not reported"
        url = artifact.get("archive_download_url", "")
        text = replace_line(text, "- Artifact: ", f"`{artifact_id}` ({artifact_name})")
        text = replace_line(text, "- Artifact URL: ", url)
        text = replace_line(text, "- Artifact digest: ", f"`{digest}`")

    STATE.write_text(text, encoding="utf-8")

    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", "docs/LIVE_DOGFOOD_STATE.md"], check=True)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        check=False,
    )
    if result.returncode == 0:
        return
    subprocess.run(
        ["git", "commit", "-m", "chore: checkpoint live dogfood state"],
        check=True,
    )
    subprocess.run(["git", "push", "origin", f"HEAD:{run.get('head_branch')}"], check=True)


if __name__ == "__main__":
    main()
