"""Multi-seed paired re-scoring — aggregate flips across K runs.

Loads poc/trajectories_multi.json (list of trajectories, each tagged with a `run` index) and
the lifted fixtures. For every (run, constraint-bearing task) it grades the recorded trajectory
with PreflightRequirementsEvaluator and compares to tau3's DB grade. Reports:
  - per-run flip count (mean ± std)
  - coverage: how many distinct constraint-bearing tasks flipped in >=1 run
Writes poc/flip_report_multi.md.
"""
import sys, types, json, os, math
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
for name, sub in [("tau2", "src/tau2"), ("tau2.domains", "src/tau2/domains"),
                  ("tau2.domains.airline", "src/tau2/domains/airline"),
                  ("tau2.environment", "src/tau2/environment"),
                  ("tau2.data_model", "src/tau2/data_model")]:
    m = types.ModuleType(name); m.__path__ = [os.path.join(ROOT, sub)]; m.__package__ = name
    sys.modules[name] = m

from tau2.data_model.preflight_requirements import UserPreflightRequirements
from tau2.data_model.fixtures_preflight import _load_airline_task_instructions
from tau2.evaluator.preflight_requirements_evaluator import PreflightRequirementsEvaluator

trajs = json.load(open(os.path.join(ROOT, "poc/trajectories_multi.json")))
lifted = json.load(open(os.path.join(ROOT, "poc/lifted_requirements.json")))
ev = PreflightRequirementsEvaluator()

constraint_tasks = {tid for tid, d in lifted.items()
                    if UserPreflightRequirements.model_validate(d).action_preconditions}
runs = sorted({t.get("run", 0) for t in trajs})
per_run_flips = {r: 0 for r in runs}
task_flip_runs = defaultdict(int)      # task -> number of runs it flipped
task_flip_action = {}                  # task -> a violated action (for the table)

for t in trajs:
    tid = str(t["task_id"])
    if tid not in constraint_tasks:
        continue
    upr = UserPreflightRequirements.model_validate(lifted[tid])
    instr = _load_airline_task_instructions(tid).model_copy(update={"user_preflight_requirements": upr})
    res = ev.evaluate_instructions(t["trajectory"], instr)
    if t.get("reward", 0) >= 1 and res is not None and not res.passed:   # tau3 PASS, preflight FAIL
        per_run_flips[t.get("run", 0)] += 1
        task_flip_runs[tid] += 1
        task_flip_action[tid] = res.violations[0].action

flips = [per_run_flips[r] for r in runs]
mean = sum(flips) / len(flips) if flips else 0.0
std = math.sqrt(sum((f - mean) ** 2 for f in flips) / len(flips)) if flips else 0.0

lines = [
    "# Multi-seed paired re-scoring (airline)\n",
    f"- **{len(runs)} runs** of {len(trajs)//max(len(runs),1)} tasks each; one agent (Haiku).",
    f"- **{len(constraint_tasks)}** tasks carry a grounded preflight prohibition.",
    f"- **Flips per run:** {flips}  →  **mean {mean:.1f} ± {std:.1f}**",
    f"- **Coverage:** **{len(task_flip_runs)} of {len(constraint_tasks)}** constraint-bearing tasks "
    f"flipped in >=1 run (a stated prohibition violated and silently passed).\n",
    "| task | flipped in N of {} runs | violated action |".format(len(runs)),
    "|---|:--:|---|",
]
for tid in sorted(task_flip_runs, key=int):
    lines.append(f"| {tid} | {task_flip_runs[tid]} | `{task_flip_action[tid]}` |")
report = "\n".join(lines) + "\n"
open(os.path.join(ROOT, "poc/flip_report_multi.md"), "w").write(report)
print(report)
