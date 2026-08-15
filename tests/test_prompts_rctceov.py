from opportunity_intel.llm.prompting import (
    ADVISOR_SYSTEM,
    APPLY_LEFTOVER_FIELDS_PROMPT,
    APPLY_PATH_PROMPT,
    APPLY_VERIFY_CLAIMS_PROMPT,
    CHECKLIST_PROMPT,
    DOC_EXTRACT_PROMPT,
    FIT_RATIONALE_PROMPT,
    PACKET_DRAFT_PROMPT,
    PHD_VACANCY_EXTRACT_PROMPT,
    PROFESSOR_INTEL_PROMPT,
    PROFILE_SYNTHESIS_PROMPT,
    REQUIREMENTS_EXTRACT_PROMPT,
    SECTIONS,
    compose_rctceov,
)


def test_compose_includes_all_rctceov_headers() -> None:
    text = compose_rctceov(
        role="r",
        context="c",
        task="t",
        constraints="k",
        examples="e",
        output="o",
        verification="v",
    )
    for name in SECTIONS:
        assert f"{name}\n" in text
    assert text.index("ROLE") < text.index("VERIFICATION")


def test_live_and_planned_agent_prompts_follow_framework() -> None:
    prompts = (
        DOC_EXTRACT_PROMPT,
        PROFILE_SYNTHESIS_PROMPT,
        ADVISOR_SYSTEM,
        PHD_VACANCY_EXTRACT_PROMPT,
        FIT_RATIONALE_PROMPT,
        PROFESSOR_INTEL_PROMPT,
        REQUIREMENTS_EXTRACT_PROMPT,
        CHECKLIST_PROMPT,
        PACKET_DRAFT_PROMPT,
        APPLY_LEFTOVER_FIELDS_PROMPT,
        APPLY_VERIFY_CLAIMS_PROMPT,
        APPLY_PATH_PROMPT,
    )
    for prompt in prompts:
        for name in SECTIONS:
            assert f"{name}\n" in prompt
        assert "UK" in prompt or "GB" in prompt or "invent" in prompt.lower()
