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


def test_apply_bare():
    assert classify_intent('apply') == Intent.APPLY


def test_apply_it():
    assert classify_intent('apply it') == Intent.APPLY


def test_apply_the_plan():
    assert classify_intent('apply the plan') == Intent.APPLY


def test_apply_with_plan_id():
    assert classify_intent('apply plan-e7f8a9b0') == Intent.APPLY


def test_run_the_plan():
    assert classify_intent('run the plan') == Intent.APPLY


def test_execute_the_plan():
    assert classify_intent('execute the plan') == Intent.APPLY


def test_go_ahead():
    assert classify_intent('go ahead') == Intent.APPLY


def test_force_apply():
    assert classify_intent('force apply it') == Intent.APPLY


def test_apply_force_flag():
    assert classify_intent('apply --force') == Intent.APPLY


def test_apply_labels_is_not_apply():
    """'apply labels to bugs' is not apply intent — falls through to ambiguous."""
    assert classify_intent('apply labels to all bugs') != Intent.APPLY


def test_can_i_apply_is_question():
    """Question mark overrides apply intent."""
    assert classify_intent('can I apply?') == Intent.QUESTION
