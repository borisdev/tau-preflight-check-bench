# Paired re-scoring: τ³ grader vs preflight-requirements grader

Same task, same simulator prose, same trajectory, same agent output — only the grader's representation of user requirements changes.

## Verdict-flip summary

- PASS -> FAIL (τ³ false-pass exposed): **1**
- FAIL -> PASS (investigate): **0**
- unchanged: **0**
- skipped (no V2 fixture yet): 43, 39, 35, 24, 11

## Per-task

| task | τ³ | structured | flip |
|------|----|-----------|------|
| 47 | PASS | FAIL | pass_to_fail |

### Task 47 — why the verdict flipped

```
[task47.no_unwanted_transfer] VIOLATED at turn 12: the agent must not transfer the user when transfer authorization is denied
    action: transfer_to_human_agents  (denied_authorization)
    evidence: called transfer_to_human_agents; user explicitly denied authorization for this action
    source (task_instructions): "you don't want to be transferred to another agent"
```
