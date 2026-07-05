# Agent belief-convergence layer: a per-turn belief tracker for τ-bench (deferred later phase)

> **Status — deferred later phase.** This document designs the **agent-side belief-tracking
> layer**: a per-turn tracker of the agent's evolving belief about the user's problem. It is
> **not** the current pilot. The current pilot is a **paired re-scoring experiment**:
> we add one optional [`user_preflight_requirements`](README.md) field (a typed
> `UserPreflightRequirements`) to τ³'s own `StructuredUserInstructions`, leaving the original
> `task_instructions` prose byte-for-byte unchanged, and a
> `PreflightRequirementsEvaluator` re-scores the *same recorded trajectory* the τ³ grader already
> scored — needing only the **grader's** view, not the agent's belief. The belief tracker below
> (and its `ProblemSpecBelief` schema) is a valuable follow-on, but nothing in the pilot depends
> on it. Read it as the deferred phase, not as shipped machinery.

> **What this is.** A design + reference implementation plan for an *optional instrumentation
> layer* on top of τ³-bench that captures and scores the agent's **evolving belief about the
> user's problem** after every conversation turn — something τ-bench, τ²-bench, and τ³-bench
> do **not** currently measure. It is agent-agnostic, backward-compatible, and computable
> post-hoc from existing trajectories.

---

## 0. Which τ are we talking about? (read this first)

| Version | Domains | Added | Status |
|---|---|---|---|
| **τ-bench** (original repo) | airline, retail | The original outcome reward: final DB-state hash + required output substrings. | Deprecated ("tasks not updated"). |
| **τ²-bench** | + telecom | *Dual-control* (the user can also act on shared state); Dec-POMDP framing. | Subsumed by τ³. |
| **τ³-bench** (this repo, `tau2-bench`, v1.0.0) | + **banking_knowledge**, + voice | RAG knowledge domain, voice full-duplex, 75+ task fixes, **componentized reward** (`reward_basis`). | **Current.** |

**This work forks τ³-bench only.** The original τ-bench is dead; τ² is folded in here. One fork
gives us airline / retail / telecom / banking + the `gym/` RL wrapper + the full evaluator stack.

---

## 1. The gap (verified against τ³, not assumed)

τ-bench evaluates whether an agent drove the **world** into the correct terminal state. It is
**blind to the agent's inference process** — the path by which the agent figured out what the
user actually needed.

Concretely, τ³'s reward (`src/tau2/data_model/tasks.py` → `RewardType`,
`EvaluationCriteria.reward_basis`) is the product of terminal/whole-trajectory components:

- `DB` — does the predicted DB end-state hash match the target (derived by replaying reference `actions`)?
- `ENV_ASSERTION` — do assertions hold on the final env?
- `COMMUNICATE` — did the agent *say* each required substring anywhere in the transcript?
- `NL_ASSERTION` — LLM-judged claims about the **whole** conversation.
- `ACTION` — (banking only) did specific tool calls appear?

**None of these asks: "what did the agent *believe* after turn _k_, and was it right?"**

### Search evidence

```
grep -rniE "belief|mental_model|problem_spec|known_fact|missing_fact|inferred|world_model" src/tau2
# → 0 belief-tracking hits (the single "belief" match is a voice-persona prompt string)
```

The nearest existing artifacts — and why each is *not* a belief layer:

| Existing in τ³ | What it does | Why it's not ProblemSpecBelief |
|---|---|---|
| `metrics/break_down_metrics.py` | Splits reward by **component type** (DB vs COMMUNICATE vs ENV). | Per-trajectory, not per-turn; about *reward components*, not *agent beliefs*. |
| `evaluator/hallucination_reviewer.py` | Detects fabrication in the **user simulator's** messages. | Wrong subject (user, not agent); gates reruns, not scored. |
| `evaluator/evaluator_nl_assertions.py` | LLM-judges NL assertions on the final transcript. | Terminal, whole-conversation; no notion of *convergence over turns*. |
| `orchestrator` `agent_state` | Opaque state the agent carries between turns (≈ the `messages` list). | Never structured, parsed, or scored — exactly the raw transcript we want to replace. |

**Conclusion: the agent's evolving problem representation is the one first-class τ-bench entity
that has never been made explicit or scored — in any version through τ³.**

### Root cause of the silent false-pass: `task_instructions` ↔ `evaluation_criteria` drift

Each τ³ task hand-authors two artifacts: the free-text scenario (`user_scenario.instructions.task_instructions`) and the structured `evaluation_criteria` (`reward_basis` = DB + COMMUNICATE + assertions). They are separate, so they can drift. On task 47 the scenario states *"you don't want to be transferred"*; the `evaluation_criteria` encode no no-transfer predicate; the grader grades the criteria, so the transfer passes.

A single typed requirement spec — `UserPreflightRequirements`, carried in the optional `user_preflight_requirements` field on τ³'s `StructuredUserInstructions` — removes the drift by construction: derive the grading predicates from the same typed source that structures the scenario, and the two cannot disagree — the hand-authored `evaluation_criteria` become a compiled view, not a second artifact. This bounds *internal consistency* (scenario and grading agree); it does not certify the spec encodes the *right* constraints (the ontology-correctness problem, separate).

---

## 2. Existing τ³ entities (where things live)

| Conceptual entity | τ³ location |
|---|---|
| **Hidden task / user scenario** | `src/tau2/data_model/tasks.py` → `Task`; concrete tasks in `data/tau2/domains/<domain>/tasks.json`. Now split into `user_scenario.instructions.{known_info, unknown_info, reason_for_call, task_instructions}`. |
| **Initial world state** | `src/tau2/environment/db.py`; domain DBs in `data/tau2/domains/<domain>/db.json`. |
| **User simulator** | `src/tau2/user/user_simulator.py` (+ streaming/voice variants). |
| **Trajectory** | `src/tau2/data_model/message.py` (Message/Tick); a run is `data_model/simulation.py` → `SimulationRun`. |
| **Evaluators** | `src/tau2/evaluator/*` (`evaluator_action`, `evaluator_env`, `evaluator_communicate`, `evaluator_nl_assertions`), combined in `evaluator/evaluator.py`. |
| **Reward criteria** | `data_model/tasks.py` → `EvaluationCriteria`, `RewardType`. |
| **RL interface** | `src/tau2/gym/gym_agent.py` — a `gymnasium` env. **The training hook.** |
| **Trajectory scoring script** | `src/tau2/scripts/evaluate_trajectories.py`. **The post-hoc hook.** |

---

## 3. The proposed artifact: `ProblemSpecBelief` (per turn, agent-agnostic, not CoT)

After each agent turn, an **observer** (a separate LLM, *not* the agent under test) reads the
transcript-so-far and emits the agent's current *belief about the user's problem* — facts and
constraints, **not** reasoning.

```python
class Belief(BaseModel):
    slot: str                      # canonical key, e.g. "reservation_id", "card.no_annual_fee"
    value: Optional[str]           # resolved value, or None if known-unknown
    status: Literal["known", "missing", "inferred", "assumed"]
    evidence_turn: Optional[int]   # turn where established (for convergence timing)

class Constraint(BaseModel):
    description: str               # "won't cancel unless refunded"
    source: Literal["user_stated", "policy", "inferred"]

class ProblemSpecBelief(BaseModel):
    turn: int
    goal_summary: str              # one-line current understanding of the task
    beliefs: list[Belief]
    constraints: list[Constraint]
    open_questions: list[str]      # what the agent knows it still needs
    ir_version: str = "aps_v1"
```

Why these choices:
- **Canonical slot keys** (not prose) make beliefs diffable against ground truth (§5).
- **`status` separates `missing` (a known-unknown) from `assumed` (silently filled).** Hallucinated
  facts = `assumed`/`inferred` beliefs with no ground-truth support — the single most
  decision-relevant signal.
- **Not chain-of-thought.** No "I will next call X." Only the *state* of understanding, so an
  observer can emit it without the agent's cooperation → works on *any* agent, including closed ones.

---

## 4. Worked examples (airline + banking)

### 4a. Airline — task #0, "Emma Kim" cancellation (real `data/tau2/domains/airline/tasks.json`)

> User scenario (ground truth, hidden from agent): wants to cancel reservation **EHGLP3**; it's
> >24h after booking; **won't cancel unless refunded**; will claim "I was told I didn't need
> insurance." Eval: `nl_assertions = ["Agent should refuse to proceed with the cancellation."]`.

The user **withholds** the refund condition until the agent says cancellation isn't free. Belief
convergence over turns:

| Turn | New belief | status | open_questions |
|---|---|---|---|
| 1 ("I want to cancel a reservation") | `intent = cancel`; `reservation_id = ?` | known / **missing** | "which reservation?" |
| 2 ("EHGLP3") | `reservation_id = EHGLP3` | known | "is it refundable?" |
| 3 (agent retrieves) | `refundable = false`; `>24h = true` | inferred | — |
| 4 (user: "only if I get a refund") | `constraint: won't_cancel_unless_refunded` | known | — |

A correct agent's spec at turn 4 contains the refund constraint and `intent=refuse_cancellation`.
A failing agent that cancels anyway will show `assumed: refund_available=true` — **a hallucinated
belief caught at the exact turn it appears**, which the terminal DB reward only reflects as a
final 0.

### 4b. Banking — task_001, "Sarah Bosch" credit-card (real `data/tau2/domains/banking_knowledge/tasks.json`)

> Wants the **highest cash-back personal card**; **rejects any annual fee unless it's the only
> option**; has a free **Rho-Bank+ subscription** she will **only reveal if asked**. RAG domain:
> the agent must *retrieve* the card catalog.

| Turn | New belief | status | note |
|---|---|---|---|
| 1 | `goal = pick_credit_card`; `optimize = max_cashback` | known | |
| 2 | `constraint: no_annual_fee (unless sole option)` | known | |
| — | `has_rho_bank_plus = ?` | **missing** | latent; only surfaces if agent *asks* |
| n (agent retrieves catalog) | candidate cards + fees | inferred | **hallucination risk: wrong fee cited from RAG** |

The `has_rho_bank_plus` slot is a designed **missing-fact recall** test: a strong agent lists it in
`open_questions` and asks; a weak one silently `assumed`s it away. The RAG fee-citation risk maps
directly to a classic "hallucinated citation" failure mode (§7).

---

## 5. Ground truth: `UserPreflightRequirements` (τ³ pre-pays most of the cost)

A skeptic's objection to this whole idea is *"isn't belief-recall just re-deriving the instruction
the user already holds?"* Two things defeat it:

1. **τ³ already ships a semi-structured ground-truth decomposition.** Unlike original τ-bench's flat
   `instruction` string, τ³ tasks expose `known_info` / `unknown_info` / `reason_for_call` /
   `task_instructions` + `evaluation_criteria`. Flattening these into `slot/value/constraint` shape
   is a light annotation pass, not a from-scratch one.
2. **The user simulator withholds facts and reveals incrementally** ("Don't dump all your
   information at once" — verbatim in the banking task). So at turn _k_ the agent *provably*
   has not been told everything; measuring what it correctly inferred vs. hallucinated vs.
   still-missing is information the terminal reward genuinely does not contain.

### Metrics (per turn, against the static `UserPreflightRequirements`)

| Metric | Definition |
|---|---|
| **Belief precision** | correct resolved beliefs / all resolved beliefs held — penalizes hallucinated/wrong-valued slots |
| **Belief recall** | correct resolved beliefs / all truth slots — how much of the problem is understood |
| **Missing-fact recall** | of unresolved truth slots, fraction correctly surfaced in `open_questions` — rewards knowing what it doesn't know |
| **Hallucination rate** | `assumed`/`inferred` beliefs contradicting or unsupported by truth, per turn |
| **Convergence (headline)** | turn at which belief-F1 first crosses τ; AUC of the F1-vs-turn curve — *how fast and how accurately the agent converges to the hidden spec* |

This converts τ-bench's single terminal bit into a **trajectory of belief F1**, separating
"slow-but-correct" from "fast-but-reckless" agents that today receive identical 0/1 rewards.

---

## 6. Integration (optional, agent-agnostic, backward-compatible)

```
            ┌──────────────── τ³-bench (unchanged) ────────────────┐
 Task ──────► UserSimulator ◄──► Agent ──► SimulationRun ──► evaluate_simulation() ──► reward
 (hidden)     user/             agent/      data_model/        evaluator/evaluator.py     ∈[0,1]
              user_simulator.py  llm_agent   simulation.py
            └─────────────────────────────┬────────────────────────┘
                                          │ trajectory (read-only)
        ┌──────────────────────────────────▼──────────── NEW: optional observer ┐
 Task ──► distill ──► UserPreflightRequirements ─┐         │
 (known_info / unknown_info / criteria)          ▼         ▼
                                     BeliefScorer ◄── BeliefExtractor (observer LLM; reads traj[:k])
                                            │           │  emits ProblemSpecBelief per agent turn
                                            ▼           ▼
                          belief_trace + convergence ──► SimulationRun.belief_trace (new optional field)
```

**Three hook points, by decoupling:**

1. **Fully decoupled (recommended):** a new `src/tau2/scripts/belief_trace_analysis.py` mirroring
   `evaluate_trajectories.py`. Reads saved `SimulationRun`s, replays turn-by-turn, calls the
   observer, scores against `UserPreflightRequirements`. **Zero changes to agents, envs, or the run loop** —
   runs on *historical* result files. This is the "optional instrumentation layer," and the answer
   to "can it work without touching existing agents?" is **yes**.
2. **As an evaluator:** a `BeliefEvaluator(EvaluatorBase[Message])` alongside the existing evaluators,
   emitting a *diagnostic* (not reward-gating) score so the leaderboard is untouched.
3. **As a gym dense reward:** in `src/tau2/gym/gym_agent.py`, expose per-turn belief-F1 delta as a
   shaped reward — turning the layer from diagnostic into a **training signal** (§7).

The extractor must be a **separate observer model**, never the agent under test — otherwise you
contaminate the very capability you measure (same principle as an evidence-fixtured grader that
isn't allowed to grade itself).

---

## 7. Why per-turn localization matters

Today an agent that fails a τ-bench task yields **one terminal bit** and, at best, a coarse
post-hoc failure label. A useful eval needs to answer a sharper
question: **at which conversational step did the agent's understanding diverge from reality, and is
the fix a prompt change or one that requires new training data?**

The per-turn belief trace localizes the divergence to a **single turn and a single slot**. Aggregated
across many trajectories, recurring divergences cluster into **failure patterns** — and each pattern
carries a disambiguating test and an intervention type. This is the reusable diagnostic schema:

| Failure Pattern | Observations (linked cases) | Hypothesized Root Cause(s) | Test to Disambiguate | Prompt Fix? | Training-Data Fix? |
|---|---|---|---|---|---|
| Belief diverges where a constraint is *withheld* then revealed | turns where `constraint` appears late but agent already acted | agent didn't probe; assumed defaults | add a required-information probe; ablate the withholding | likely **prompt** | maybe |
| Silent `assumed` fills a `missing` slot (no clarifying question) | turns with `status=assumed` ∧ truth=`missing` | model believed it had enough info | force-feed the missing fact; re-run | prompt **or** training | **yes** |
| Hallucinated fact / wrong RAG citation | banking turns with unsupported `inferred` beliefs | weak grounding to retrieved doc | replace retrieval with provided evidence | rarely | **training** |
| Correct beliefs, wrong terminal action | high belief-F1 at last turn, reward=0 | tool-argument / execution error | replay with corrected args | **prompt** | no |

- **Prompt fix** = the belief was recoverable from context; the agent just wasn't steered to it.
- **Training-data fix** = the belief was *not* reliably recoverable → a domain expert authors an
  example that nudges the model at that exact granular step. This is the per-step labeling work a
  benchmark with only terminal rewards **cannot scope** — and it's precisely the dense-reward signal
  the `gym/` wrapper can consume for fine-tuning.

In short: terminal reward tells you *that* the agent failed; the belief trace tells you *where* and
*why*, and the diagnostic schema tells you *which lever* to reach for (prompt vs. data).

---

## 8. Where expert elicitation raises grader fidelity

The grader is a compiler from an expert ontology into checkable predicates. Its fidelity is
upper-bounded by the coverage, calibration, and correctness of that ontology — and the ontology
cannot be read off the written policy, because the load-bearing structure is **tacit**: it lives in
expert practice, not the manual. Subject-matter-expert (SME) elicitation is the mechanism that
converts that tacit structure into gradeable form. Six discrete surfaces, each with a measurable
fidelity effect:

1. **Ontology coverage → the grader's recall ceiling.** A grader can only flag predicates that have
   been enumerated. "Don't escalate unprompted" is an *invariant of competent practice* that appears
   nowhere in the τ³ policy as a checkable rule. An expert surfaces these unwritten invariants. The
   grader's false-negative rate is bounded below by the incompleteness of the invariant set;
   elicitation lowers that bound. This is the tacit-to-explicit move — the single largest lever on recall.

2. **Action-precondition graph → what makes "acted under `None`" detectable at all.** Severity-by-
   epistemic-state only works if you know *which slots must be resolved before which actions* (transfer
   requires `transfer_requested` resolved; cancel requires `refund_eligible ∧ user_accepts_terms`). That
   mapping is the operational structure of the job — expert knowledge. Without it there is no notion of
   "a decision that outran the evidence."

3. **Severity / harm model → the grader's decision-relevance.** The `None`/`False`/`True` ladder is
   structural, but the *weights* — is an unwarranted transfer a minor friction or a trust breach; is an
   irreversible non-refundable cancellation catastrophic — are elicited priors. Without them the grader is
   internally precise while optimizing the wrong loss: high agreement on things that don't matter. An
   expert-elicited harm model is what makes the grader *relevant*, not merely consistent.

4. **Epistemic bar → who adjudicates the ambiguous cases.** Grade against ground truth, or against what
   was resolvable at decision time? That is not a math question but a domain-policy judgment about
   culpability — is an agent responsible for proactively resolving ambiguity, or only for defying a stated
   preference? The SME sets that bar. It is what turns a contestable call into a defensible one, and the
   difference between a grader annotators agree with and one they argue with.

5. **Reference trajectories → *flag* to *counterfactual*.** When a failure is not prompt-recoverable, the
   expert authors the correct behavior (the clarifying turn, the calibrated refusal). This does double
   duty: it makes the verdict concrete ("here is what should have happened at turn 12") and it *is* the
   supervision signal. The grader stops saying "wrong" and starts specifying "wrong relative to *this*."

6. **Judge calibration → what makes "fidelity" a falsifiable claim.** The belief observer is itself an
   LLM, and it fabricates (§the verifier caught 3 of 6 findings in the pilot). Fidelity cannot be
   asserted; it can only be *measured* as agreement between the automated judge and expert labels on a
   held-out set — and that set is an elicitation deliverable. Without it, "high-fidelity grader" is
   unfalsifiable; with it, it is a number (judge–SME agreement, per predicate).

The through-line, stated as engineering leverage: **each of these is a bounded, one-time elicitation
whose output is amortized across every trajectory the grader ever scores.** The expert labels an
invariant, a precondition, a severity, an epistemic bar, or a held-out set *once*; the grader reuses it
at scale. Tacit judgment compiled once, applied continuously.

The sharp version: **a grader is only as good as the ontology it compiles, and the ontology is exactly
the part that isn't written down** — which is why the expert, not further prompt engineering, is the
binding constraint on grader fidelity.

---

## 9. Assessment

**Meaningful contribution — verified novel against τ³, with one caveat now largely mitigated.**

- The gap is real and survives to the latest version: τ³'s reward is outcome/whole-trajectory only;
  `break_down_metrics`, `hallucination_reviewer`, and `nl_assertions` are adjacent but none tracks
  per-turn agent belief or convergence.
- τ³'s `known_info` / `unknown_info` split and the incrementally-withholding user simulator together
  make `UserPreflightRequirements` cheap to build *and* defensible against the "you're just re-reading the
  instruction" objection. **Make the convergence curve, not terminal belief-F1, the headline.**
- It is cheap and non-invasive (post-hoc observer over existing `SimulationRun`s), which is what
  makes a benchmark extension adoptable — and it upgrades cleanly into a training signal via `gym/`.

**Open verification before publishing:** confirm no τ³ *blog/leaderboard* tooling (outside this repo)
already reports a per-turn belief metric; the code here does not.

---

*Status: design + plan. Next: implement `belief_trace_analysis.py` as a decoupled PoC against the
trajectories already in this repo, on airline task #0 and banking task_001.*
