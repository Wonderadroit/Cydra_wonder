from pathlib import Path


def test_target_build_stack_depth_retries_via_ir(monkeypatch, tmp_path: Path):
    import scripts.run_benchmark_blind as runner

    calls = []

    class Result:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        if tuple(command) == ("forge", "build"):
            return Result(1, stderr="Error: Stack too deep. Try compiling with --via-ir")
        return Result(0, stdout="Compiler run successful")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner._command_capture(tmp_path, "forge", "build")

    assert calls == [("forge", "build"), ("forge", "build", "--via-ir")]
    assert result["ok"] is True
    assert result["command"] == ["forge", "build", "--via-ir"]
    assert result["fallback"]["trigger"] == "stack-too-deep"
    assert result["fallback"]["initial_exit_code"] == 1
