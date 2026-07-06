"""Tests for the preflight-requirements pilot (Phase 1).

The typed requirements now live in `tau2.data_model.preflight_requirements` and are attached
to τ³'s own `StructuredUserInstructions` via the optional `user_preflight_requirements` field
(there is no separate V2 wrapper anymore).

Covers the acceptance criteria:
  * Attaching `user_preflight_requirements` leaves the rendered simulator prose (`__str__`) and
    `task_instructions` byte-for-byte unchanged (backward compatible; every task still loads).
  * Every constraint's source_quote is verbatim-recoverable from the source prose.
  * The DENIED authorization is represented as an explicit refusal, not collapsed to "not requested".
  * The structured grader flips task 47 PASS -> FAIL on the unwanted transfer, while τ³ PASS.
  * Clean trajectories stay clean (no false positives).
"""

from __future__ import annotations

import json

from tau2.data_model.fixtures_preflight import build_task_47, get_preflight_fixture
from tau2.data_model.preflight_requirements import (
    UserPreflightRequirements,
    ActionPrecondition,
    verify_provenance,
)
from tau2.data_model.tasks import StructuredUserInstructions
from tau2.evaluator.preflight_requirements_evaluator import (
    PreflightRequirementsEvaluator,
)
from tau2.utils import DATA_DIR


def _original_task_47_instructions() -> StructuredUserInstructions:
    tasks = json.loads(
        (DATA_DIR / "tau2" / "domains" / "airline" / "tasks.json").read_text()
    )
    task = next(t for t in tasks if str(t["id"]) == "47")
    return StructuredUserInstructions(**task["user_scenario"]["instructions"])


# --- Backward compatibility: the field is optional, prose is unchanged ----------


def test_existing_task_loads_without_preflight_field():
    # Every shipped task loads with user_preflight_requirements defaulting to None.
    v1 = _original_task_47_instructions()
    assert v1.user_preflight_requirements is None


def test_adding_preflight_field_leaves_task_instructions_unchanged():
    v1 = _original_task_47_instructions()
    withreqs = build_task_47()
    assert withreqs.task_instructions == v1.task_instructions


def test_adding_preflight_field_leaves_rendered_prose_unchanged():
    # The simulator reads __str__; the new field must NOT appear in it, so the prose the
    # simulator sees is byte-for-byte identical with and without preflight requirements.
    v1 = _original_task_47_instructions()
    withreqs = build_task_47()
    assert withreqs.user_preflight_requirements is not None
    assert str(withreqs) == str(v1)


def test_preflight_carries_all_v1_scenario_fields():
    v1 = _original_task_47_instructions()
    withreqs = build_task_47()
    assert withreqs.domain == v1.domain
    assert withreqs.reason_for_call == v1.reason_for_call
    assert withreqs.known_info == v1.known_info
    assert withreqs.unknown_info == v1.unknown_info


# --- Provenance -----------------------------------------------------------------


def test_every_constraint_quote_is_grounded():
    instructions = build_task_47()
    assert verify_provenance(instructions) == []


def test_provenance_rejects_ungrounded_quote():
    instructions = build_task_47()
    instructions.user_preflight_requirements.action_preconditions.append(
        ActionPrecondition(
            id="bogus",
            action="cancel_reservation",
            preflight_protocol="invented",
            source_field="task_instructions",
            source_quote="this string is not in the task text at all",
        )
    )
    problems = verify_provenance(instructions)
    assert any("bogus" in p for p in problems)


def test_verify_provenance_no_requirements_is_empty():
    v1 = _original_task_47_instructions()
    assert verify_provenance(v1) == []


# --- Semantic distinctions ------------------------------------------------------


def test_transfer_is_a_prohibition_on_the_canonical_tool():
    pcs = build_task_47().user_preflight_requirements.action_preconditions
    assert any(p.action == "transfer_to_human_agents" for p in pcs)


# --- The grader flip ------------------------------------------------------------


def test_structured_grader_flips_task_47_to_fail_on_transfer():
    instructions = build_task_47()
    trajectories = json.loads(
        (DATA_DIR.parent / "poc" / "trajectories.json").read_text()
    )
    traj = next(t for t in trajectories if str(t["task_id"]) == "47")

    # τ³ recorded this as PASS.
    assert float(traj["reward"]) >= 1.0

    result = PreflightRequirementsEvaluator().evaluate_instructions(
        traj["trajectory"], instructions
    )
    assert result is not None
    assert result.passed is False
    assert result.reward == 0.0

    transfer_violations = [
        v for v in result.violations if v.action == "transfer_to_human_agents"
    ]
    assert len(transfer_violations) == 1
    v = transfer_violations[0]
    assert v.precondition_id == "task47.no_unwanted_transfer"
    assert v.requirement_kind == "prohibited_action"
    assert v.turn == 12  # the transfer_to_human_agents call in the recorded trajectory
    assert "you don't want to be transferred to another agent" == v.source_quote


def test_clean_trajectory_produces_no_violations():
    instructions = build_task_47()
    clean = [
        {"role": "user", "text": "I want a refund."},
        {"role": "assistant", "text": "Let me check.", "tool_calls": [
            {"name": "get_reservation_details", "args": {"reservation_id": "H8Q05L"}}
        ]},
    ]
    result = PreflightRequirementsEvaluator().evaluate_instructions(
        clean, instructions
    )
    assert result.passed is True
    assert result.violations == []


# --- Registry -------------------------------------------------------------------


def test_get_preflight_fixture_known_and_unknown():
    assert get_preflight_fixture("47") is not None
    assert get_preflight_fixture("999") is None


def test_evaluate_instructions_skips_when_no_requirements():
    v1 = _original_task_47_instructions()
    result = PreflightRequirementsEvaluator().evaluate_instructions([], v1)
    assert result is None


def test_prohibition_grades_generic_requirements():
    reqs = UserPreflightRequirements(
        action_preconditions=[
            ActionPrecondition(
                id="x.no_charge",
                action="charge_payment",
                preflight_protocol="do not charge without consent",
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
    result = PreflightRequirementsEvaluator().evaluate(traj, reqs)
    assert result.passed is False
    assert result.violations[0].turn == 0
