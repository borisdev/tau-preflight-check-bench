"""StructuredUserInstructionsV2 — the Phase-1 pilot representation (handoff spec).

τ³ already gives each simulated user a semi-structured `StructuredUserInstructions`
(see `tau2.data_model.tasks`). Its `task_instructions` field, however, is overloaded
prose: it mixes the user's goal, constraints, preferences, consent/refusal, conditional
authorization, and simulator-only behaviour. The τ³ grader is DB/COMMUNICATE-oriented and
has no predicate for most of those requirements, so a stated requirement like "don't
transfer me" is *revealed to the simulator but missed by the grader* (task 47's silent
false-pass).

V2 keeps the original simulator prose **byte-for-byte** and adds a typed, checkable
`structured_requirements` representation for a *second* grader. Re-scoring the same
trajectory with both graders isolates one variable: what the grader can represent.

The critical invariant:

    v2.task_instructions == v1.task_instructions   # byte-for-byte

Scope discipline (non-goals, per handoff): this is the *smallest action-relevant* model
needed to grade requirements already recoverable from τ³'s own scenario prose. It is not a
universal user model, not a logic engine, and not a `PreflightPolicyPack`. Every typed
requirement carries provenance (`source_field` + `source_quote`) that must be a verbatim
substring of the referenced source field — see `verify_provenance`.

Dependency-light on purpose (pydantic only) so it imports and tests without the harness.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ConsentStatus(str, Enum):
    """Whether the user has authorized an action.

    Note the deliberate three-valued design. `DENIED` (an *explicit refusal*) is a stronger
    fact than "no request observed" — do NOT collapse `DENIED` into a `transfer_requested=False`
    style flag. `UNKNOWN` means the scenario says nothing about that action.
    """

    GRANTED = "granted"
    DENIED = "denied"
    UNKNOWN = "unknown"


class ConditionalAuthorization(BaseModel):
    """An action the user permits *only* when a condition holds.

    Example (task 47): cancel is authorized only if a full refund is available. The
    condition is a world/policy fact resolved later — it is NOT itself a user-state fact
    (contrast `refund_eligible`, which is a world fact and never a user requirement).
    """

    action: str
    condition: str


class TaskConstraint(BaseModel):
    """A single gradeable, task-local requirement with provenance back to the source prose.

    The pilot's legitimacy rests on provenance: we did not invent a rule, we made an
    already-stated rule gradeable. `source_quote` must be a verbatim substring of the field
    named by `source_field` (checked by `verify_provenance`).
    """

    id: str
    action: str
    rule: str
    source_field: str
    source_quote: str


class StructuredUserRequirements(BaseModel):
    """The typed, task-local requirements derived only from the existing τ³ scenario.

    - `goal`         — the user's objective (prose is fine; not itself a gradeable predicate).
    - `preferences`  — soft, non-binding wants.
    - `authorizations` — per-action consent: an explicit `ConsentStatus` or a
                         `ConditionalAuthorization`. This carries the *semantics* the grader
                         reads (DENIED vs conditional vs granted).
    - `constraints`  — the gradeable units with provenance; each references an `action` that
                       the grader cross-checks against `authorizations`.
    """

    goal: str | None = None
    preferences: list[str] = Field(default_factory=list)
    authorizations: dict[str, ConsentStatus | ConditionalAuthorization] = Field(
        default_factory=dict
    )
    constraints: list[TaskConstraint] = Field(default_factory=list)


class SimulatorPolicy(BaseModel):
    """Simulator-only behaviour, kept *separate* from user authorization.

    These control how the simulated user speaks (incremental disclosure, persistence,
    termination) — they are NOT things the grader treats as user consent. Optional and not
    rendered into any prompt during the pilot (we never regenerate simulator prose from V2).
    """

    reveal_incrementally: bool = False
    persistence_limit: int | None = None
    end_after_persistence_limit: bool = False


class StructuredUserInstructionsV2(BaseModel):
    """τ³'s `StructuredUserInstructions` plus a typed representation of action-relevant
    requirements. The original `task_instructions` string is preserved byte-for-byte for the
    user simulator; `structured_requirements` is the new grader-visible representation."""

    domain: str
    reason_for_call: str
    known_info: str | None = None
    unknown_info: str | None = None

    # Preserved exactly — this is what the user simulator reads. Never regenerate from V2.
    task_instructions: str

    # New typed representation used only by the structured-requirements grader.
    structured_requirements: StructuredUserRequirements

    # Optional typed simulator-only controls.
    simulator_policy: SimulatorPolicy | None = None

    @classmethod
    def from_v1(
        cls,
        v1,
        structured_requirements: StructuredUserRequirements,
        simulator_policy: SimulatorPolicy | None = None,
    ) -> "StructuredUserInstructionsV2":
        """Lift a τ³ `StructuredUserInstructions` (or any object exposing the same fields)
        into V2, copying `task_instructions` verbatim so the byte-for-byte invariant holds by
        construction."""
        return cls(
            domain=v1.domain,
            reason_for_call=v1.reason_for_call,
            known_info=v1.known_info,
            unknown_info=v1.unknown_info,
            task_instructions=v1.task_instructions,
            structured_requirements=structured_requirements,
            simulator_policy=simulator_policy,
        )


def verify_provenance(v2: StructuredUserInstructionsV2) -> list[str]:
    """Deterministically verify every constraint's `source_quote` is a verbatim substring of
    the field it cites. Returns a list of human-readable problems (empty == all grounded).

    This is the verification discipline from the handoff: reject any requirement whose quote
    cannot be recovered from the real task text.
    """
    problems: list[str] = []
    field_values = {
        "task_instructions": v2.task_instructions,
        "reason_for_call": v2.reason_for_call,
        "known_info": v2.known_info,
        "unknown_info": v2.unknown_info,
        "domain": v2.domain,
    }
    for c in v2.structured_requirements.constraints:
        source = field_values.get(c.source_field)
        if source is None:
            problems.append(
                f"{c.id}: source_field {c.source_field!r} is missing or None"
            )
        elif c.source_quote not in source:
            problems.append(
                f"{c.id}: source_quote not found verbatim in {c.source_field!r}: "
                f"{c.source_quote!r}"
            )
    return problems
