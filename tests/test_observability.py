from opportunity_intel.observability.trace import agent_run, clip, redact


def test_redact_secrets() -> None:
    assert "[redacted]" in redact("key sk-abc123token")
    assert "gsk_" not in redact("gsk_ABCDEFG123")


def test_clip() -> None:
    assert clip("short") == "short"
    assert clip("x" * 50, 10).endswith("…")


def test_agent_run_records_error() -> None:
    try:
        with agent_run("test_agent", "fail", "demo"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    from opportunity_intel.observability.trace import jsonl_path

    lines = jsonl_path().read_text(encoding="utf-8").strip().splitlines()
    assert any('"event": "error"' in line and "test_agent" in line for line in lines[-5:])
