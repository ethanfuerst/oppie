from oppie.prompts.builder import PromptMode, build_system_prompt, flatten_system_prompt
from oppie.prompts.text.ask import ASK_BASE_PROMPT
from oppie.prompts.text.plan import PLAN_BASE_PROMPT
from tests.helpers import setup_instance


def test_build_plan_prompt_includes_base(tmp_path):
    home = setup_instance(tmp_path)

    parts = build_system_prompt(mode=PromptMode.PLAN, home=home)

    flat = flatten_system_prompt(parts)
    assert PLAN_BASE_PROMPT in flat


def test_build_ask_prompt_includes_base(tmp_path):
    home = setup_instance(tmp_path)

    parts = build_system_prompt(mode=PromptMode.ASK, home=home)

    flat = flatten_system_prompt(parts)
    assert ASK_BASE_PROMPT in flat


def test_build_prompt_includes_context(tmp_path):
    home = setup_instance(tmp_path)
    (home / 'context' / 'vision.md').write_text('Ship fast.')

    parts = build_system_prompt(mode=PromptMode.PLAN, home=home)

    flat = flatten_system_prompt(parts)
    assert 'Ship fast.' in flat


def test_build_plan_prompt_includes_constraints(tmp_path):
    from oppie.models.capabilities import ProviderCapabilities

    home = setup_instance(tmp_path)
    caps = ProviderCapabilities(
        supports_write=True,
        supported_field_updates=['status'],
        field_constraints={'status': ['open', 'done']},
    )

    parts = build_system_prompt(mode=PromptMode.PLAN, home=home, capabilities=caps)

    flat = flatten_system_prompt(parts)
    assert 'status' in flat
    assert 'open' in flat


def test_flatten_joins_parts():
    from oppie.prompts.builder import SystemPromptPart

    parts = [
        SystemPromptPart(content='part1'),
        SystemPromptPart(content='part2'),
    ]

    result = flatten_system_prompt(parts)

    assert result == 'part1\n\npart2'
