from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = os.getenv("CYDRA_LLM_PROVIDER", "openai").strip().lower()
MODEL = os.getenv("CYDRA_LLM_MODEL", "openrouter/free" if PROVIDER == "openrouter" else "gpt-5.6-sol")
BASE_URL = os.getenv("CYDRA_LLM_BASE_URL", "https://openrouter.ai/api/v1" if PROVIDER == "openrouter" else "https://api.openai.com/v1").rstrip("/")
API_KEY = os.getenv("CYDRA_LLM_API_KEY", "").strip() or os.getenv("OPENROUTER_API_KEY" if PROVIDER == "openrouter" else "OPENAI_API_KEY", "").strip()
MAX_HOURS = float(os.getenv("CYDRA_EMERGENCY_MAX_HOURS", "6"))
MAX_ATTEMPTS = int(os.getenv("CYDRA_LLM_MAX_ATTEMPTS", "20"))
ALLOWED_PATCH_ROOTS = ("src/cydra/", "tests/", "scripts/")
FORBIDDEN_PATCH_ROOTS = (".github/", "targets/", ".git/", "scripts/run_llm_repair_campaign.py")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def api(prompt: str):
    key = API_KEY
    if not key:
        return None
    body = {
        "model": MODEL,
        "instructions": (
            "You are CYDRA's autonomous generic repair engineer. "
            "LLMs propose; deterministic tools test; evidence decides. "
            "Repair CYDRA only, never the target. "
            "No target-specific detectors, fake evidence, weakened fail-closed behavior, "
            "workflow/secrets changes, or bounty conclusions. "
            "Return JSON only with decision PATCH or BOUNDARY, reason, patch. "
            "The patch must be a unified git diff. Do not return commands."
        ),
        "input": prompt,
        "max_output_tokens": 14000,
    }
    req = urllib.request.Request(
        f"{BASE_URL}/responses",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print("LLM request failed:", exc)
        return None


def output_text(response) -> str:
    if not response:
        return ""
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    return "\n".join(
        str(part.get("text", ""))
        for item in response.get("output", []) or []
        for part in item.get("content", []) or []
        if part.get("type") == "output_text"
    )


def files_for(capability: str) -> list[str]:
    """Find relevant source files without relying on an external search binary."""
    matches: list[str] = []
    for root_name in ("src", "tests", "scripts"):
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            if capability in text:
                matches.append(path.relative_to(ROOT).as_posix())
    return list(
        dict.fromkeys(
            [
                "AGENTS.md",
                "PROJECT_BIBLE.md",
                "src/cydra/capability_repair.py",
                "scripts/run_live_contest.py",
            ]
            + sorted(matches)[:25]
        )
    )

def context(artifact: Path, capability: str) -> str:
    campaign_path = artifact / "capability_campaign.json"
    campaign = campaign_path.read_text() if campaign_path.exists() else "{}"
    parts = [f"CAPABILITY: {capability}", "CAMPAIGN:\n" + campaign[:50000]]
    for relative in files_for(capability):
        path = ROOT / relative
        if path.is_file():
            parts.append(f"\nFILE {relative}\n{path.read_text(errors='replace')[:30000]}")
    return "\n".join(parts)


def patch_paths_are_safe() -> tuple[bool, str]:
    diff = run(["git", "diff", "--name-only", "--diff-filter=ACDMRT"])
    if diff.returncode != 0:
        return False, diff.stderr[:4000]
    paths = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    status = run(["git", "status", "--porcelain"])
    if status.returncode != 0:
        return False, status.stderr[:4000]
    paths.extend(line[3:].strip() for line in status.stdout.splitlines() if line.startswith("?? "))
    unsafe = [
        path for path in paths
        if path.startswith(FORBIDDEN_PATCH_ROOTS)
        or not path.startswith(ALLOWED_PATCH_ROOTS)
    ]
    if unsafe:
        return False, "forbidden patch paths: " + ", ".join(unsafe)
    return True, ""


def apply_patch(patch: str) -> tuple[bool, str]:
    if not patch.strip():
        return False, "empty patch"
    patch_file = ROOT / ".cydra-llm.patch"
    patch_file.write_text(patch)
    try:
        check = run(["git", "apply", "--check", "--whitespace=nowarn", str(patch_file)])
        if check.returncode:
            return False, check.stderr[:8000]
        applied = run(["git", "apply", "--whitespace=nowarn", str(patch_file)])
        if applied.returncode:
            return False, (applied.stderr or applied.stdout)[:8000]
        safe, reason = patch_paths_are_safe()
        if not safe:
            run(["git", "reset", "--hard", "HEAD"])
            return False, reason
        return True, (applied.stderr or applied.stdout)[:8000]
    finally:
        patch_file.unlink(missing_ok=True)


def parse_llm_json(raw: str) -> tuple[dict | None, str]:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
        return (value if isinstance(value, dict) else None), ""
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start:end + 1])
                return (value if isinstance(value, dict) else None), ""
            except json.JSONDecodeError:
                pass
        return None, f"invalid JSON: {exc}"


def main() -> int:
    if not API_KEY:
        print("No LLM API key configured for provider:", PROVIDER)
        return 0

    started = time.time()
    target = [
        "python",
        "scripts/run_live_contest.py",
        "--target-spec",
        "targets/live-contest.json",
        "--target-checkout",
        ".cydra-live-target",
        "--output",
        "live-artifacts",
    ]

    blocked_capabilities: set[str] = set()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if time.time() - started >= MAX_HOURS * 3600:
            break

        print(f"=== autonomous repair/replay cycle {attempt} ===")
        artifact = ROOT / "live-artifacts"
        if artifact.exists():
            shutil.rmtree(artifact)
        artifact.mkdir(parents=True, exist_ok=True)
        result = run(target)
        campaign_path = artifact / "capability_campaign.json"
        campaign = json.loads(campaign_path.read_text()) if campaign_path.exists() else {}
        clusters = campaign.get("capability_clusters") or []

        if not clusters:
            print("No capability frontier remains.")
            return 0

        available = [cluster for cluster in clusters if str(cluster.get("capability") or "") not in blocked_capabilities]
        if not available:
            print("No unblocked capability frontier remains.")
            return 0
        capability = str(available[0].get("capability") or "")
        if not capability:
            print("Capability frontier entry has no capability name; failing closed.")
            return 0

        base_prompt = (
            context(artifact, capability)
            + "\n\nRunner output:\n"
            + result.stdout[-12000:]
            + result.stderr[-12000:]
        )
        feedback = ""
        proposal = {}
        for repair_attempt in range(1, 4):
            if time.time() - started >= MAX_HOURS * 3600:
                break
            prompt = base_prompt
            if feedback:
                prompt += (
                    "\n\nPREVIOUS PROPOSAL VALIDATION FAILED. "
                    "Correct the proposal using this exact deterministic error. "
                    "Return JSON only; do not explain outside the JSON.\n"
                    + feedback[:8000]
                )
            proposal_response = api(prompt)
            raw = output_text(proposal_response)
            proposal, parse_error = parse_llm_json(raw)
            if proposal is None:
                feedback = parse_error + "\nLLM output:\n" + raw[:6000]
                print(f"LLM response attempt {repair_attempt} invalid:", parse_error)
                continue

            if proposal.get("decision") != "PATCH":
                print("LLM boundary:", proposal.get("reason", ""))
                blocked_capabilities.add(capability)
                break

            ok, message = apply_patch(str(proposal.get("patch") or ""))
            print(f"patch attempt {repair_attempt}:", ok, message)
            if ok:
                break
            feedback = "patch validation failed: " + message
            proposal = {}

        if proposal.get("decision") != "PATCH":
            continue
        if not proposal.get("patch"):
            blocked_capabilities.add(capability)
            print("PATCH decision contained no patch; failing closed.")
            continue

        # The model never supplies the executable test command. CYDRA owns the
        # deterministic regression command so the model cannot turn validation
        # into arbitrary CI command execution.
        regression = run(["python", "-m", "pytest"])
        if regression.returncode != 0:
            print("regression failed; reverting patch and continuing")
            run(["git", "reset", "--hard", "HEAD"])
            blocked_capabilities.add(capability)
            continue

        print("regression passed; replaying exact frozen target on next cycle.")

    print("Emergency autonomous repair ceiling reached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
