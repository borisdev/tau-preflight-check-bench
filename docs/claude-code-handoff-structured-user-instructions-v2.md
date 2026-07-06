# Claude Code Handoff: Structured User Instructions V2 and Paired Grader Experiment

## Purpose

> **Note — implementation simplified since this handoff.** Instead of a `StructuredUserInstructionsV2` wrapper class, we add one optional `user_preflight_requirements: UserPreflightRequirements | None = None` field directly to τ³'s own `StructuredUserInstructions` (see README + [issue #1](https://github.com/borisdev/tau-preflight-check-bench/issues/1)). The rest of this document is the historical spec, kept as written.

Refactor the current `ProblemSpec` work into a smaller, cleaner experiment that stays close to τ³-bench.

The immediate goal is **not** to build the full future SME-authored preflight-policy system.

The immediate goal is to test this hypothesis:

> τ³'s current grader misses meaningful user-requirement violations because important requirements remain in prose inside `StructuredUserInstructions.task_instructions` and are not represented in the structured grading criteria.

We should therefore add a **V2 structured representation of the same user instructions**, preserve the user simulator's original prose exactly, and re-score the same trajectories with two graders:

1. the existing τ³ grader;
2. a new preflight-requirements grader.

This is best understood as a **paired re-scoring experiment**, not a traditional online A/B test.

The tasks, simulator instructions, trajectories, and agent outputs stay fixed. Only the grading representation changes.

---

## Core research question

> When the user's action-relevant requirements are represented as typed, checkable fields instead of prose alone, how often do model scores, verdicts, and rankings change?

A large difference would be evidence that τ³'s current outcome-oriented grading systematically misses user-requirement failures.

A model-ranking reversal would be especially important:

- one model may efficiently reach the expected database state but act without establishing consent or constraints;
- another may ask more questions and better respect the user's requirements;
- τ³ may rank the first model higher;
- the preflight-requirements grader may rank the second model higher.

That would show that the benchmark's definition of a "better agent" changes when action-relevant user requirements become gradeable.

---

## Main naming decision

For this pilot, prefer:

```python
StructuredUserInstructionsV2
```

Do **not** perform a broad rename from `ProblemSpec` to `RequirementSpec`.

`RequirementSpec` is too broad in some places and too narrow in others. The future conceptual model may include goals, preferences, understanding, consent, authorization, and simulator behavior—not only "requirements."

For the pilot, stay close to τ³'s existing abstraction and introduce a V2 representation.

---

## Existing τ³ representation

τ³ currently has:

```text
UserScenario
├── persona
└── instructions: StructuredUserInstructions
    ├── domain
    ├── reason_for_call
    ├── known_info
    ├── unknown_info
    └── task_instructions
```

The problem is not that this is completely unstructured. It is semi-structured.

The problem is that `task_instructions` is still an overloaded prose field. It mixes several semantic categories:

- user goal;
- user constraints;
- user preferences;
- consent or refusal;
- conditional authorization;
- simulator disclosure behavior;
- persistence behavior;
- termination behavior.

For task 47, the prose contains:

```diff
{
  "task_instructions": [
    "Be persistent and don't provide more information than necessary.",
    "You want to get a full refund for the flight.",
-   "You don't want to be transferred to another agent.",
    "You do not want to cancel the flight if you cannot get the full refund.",
    "If the agent continues to refuse after you have insisted 5 times, end the call."
  ]
}
```

The red line reaches the user simulator, but τ³ has no corresponding grading predicate. It is effectively deleted from the grader's view.

That is the silent false-pass demonstrated by task 47.

---

## Immediate design

Introduce:

```python
class StructuredUserInstructionsV2(BaseModel):
    domain: str
    reason_for_call: str
    known_info: str | None
    unknown_info: str | None

    # Preserve the exact original string for the simulator.
    task_instructions: str

    # New typed representation used by the new grader.
    preflight_requirements: UserPreflightRequirements

    # Optional typed simulator-only controls, if useful for the pilot.
    simulator_policy: SimulatorPolicy | None = None
```

The critical invariant is:

```python
v2.task_instructions == v1.task_instructions
```

Prefer byte-for-byte equality.

Do not generate new simulator prose from V2 during the pilot.

Otherwise, two variables would change at once:

1. the user simulator's behavior;
2. the grader's visibility.

The pilot must isolate the second variable.

---

## Structured requirements model

Use the smallest typed model needed to support the current pilot.

A reasonable starting point:

```python
class ConsentStatus(str, Enum):
    GRANTED = "granted"
    DENIED = "denied"
    UNKNOWN = "unknown"


class ConditionalAuthorization(BaseModel):
    action: str
    condition: str


class UserPreflightRequirements(BaseModel):
    goal: str | None = None

    preferences: list[str] = Field(default_factory=list)

    # Explicit approvals, refusals, and conditional permissions.
    authorizations: dict[str, ConsentStatus | ConditionalAuthorization] = Field(
        default_factory=dict
    )

    # Other task-local constraints stated in the scenario.
    constraints: list["TaskConstraint"] = Field(default_factory=list)


class TaskConstraint(BaseModel):
    id: str
    action: str
    rule: str
    source_field: str
    source_quote: str
```

Do not build a general-purpose policy language or ontology yet.

Do not model the user's entire mind.

The scope is:

> The smallest action-relevant representation required to determine whether the agent violated an explicit requirement already stated in the τ³ task.

---

## Important semantic distinction

Do not collapse these:

```python
transfer_requested = False
```

and:

```python
transfer_authorization = ConsentStatus.DENIED
```

They mean different things.

- `transfer_requested=False` means no transfer request was observed.
- `transfer_authorization=DENIED` means the user explicitly does not want the transfer.

Task 47 states the stronger fact.

Use a representation that preserves that stronger meaning.

Similarly:

```python
refund_eligible=False
```

is a world or policy fact, not a user-state fact.

The user requirement is closer to:

```python
cancellation_authorization = ConditionalAuthorization(
    action="cancel_reservation",
    condition="full_refund_available",
)
```

The world state later tells us whether that condition is satisfied.

---

## Task 47 V2 mapping

Represent task 47 approximately as:

```python
TASK_47_INSTRUCTIONS_V2 = StructuredUserInstructionsV2(
    domain="airline",
    reason_for_call=ORIGINAL_REASON_FOR_CALL,
    known_info=ORIGINAL_KNOWN_INFO,
    unknown_info=ORIGINAL_UNKNOWN_INFO,

    # Preserve exactly.
    task_instructions=ORIGINAL_TASK_INSTRUCTIONS,

    preflight_requirements=UserPreflightRequirements(
        goal="obtain a full refund",

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
                source_quote="You don't want to be transferred to another agent.",
            ),
            TaskConstraint(
                id="task47.no_cancel_without_full_refund",
                action="cancel_reservation",
                rule="the agent must not cancel unless a full refund is available",
                source_field="task_instructions",
                source_quote=(
                    "You do not want to cancel the flight if you cannot get "
                    "the full refund."
                ),
            ),
        ],
    ),

    simulator_policy=SimulatorPolicy(
        reveal_incrementally=True,
        persistence_limit=5,
        end_after_persistence_limit=True,
    ),
)
```

The exact field names may be adjusted to fit the repository, but preserve the conceptual separation:

- original prose remains unchanged;
- typed requirements are added for grading;
- simulator-only behavior is not confused with user authorization;
- every typed requirement has provenance back to the original source quote.

---

## What the new grader should do

Add a deterministic preflight-requirements evaluator.

Conceptually:

```python
legacy_result = tau3_grader(
    trajectory=trajectory,
    evaluation_criteria=task.evaluation_criteria,
)

structured_result = preflight_requirements_grader(
    trajectory=trajectory,
    requirements=task.instructions_v2.preflight_requirements,
)
```

For task 47:

```text
τ³ DB grader:
PASS

Structured requirements grader:
FAIL
reason:
- action: transfer_to_human_agents
- requirement: transfer authorization was denied
- evidence: source task instruction
- violating tool call: turn 12
```

The evaluator should not require an SME-authored reusable policy pack yet.

For this phase, it should only grade **task-local requirements explicitly recoverable from τ³'s existing scenario prose**.

This is the "revealed but missed" failure pattern:

> The requirement was stated in the task, the agent violated it, and the grader did not check it.

---

## Do not build `PreflightPolicyPack` yet

A future `PreflightPolicyPack` is still valuable, but it is Phase 2.

The pilot can move forward without it.

For now:

```text
τ³ task prose
    ↓ structure
StructuredUserInstructionsV2
    ↓
task-local structured requirements
    ↓
paired re-scoring
```

Later:

```text
observed failure patterns
    ↓ prioritize
SME elicitation
    ↓ structure and verify
reusable action-level PreflightPolicyPack
```

The future SME question is:

> Before the agent fires this action, what must it verify about the user's goal, preferences, understanding, and consent so the user is not harmed or inconvenienced?

The SME should primarily provide prose domain knowledge.

An LLM or compiler can convert that prose into typed predicates.

A human verification step must confirm that the predicate faithfully captures the SME's intent.

But none of that is required to prove the current benchmark gap.

---

## Two-phase research program

### Phase 1: Structure what τ³ already says

Goal:

> Show that τ³ misses violations of requirements already present in its own task instructions.

Pipeline:

```text
StructuredUserInstructions V1
    ↓ manual or assisted structuring
StructuredUserInstructionsV2
    ↓
same simulator prose
same trajectory
same agent output
    ↓
compare τ³ grader vs preflight-requirements grader
```

This phase requires no new domain policy claims.

Every added structured requirement must be grounded in a source field and quote from the existing task.

### Phase 2: Use failure patterns to prioritize SME policy authoring

After Phase 1, cluster the observed differences by:

- action;
- requirement type;
- model;
- frequency;
- severity;
- current grader blindness;
- ranking impact;
- cross-task reuse.

Then use those patterns to decide where SME time is most valuable.

A rough prioritization function:

```text
SME priority
≈ frequency
× harm severity
× grader blindness
× model-ranking impact
× cross-task reuse
```

Examples of likely high-value actions:

- transfer to a human;
- cancel a reservation;
- charge a payment method;
- change a booking;
- disclose personal information.

The output of Phase 2 may become:

```python
PreflightPolicyPack(
    domain="airline",
    rules=[...],
)
```

But do not implement this until Phase 1 has produced evidence about which actions and failure patterns matter most.

---

## Experimental design

This is a paired re-scoring experiment.

Hold constant:

- task;
- original `task_instructions`;
- user-simulator prompt;
- model trajectory;
- tool calls;
- database state;
- agent output.

Change only:

- the grader's access to typed user requirements.

For each trajectory, record:

```python
class PairedGradeResult(BaseModel):
    task_id: str
    model_id: str
    run_id: str

    tau3_score: float
    structured_score: float

    tau3_pass: bool
    structured_pass: bool

    verdict_flip: Literal[
        "none",
        "pass_to_fail",
        "fail_to_pass",
    ]

    violations: list[StructuredRequirementViolation]
```

Prefer re-scoring already-recorded trajectories first. This gives the cleanest comparison and avoids simulator stochasticity.

When later comparing multiple models, use the same task set and enough repeated runs to estimate uncertainty.

---

## Primary measurements

Report at minimum:

### 1. Verdict-flip rate

```text
PASS under τ³ → FAIL under V2
```

This is the clearest false-pass signal.

### 2. Failure-pattern distribution

Examples:

- explicit refusal ignored;
- conditional consent ignored;
- preference violated;
- user understanding not established;
- wrong goal inferred;
- action taken while a required field remained unresolved.

For the first pilot, do not overclaim categories not actually represented.

Task 47 most directly demonstrates explicit refusal or authorization.

### 3. Score delta by action

Examples:

- transfer;
- cancellation;
- payment;
- disclosure;
- booking change.

### 4. Model-specific deltas

For each model:

```text
V2 score − τ³ score
```

### 5. Ranking stability

Compare model rankings under the two graders.

Report:

- Kendall rank correlation;
- Spearman rank correlation;
- pairwise ranking reversals;
- confidence intervals or bootstrap intervals;
- number of tasks supporting each reversal.

Do not make a ranking claim from one stochastic run.

### 6. Direction of flips

Expect primarily:

```text
PASS → FAIL
```

Investigate every:

```text
FAIL → PASS
```

because the structured grader is intended to add visibility, not excuse existing failures.

---

## Why model-ranking changes matter

A model can appear strong under outcome-only grading because it:

- acts quickly;
- minimizes dialogue;
- reaches the expected DB state;
- avoids visible terminal errors.

But it may also:

- assume consent;
- ignore explicit refusals;
- fail to ask before a consequential action;
- optimize the world state while violating the user's process requirements.

A second model may ask more questions and better respect user constraints.

If V2 reverses their order, the benchmark is not merely missing isolated edge cases. It may be selecting for the wrong agent behavior.

The strongest eventual claim would be:

> Outcome-only grading may rank agents incorrectly because it cannot observe whether they established the user requirements needed to act.

Do not make that claim until supported by multi-model evidence.

---

## Implementation plan

### Step 1: Inspect the current branch

Inspect:

- `feat/structured-user-instructions-v2`;
- `src/tau2/data_model/problem_spec.py`;
- the existing `ConstraintEvaluator`;
- task-47 fixtures;
- README and design documents;
- issue #1;
- any uncommitted changes.

Do not blindly preserve the existing `ProblemSpec` abstraction.

Do not blindly delete useful work either.

Reuse:

- provenance support;
- deterministic constraint evaluation;
- the existing task-47 PASS-to-FAIL proof;
- tests that already ground quotes and tool calls.

### Step 2: Add V2 types

Create a minimal module, likely:

```text
src/tau2/data_model/structured_user_instructions_v2.py
```

or another name consistent with the repository.

Include:

- `StructuredUserInstructionsV2`;
- `UserPreflightRequirements`;
- authorization/consent types;
- task-local constraint type;
- optional simulator-policy type;
- provenance fields.

Avoid introducing several new modules unless clearly useful.

### Step 3: Add task-47 V2 fixture

Create a V2 representation of task 47 while preserving:

```python
v2.task_instructions == original.task_instructions
```

Add an explicit test for this equality.

### Step 4: Add structured grader

Implement a deterministic evaluator that:

- reads recorded trajectory tool calls;
- checks the V2 task-local structured requirements;
- emits a human-readable violation;
- links the violation to:
  - action;
  - turn;
  - rule ID;
  - source field;
  - source quote.

For task 47, it should detect the unwanted transfer.

### Step 5: Add paired result output

Create a small result schema and script that re-scores one or more saved trajectories with both graders.

For example:

```text
poc/compare_graders.py
```

Output JSON and a readable Markdown summary.

### Step 6: Preserve the existing pilot

The existing six-task pilot should continue to run.

At minimum:

- task 47 remains τ³ PASS;
- task 47 becomes structured FAIL;
- clean tasks remain clean;
- previously caught DB failures are not misrepresented as novel structured-only findings.

### Step 7: Prepare multi-model extension

Do not run a huge model study unless already configured.

But structure outputs so future runs can compare:

- models;
- tasks;
- seeds;
- τ³ score;
- V2 score;
- verdict flips;
- rankings.

---

## README rewrite

Replace the current broad `ProblemSpec` framing with a more experimentally precise section.

Suggested text:

### From τ³'s `StructuredUserInstructions` to V2

τ³ already gives each simulated user a semi-structured `StructuredUserInstructions` object. But its `task_instructions` field remains overloaded prose: it mixes goals, constraints, consent, and simulator behavior.

We add `StructuredUserInstructionsV2`: the original simulator instructions remain unchanged, while the user's action-relevant requirements are also represented as typed, checkable fields.

```text
UserScenario
├── persona
└── instructions: StructuredUserInstructionsV2
    ├── domain
    ├── reason_for_call
    ├── known_info
    ├── unknown_info
    ├── task_instructions          ← unchanged simulator prose
    └── preflight_requirements    ← new grader-visible representation
```

This lets us score the same trajectory in two ways:

```text
same task
same simulator instructions
same trajectory
same agent output
         │
         ├── τ³ grader
         └── preflight-requirements grader
```

Any verdict difference is therefore attributable to what the grader can represent, not to a changed conversation.

For task 47, the user's instruction not to transfer is present in the simulator prompt but absent from τ³'s grading criteria. The τ³ grader returns PASS; the preflight-requirements grader returns FAIL.

---

## Terminology guidance

Use these terms consistently in the pilot:

### `StructuredUserInstructions`

τ³'s existing semi-structured user-simulator input.

### `StructuredUserInstructionsV2`

The same user-simulator input plus a typed representation of action-relevant requirements.

### `UserPreflightRequirements`

The typed task-local requirements derived only from the existing τ³ scenario.

### `PreflightRequirementsEvaluator`

The new deterministic grader for those requirements.

### `Paired re-scoring`

The experiment in which identical trajectories are graded by τ³ and V2.

### `Revealed but missed`

A requirement is stated in the τ³ task, violated by the agent, and missed by the existing grader.

### `Should exist but omitted`

A future SME identifies an action requirement absent from both the task and grader.

Reserve this for the later policy-pack phase.

### `Epistemic precondition`

Keep as the theoretical mechanism-level term:

> A fact the agent must know or resolve before firing an action.

Do not require the README's first pass to explain the entire epistemic-planning literature.

### `PreflightPolicyPack`

Future domain-level collection of SME-authored reusable action rules.

Do not make it a dependency of the current experiment.

---

## Required provenance

Every V2 structured requirement must carry provenance.

At minimum:

```python
source_field: str
source_quote: str
```

Prefer also:

```python
task_id: str
source_path: str | None
source_line: int | None
```

This is important because the pilot's legitimacy depends on showing:

> We did not invent a new rule. We made an existing stated rule gradeable.

Later SME-authored rules should use different provenance, such as:

```python
source_type="sme"
expert_role="airline_customer_service"
review_status="verified"
```

But do not implement the full SME metadata system now.

---

## Verification discipline

Do not trust an LLM extraction without verification.

If an LLM helps convert task prose into V2 fields:

1. retain the exact source quote;
2. deterministically verify the quote exists;
3. manually review the pilot tasks;
4. distinguish extracted requirements from invented interpretations;
5. reject unsupported rules.

For the first pilot, a small manually verified V2 dataset is preferable to a large noisy extraction.

---

## Acceptance criteria

The refactor is complete when all of the following hold.

### Data model

- `StructuredUserInstructionsV2` exists.
- It preserves the original `task_instructions` string.
- It adds a typed `preflight_requirements` field.
- Task-local structured requirements include source provenance.
- Simulator-only behavior is separated where practical.

### Task 47

- "You don't want to be transferred to another agent" is represented as explicit denied authorization or an equivalent typed constraint.
- "Do not cancel without a full refund" is represented as conditional authorization or an equivalent typed constraint.
- `transfer_requested=False` is not used as a substitute for explicit refusal.
- `refund_eligible` remains a world or policy fact, not a user requirement.

### Experiment

- The same recorded trajectory is scored by both graders.
- The original τ³ grader returns PASS for task 47.
- The V2 structured grader returns FAIL for task 47.
- The output explains exactly why the verdict flipped.
- No simulator prompt or trajectory changes are required for the flip.

### Regression

- Existing τ³ code paths remain usable.
- Clean tasks do not become failures without grounded requirements.
- Existing DB failures are not falsely presented as newly discovered.
- No hidden task values are leaked to the tested agent.

### Reporting

- A paired comparison JSON artifact is produced.
- A readable Markdown summary is produced.
- Results include counts of `PASS → FAIL`, `FAIL → PASS`, and unchanged verdicts.
- Output schema supports future grouping by model and seed.

---

## Non-goals

Do not do these during this refactor:

- do not build a universal user model;
- do not formalize the user's complete epistemic state;
- do not build a general-purpose logic engine;
- do not build the full SME authoring UI;
- do not require `PreflightPolicyPack`;
- do not rewrite the user-simulator prompt;
- do not claim current task-local requirements are a complete safety policy;
- do not claim model rankings change until multiple models are actually tested;
- do not silently infer requirements unsupported by τ³ source text;
- do not perform a repo-wide blind string replacement.

---

## Documents and code to update

Inspect and deliberately update references in:

- `README.md`;
- `PROBLEM_BELIEF_SPEC.md`;
- `FRAMING.md`;
- `docs/design-notes-what-to-establish.md`;
- `docs/epistemic-preconditions.md`;
- `poc/CASE_STUDY.md`;
- `poc/FINDINGS.md`;
- `docs/pilot-details.md`;
- current `ProblemSpec` source;
- current constraint evaluator;
- tests;
- issue #1 references;
- branch links and repository map.

Search for:

```text
ProblemSpec
ProblemSpecBelief
problem_spec
RequirementSpec
user requirements
same object
preflight policy
policy pack
transfer_requested
```

For each occurrence, decide whether it refers to:

- the old abandoned abstraction;
- V2 structured task-local requirements;
- future agent belief tracking;
- future SME policy authoring.

Do not force all of those concepts into one type.

---

## Recommended final narrative

The repository should tell one simple story:

1. τ³ gives the user simulator prose containing important user requirements.
2. The grader checks only a subset of them.
3. We add `StructuredUserInstructionsV2`, preserving the exact simulator prose while making those requirements typed and gradeable.
4. We re-score the same trajectories with both graders.
5. We measure verdict flips, score changes, and eventually model-ranking changes.
6. We cluster the new failure patterns by action and severity.
7. Those patterns tell us where future SME-authored reusable preflight rules would have the highest value.

The immediate claim is:

> Structuring requirements already present in τ³ exposes grader false-passes.

The later claim, if supported, is:

> These missed requirements can change which models appear best.

The future product/research direction is:

> Use observed failure patterns to prioritize SME-authored preflight policy packs for high-impact actions.

---

## Final deliverable from Claude Code

After implementation, return:

1. a concise architectural summary;
2. a file-by-file change list;
3. the final V2 schema;
4. the task-47 V1 versus V2 representation;
5. the paired grader output for task 47;
6. test results;
7. any unsupported assumptions removed;
8. any remaining decisions that genuinely block broader evaluation;
9. a recommended next experiment for comparing multiple LLM rankings.

Do not merely rename classes. Make the paired re-scoring experiment explicit and executable.
