from opportunity_intel.agents.advisor import usable_parsed_facts
from opportunity_intel.config import Settings


def test_usable_parsed_facts_skips_errors() -> None:
    good = '{"full_name": "Chandan Kumar", "skills": ["Python"]}'
    assert usable_parsed_facts(good)["full_name"] == "Chandan Kumar"
    assert usable_parsed_facts('{"error": "boom"}') is None
    assert usable_parsed_facts("not json") is None
    assert usable_parsed_facts("") is None


def test_cors_default_includes_ipv4_vite() -> None:
    default = Settings.model_fields["cors_origins"].default
    assert "http://127.0.0.1:5173" in default
    assert "http://localhost:5173" in default
    origins = Settings(cors_origins="http://localhost:5173,http://127.0.0.1:5173").cors_origin_list
    assert "http://127.0.0.1:5173" in origins
