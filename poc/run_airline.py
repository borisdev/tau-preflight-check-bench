"""PoC runner: real τ³ airline tools + policy, Haiku agent vs Sonnet user-sim.
Bypasses the heavy tau2 package __init__ (voice stack) via sys.modules stubs.
Saves trajectories + DB-hash reward to poc/trajectories.json.
"""
import sys, types, json, os, concurrent.futures, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
for name, sub in [("tau2", "src/tau2"), ("tau2.domains", "src/tau2/domains"),
                  ("tau2.domains.airline", "src/tau2/domains/airline"),
                  ("tau2.environment", "src/tau2/environment")]:
    m = types.ModuleType(name); m.__path__ = [os.path.join(ROOT, sub)]; m.__package__ = name
    sys.modules[name] = m

from tau2.domains.airline.tools import AirlineTools
from tau2.domains.airline.data_model import FlightDB
from tau2.domains.airline.utils import AIRLINE_DB_PATH
import anthropic

AGENT_MODEL = "claude-haiku-4-5-20251001"
USER_MODEL  = "claude-sonnet-4-6"
# TASK_IDS set below (after ALL_TASKS): env RUN_TASKS overrides, else all airline tasks
MAX_EXCHANGES = 12
MAX_TOOL_STEPS = 8

POLICY = open(os.path.join(ROOT, "data/tau2/domains/airline/policy.md")).read()
ALL_TASKS = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "data/tau2/domains/airline/tasks.json")))}
TASK_IDS = os.environ["RUN_TASKS"].split() if os.environ.get("RUN_TASKS") else list(ALL_TASKS.keys())
client = anthropic.Anthropic()
import time as _time
def _msg(**kw):
    for _a in range(6):
        try:
            return client.messages.create(**kw)
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError):
            if _a == 5:
                raise
            _time.sleep(2 ** _a)

USER_SIM_TMPL = """You are role-playing a CUSTOMER contacting an airline customer-service agent. Stay in character.

YOUR SITUATION (do not reveal all of this at once):
{instructions}

Rules:
- Send ONE short, natural message at a time, in your own words.
- Reveal information only when the agent asks for it or when it's needed for the current step. Do NOT dump everything up front.
- Do not invent facts not in your situation. If the agent asks for something you don't have, say you don't have/remember it.
- When your goal is accomplished, OR the agent has clearly told you it cannot be done and you don't want to continue, reply with exactly ###STOP### and nothing else.
- Never act as the agent."""

def fresh_tools():
    return AirlineTools(FlightDB.load(AIRLINE_DB_PATH))

def anthropic_tools(tk):
    out = []
    for _, tool in tk.get_tools().items():
        fn = tool.openai_schema["function"]
        out.append({"name": fn["name"], "description": fn["description"], "input_schema": fn["parameters"]})
    return out

def user_instructions(task):
    ins = task["user_scenario"]["instructions"]
    if isinstance(ins, dict):
        parts = [ins.get("task_instructions") or "",
                 ("Reason you are calling: " + ins["reason_for_call"]) if ins.get("reason_for_call") else "",
                 ("What you know: " + ins["known_info"]) if ins.get("known_info") else ""]
        ins = "\n\n".join(p for p in parts if p)
    return ins

def text_of(blocks):
    return "".join(b.text for b in blocks if b.type == "text").strip()

def replay_target_hash(task):
    tk = fresh_tools()
    for a in (task.get("evaluation_criteria") or {}).get("actions") or []:
        args = a.get("arguments", a.get("kwargs", {})) or {}
        try: tk.use_tool(a["name"], **args)
        except Exception: pass
    return tk.get_db_hash()

def run_task(tid, run=0):
    task = ALL_TASKS[tid]
    tk = fresh_tools()
    tools = anthropic_tools(tk)
    agent_msgs, user_msgs, trace = [], [{"role": "user", "content": "Hi! How can I help you today?"}], []
    usys = USER_SIM_TMPL.format(instructions=user_instructions(task))

    # user opens
    u = _msg(model=USER_MODEL, max_tokens=300, system=usys, messages=user_msgs)
    utext = text_of(u.content); user_msgs.append({"role": "assistant", "content": utext})
    trace.append({"role": "user", "text": utext})

    for _ in range(MAX_EXCHANGES):
        if "###STOP###" in utext:
            break
        agent_msgs.append({"role": "user", "content": utext})
        # agent inner tool loop until it emits a user-facing text
        agent_text = ""
        for _ in range(MAX_TOOL_STEPS):
            r = _msg(model=AGENT_MODEL, max_tokens=1024, system=POLICY, tools=tools, messages=agent_msgs)
            agent_msgs.append({"role": "assistant", "content": r.content})
            tool_uses = [b for b in r.content if b.type == "tool_use"]
            txt = text_of(r.content)
            if txt:
                trace.append({"role": "assistant", "text": txt,
                              "tool_calls": [{"name": b.name, "args": b.input} for b in tool_uses]})
            if r.stop_reason == "tool_use":
                results = []
                for b in tool_uses:
                    try: obs = tk.use_tool(b.name, **b.input)
                    except Exception as e: obs = f"Error: {e}"
                    trace.append({"role": "tool", "name": b.name, "args": b.input, "observation": str(obs)[:1500]})
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(obs)})
                agent_msgs.append({"role": "user", "content": results})
                continue
            agent_text = txt
            break
        if not agent_text:
            agent_text = "(no response)"
        # user reacts
        user_msgs.append({"role": "user", "content": agent_text})
        u = _msg(model=USER_MODEL, max_tokens=300, system=usys, messages=user_msgs)
        utext = text_of(u.content); user_msgs.append({"role": "assistant", "content": utext})
        trace.append({"role": "user", "text": utext})

    end_hash = tk.get_db_hash()
    target_hash = replay_target_hash(task)
    return {"task_id": tid, "purpose": (task.get("description") or {}).get("purpose"),
            "instructions": user_instructions(task), "reward": int(end_hash == target_hash),
            "db_changed": end_hash != fresh_tools().get_db_hash(), "trajectory": trace, "run": run}

def main():
    repeats = int(os.environ.get("REPEATS", "1"))
    workers = int(os.environ.get("RUN_WORKERS", "3"))
    work = [(tid, r) for r in range(repeats) for tid in TASK_IDS]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_task, tid, r): (tid, r) for tid, r in work}
        for f in concurrent.futures.as_completed(futs):
            tid, r = futs[f]
            try:
                res = f.result(); results.append(res)
                print(f"run {r} task {tid}: reward={res['reward']} db_changed={res['db_changed']} turns={len(res['trajectory'])}")
            except Exception:
                print(f"run {r} task {tid} FAILED"); traceback.print_exc()
    results.sort(key=lambda x: (x.get("run", 0), TASK_IDS.index(x["task_id"])))
    out = os.path.join(ROOT, os.environ.get("RUN_OUT", "poc/trajectories_all.json"))
    json.dump(results, open(out, "w"), indent=2, default=str)
    print(f"\nsaved {len(results)} trajectories ({repeats} run(s)) -> {out}")
    print("pass:", sum(r["reward"] for r in results), "/", len(results))

if __name__ == "__main__":
    main()
