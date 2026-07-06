"""Pass 1 — lift typed UserPreflightRequirements from each airline task's prose.

For every airline task, an LLM reads `task_instructions` and extracts the customer's
EXPLICIT, UNCONDITIONAL refusals of consequential agent actions, mapped to canonical
tau3 tool names, each with a VERBATIM `source_quote`. Provenance is then verified
deterministically (verify_provenance) and any ungrounded constraint is dropped — so the
fixture set is "lifted, not invented". Writes poc/lifted_requirements.json.

Scope (matches the Phase-1 grader): outright DENIED refusals only. Conditional /
world-state authorizations are out of scope.
"""
import sys, types, json, os, concurrent.futures, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
for name, sub in [("tau2", "src/tau2"), ("tau2.domains", "src/tau2/domains"),
                  ("tau2.domains.airline", "src/tau2/domains/airline"),
                  ("tau2.environment", "src/tau2/environment"),
                  ("tau2.data_model", "src/tau2/data_model")]:
    m = types.ModuleType(name); m.__path__ = [os.path.join(ROOT, sub)]; m.__package__ = name
    sys.modules[name] = m

from tau2.data_model.preflight_requirements import (
    UserPreflightRequirements, ActionPrecondition, verify_provenance)
from tau2.data_model.fixtures_preflight import _load_airline_task_instructions
import anthropic

MODEL = "claude-sonnet-4-6"
CONSEQUENTIAL = ["book_reservation", "cancel_reservation", "send_certificate",
                 "transfer_to_human_agents", "update_reservation_flights",
                 "update_reservation_passengers", "update_reservation_baggages"]
TASKS = json.load(open(os.path.join(ROOT, "data/tau2/domains/airline/tasks.json")))
client = anthropic.Anthropic()

SYSTEM = """You extract a customer's EXPLICIT, UNCONDITIONAL refusals of consequential actions from a customer-service task's user instructions.

The agent can take these consequential actions (canonical tool names):
{tools}
(Read-only actions like search / list / calculate are never constrained.)

From the customer's task instructions, list every consequential action the customer EXPLICITLY says must NOT be taken — an outright prohibition that holds for the whole task.

Rules:
- ONLY unconditional refusals. If the customer forbids an action only under a condition ("don't cancel unless refunded", "only if ..."), DO NOT include it.
- Map the customer's wording to the exact canonical tool name from the list above.
- source_quote MUST be copied VERBATIM (character-for-character, same case, same punctuation) from the instructions; it must appear exactly in the text.
- If there is no unconditional refusal, return an empty list.
""".format(tools="\n".join("  - " + t for t in CONSEQUENTIAL))

TOOL = {"name": "emit", "description": "Emit the extracted refusal constraints.",
        "input_schema": {"type": "object", "properties": {"constraints": {"type": "array", "items": {
            "type": "object", "properties": {
                "action": {"type": "string", "enum": CONSEQUENTIAL},
                "rule": {"type": "string", "description": "one-line statement of the prohibition"},
                "source_quote": {"type": "string", "description": "verbatim substring of task_instructions"}},
            "required": ["action", "rule", "source_quote"]}}}, "required": ["constraints"]}}


def lift(task):
    tid = str(task["id"])
    ti = task["user_scenario"]["instructions"]["task_instructions"]
    r = client.messages.create(model=MODEL, max_tokens=1024, system=SYSTEM, tools=[TOOL],
                               tool_choice={"type": "tool", "name": "emit"},
                               messages=[{"role": "user", "content": f"Task instructions:\n\n{ti}"}])
    cons = next((b.input.get("constraints", []) for b in r.content
                 if b.type == "tool_use" and b.name == "emit"), [])
    preconds = [ActionPrecondition(id=f"task{tid}.no_{c['action']}_{i}", action=c["action"],
                                   preflight_protocol=c.get("rule", ""), source_field="task_instructions",
                                   source_quote=c["source_quote"]) for i, c in enumerate(cons)]
    upr = UserPreflightRequirements(action_preconditions=preconds)
    v1 = _load_airline_task_instructions(tid).model_copy(update={"user_preflight_requirements": upr})
    problems = verify_provenance(v1)
    bad = {p.split(":")[0] for p in problems}
    if bad:  # drop ungrounded preconditions
        preconds = [c for c in preconds if c.id not in bad]
        upr = UserPreflightRequirements(action_preconditions=preconds)
    return tid, upr.model_dump(mode="json"), len(cons), len(bad)


def main():
    out, with_c, total, dropped = {}, 0, 0, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(lift, t): str(t["id"]) for t in TASKS}
        for f in concurrent.futures.as_completed(futs):
            tid = futs[f]
            try:
                tid, dump, n_raw, n_bad = f.result()
                out[tid] = dump
                n = len(dump["action_preconditions"])
                with_c += (n > 0); total += n; dropped += n_bad
                if n or n_bad:
                    print(f"task {tid}: {n} constraint(s)" + (f"  [dropped {n_bad} ungrounded]" if n_bad else ""))
            except Exception:
                print(f"task {tid} FAILED"); traceback.print_exc()
    out = {k: out[k] for k in sorted(out, key=int)}
    json.dump(out, open(os.path.join(ROOT, "poc/lifted_requirements.json"), "w"), indent=2)
    print(f"\n{with_c}/{len(TASKS)} tasks have >=1 grounded constraint; {total} total constraints; "
          f"{dropped} ungrounded dropped by provenance check")
    print("saved -> poc/lifted_requirements.json")


if __name__ == "__main__":
    main()
