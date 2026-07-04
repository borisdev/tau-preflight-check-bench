# Framing & related work

A customer-service dialogue is *partially observable*: the user's objective is a **latent variable** the agent infers from partial, incrementally-revealed evidence. τ-bench applies **outcome supervision** (it scores the terminal state); this layer adds **process supervision over the belief state**.

## 1. The agent's belief converging to the hidden problem

The task is *partially observable*: the agent maintains a **belief state** — a posterior over a **latent variable** (the user's true objective) that it updates from partial, incrementally-revealed evidence.

- **Belief-state tracking under partial observability (POMDP).** The hidden problem is the latent state; the agent's estimate is the belief state. "Belief state" is also the term of art in **dialogue-state tracking (DST)** for task-oriented dialogue (Young et al. 2013), so tracking a `ProblemSpecBelief` here is native, not a metaphor.
- **Assistance games / CIRL** (Hadfield-Menell & Russell). Names *why* task 47 fails: an agent uncertain about the human's objective should be deferential / information-gathering, not act decisively. Acting while the objective is `UNKNOWN` is the canonical assistance-game failure — acting under epistemic uncertainty instead of reducing it.
- **Grounding / common ground** (Clark). The dialogue-pragmatics term for two parties converging on shared understanding.
- **Theory of Mind / intent inference / user modeling** (Fischer 2001). Modeling the user's goal as a hidden mental state. `ProblemSpec` is the *action-relevant, checkable projection* of the user model — not the full model.
- **The convergence itself:** posterior contraction / concentration (Bayesian); identifiability (whether the truth can be recovered from the observations at all).

## 2. Decompose into structured parts; grade the process, not just the outcome

- **Process supervision vs. outcome supervision** — process reward models (PRM) vs. outcome reward models (ORM) (OpenAI, *Let's Verify Step by Step*). We propose a **PRM over the belief trajectory**: grade how well the agent extracted the truth, not only the terminal state.
- **The structure experts define:** semantic frames / slot filling / a domain ontology (dialogue systems). The "hydrated problem spec" is a filled semantic frame / grounded specification.
- **Structured prediction** — the `ProblemSpec` is a structured output, not a scalar.
- **Why structure makes the grader more accurate:** factored / decomposed evaluation and scalable oversight (Christiano's IDA, Irving's debate, Ought's factored cognition; Anthropic's scalable-oversight agenda). Decomposition raises inter-rater reliability — the reason rubric-based grading beats holistic scoring.

## 3. Preconditions on knowledge, not just the world (epistemic planning)

Our core move — an action may require the agent to *know* something, not merely for something to be *true* — is **epistemic planning**, a long-established line in symbolic AI. This is what makes "epistemic precondition" grounded prior art, not a coinage:

- **Knowledge preconditions** — Moore, *A Formal Theory of Knowledge and Action* (1985). To act you may need to *know* a fact (to dial a safe, know the combination), not merely for it to hold. Our `epistemic_pre` is a knowledge precondition.
- **Knowledge-based programs** — Fagin, Halpern, Moses & Vardi, *Reasoning About Knowledge* (1995). Programs whose guards are tests on knowledge: "if the agent knows φ, act." An epistemic precondition is a knowledge-based guard on a tool call.
- **Epistemic planning** — Bolander & Andersen (2011). Planning in the space of belief/knowledge states rather than world states.
- **Sensing / knowledge-producing actions** — Scherl & Levesque (1993). Actions whose effect changes what the agent *knows*, not the world. A clarifying question is a sensing action that resolves an `UNKNOWN` slot.
- **The stopping rule — Clark's grounding criterion.** Grounding need only reach a *criterion sufficient for current purposes*; equivalently, **satisficing** (Simon) and **value of information** (stop asking when marginal VOI < cost). This is why we scope ambiguity to the fields the *pending action* needs, not every field.
- **Explicit belief in PDDL** — PDDL-Mind (Zhu et al., [arXiv:2604.17819](https://arxiv.org/abs/2604.17819)) makes the belief state explicit in PDDL for theory-of-mind accuracy; we extend belief from a *tracked* quantity to an *action precondition*.

### Software-engineering lineage

- **Design by Contract** — Meyer (Eiffel): `require` / `ensure` / `invariant`. Our per-action guards are preconditions in the DbC sense; the *invariant / action-precondition / severity* decomposition is DbC applied per tool.
- **FMEA** (failure mode and effects analysis): enumerate each action's failure mode and severity — the origin of our per-guard **severity** weight.
- **ABAC / policy-as-code** (OPA, AWS IAM): the runtime gate is attribute-based access control over the belief state, extended to three-valued **allow / deny / ask**. See [`docs/epistemic-preconditions.md`](docs/epistemic-preconditions.md).

## 4. Clarification & information gain (closest prior art)

**Deng et al. 2026, "Uncertainty-Aware Clarification in LLM Agents with Information Gain"** ([arXiv:2606.03135](https://arxiv.org/abs/2606.03135)) is the nearest neighbor: like us it works on τ-Bench, treats the user's goal as a latent variable, and rewards the agent for reducing uncertainty about it before acting. Their **Information Gain Reward** — the log-likelihood shift of the ground-truth goal under the model after a clarifying question — is an instantiation of the **value of information** (§3). We share that premise, and differ on representation, mechanism, and what we measure:

- **Reactive vs. proactive.** Their clarifier fires *reactively, when tool-execution feedback reveals missing information*. Ours is a *proactive precondition* checked **before** the action fires. This matters concretely: **task 47 produces no failing tool call** — the transfer succeeds and leaves the DB unchanged — so a reactive-on-feedback clarifier structurally cannot detect it. A precondition gate can.
- **Flat goal string vs. typed spec.** Their target is a normalized natural-language goal string; the belief is implicit in the model's token-level probabilities ("no explicit discrete goal space or slot inventory"). Ours is a typed `ProblemSpec` with per-field **ontic/epistemic preconditions** and explicit `UNKNOWN` slots — auditable and per-action.
- **Agent method vs. eval + policy.** They contribute a clarifier-training method and a reward; success is measured Pass@1. We contribute (a) an **eval** that catches the false-pass outcome-grading misses, and (b) a **per-action enumeration** of which fields must be resolved — expert-authored. They enumerate no per-action precondition policy.
- **They defer our exact target.** Their failure analysis (App. 6.5) notes a case where "clarification resolves ambiguity but execution violates policy," concluding it "motivat[es] future work on jointly optimizing clarification and execution." That clarify-succeeds-yet-action-violates case is precisely what our precondition grader scores.

**Complementary, not competing.** Their clarifier is a *Phase-3* mechanism; it presupposes a goal you can already score and knowing *which* latent fields matter per action — exactly the eval and enumeration we provide. Their agent method rides on our eval-and-policy layer.

## Beyond AI

- **The Good Regulator theorem** (Conant & Ashby, 1970): *"Every good regulator of a system must be a model of that system."* To act well on a hidden problem you must model it — so to *grade* whether an agent will act well, grade its **model of the problem**, not just its final move.
- **Control theory:** state estimation / observer design / the separation principle (estimate the hidden state, then act) — task 47 violates it by acting before estimating.
- **Epistemology:** Bayesian convergence to truth; abduction (inference to the best explanation).

## The crux, in one sentence

Customer-service dialogue is a **partially observable assistance game**: the agent must **ground** a **latent objective** by tracking a **belief state** that should **converge** to the truth — so evaluate it with **process supervision over the belief trajectory**, against an **expert-authored ontology (semantic frame)**, which also makes the grader more reliable via **factored / decomposed evaluation**.
