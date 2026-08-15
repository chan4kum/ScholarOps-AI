from opportunity_intel.config import Settings
from opportunity_intel.llm.models_config import RoleConfig, load_model_config
from opportunity_intel.llm.router import LLMRouter


def test_polish_blocked_when_flag_off() -> None:
    from opportunity_intel.config import ROOT

    cfg = load_model_config(ROOT / "config" / "models.yaml")
    settings = Settings(groq_polish_enabled=False, offline=False)
    router = LLMRouter(settings, cfg)
    try:
        router.complete("polish", [{"role": "user", "content": "rewrite"}])
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass


def test_role_config_thinking_payload_shape() -> None:
    spec = RoleConfig(
        name="draft",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking="enabled",
        reasoning_effort="high",
    )
    assert spec.thinking == "enabled"
    assert spec.model != "deepseek-reasoner"
    assert spec.model != "deepseek-chat"
