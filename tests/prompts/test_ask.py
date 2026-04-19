from oppie.prompts.builder import PromptMode, build_system_prompt, flatten_system_prompt
from oppie.prompts.text.ask import ASK_BASE_PROMPT
from tests.helpers import setup_instance


def test_ask_base_prompt_instructs_silent_research():
    """ETH-412: ask base prompt discourages research-step narration."""
    assert 'research step' in ASK_BASE_PROMPT
    assert 'discarded' in ASK_BASE_PROMPT


def test_build_ask_prompt_includes_base(tmp_path):
    home = setup_instance(tmp_path)

    parts = build_system_prompt(mode=PromptMode.ASK, home=home)

    flat = flatten_system_prompt(parts)

    assert ASK_BASE_PROMPT in flat
