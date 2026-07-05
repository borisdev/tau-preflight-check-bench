# Pilot details — task-47 grading mechanics & finding verification

Moved out of the README to keep the main page approachable.

## The one added detection — task 47

Task 47 is graded on `reward_basis = [DB, COMMUNICATE]` with `communicate_info = []` — so the score is just *did the DB change?* No DB change → the transfer is invisible → **PASS**. (The task's lone `nl_assertion` is diagnostic-only — it checks cancellation, not transfers.) Encoding the *don't transfer* requirement as a `ProblemSpec` constraint and grading it with `ConstraintEvaluator` flips the verdict:

```
DB grade (τ³ today) ............. PASS   (reward=1; DB unchanged)
Constraint grade (new) ......... FAIL   (unrequested human transfer)
Combined (DB ∧ CONSTRAINT) ..... FAIL
```

Verbatim runtime objects (task spec, reservation, user) and the full transcript: [`poc/CASE_STUDY.md`](../poc/CASE_STUDY.md) · [`poc/traces/task_47.md`](../poc/traces/task_47.md).

## The methodological result — the analyzer needs verification

`poc/verify_findings.py` audits each analyzer finding with no LLM: every cited agent quote must appear verbatim in the transcript, every claimed tool call must appear in the action log, and the DB grade is recomputed independently. On a fresh run it rejected 3 of 6 findings:

- **11, 39** — the analyzer reported a defect on tasks that are, by the recomputed grade, clean passes; its supporting quotes do not exist in the transcript (fabricated).
- **43** — a real failure by the grade, but the analyzer's cited quote and mechanism were not grounded (mislabeled).

The three grounded findings (24, 35, 47) are the ones whose evidence holds. For anyone building an LLM-as-judge belief extractor: ground every claim in the trace and the authoritative grade; don't trust the model's narrative.
