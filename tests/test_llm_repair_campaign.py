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
