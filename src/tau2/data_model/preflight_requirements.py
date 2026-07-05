"""Typed, task-local user requirements — a grader-visible representation.

τ³ already gives each simulated user a semi-structured `StructuredUserInstructions`
(see `tau2.data_model.tasks`). Its `task_instructions` field, however, is overloaded
prose: it mixes the user's goal, constraints, preferences, consent/refusal, conditional
authorization, and simulator-only behaviour. The τ³ grader is DB/COMMUNICATE-oriented and
has no predicate for most of those requirements, so a stated requirement like "don't
transfer me" is *revealed to the simulator but missed by the grader* (task 47's silent
false-pass).

This module holds the typed, checkable representation (`UserPreflightRequirements`) that a
*second* grader reads. It is attached to τ³'s own `StructuredUserInstructions` via the
optional `user_preflight_requirements` field, so the simulator prose (`task_instructions`)
stays byte-for-byte unchanged and every existing task still loads. Re-scoring the same
trajectory with both graders isolates one variable: what the grader can represent.

Scope discipline (non-goals, per handoff): this is the *smallest action-relevant* model
needed to grade requirements already recoverable from τ³'s own scenario prose. It is not a
universal user model, not a logic engine, and not a `PreflightPolicyPack`. Every typed
requirement carries provenance (`source_field` + `source_quote`) that must be a verbatim
substring of the referenced source field — see `verify_provenance`.

Import discipline: this module MUST NOT import from `tasks.py` (that would create a circular
import — `tasks.py` imports `UserPreflightRequirements` from here). `verify_provenance`
therefore duck-types the instructions object rather than importing its class.

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


class SimulatorPolicy(BaseModel):
    """Simulator-only behaviour, kept *separate* from user authorization.

    These control how the simulated user speaks (incremental disclosure, persistence,
    termination) — they are NOT things the grader treats as user consent. Optional and not
    rendered into any prompt during the pilot (we never regenerate simulator prose from the
    typed requirements).
    """

    reveal_incrementally: bool = False
    persistence_limit: int | None = None
    end_after_persistence_limit: bool = False


class UserPreflightRequirements(BaseModel):
    """The typed, task-local requirements derived only from the existing τ³ scenario.

    - `goal`         — the user's objective (prose is fine; not itself a gradeable predicate).
    - `preferences`  — soft, non-binding wants.
    - `authorizations` — per-action consent: an explicit `ConsentStatus` or a
                         `ConditionalAuthorization`. This carries the *semantics* the grader
                         reads (DENIED vs conditional vs granted).
    - `constraints`  — the gradeable units with provenance; each references an `action` that
                       the grader cross-checks against `authorizations`.
    - `simulator_policy` — optional simulator-only controls, kept separate from the graded
                         authorizations (never rendered into the simulator prose).
    """

    goal: str | None = None
    preferences: list[str] = Field(default_factory=list)
    authorizations: dict[str, ConsentStatus | ConditionalAuthorization] = Field(
        default_factory=dict
    )
    constraints: list[TaskConstraint] = Field(default_factory=list)
    simulator_policy: SimulatorPolicy | None = None


def verify_provenance(instructions) -> list[str]:
    """Deterministically verify every constraint's `source_quote` is a verbatim substring of
    the field it cites. Returns a list of human-readable problems (empty == all grounded).

    `instructions` is a τ³ `StructuredUserInstructions` (duck-typed to avoid importing
    `tasks.py`): it must expose the scenario source fields and a
    `user_preflight_requirements` attribute. If no requirements are attached, there is
    nothing to verify and the result is empty.

    This is the verification discipline from the handoff: reject any requirement whose quote
    cannot be recovered from the real task text.
    """
    requirements = getattr(instructions, "user_preflight_requirements", None)
    if requirements is None:
        return []

    problems: list[str] = []
    field_values = {
        "task_instructions": instructions.task_instructions,
        "reason_for_call": instructions.reason_for_call,
        "known_info": instructions.known_info,
        "unknown_info": instructions.unknown_info,
        "domain": instructions.domain,
    }
    for c in requirements.constraints:
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
