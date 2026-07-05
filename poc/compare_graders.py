"""Paired re-scoring: grade the SAME recorded trajectories with BOTH graders.

For each saved trajectory that has a V2 fixture, this re-scores it with:
  1. the existing τ³ DB/COMMUNICATE grade (read from the recorded run — unchanged);
  2. the new deterministic StructuredRequirementsEvaluator (V2 typed requirements).

Only the grader's representation changes; the task, simulator prose, trajectory, tool calls,
DB state, and agent output are all held fixed. Any verdict difference is therefore attributable
to what the grader can represent — this is the pilot's core claim.

For task 47:  τ³ -> PASS,  structured -> FAIL (unwanted transfer_to_human_agents at turn 12).

Run:  uv run python poc/compare_graders.py
Outputs: poc/paired_grades.json  and  poc/paired_grades.md
"""

from __future__ import annotations

import json
import os
from typing import Literal

from pydantic import BaseModel

from tau2.data_model.fixtures_v2 import get_v2_fixture
from tau2.evaluator.structured_requirements_evaluator import (
    StructuredRequirementsEvaluator,
    StructuredRequirementViolation,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAJECTORIES = os.path.join(ROOT, "poc", "trajectories.json")
VERIFIED_FINDINGS = os.path.join(ROOT, "poc", "verified_findings.json")
OUT_JSON = os.path.join(ROOT, "poc", "paired_grades.json")
OUT_MD = os.path.join(ROOT, "poc", "paired_grades.md")


class PairedGradeResult(BaseModel):
    task_id: str
    model_id: str
    run_id: str

    tau3_score: float
    structured_score: float

    tau3_pass: bool
    structured_pass: bool

    verdict_flip: Literal["none", "pass_to_fail", "fail_to_pass"]

    violations: list[StructuredRequirementViolation]


def _tau3_score(traj: dict, verified: dict) -> float:
    """The recorded τ³ DB/COMMUNICATE grade for this trajectory (unchanged by this experiment).

    Prefer the trajectory's own recorded `reward`; fall back to the verified-findings
    recomputed grade so the number matches the audited PoC pipeline.
    """
    if traj.get("reward") is not None:
        return float(traj["reward"])
    v = verified.get(traj["task_id"])
    if v and v.get("recomputed_grade") is not None:
        return float(v["recomputed_grade"])
    return 0.0


def _flip(tau3_pass: bool, structured_pass: bool) -> Literal["none", "pass_to_fail", "fail_to_pass"]:
    if tau3_pass and not structured_pass:
        return "pass_to_fail"
    if not tau3_pass and structured_pass:
        return "fail_to_pass"
    return "none"


def run() -> tuple[list[PairedGradeResult], list[str]]:
    trajectories = json.load(open(TRAJECTORIES))
    verified = {f["task_id"]: f for f in json.load(open(VERIFIED_FINDINGS))}
    evaluator = StructuredRequirementsEvaluator()

    results: list[PairedGradeResult] = []
    skipped: list[str] = []

    for traj in trajectories:
        task_id = str(traj["task_id"])
        v2 = get_v2_fixture(task_id)
        if v2 is None:
            skipped.append(task_id)
            continue

        tau3 = _tau3_score(traj, verified)
        structured = evaluator.evaluate(traj["trajectory"], v2.structured_requirements)

        tau3_pass = tau3 >= 1.0
        results.append(
            PairedGradeResult(
                task_id=task_id,
                model_id=str(traj.get("model_id", "tau3-poc")),
                run_id=str(traj.get("run_id", "poc-recorded")),
                tau3_score=tau3,
                structured_score=structured.reward,
                tau3_pass=tau3_pass,
                structured_pass=structured.passed,
                verdict_flip=_flip(tau3_pass, structured.passed),
                violations=structured.violations,
            )
        )
    return results, skipped


def to_markdown(results: list[PairedGradeResult], skipped: list[str]) -> str:
    flips = {"none": 0, "pass_to_fail": 0, "fail_to_pass": 0}
    for r in results:
        flips[r.verdict_flip] += 1

    lines = [
        "# Paired re-scoring: τ³ grader vs structured-requirements grader",
        "",
        "Same task, same simulator prose, same trajectory, same agent output — only the "
        "grader's representation of user requirements changes.",
        "",
        "## Verdict-flip summary",
        "",
        f"- PASS -> FAIL (τ³ false-pass exposed): **{flips['pass_to_fail']}**",
        f"- FAIL -> PASS (investigate): **{flips['fail_to_pass']}**",
        f"- unchanged: **{flips['none']}**",
        f"- skipped (no V2 fixture yet): {', '.join(skipped) if skipped else 'none'}",
        "",
        "## Per-task",
        "",
        "| task | τ³ | structured | flip |",
        "|------|----|-----------|------|",
    ]
    for r in results:
        lines.append(
            f"| {r.task_id} | {'PASS' if r.tau3_pass else 'FAIL'} | "
            f"{'PASS' if r.structured_pass else 'FAIL'} | {r.verdict_flip} |"
        )

    for r in results:
        if not r.violations:
            continue
        lines += ["", f"### Task {r.task_id} — why the verdict flipped", ""]
        for v in r.violations:
            lines += ["```", v.describe(), "```"]
    return "\n".join(lines) + "\n"


def main() -> None:
    results, skipped = run()

    payload = {
        "experiment": "paired_rescoring_v1",
        "skipped_tasks": skipped,
        "results": [r.model_dump() for r in results],
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    md = to_markdown(results, skipped)
    with open(OUT_MD, "w") as f:
        f.write(md)

    # Console summary.
    print(md)
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
