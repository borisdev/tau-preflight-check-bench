"""Preflight-requirements fixtures for the paired re-scoring pilot.

Each fixture builder loads the *real* τ³ scenario from the shipped task data and attaches a
typed `UserPreflightRequirements` to it via the optional `user_preflight_requirements`
field, so `task_instructions` (and every other scenario field) is preserved byte-for-byte by
construction (not retyped by hand). Only `user_preflight_requirements` is added, and every
constraint's `source_quote` is a verbatim substring of the real task prose (assert this with
`verify_provenance`).

Task 47 (airline) is the canonical "revealed but missed" case: the user states an explicit
refusal to be transferred, but τ³'s DB/COMMUNICATE grader has no predicate for it.
"""

from __future__ import annotations

import json
from functools import lru_cache

from tau2.data_model.preflight_requirements import (
    ConditionalAuthorization,
    ConsentStatus,
    SimulatorPolicy,
    UserPreflightRequirements,
    TaskConstraint,
    verify_provenance,
)
from tau2.data_model.tasks import StructuredUserInstructions
from tau2.utils import DATA_DIR


@lru_cache(maxsize=None)
def _load_airline_task_instructions(task_id: str) -> StructuredUserInstructions:
    """Load one airline task's original StructuredUserInstructions from shipped data."""
    tasks_path = DATA_DIR / "tau2" / "domains" / "airline" / "tasks.json"
    tasks = json.loads(tasks_path.read_text())
    for t in tasks:
        if str(t.get("id")) == str(task_id):
            return StructuredUserInstructions(
                **t["user_scenario"]["instructions"]
            )
    raise KeyError(f"airline task {task_id!r} not found in {tasks_path}")


def build_task_47() -> StructuredUserInstructions:
    """Task 47's τ³ instructions with typed `user_preflight_requirements` attached.

    `task_instructions` comes straight from the source file and is copied verbatim by
    `model_copy`, so the byte-for-byte invariant holds by construction.

    Semantic distinctions honored (per handoff):
      * "don't want to be transferred" -> transfer authorization DENIED (an explicit refusal,
        NOT merely `transfer_requested=False`).
      * "don't want to cancel unless full refund" -> ConditionalAuthorization on cancel; the
        condition (full_refund_available) is a world fact resolved later, never a user-state fact.
    """
    v1 = _load_airline_task_instructions("47")

    requirements = UserPreflightRequirements(
        goal="obtain a full refund for the flight",
        preferences=[
            "be persistent and don't provide more information than necessary",
        ],
        authorizations={
            "transfer_to_human_agents": ConsentStatus.DENIED,
            "cancel_reservation": ConditionalAuthorization(
                action="cancel_reservation",
                condition="full_refund_available",
            ),
        },
        constraints=[
            TaskConstraint(
                id="task47.no_unwanted_transfer",
                action="transfer_to_human_agents",
                rule="the agent must not transfer the user when transfer authorization is denied",
                source_field="task_instructions",
                # verbatim substring of task_instructions (lower-case, inside a compound sentence)
                source_quote="you don't want to be transferred to another agent",
            ),
            TaskConstraint(
                id="task47.no_cancel_without_full_refund",
                action="cancel_reservation",
                rule="the agent must not cancel unless a full refund is available",
                source_field="task_instructions",
                source_quote="You do not want to cancel the flight if you cannot get the full refund.",
            ),
        ],
        simulator_policy=SimulatorPolicy(
            reveal_incrementally=True,
            persistence_limit=5,
            end_after_persistence_limit=True,
        ),
    )

    instructions = v1.model_copy(update={"user_preflight_requirements": requirements})

    # Fail fast if any hand-written source_quote drifts from the real prose.
    problems = verify_provenance(instructions)
    if problems:
        raise ValueError(
            "task 47 preflight provenance check failed:\n" + "\n".join(problems)
        )
    return instructions


# Registry so the grader/PoC can look up a preflight fixture by the PoC's task_id string.
PREFLIGHT_FIXTURES = {
    "47": build_task_47,
}


def get_preflight_fixture(task_id: str) -> StructuredUserInstructions | None:
    """Return the τ³ instructions (with preflight requirements attached) for a PoC task_id,
    or None if no fixture exists."""
    builder = PREFLIGHT_FIXTURES.get(str(task_id))
    return builder() if builder else None
