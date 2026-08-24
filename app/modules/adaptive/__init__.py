"""Evidence-backed Adaptive Tutor domain.

This package is deliberately independent from the chat Agent.  The policy
and state updater are deterministic and can be evaluated without an LLM.
"""

from app.modules.adaptive.policy import (
    POLICY_VERSION,
    choose_next_action,
    select_action,
    select_objective,
    update_student_state,
)

__all__ = [
    "POLICY_VERSION",
    "choose_next_action",
    "select_action",
    "select_objective",
    "update_student_state",
]
