"""Tests for the StructuredUserInstructionsV2 pilot (handoff Phase 1).

Covers the acceptance criteria:
  * V2 preserves the original `task_instructions` byte-for-byte.
  * Every V2 constraint's source_quote is verbatim-recoverable from the source prose.
  * The semantic distinctions (DENIED authorization; conditional cancel; refund_eligible is a
    world fact) are represented, not collapsed.
  * The structured grader flips task 47 PASS -> FAIL on the unwanted transfer, while τ³ PASS.
  * Clean trajectories stay clean (no false positives; conditional cancel does not misfire).
"""

from __future__ import annotations

import json

from tau2.data_model.fixtures_v2 import build_task_47_v2, get_v2_fixture
from tau2.data_model.structured_user_instructions_v2 import (
    ConditionalAuthorization,
    ConsentStatus,
    StructuredUserRequirements,
    TaskConstraint,
    verify_provenance,
)
from tau2.data_model.tasks import StructuredUserInstructions
from tau2.evaluator.structured_requirements_evaluator import (
    StructuredRequirementsEvaluator,
)
from tau2.utils import DATA_DIR


def _original_task_47_instructions() -> StructuredUserInstructions:
    tasks = json.loads(
        (DATA_DIR / "tau2" / "domains" / "airline" / "tasks.json").read_text()
    )
    task = next(t for t in tasks if str(t["id"]) == "47")
    return StructuredUserInstructions(**task["user_scenario"]["instructions"])


# --- Byte-for-byte preservation -------------------------------------------------


def test_task_instructions_preserved_byte_for_byte():
    v1 = _original_task_47_instructions()
    v2 = build_task_47_v2()
    assert v2.task_instructions == v1.task_instructions


def test_v2_carries_all_v1_scenario_fields():
    v1 = _original_task_47_instructions()
    v2 = build_task_47_v2()
    assert v2.domain == v1.domain
    assert v2.reason_for_call == v1.reason_for_call
    assert v2.known_info == v1.known_info
    assert v2.unknown_info == v1.unknown_info


# --- Provenance -----------------------------------------------------------------


def test_every_constraint_quote_is_grounded():
    v2 = build_task_47_v2()
    assert verify_provenance(v2) == []


def test_provenance_rejects_ungrounded_quote():
    v2 = build_task_47_v2()
    v2.structured_requirements.constraints.append(
        TaskConstraint(
            id="bogus",
            action="cancel_reservation",
            rule="invented",
            source_field="task_instructions",
            source_quote="this string is not in the task text at all",
        )
    )
    problems = verify_provenance(v2)
    assert any("bogus" in p for p in problems)


# --- Semantic distinctions ------------------------------------------------------


def test_transfer_is_denied_not_merely_unrequested():
    v2 = build_task_47_v2()
    auths = v2.structured_requirements.authorizations
    assert auths["transfer_to_human_agents"] == ConsentStatus.DENIED


def test_cancel_is_conditional_authorization_on_full_refund():
    v2 = build_task_47_v2()
    cancel = v2.structured_requirements.authorizations["cancel_reservation"]
    assert isinstance(cancel, ConditionalAuthorization)
    assert cancel.action == "cancel_reservation"
    assert cancel.condition == "full_refund_available"


# --- The grader flip ------------------------------------------------------------


def test_structured_grader_flips_task_47_to_fail_on_transfer():
    v2 = build_task_47_v2()
    trajectories = json.loads(
        (DATA_DIR.parent / "poc" / "trajectories.json").read_text()
    )
    traj = next(t for t in trajectories if str(t["task_id"]) == "47")

    # τ³ recorded this as PASS.
    assert float(traj["reward"]) >= 1.0

    result = StructuredRequirementsEvaluator().evaluate(
        traj["trajectory"], v2.structured_requirements
    )
    assert result.passed is False
    assert result.reward == 0.0

    transfer_violations = [
        v for v in result.violations if v.action == "transfer_to_human_agents"
    ]
    assert len(transfer_violations) == 1
    v = transfer_violations[0]
    assert v.constraint_id == "task47.no_unwanted_transfer"
    assert v.requirement_kind == "denied_authorization"
    assert v.turn == 12  # the transfer_to_human_agents call in the recorded trajectory
    assert "you don't want to be transferred to another agent" == v.source_quote


def test_conditional_cancel_does_not_misfire_when_cancel_absent():
    # Task 47's trajectory never calls cancel_reservation, so the conditional constraint
    # must NOT produce a violation (clean-by-construction).
    v2 = build_task_47_v2()
    trajectories = json.loads(
        (DATA_DIR.parent / "poc" / "trajectories.json").read_text()
    )
    traj = next(t for t in trajectories if str(t["task_id"]) == "47")
    result = StructuredRequirementsEvaluator().evaluate(
        traj["trajectory"], v2.structured_requirements
    )
    cancel_violations = [
        v for v in result.violations if v.action == "cancel_reservation"
    ]
    assert cancel_violations == []


def test_clean_trajectory_produces_no_violations():
    v2 = build_task_47_v2()
    clean = [
        {"role": "user", "text": "I want a refund."},
        {"role": "assistant", "text": "Let me check.", "tool_calls": [
            {"name": "get_reservation_details", "args": {"reservation_id": "H8Q05L"}}
        ]},
    ]
    result = StructuredRequirementsEvaluator().evaluate(
        clean, v2.structured_requirements
    )
    assert result.passed is True
    assert result.violations == []


# --- Registry -------------------------------------------------------------------


def test_get_v2_fixture_known_and_unknown():
    assert get_v2_fixture("47") is not None
    assert get_v2_fixture("999") is None


def test_denied_authorization_grades_generic_requirements():
    reqs = StructuredUserRequirements(
        authorizations={"charge_payment": ConsentStatus.DENIED},
        constraints=[
            TaskConstraint(
                id="x.no_charge",
                action="charge_payment",
                rule="do not charge without consent",
                source_field="task_instructions",
                source_quote="n/a",
            )
        ],
    )
    traj = [
        {"role": "assistant", "text": "", "tool_calls": [
            {"name": "charge_payment", "args": {"amount": 100}}
        ]},
    ]
    result = StructuredRequirementsEvaluator().evaluate(traj, reqs)
    assert result.passed is False
    assert result.violations[0].turn == 0
