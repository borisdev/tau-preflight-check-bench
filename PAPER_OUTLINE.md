# τ-PreflightCheck — paper outline

**Working title:** *τ-PreflightCheck: Grading Whether LLM Agents Verify Latent User Requirements Before Acting*

**One-line thesis.** Outcome-based grading measures whether the right tool eventually fired; it ignores *epistemic safety* — whether the agent verified the user's latent requirements **before** an irreversible action. We model tool execution as a flight departure gated by a **preflight checklist** of epistemic preconditions, show that state-graders silently pass violations of it (task 47), and turn the failures into concrete questions for domain experts.

---

## Abstract
Existing agent benchmarks evaluate on terminal success — did an API tool fire correctly at the end of a run. This ignores epistemic safety: did the agent verify the user's latent constraints before executing an irreversible action? We introduce **τ-PreflightCheck**, which models tool execution as a flight departure. Before an agent fires a consequential action it must satisfy an **epistemic preflight checklist** — proving its belief state matches the user's hidden requirements; if a required slot is `UNKNOWN`, it must halt and ask. We show τ³'s outcome grader passes a real violation (task 47), formalize the check as typed epistemic preconditions over a belief state, and distinguish two failure patterns — *revealed-but-missed* (auto-detectable, the proof) and *should-exist-but-omitted* (expert-authored, the product).

## 1. Introduction
- Terminal-success grading and its blind spot (epistemic safety).
- Motivating false-pass: agent transfers a user who never asked; DB unchanged → **PASS** (task 47).
- Contributions: (a) an eval that catches the false-pass; (b) the per-action **preflight checklist** of epistemic preconditions; (c) the **two-pattern** decomposition that turns findings into an expert data program.
- Framing: *move fast vs. be careful* — the preflight check forces a halt exactly when uncertainty is high.

## 2. Background & related work
- **τ / τ² / τ³**; τ³'s "ambiguous instructions" fix is a *different axis* (task authoring ↔ simulator), ours is agent belief ↔ user.
- **Belief state / dialogue-state tracking** (Young 2013); **assistance games / CIRL** (Hadfield-Menell & Russell); **user modeling** (Fischer 2001).
- **Epistemic planning**: knowledge preconditions (Moore 1985), knowledge-based programs (Fagin et al. 1995), sensing actions (Scherl & Levesque 1993), PDDL-Mind (Zhu et al. 2026).
- **Clarification & information gain** (Deng et al. 2026) — *reactive-on-tool-feedback* vs our *proactive precondition gate*; they defer our exact target (their App. 6.5).
- **Intent-governed authorization** (Zhu & Wang 2026) — authz from *expressed* intent vs our eval of *latent* intent.
- **Checklists / Design by Contract / FMEA / ABAC** — the safety and policy lineage.

## 3. Framework
- `UserPreflightRequirements` (typed, action-scoped requirements lifted from `task_instructions`, checked by the grader) carried in one optional `user_preflight_requirements` field added to τ³'s `StructuredUserInstructions`, alongside the unchanged prose. Agent-side belief tracking (the belief state; slots `UNKNOWN` until probed) is a deferred later phase.
- **Ontic vs epistemic** preconditions (DB-query vs probe).
- The **preflight check**: the per-action checklist of epistemic preconditions; three-valued **allow / deny / ask**.
- Vocabulary discipline: *ignorance* (missing field) vs *epistemic ambiguity* (known field, `UNKNOWN` value) vs τ³ *ambiguous instructions*.

## 4. The two failure patterns
- **Revealed-but-missed** *(the proof)* — requirement is in `task_instructions`, agent ignores it, criteria don't cover it (drift). Auto-detectable by comparing instructions ↔ actions ↔ criteria.
- **Should-exist-but-omitted** *(the product)* — no task states it, yet the action is unsafe without it. Expert-authored.
- **B funds A**: demonstrable false-passes justify the systematic per-action checklist experts then build.

## 5. Method
- Run agents on τ³ tasks; observe belief; **deterministic verification** of every finding (quote/action grounding + independent grade recompute).
- `PreflightRequirementsEvaluator`: encode the requirement as a typed constraint, recompute DB ∧ CONSTRAINT → flips PASS→FAIL (paired re-scoring of the same recorded trajectory).
- Phase-1 automated flagging (LLM-judge over latent constraints); Phase-2 expert enumeration.

## 6. Pilot results
- 6 airline tasks; task 47 is the one added detection; verification rejected 3/6 first-pass findings (methodological rigor, not a weakness to hide).
- **Future (the number labs want):** rate across the full suite × multiple models; does the preflight grade **re-rank** models?

## 7. The preflight checklist as a data product
- Per-action enumeration; SME hydration; the discovery flywheel (run → false-pass → expert adds a checklist item → coverage grows).
- Scope discipline: only resolvable, gradeable, action-relevant preconditions (not full user modeling).

## 8. Limitations
- Pilot scale; single-control (airline) domain; `PreflightRequirementsEvaluator` runs on recorded trajectories (paired re-scoring); live integration is future work.

## 9. Conclusion
- Grade the *model of the problem*, not just the final move; the preflight check is the minimal instrument, and the two patterns make it a program, not a one-off.

---

### Notes for drafting
- Lead the intro with task 47 (concrete), then generalize.
- Keep "epistemic precondition" as the technical term; "preflight check" as the mechanism/name; "common ground" as supporting concept (Clark).
- Verify any Gemini/LLM-suggested citations before including (arXiv:2606.22916 confirmed real; PDDL-Mind 2604.17819 confirmed; Deng 2606.03135 confirmed).
