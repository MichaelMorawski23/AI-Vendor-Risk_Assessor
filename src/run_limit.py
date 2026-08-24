"""Session run-limit state for the UI.

Each assessment run is a billed API call. This caps a session at one initial
run plus MAX_RERUNS reruns — relevant mainly for a publicly deployed demo,
where visitors would otherwise spend the owner's API budget without limit.

Kept out of app.py so the reruns-vs-total-runs arithmetic is unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_RERUNS = 5


@dataclass(frozen=True)
class RunButtonState:
    label: str
    disabled: bool
    reruns_left: int


def run_button_state(run_count: int, max_reruns: int = MAX_RERUNS) -> RunButtonState:
    """Given how many runs a session has already spent, describe the submit button.

    run_count == 0 is a fresh session; the first run is not a rerun, so a
    session gets max_reruns + 1 total runs.
    """
    reruns_used = max(run_count - 1, 0)
    reruns_left = max(max_reruns - reruns_used, 0)

    if reruns_left == 0 and run_count > 0:
        return RunButtonState(f"Rerun limit reached ({max_reruns} reruns)", True, 0)
    if run_count > 0:
        return RunButtonState(f"Rerun assessment ({reruns_left} left)", False, reruns_left)
    return RunButtonState("Run assessment", False, reruns_left)
