from src.run_limit import MAX_RERUNS, run_button_state


def test_fresh_session_offers_a_first_run():
    state = run_button_state(0)
    assert state.label == "Run assessment"
    assert not state.disabled


def test_button_becomes_a_rerun_after_the_first_run():
    state = run_button_state(1)
    assert state.label.startswith("Rerun assessment")
    assert not state.disabled
    assert state.reruns_left == MAX_RERUNS


def test_remaining_reruns_count_down():
    assert run_button_state(2).reruns_left == MAX_RERUNS - 1
    assert run_button_state(3).reruns_left == MAX_RERUNS - 2


def test_first_run_is_not_counted_as_a_rerun():
    """A session gets one initial run plus MAX_RERUNS reruns."""
    last_allowed = run_button_state(MAX_RERUNS)
    assert not last_allowed.disabled
    assert last_allowed.reruns_left == 1


def test_button_disables_once_reruns_are_exhausted():
    state = run_button_state(MAX_RERUNS + 1)
    assert state.disabled
    assert state.reruns_left == 0
    assert "limit reached" in state.label


def test_limit_holds_past_the_boundary():
    assert run_button_state(MAX_RERUNS + 5).disabled
