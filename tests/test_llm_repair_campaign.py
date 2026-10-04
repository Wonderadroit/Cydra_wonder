from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_llm_repair_campaign.py"


def load_module():
    spec = importlib.util.spec_from_file_location("cydra_llm_repair_campaign", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_text_reads_openrouter_chat_completion():
    module = load_module()
    response = {
        "choices": [{"message": {"role": "assistant", "content": '{"decision":"BOUNDARY","reason":"missing capability","patch":""}'}}]
    }
    assert module.output_text(response).startswith('{"decision":"BOUNDARY"')


def test_output_text_reads_openai_responses_output():
    module = load_module()
    response = {
        "output": [{"content": [{"type": "output_text", "text": '{"decision":"BOUNDARY","reason":"blocked","patch":""}'}]}]
    }
    assert module.output_text(response).startswith('{"decision":"BOUNDARY"')


def test_parse_llm_json_accepts_markdown_wrapped_json():
    module = load_module()
    value, error = module.parse_llm_json(
        '```json\n{"decision":"PATCH","reason":"generic fix","patch":"diff --git a/src/cydra/x.py b/src/cydra/x.py"}\n```'
    )
    assert error == ""
    assert value["decision"] == "PATCH"


def test_parse_llm_json_recovers_json_embedded_in_text():
    module = load_module()
    value, error = module.parse_llm_json(
        'Here is the proposal:\n{"decision":"BOUNDARY","reason":"unsupported","patch":""}\n'
    )
    assert error == ""
    assert value["decision"] == "BOUNDARY"


def test_parse_llm_json_rejects_non_object():
    module = load_module()
    value, error = module.parse_llm_json('[]')
    assert value is None
    assert error == ""


def test_patch_paths_stay_fail_closed():
    module = load_module()
    assert module.ALLOWED_PATCH_ROOTS == ("src/cydra/", "tests/", "scripts/")
    assert "targets/" in module.FORBIDDEN_PATCH_ROOTS
    assert "scripts/run_llm_repair_campaign.py" in module.FORBIDDEN_PATCH_ROOTS


def test_proposal_contract_requires_existing_allowed_files():
    module = load_module()
    ok, error = module.proposal_paths_are_safe({
        "decision": "PATCH",
        "reason": "generic fix",
        "required_files": ["src/cydra/capability_repair.py"],
        "expected_tests": ["python -m pytest"],
        "patch": "diff --git a/src/cydra/capability_repair.py b/src/cydra/capability_repair.py\n--- a/src/cydra/capability_repair.py\n+++ b/src/cydra/capability_repair.py\n@@ -1 +1 @@\n-x\n+y\n",
    })
    assert ok
    assert error == ""


def test_proposal_contract_rejects_unsafe_or_missing_files():
    module = load_module()
    ok, error = module.proposal_paths_are_safe({
        "required_files": ["targets/live-contest.json"],
        "expected_tests": [],
    })
    assert not ok
    assert "forbidden required_files" in error

    ok, error = module.proposal_paths_are_safe({
        "required_files": ["src/cydra/does_not_exist.py"],
        "expected_tests": [],
    })
    assert not ok
    assert "do not exist" in error


def test_patch_structure_rejects_plain_text_and_incomplete_hunks():
    module = load_module()
    ok, error = module.patch_is_structurally_valid("please edit this file")
    assert not ok
    assert "unified git diff" in error

    ok, error = module.patch_is_structurally_valid(
        "diff --git a/src/cydra/x.py b/src/cydra/x.py\n--- a/src/cydra/x.py\n+++ b/src/cydra/x.py\n"
    )
    assert not ok
    assert "incomplete" in error


def test_patch_structure_rejects_forbidden_paths():
    module = load_module()
    ok, error = module.patch_is_structurally_valid(
        "diff --git a/.github/workflows/x.yml b/.github/workflows/x.yml\n"
        "--- a/.github/workflows/x.yml\n+++ b/.github/workflows/x.yml\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    assert not ok
    assert "forbidden patch paths" in error
