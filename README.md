# tau-belief-state-bench

A per-turn **belief-state** instrumentation layer for τ-bench (the `tau2-bench` repo at its τ³ release). τ-bench grades an agent on the **terminal world state**; it does not measure whether the agent understood the user's problem, or whether it honored requirements that never touch the database. This repo adds two agent-agnostic components on top of the existing benchmark:

1. a **belief observer** that extracts the agent's estimate of the user's problem after each turn, and
2. a structured **`ProblemSpec`** that lifts a task's requirements out of free-text instructions into typed constraints a grader can check directly.

Trimmed, text-only derivative of [`sierra-research/tau2-bench`](https://github.com/sierra-research/tau2-bench) (MIT); see [`VENDOR.md`](VENDOR.md).

---

## Example

In airline **task 47** the agent correctly refuses an ineligible refund (**a pass**) — then transfers the user to a human, which the task forbade. That requirement was one clause buried in the free-text spec. Structured, it becomes a typed constraint the grader can check:

**1 — Static: the task, restructured** — this is `TASK_47_SPEC` in [`problem_spec.py`](https://github.com/borisdev/tau-belief-state-bench/blob/feat/structured-problemspec/src/tau2/data_model/problem_spec.py).

<table>
<tr><th align="left">Raw τ³ task — one prose blob</th><th align="left">Restructured — typed <code>ProblemSpec</code></th></tr>
<tr valign="top">
<td>

```json
"task_instructions":
  "Be persistent; don't volunteer
   info. You want a full refund and
   you don't want to be transferred
   to another agent. Don't cancel if
   you can't get the refund; after 5
   refusals, end the call.",
"reason_for_call": "friend's birthday",
"known_info":
  "Sophia Silva / ..._7557 / H8Q05L"
```

*"Don't transfer me"* is one clause among
persona notes and an exit rule — not
separable, not gradeable.

</td>
<td>

```python
TaskInstructions(
  general_instructions=
    "be persistent; reveal only as "
    "needed; end after 5 refusals",
  problem_spec=ProblemSpec(
    goal="cancel H8Q05L, refund-only",
    known_facts=[
      Fact("user", "Sophia Silva"),
      Fact("reservation", "H8Q05L"),
      Fact("reason", "friend b-day")],
    constraints=[
      Constraint("no transfer unless "
                 "the user asks"),
      Constraint("no cancel unless "
                 "full refund")]))
```

`general_instructions` drives the user-sim;
the problem is `goal` + `known_facts`; each
requirement is a typed `Constraint`.

</td>
</tr>
</table>

**2 — Dynamic: the belief that should converge to it.** The agent never sees the spec; it must infer one slot, `transfer_requested`, from the dialogue:

| Turn | What the user has said | belief · `transfer_requested` | Agent |
|:--:|---|:--:|---|
| **1** | wants to cancel + a full refund | `None` | gathers details |
| **12** | asked for a refund ~5×; **never** a transfer | still `None` | **calls `transfer_to_human_agents`** — acts on an unresolved slot |
| **13** | "I don't want to be transferred" | `False` *(revealed)* | the turn-12 decision was made blind |

The slot stayed `None` for twelve turns — repeated refund requests, not one transfer request — yet the agent escalated. The reveal at turn 13 shows the decision outran the evidence.

**3 — Graded verdict, by the slot's state at the action turn** — a signal only a per-turn trace can produce:

| At the moment the agent transfers | `transfer_requested` | Verdict |
|---|:--:|---|
| user asked for a human | `True` | correct — no violation |
| user never raised it&nbsp;&nbsp;**← task 47** | **`None`** | **moderate** — escalated on an unresolved slot (negligence) |
| user explicitly said no | `False` | **severe** — overrode a stated preference (defiance) |

Task 47 is the `None` / moderate case, not the severe one. The two things this table can't derive on its own — the **severity weights** and where to set the **culpability bar** for `None` — are expert-set; see [Where expert elicitation raises grader fidelity](#where-expert-elicitation-raises-grader-fidelity).

---

## Overview

- **The gap.** τ³'s reward is the terminal DB state plus required output substrings (`reward_basis`). A requirement that does not change the DB — e.g. *"do not transfer me to a human"* — is unobservable to the grade. This is verified against τ³'s real grading spec, not assumed.
- **Pilot (6 airline tasks).** Claude Haiku as the agent under test; Claude Sonnet as user-simulator and belief observer. On **1 of 6 tasks** the belief/constraint layer changes the verdict: **task 47 passes the DB grade while the agent violates an explicit "don't transfer" requirement.** The standard grade already fails 3 tasks (wrongful cancellations); 2 are clean passes. So the layer's net new signal in this pilot is one task.
- **A second, methodological result.** The LLM used to extract belief-findings is unreliable on its own. A deterministic, evidence-grounding verifier **rejected 3 of its 6 findings** as unsupported by the transcript (two fabricated defects on clean passes, one mislabeled mechanism). Belief-extraction has to be checked against the trace, not trusted.
- **Refactor (in progress).** A structured `ProblemSpec` + a `ConstraintEvaluator` makes the task-47 requirement gradeable and flips task 47's verdict pass → fail — [issue #1](https://github.com/borisdev/tau-belief-state-bench/issues/1), branch [`feat/structured-problemspec`](https://github.com/borisdev/tau-belief-state-bench/tree/feat/structured-problemspec).

This is a **pilot / existence proof**, not a benchmark result. Six tasks is enough to demonstrate the mechanism and one concrete instance; it is not a rate.

---

## The gap, precisely

τ³ combines its reward from components listed in `EvaluationCriteria.reward_basis` (`src/tau2/data_model/tasks.py`). The default is `[DB, COMMUNICATE]`: the predicted end-state DB hash must match the target, and required substrings must appear. Task **47**'s criteria are `reward_basis = [DB, COMMUNICATE]` with `communicate_info = []`, so the grade reduces to a single question: *did the database change?*

Task 47's user instructions include: *"you don't want to be transferred to another agent."* The agent correctly refuses an ineligible refund (no DB change → the grade is a **pass**) and then calls `transfer_to_human_agents` anyway, with no prior user request to be transferred. Nothing in `reward_basis` observes this. The one `nl_assertion` on the task is diagnostic-only (it is not in `reward_basis`) and checks cancellation, not transfers.

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

The concrete task-47 before/after, the belief trajectory, and the graded verdict are shown at the top in [**Example**](#example).

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
