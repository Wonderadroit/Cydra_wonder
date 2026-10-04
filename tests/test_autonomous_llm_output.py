from scripts.run_llm_repair_campaign import output_text, parse_llm_json


def test_output_text_reads_responses_api_output_text():
    assert output_text({"output_text": '{\"decision\":\"BOUNDARY\",\"reason\":\"x\",\"patch\":\"\"}'}) == (
        '{\"decision\":\"BOUNDARY\",\"reason\":\"x\",\"patch\":\"\"}'
    )


def test_output_text_reads_chat_completion_content():
    response = {"choices": [{"message": {"content": '{\"decision\":\"BOUNDARY\"}'}}]}
    assert output_text(response) == '{\"decision\":\"BOUNDARY\"}'


def test_output_text_reads_responses_content_text_variant():
    response = {"output": [{"content": [{"type": "text", "text": '{\"decision\":\"BOUNDARY\"}'}]}]}
    assert output_text(response) == '{\"decision\":\"BOUNDARY\"}'


def test_parse_llm_json_accepts_fenced_json():
    parsed, error = parse_llm_json('```json\\n{\"decision\":\"BOUNDARY\",\"reason\":\"x\",\"patch\":\"\"}\\n```')
    assert error == ""
    assert parsed["decision"] == "BOUNDARY"
