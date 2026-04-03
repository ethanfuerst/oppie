from oppie.intent import Intent, classify_intent


def test_question_with_question_mark():
    assert classify_intent('what is blocking?') == Intent.QUESTION


def test_question_with_keyword():
    assert classify_intent('how many tickets are open') == Intent.QUESTION


def test_instruction_with_action_verb():
    assert classify_intent('move all blocked bugs to todo') == Intent.INSTRUCTION


def test_instruction_close():
    assert classify_intent('close stale tickets') == Intent.INSTRUCTION


def test_ambiguous_single_word():
    assert classify_intent('bugs') == Intent.AMBIGUOUS


def test_ambiguous_empty():
    assert classify_intent('') == Intent.AMBIGUOUS


def test_question_overrides_when_both():
    # "can you move X?" has both question keyword and action verb
    assert classify_intent('can you move the tickets?') == Intent.QUESTION


def test_list_keyword_is_question():
    assert classify_intent('list all urgent bugs') == Intent.QUESTION


def test_show_keyword_is_question():
    assert classify_intent('show tickets in progress') == Intent.QUESTION


def test_prioritize_is_instruction():
    assert classify_intent('prioritize security work') == Intent.INSTRUCTION


def test_triage_is_instruction():
    assert classify_intent('triage the open bugs') == Intent.INSTRUCTION
