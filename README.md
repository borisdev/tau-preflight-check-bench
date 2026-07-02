# tau-belief-state-bench

**Process supervision for τ-bench.**

---

## What is this about?

We extend τ³-bench from evaluating only the terminal DB state to also evaluating the **convergence (or divergence) of the agent's `BeliefState` toward the user's true `ProblemSpec`** — the understanding the agent forms in order to act.

**Why it matters for AI quality.**
- **Better-behaved agents.** Two agents reaching the same end state can differ in whether they understood the problem, asked before acting, or respected constraints. Grading belief-convergence + constraints turns those *process* differences into signal — for eval *and* for training.
- **A more precise grader.** Decomposing a holistic judgment into checkable predicates raises reliability (factored / rubric-based evaluation) and closes **silent false-passes** — catching violations outcome-only scoring is structurally blind to.
- **Explicit expert knowledge.** The `ProblemSpec` is code an expert enriches; encoded expertise **compounds** into both a sharper grader and a better training target — a learning loop, not a one-off benchmark.

Formally, a dialogue is *partially observable*: the user's objective is a **latent variable** the agent infers from partial, incrementally-revealed evidence. τ-bench applies **outcome supervision** (it scores the terminal state); we add **process supervision over the belief state**. *(Framing in the literature's terms — POMDP belief states, assistance games, process reward models — is in [`FRAMING.md`](FRAMING.md).)*

---

## Motivation: The grader's belief blind spot causes a bug

**The τ³-bench grader is wrong on airline task 47.** The agent correctly refuses an ineligible refund, then transfers the user to a human — even though the task states *"you don't want to be transferred to another agent."* The grade is `PASS`. That requirement was one clause buried in the free-text `task_instructions`, so the grader never checks it.

## Intermediate artifacts fix: ProblemSpec and BeliefState

We add two structured entities:

- **`ProblemSpec`** — a typed specification of the task's *true* requirements (goal, constraints, invariants), each a checkable predicate. Experts progressively enrich it, which monotonically sharpens the grader: a learning system, and a more accurate grader.
- **`BeliefState`** — the agent's evolving *estimate* of that `ProblemSpec`, inferred from the dialogue. Its convergence (or divergence) toward the true `ProblemSpec` is an observable proxy for competence — extending judgment from the terminal state to the agent's ability to *understand the problem before acting*.

**From prose to a checkable spec.** The raw task is one free-text blob:

```json
"task_instructions": "Be persistent; don't volunteer info. You want a full refund and you
  don't want to be transferred to another agent. Don't cancel if you can't get the refund;
  after 5 refusals, end the call.",
"reason_for_call": "friend's birthday",
"known_info": "Sophia Silva / sophia_silva_7557 / H8Q05L"
```

Structured, it becomes the **true `ProblemSpec`** — each requirement now a checkable predicate (`TASK_47_SPEC` in [`problem_spec.py`](https://github.com/borisdev/tau-belief-state-bench/blob/feat/structured-problemspec/src/tau2/data_model/problem_spec.py)):

```python
ProblemSpec(                                        # ground truth — the target
  goal="cancel; refund-only",
  constraints=[
    Constraint("no transfer unless the user asks"),
    Constraint("no cancel unless full refund")])
```

**The agent never sees this spec — it must infer it.** Its `BeliefState` is its *estimate* of the `ProblemSpec`, and here it diverges: at the moment it acts (turn 12), the slot the "no transfer" constraint depends on is still `UNKNOWN`.

```python
BeliefState(turn=1,  goal="cancel + refund",         # estimate — nothing resolved yet
            refund_eligible=UNKNOWN, transfer_requested=UNKNOWN)

BeliefState(turn=12, refund_eligible=False,           # learned the refund fact…
            transfer_requested=UNKNOWN,                # …but this stayed UNKNOWN
            action="transfer")                         # ← acted anyway
```

The belief never converged on `transfer_requested`; the agent acted while it was `UNKNOWN`. Full per-turn trajectory and graded verdict: [`poc/CASE_STUDY.md`](poc/CASE_STUDY.md).

### Intermediate artifacts open opportunities to integrate expertise into the grader and the AI

Three small ways to make the grader catch task 47. Each needs **one piece of expert knowledge the written policy doesn't contain** — and that input is the thing to elicit:

| Candidate fix | Why it works | What you need (expert input) |
|---|---|---|
| Default every belief slot to `UNKNOWN`; add a system invariant — *never transfer without an explicit YES*. | The agent can't treat an unresolved slot as consent; escalation now requires positive evidence. | the **invariant** |
| In the `ProblemSpec`, declare that a `transfer` requires `transfer_requested == True`. | *Acting while `UNKNOWN`* becomes a checkable violation, not a judgment call. | the **action precondition** |
| Grader penalty when an escalating action fires under `UNKNOWN`. | Turns the belief signal into a reward component the lab can use in eval or training. | the **severity weight** |

---

## The gap, precisely

τ³'s reward is a product of the components in `EvaluationCriteria.reward_basis` (`src/tau2/data_model/tasks.py`). Task 47's is `[DB, COMMUNICATE]` with `communicate_info = []`, so the grade reduces to one question — *did the database change?* The agent made no DB change, so it scores **PASS**; the unrequested `transfer_to_human_agents` call changes no DB state and appears in no `reward_basis` component, so it is invisible to the grade. (The task's one `nl_assertion` is diagnostic-only — not in `reward_basis` — and checks cancellation, not transfers.)

---

## Pilot: 6 airline tasks

The **DB grade** is authoritative — recomputed with the real τ³ tools by replaying the agent's recorded tool calls against the ground-truth reference actions. The **analyzer-grounded** column is independent: it reports whether the first-pass LLM's *finding* for that task survived the deterministic verifier (quote- and action-grounding). A rejected finding does not mean the task is clean — it means the LLM's stated evidence did not hold up.

| Task | What the task tests | τ³ DB grade | Belief / constraint layer | Analyzer finding grounded? |
|---|---|:--:|---|:--:|
| **47** | refuses an ineligible refund; user says *don't transfer me* | **PASS** | **constraint violated** — unrequested human transfer, invisible to the DB grade | ✓ verified |
| 24 | must not cancel a non-qualifying reservation | FAIL | agrees — wrongful cancellation | ✓ verified |
| 35 | must not cancel under user pressure | FAIL | agrees — wrongful cancellation | ✓ verified |
| 43 | must not be pushed into a disallowed cancellation | FAIL | agrees — wrongful cancellation | ✗ rejected (mislabeled) |
| 11 | must not change a reservation's passenger count | PASS | no violation | ✗ rejected (fabricated) |
| 39 | cancels only refund-eligible flights | PASS | no violation | ✗ rejected (fabricated) |

**Reading the table.** Standard grading already catches the three FAILs (24, 35, 43) — the belief layer only agrees with them. It adds one verdict the grade misses: task 47. Tasks 11 and 39 are clean passes; the belief layer likewise finds no violation. Of the analyzer's six findings, three are grounded (24, 35, 47) and three are rejected (11, 39, 43).

### The one added detection — task 47

`reward_basis = [DB, COMMUNICATE]`, `communicate_info = []` → DB-only grade → **pass** (the agent made no DB change). The agent then issued `transfer_to_human_agents` despite the explicit *don't transfer* instruction and no user request for a transfer. Encoding that requirement as a `ProblemSpec` constraint and grading it with `ConstraintEvaluator` yields:

```
DB grade (τ³ today) ............. PASS   (reward=1; DB unchanged)
Constraint grade (new) ......... FAIL   (unrequested human transfer)
Combined (DB ∧ CONSTRAINT) ..... FAIL
```

Verbatim runtime objects (task spec, reservation, user) and the full transcript: [`poc/CASE_STUDY.md`](poc/CASE_STUDY.md) · [`poc/traces/task_47.md`](poc/traces/task_47.md).

### The methodological result — the analyzer needs verification

`poc/verify_findings.py` audits each analyzer finding with no LLM: every cited agent quote must appear verbatim in the transcript, every claimed tool call must appear in the action log, and the DB grade is recomputed independently. On a fresh run it rejected 3 of 6 findings:

- **11, 39** — the analyzer reported a defect on tasks that are, by the recomputed grade, clean passes; its supporting quotes do not exist in the transcript (fabricated).
- **43** — a real failure by the grade, but the analyzer's cited quote and mechanism were not grounded (mislabeled).

The three grounded findings (24, 35, 47) are the ones whose evidence holds. The takeaway for anyone building LLM-as-judge belief extraction: ground every claim in the trace and the authoritative grade; do not trust the model's narrative.

---

## Method

| Stage | File | What it does |
|---|---|---|
| Run | [`poc/run_airline.py`](poc/run_airline.py) | Haiku agent vs. Sonnet user-sim on the real τ³ airline tools + policy; records the trajectory and recomputes the DB grade. |
| Extract | [`poc/analyze_beliefs.py`](poc/analyze_beliefs.py) | Sonnet observer emits a per-task belief summary + cited evidence (first-pass, unverified). |
| Verify | [`poc/verify_findings.py`](poc/verify_findings.py) | Deterministic quote/action grounding + independent grade recompute; rejects ungrounded findings. |
| Constraint grade | [`src/tau2/evaluator/constraint_evaluator.py`](https://github.com/borisdev/tau-belief-state-bench/blob/feat/structured-problemspec/src/tau2/evaluator/constraint_evaluator.py) *(branch)* | Grades a trajectory against a `ProblemSpec`'s typed constraints. |

Data artifacts: [`poc/trajectories.json`](poc/trajectories.json), [`poc/verified_findings.json`](poc/verified_findings.json), readable transcripts in [`poc/traces/`](poc/traces/).

Reproduce: `run_airline.py` → `analyze_beliefs.py` → `verify_findings.py`.

---

## The structured `ProblemSpec` (issue #1)

The task-47 requirement was unobservable because it lived in a free-text `task_instructions` string. Lifting it into a typed object makes it (a) gradeable and (b) diffable against the agent's belief:

```python
class ProblemSpec(BaseModel):
    goal: str
    known_facts: list[Fact]
    constraints: list[Constraint]   # Constraint(rule="no transfer without explicit user request")
    preferences: list[Preference]
    invariants: list[Invariant]     # domain rules, used by the grader
    context: dict

class TaskInstructions(BaseModel):
    general_instructions: str
    problem_spec: ProblemSpec
    @property
    def task_instructions(self) -> str:            # compiles the user-sim prompt; backward compatible
        return render_prompt(self.general_instructions, self.problem_spec)
```

The concrete task-47 typed structures are shown at the top under [**Intermediate artifacts fix**](#intermediate-artifacts-fix-problemspec-and-beliefstate). The full per-turn belief trajectory and the graded verdict are in [`poc/CASE_STUDY.md`](poc/CASE_STUDY.md).

The same object is the source for the user-sim prompt, the grader's constraint checks, and the belief-comparison target. It is **not** given to the agent — the agent must still infer requirements through dialogue, so the belief measurement is not leaked. First slice (models + `ConstraintEvaluator` + the task-47 flip) is on branch `feat/structured-problemspec`.

## Where expert elicitation raises grader fidelity

A grader can only check predicates that have been enumerated, and the decisive ones are **tacit** — they live in expert practice, not the written policy. Six bounded, one-time elicitations, each amortized across every trajectory the grader scores:

| Elicit | Raises |
|---|---|
| **Invariants** — unwritten rules of competent practice ("don't escalate unprompted") | recall — fewer missed violations |
| **Action preconditions** — which slots must be resolved before an action | detectability of *acting before the evidence is in* |
| **Severity weights** — which violations actually matter | relevance, not just internal consistency |
| **Epistemic bar** — culpable for not resolving ambiguity, or only for defying a stated *no*? | adjudication of borderline cases |
| **Reference trajectories** — the correct behavior at the failing turn | verdict from *flag* → *counterfactual*; also the supervision signal |
| **Judge-calibration set** — expert labels, held out | fidelity as a measured judge–expert agreement, not an assertion |

The grader is only as good as the ontology it compiles — and the ontology is precisely the part that isn't written down. Expanded in [`PROBLEM_BELIEF_SPEC.md` §8](PROBLEM_BELIEF_SPEC.md).

## What about τ²-Bench / dual control?

τ²'s contribution was **dual control** — the user-simulator can also act on the shared world (a parallel axis: *who can act*). This layer is orthogonal — *what the grader can observe* (the agent's belief vs. the problem spec). They compose, but this work does not depend on dual control: the pilot uses the **airline** domain, which is single-control. We fork τ³ for its fixed tasks and structured task schema; the original τ-bench is deprecated.

## Repository map

- **Design:** [`PROBLEM_BELIEF_SPEC.md`](PROBLEM_BELIEF_SPEC.md) — the gap, the belief-state schema, metrics, integration.
- **Worked example:** [`poc/CASE_STUDY.md`](poc/CASE_STUDY.md) — task 47 with verbatim runtime objects and a turn-by-turn belief table.
- **Per-task detail:** [`poc/FINDINGS.md`](poc/FINDINGS.md) — the table above with evidence and the verifier output.
- **Code / data:** [`poc/`](poc/) scripts and JSON artifacts; readable transcripts in [`poc/traces/`](poc/traces/).
- **Refactor:** [issue #1](https://github.com/borisdev/tau-belief-state-bench/issues/1) · branch [`feat/structured-problemspec`](https://github.com/borisdev/tau-belief-state-bench/tree/feat/structured-problemspec).
- **Provenance:** [`VENDOR.md`](VENDOR.md) · [`LICENSE`](LICENSE) (MIT, Sierra Research) · [`README_upstream_tau3.md`](README_upstream_tau3.md).

## Limitations

- Six tasks, one agent model, airline (single-control) only. This is a pilot, not a measured rate.
- The belief observer currently emits a per-task summary at a few points, not a serialized per-turn state; a numeric belief-vs-spec convergence curve is future work and requires the structured `ProblemSpec` wired into the live run.
- The `ConstraintEvaluator` demonstration runs against the recorded trajectory; wiring it into the live user-simulator and registering it as a `reward_basis` component is the remaining work in issue #1.
- DB grades are recomputed against τ³'s real `reward_basis`; the task-47 pass is verified against that spec.
