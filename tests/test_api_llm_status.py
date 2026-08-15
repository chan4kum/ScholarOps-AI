import json

from fastapi.testclient import TestClient

from opportunity_intel.main import app


def test_llm_status_returns_200() -> None:
    client = TestClient(app)
    response = client.get("/api/llm/status")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["target_countries"], list)
    assert isinstance(body["excluded_countries"], list)
    assert False not in body["target_countries"]
    assert "tavily_configured" in body
    assert "gemini_configured" in body
    assert "openai_configured" in body
    blob = json.dumps(body)
    assert "AQ." not in blob
    assert "AIza" not in blob
    assert "sk-proj" not in blob
