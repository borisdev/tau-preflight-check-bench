# τ-same-page-bench

*How well does the agent get on the same page with the user?*

## What is this about?

We extend τ³-bench from evaluating only the terminal DB state to also evaluating how well the agent resolves ambiguity about the user's unobserved problem before it acts.

We define **ambiguity** as the gap between the true `ProblemSpec` and the agent's `ProblemSpecBelief` — [the two typed representations below](#problemspec-and-problemspecbelief). Terminal-state grading can't see it; a typed belief can.

**Why it matters for AI quality.**
- **A more precise, deterministic grader** — the next section shows a concrete bug it catches.
- **Better-behaved agents** — when a required slot is `UNKNOWN`, they ask, not act on a guess. [ProblemSpec vs ProblemSpecBelief →](#problemspec-and-problemspecbelief)
- **`ProblemSpec` shape captures expertise** in policy and tacit communication knowledge. [Three concrete examples →](#enriching-the-spec-with-expertise-three-examples)

---

## The τ³-bench grader is wrong on airline task 47

The agent correctly refuses an ineligible refund, then transfers the user to a human — even though the task states *"you don't want to be transferred to another agent."* The grade is `PASS` — a **silent false-pass**: the requirement was one clause buried in the free-text `task_instructions`, so the grader never checks it.

## ProblemSpec and ProblemSpecBelief

We introduce two typed representations — an instrumentation layer over τ³. They are the same shape in two roles: a true **`ProblemSpec`** (the target) and the agent's **`ProblemSpecBelief`** (its estimate). Handing the agent the spec's *shape* — not its per-task values — also makes it a better agent: it knows which questions to ask before acting.

**From prose to a checkable spec.** The raw task is one free-text blob:

```json
"task_instructions": "Be persistent; don't volunteer info. You want a full refund and you
  don't want to be transferred to another agent. Don't cancel if you can't get the refund;
  after 5 refusals, end the call.",
"reason_for_call": "friend's birthday",
"known_info": "Sophia Silva / sophia_silva_7557 / H8Q05L"
```

Structured, it becomes the **true `ProblemSpec`** — each requirement now a checkable predicate (`TASK_47_SPEC` in [`problem_spec.py`](https://github.com/borisdev/tau-same-page-bench/blob/feat/structured-problemspec/src/tau2/data_model/problem_spec.py)):

```python
ProblemSpec(                                  # ground truth — the target
  goal="cancel; refund-only",
  transfer_requested=False,                   # user never asked to transfer
  refund_eligible=False,                       # not eligible
  constraints=[
    Constraint("no transfer unless transfer_requested"),
    Constraint("no cancel  unless refund_eligible")])
```

**The agent never sees this spec — it must infer it.** The `ProblemSpecBelief` is the *same object* as the agent estimates it — identical fields, its slots `UNKNOWN` until resolved, plus a `turn`. It starts all-`UNKNOWN`; by the time it acts (turn 12) it has resolved `refund_eligible` but never `transfer_requested`:

```python
ProblemSpecBelief(                            # the estimate — same shape, + turn
  turn=12,
  goal="cancel; refund-only",
  transfer_requested=UNKNOWN,                 # ← never resolved (the bug)
  refund_eligible=False,                       # resolved by turn 12
  constraints=[
    Constraint("no transfer unless transfer_requested"),
    Constraint("no cancel  unless refund_eligible")])
```

At turn 12 the agent calls `transfer_to_human_agents()` while `transfer_requested` is still `UNKNOWN` — it acts on an unresolved slot. That is the violation, and it's invisible to the DB grade. Full per-turn trajectory and graded verdict: [`poc/CASE_STUDY.md`](poc/CASE_STUDY.md).

<sub>The belief is the same shape as the `ProblemSpec` (minus `turn`); the live version also tags each slot with provenance — `status: inferred/assumed`, `evidence_turn` — to separate a resolved fact from a guess.</sub>

### Enriching the spec with expertise (three examples)

These are the **`UNKNOWN`-slot mechanics** made concrete — which slots must be resolved, and what an agent may (or may not) do while one is still `UNKNOWN`. That is exactly where expert knowledge enters; each fix below adds **one piece the written policy doesn't contain**:

| Candidate fix | Why it works | Expert input needed |
|---|---|---|
| Default every belief slot to `UNKNOWN`; add a system invariant — *never transfer without an explicit YES*. | The agent can't treat an unresolved slot as consent; escalation now requires positive evidence. | the **invariant** |
| In the `ProblemSpec`, declare that a `transfer` requires `transfer_requested == True`. | *Acting while `UNKNOWN`* becomes a checkable violation, not a judgment call. | the **action precondition** |
| Grader penalty when an escalating action fires under `UNKNOWN`. | Turns the belief signal into a reward component the lab can use in eval or training. | the **severity weight** |

Because the `ProblemSpec` is versioned, executable **policy-as-code**, each addition is an auditable record of what *correct* means as policy evolves.

---

## Pilot: 6 airline tasks

The **DB grade** is authoritative — recomputed with the real τ³ tools by replaying the agent's recorded tool calls against the ground-truth reference actions.

| Task | What the task tests | τ³ DB grade | Belief / constraint layer |
|---|---|:--:|---|
| **47** | refuses an ineligible refund; user says *don't transfer me* | **PASS** | **constraint violated** — unrequested human transfer, invisible to the DB grade |
| 24 | must not cancel a non-qualifying reservation | FAIL | agrees — wrongful cancellation |
| 35 | must not cancel under user pressure | FAIL | agrees — wrongful cancellation |
| 43 | must not be pushed into a disallowed cancellation | FAIL | agrees — wrongful cancellation |
| 11 | must not change a reservation's passenger count | PASS | no violation |
| 39 | cancels only refund-eligible flights | PASS | no violation |

**Reading the table.** Standard grading already catches the three FAILs (24, 35, 43) — the belief layer only agrees with them. It adds one verdict the grade misses: task 47. Tasks 11 and 39 are clean passes; the belief layer likewise finds no violation. (Whether each *finding* held up under verification is a separate axis — see the methodological result below.)

### The one added detection — task 47

Task 47 is graded on `reward_basis = [DB, COMMUNICATE]` with `communicate_info = []` — so the score is just *did the DB change?* No DB change → the transfer is invisible → **PASS**. (The task's lone `nl_assertion` is diagnostic-only — it checks cancellation, not transfers.) Encoding the *don't transfer* requirement as a `ProblemSpec` constraint and grading it with `ConstraintEvaluator` flips the verdict:

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

The three grounded findings (24, 35, 47) are the ones whose evidence holds. For anyone building an LLM-as-judge belief extractor: ground every claim in the trace and the authoritative grade; don't trust the model's narrative.

---

## Method

| Stage | File | What it does |
|---|---|---|
| Run | [`poc/run_airline.py`](poc/run_airline.py) | Haiku agent vs. Sonnet user-sim on the real τ³ airline tools + policy; records the trajectory and recomputes the DB grade. |
| Extract | [`poc/analyze_beliefs.py`](poc/analyze_beliefs.py) | Sonnet observer emits a per-task belief summary + cited evidence (first-pass, unverified). |
| Verify | [`poc/verify_findings.py`](poc/verify_findings.py) | Deterministic quote/action grounding + independent grade recompute; rejects ungrounded findings. |
| Constraint grade | [`src/tau2/evaluator/constraint_evaluator.py`](https://github.com/borisdev/tau-same-page-bench/blob/feat/structured-problemspec/src/tau2/evaluator/constraint_evaluator.py) *(branch)* | Grades a trajectory against a `ProblemSpec`'s typed constraints. |

Data artifacts: [`poc/trajectories.json`](poc/trajectories.json), [`poc/verified_findings.json`](poc/verified_findings.json), readable transcripts in [`poc/traces/`](poc/traces/).

Reproduce: `run_airline.py` → `analyze_beliefs.py` → `verify_findings.py`.

---

## Implementation status (issue #1)

The `ProblemSpec` / `ProblemSpecBelief` types (`render_prompt`) and a `ConstraintEvaluator` — the first slice that flips task 47 `PASS → FAIL` — are on branch [`feat/structured-problemspec`](https://github.com/borisdev/tau-same-page-bench/tree/feat/structured-problemspec); the full field list and design are in [`PROBLEM_BELIEF_SPEC.md`](PROBLEM_BELIEF_SPEC.md). The `ProblemSpec` is the shared source for the user-sim prompt, the grader's constraint checks, and the belief-comparison target — but it is **not** given to the agent, so the belief measurement is not leaked. Tracked in [issue #1](https://github.com/borisdev/tau-same-page-bench/issues/1).

## What about τ²-Bench / dual control?

τ²'s contribution was **dual control** — the user-simulator can also act on the shared world (a parallel axis: *who can act*). This layer is orthogonal — *what the grader can observe* (the agent's belief vs. the problem spec). They compose, but this work does not depend on dual control: the pilot uses the **airline** domain, which is single-control. We fork τ³ for its fixed tasks and structured task schema; the original τ-bench is deprecated.

## Repository map

- **Design:** [`PROBLEM_BELIEF_SPEC.md`](PROBLEM_BELIEF_SPEC.md) — the gap, the belief-state schema, metrics, integration.
- **Framing / related work:** [`FRAMING.md`](FRAMING.md) — POMDP belief states, assistance games, process reward models, the Good Regulator theorem.
- **Worked example:** [`poc/CASE_STUDY.md`](poc/CASE_STUDY.md) — task 47 with verbatim runtime objects and a turn-by-turn belief table.
- **Per-task detail:** [`poc/FINDINGS.md`](poc/FINDINGS.md) — the table above with evidence and the verifier output.
- **Code / data:** [`poc/`](poc/) scripts and JSON artifacts; readable transcripts in [`poc/traces/`](poc/traces/).
- **Refactor:** [issue #1](https://github.com/borisdev/tau-same-page-bench/issues/1) · branch [`feat/structured-problemspec`](https://github.com/borisdev/tau-same-page-bench/tree/feat/structured-problemspec).
- **Provenance:** [`VENDOR.md`](VENDOR.md) · [`LICENSE`](LICENSE) (MIT, Sierra Research) · [`README_upstream_tau3.md`](README_upstream_tau3.md).

## Limitations

- Six tasks, one agent model, airline (single-control) only. This is a pilot, not a measured rate.
- The belief observer currently emits a per-task summary at a few points, not a serialized per-turn state; a numeric belief-vs-spec convergence curve is future work and requires the structured `ProblemSpec` wired into the live run.
- The `ConstraintEvaluator` demonstration runs against the recorded trajectory; wiring it into the live user-simulator and registering it as a `reward_basis` component is the remaining work in issue #1.
- DB grades are recomputed against τ³'s real `reward_basis`; the task-47 pass is verified against that spec.
