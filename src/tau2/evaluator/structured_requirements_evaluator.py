"""StructuredRequirementsEvaluator — the deterministic V2 grader.

Given a recorded trajectory (the poc/trajectories.json shape: a list of role/text/tool_calls
dicts) and a `StructuredUserRequirements`, it reports human-readable violations of the
*task-local* requirements, each linked to action / turn / rule-id / source_field / source_quote.

It is deterministic (no LLM) and grades only requirements already recoverable from τ³'s own
scenario prose — the "revealed but missed" pattern. It reuses `ConstraintEvaluator`'s tool-call
iterator so both graders read tool calls identically.

Semantics (the distinction the handoff insists on):
  * authorization == ConsentStatus.DENIED   -> the action must NOT occur at all. Any occurrence
    is a violation. This is stronger than "no request observed".
  * authorization == ConditionalAuthorization -> the action is permitted only if a world/policy
    condition holds. That condition is not a user-state fact and is not deterministically
    readable from the tool-call list, so we flag an occurrence as a *conditional* violation whose
    evidence names the unresolved condition. (In task 47 the action never fires, so this stays
    silent — clean by construction.)
  * GRANTED / UNKNOWN / no authorization    -> no gradeable prohibition; skipped.
"""

from __future__ import annotations

from pydantic import BaseModel

from tau2.data_model.structured_user_instructions_v2 import (
    ConditionalAuthorization,
    ConsentStatus,
    StructuredUserRequirements,
    TaskConstraint,
)
from tau2.evaluator.constraint_evaluator import _all_tool_calls


def _action_invocations(trajectory: list[dict]):
    """Yield (index, name, args) once per *agent-issued* action.

    A trajectory records a tool use twice: as an assistant `tool_calls` entry (the invocation)
    and again as a `tool` result row. We count the invocation, so we prefer assistant rows and
    only fall back to `tool` rows if the trajectory has no assistant tool calls at all. Built on
    ConstraintEvaluator's `_all_tool_calls` iterator so both graders read tool calls identically.
    """
    assistant_calls = [
        (i, name, args)
        for i, e in enumerate(trajectory)
        if e.get("role") == "assistant"
        for name, args in (
            (c.get("name"), c.get("args", {})) for c in (e.get("tool_calls") or [])
        )
    ]
    if assistant_calls:
        return assistant_calls
    return list(_all_tool_calls(trajectory))


class StructuredRequirementViolation(BaseModel):
    constraint_id: str
    action: str
    rule: str
    source_field: str
    source_quote: str
    requirement_kind: str  # "denied_authorization" | "conditional_authorization"
    turn: int
    evidence: str

    def describe(self) -> str:
        return (
            f"[{self.constraint_id}] VIOLATED at turn {self.turn}: {self.rule}\n"
            f"    action: {self.action}  ({self.requirement_kind})\n"
            f"    evidence: {self.evidence}\n"
            f'    source ({self.source_field}): "{self.source_quote}"'
        )


class StructuredGradeResult(BaseModel):
    reward: float  # 1.0 if no violation, else 0.0
    passed: bool
    violations: list[StructuredRequirementViolation]
    constraints_total: int
    constraints_honored: int

    @property
    def requirement_recall(self) -> float:
        if self.constraints_total == 0:
            return 1.0
        return self.constraints_honored / self.constraints_total


def _check_constraint(
    trajectory: list[dict],
    constraint: TaskConstraint,
    authorizations: dict,
) -> list[StructuredRequirementViolation]:
    """Flag every trajectory tool call that violates a single typed constraint."""
    auth = authorizations.get(constraint.action)
    violations: list[StructuredRequirementViolation] = []

    if auth == ConsentStatus.DENIED:
        for idx, name, _args in _action_invocations(trajectory):
            if name == constraint.action:
                violations.append(
                    StructuredRequirementViolation(
                        constraint_id=constraint.id,
                        action=constraint.action,
                        rule=constraint.rule,
                        source_field=constraint.source_field,
                        source_quote=constraint.source_quote,
                        requirement_kind="denied_authorization",
                        turn=idx,
                        evidence=(
                            f"called {name}; user explicitly denied authorization for this action"
                        ),
                    )
                )
    elif isinstance(auth, ConditionalAuthorization):
        for idx, name, _args in _action_invocations(trajectory):
            if name == constraint.action:
                violations.append(
                    StructuredRequirementViolation(
                        constraint_id=constraint.id,
                        action=constraint.action,
                        rule=constraint.rule,
                        source_field=constraint.source_field,
                        source_quote=constraint.source_quote,
                        requirement_kind="conditional_authorization",
                        turn=idx,
                        evidence=(
                            f"called {name}; authorized only if condition "
                            f"'{auth.condition}' holds, which is not established in the trajectory"
                        ),
                    )
                )
    # GRANTED / UNKNOWN / missing -> no gradeable prohibition.
    return violations


class StructuredRequirementsEvaluator:
    """reward = 0 if ANY task-local requirement is violated, else 1 (mirrors τ³'s
    multiplicative pass/fail component style)."""

    def evaluate(
        self,
        trajectory: list[dict],
        requirements: StructuredUserRequirements,
    ) -> StructuredGradeResult:
        all_violations: list[StructuredRequirementViolation] = []
        honored = 0
        for c in requirements.constraints:
            vs = _check_constraint(trajectory, c, requirements.authorizations)
            if vs:
                all_violations.extend(vs)
            else:
                honored += 1

        passed = len(all_violations) == 0
        return StructuredGradeResult(
            reward=1.0 if passed else 0.0,
            passed=passed,
            violations=all_violations,
            constraints_total=len(requirements.constraints),
            constraints_honored=honored,
        )
