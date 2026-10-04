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
LLM_REPAIR_ATTEMPTS = int(os.getenv("CYDRA_LLM_REPAIR_ATTEMPTS", "3"))
ALLOWED_PATCH_ROOTS = ("src/cydra/", "tests/", "scripts/")
FORBIDDEN_PATCH_ROOTS = (".github/", "targets/", ".git/", "scripts/run_llm_repair_campaign.py")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def api(prompt: str):
    key = API_KEY
    if not key:
        return None

    system_prompt = (
        "You are CYDRA's autonomous generic repair engineer. "
        "LLMs propose; deterministic tools test; evidence decides. "
        "Repair CYDRA only, never the target. "
        "No target-specific detectors, fake evidence, weakened fail-closed behavior, "
        "workflow/secrets changes, or bounty conclusions. "
        "Return exactly one JSON object with decision PATCH or BOUNDARY, reason, required_files, expected_tests, and patch. "
        "For PATCH, required_files must list the CYDRA source files you intend to change and expected_tests must list deterministic test names or commands that CYDRA can verify. "
        "The patch must be a complete unified git diff whose hunks can be applied to the supplied checkout. Do not return commands."
    )
    schema = {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["PATCH", "BOUNDARY"]},
            "reason": {"type": "string"},
            "required_files": {"type": "array", "items": {"type": "string"}},
            "expected_tests": {"type": "array", "items": {"type": "string"}},
            "patch": {"type": "string"},
        },
        "required": ["decision", "reason", "required_files", "expected_tests", "patch"],
        "additionalProperties": False,
    }

    if PROVIDER == "openrouter":
        body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 14000,
            "response_format": {"type": "json_object"},
        }
        endpoint = f"{BASE_URL}/chat/completions"
    else:
        body = {
            "model": MODEL,
            "instructions": system_prompt,
            "input": prompt,
            "max_output_tokens": 14000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "cydra_repair_proposal",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        endpoint = f"{BASE_URL}/responses"

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode(errors="replace")
        except Exception:
            detail = ""
        print("LLM request failed:", exc, detail[:4000])
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        print("LLM request failed:", exc)
        return None


def output_text(response) -> str:
    if not response:
        return ""

    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct

    choices = response.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)

    parts = []
    for item in response.get("output", []) or []:
        for part in item.get("content", []) or []:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif part.get("type") in {"output_text", "text"}:
                    value = part.get("value")
                    if isinstance(value, str):
                        parts.append(value)
    return "\n".join(parts)


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


def capability_source_files(capability: str) -> list[str]:
    """Return editable CYDRA implementation files that actually mention a capability."""
    matches: list[str] = []
    for path in (ROOT / "src" / "cydra").rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if capability in text:
            matches.append(path.relative_to(ROOT).as_posix())
    return sorted(matches)


def proposal_paths_are_safe(proposal: dict) -> tuple[bool, str]:
    """Validate the proposal contract before attempting to apply model output."""
    required = proposal.get("required_files")
    if not isinstance(required, list) or not required:
        return False, "PATCH proposal must declare non-empty required_files"
    if not all(isinstance(path, str) and path for path in required):
        return False, "required_files must contain only non-empty strings"
    unsafe = [
        path for path in required
        if path.startswith(FORBIDDEN_PATCH_ROOTS) or not path.startswith(ALLOWED_PATCH_ROOTS)
    ]
    if unsafe:
        return False, "forbidden required_files: " + ", ".join(unsafe)
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        return False, "required_files do not exist: " + ", ".join(missing)
    tests = proposal.get("expected_tests")
    if not isinstance(tests, list) or not all(isinstance(item, str) for item in tests):
        return False, "expected_tests must be a list of strings"
    return True, ""


def patch_paths_from_text(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git a/") and " b/" in line:
            paths.append(line[len("diff --git a/"):].split(" b/", 1)[0])
    return list(dict.fromkeys(paths))


def patch_is_structurally_valid(patch: str) -> tuple[bool, str]:
    if not patch.strip():
        return False, "empty patch"
    paths = patch_paths_from_text(patch)
    if not paths:
        return False, "patch is not a unified git diff (missing diff --git headers)"
    if "--- " not in patch or "+++ " not in patch or "@@" not in patch:
        return False, "patch is structurally incomplete: expected ---/+++/@@ hunks"
    unsafe = [
        path for path in paths
        if path.startswith(FORBIDDEN_PATCH_ROOTS) or not path.startswith(ALLOWED_PATCH_ROOTS)
    ]
    if unsafe:
        return False, "forbidden patch paths: " + ", ".join(unsafe)
    return True, ""


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
    structurally_valid, structural_reason = patch_is_structurally_valid(patch)
    if not structurally_valid:
        return False, structural_reason
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


def write_llm_artifact(attempt: int, name: str, value: object) -> None:
    root = ROOT / "live-artifacts" / "llm-repair" / f"cycle-{attempt:03d}"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def frontier_counts(campaign: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for cluster in campaign.get("capability_clusters") or []:
        if not isinstance(cluster, dict):
            continue
        key = str(cluster.get("capability") or "")
        if key:
            counts[key] = counts.get(key, 0) + int(cluster.get("count") or 1)
    return counts


def main() -> int:
    if not API_KEY:
        print("No LLM API key configured for provider:", PROVIDER)
        write_llm_artifact(0, "status.json", {
            "status": "llm_unconfigured",
            "provider": PROVIDER,
            "message": "Deterministic CYDRA repair/replay remains authoritative; LLM handoff was not attempted.",
        })
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
        write_llm_artifact(attempt, "frontier-before.json", campaign)
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

        editable_surface = capability_source_files(capability)
        base_prompt = (
            context(artifact, capability)
            + "\n\nEDITABLE IMPLEMENTATION SURFACE (deterministic scan):\n"
            + ("\n".join(editable_surface) if editable_surface else "NONE — do not invent a source file; return BOUNDARY if no generic repair surface exists.")
            + "\n\nRunner output:\n"
            + result.stdout[-12000:]
            + result.stderr[-12000:]
        )
        feedback = ""
        proposal = {}
        for repair_attempt in range(1, LLM_REPAIR_ATTEMPTS + 1):
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
            write_llm_artifact(attempt, f"llm-response-{repair_attempt}.txt", raw)
            parsed, parse_error = parse_llm_json(raw)
            if parsed is None:
                proposal = {}
                feedback = parse_error + "\nLLM output:\n" + raw[:6000]
                write_llm_artifact(attempt, f"validation-{repair_attempt}.json", {
                    "status": "invalid_response",
                    "error": parse_error,
                })
                print(f"LLM response attempt {repair_attempt} invalid:", parse_error)
                continue
            proposal = parsed
            write_llm_artifact(attempt, "proposal.json", proposal)

            if proposal.get("decision") != "PATCH":
                write_llm_artifact(attempt, "proposal.json", proposal)
                write_llm_artifact(attempt, "validation.json", {
                    "status": "boundary",
                    "capability": capability,
                    "reason": proposal.get("reason", ""),
                })
                print("LLM boundary:", proposal.get("reason", ""))
                blocked_capabilities.add(capability)
                break

            proposal_safe, proposal_error = proposal_paths_are_safe(proposal)
            if not proposal_safe:
                feedback = "proposal validation failed: " + proposal_error
                proposal = {}
                write_llm_artifact(attempt, f"validation-{repair_attempt}.json", {
                    "status": "invalid_proposal",
                    "error": proposal_error,
                })
                print(f"proposal attempt {repair_attempt} invalid:", proposal_error)
                continue
            ok, message = apply_patch(str(proposal.get("patch") or ""))
            write_llm_artifact(attempt, f"patch-validation-{repair_attempt}.json", {
                "status": "applied" if ok else "rejected",
                "message": message,
            })
            print(f"patch attempt {repair_attempt}:", ok, message)
            if ok:
                touched = set(patch_paths_from_text(str(proposal.get("patch") or "")))
                required = set(proposal.get("required_files") or [])
                if not touched & required:
                    run(["git", "reset", "--hard", "HEAD"])
                    feedback = "patch validation failed: patch does not touch any declared required_file"
                    proposal = {}
                    print(f"patch attempt {repair_attempt} rejected:", feedback)
                    continue
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
        write_llm_artifact(attempt, "regression.json", {
            "exit_code": regression.returncode,
            "passed": regression.returncode == 0,
            "stdout": regression.stdout[-12000:],
            "stderr": regression.stderr[-12000:],
        })
        if regression.returncode != 0:
            print("regression failed; reverting patch and continuing")
            run(["git", "reset", "--hard", "HEAD"])
            blocked_capabilities.add(capability)
            continue

        write_llm_artifact(attempt, "handoff.json", {
            "status": "REPAIR_ACCEPTED_FOR_EXACT_REPLAY",
            "capability": capability,
            "required_files": proposal.get("required_files", []),
            "expected_tests": proposal.get("expected_tests", []),
            "next_action": "run_live_contest.py on the same pinned target and refresh capability_campaign.json",
        })
        print("regression passed; handing the repaired workspace back to the exact frozen-target replay.")

    print("Emergency autonomous repair ceiling reached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
