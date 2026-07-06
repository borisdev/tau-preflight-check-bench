# Provenance

This repo is a **trimmed, text-only PoC fork** of τ³-bench
(`sierra-research/tau2-bench`), vendored at upstream commit:

    8ebb7499622fc2be9b9d510d6f7a7653461f4f29  (8ebb749, 2026-06-22)

## What was removed vs. upstream (PoC trim)
- `data/tau2/results/` — 576 MB of pre-computed leaderboard trajectory dumps
- `data/tau2/domains/{telecom,retail}` — kept only airline + banking + mock
- every `tasks_voice.json` / `audio_difficulty.json` and audio assets (voice modality out of PoC scope)
- `web/` leaderboard viewer, `figs/`, and upstream git history

All `src/` code is intact (incl. voice modules, unused here). To pull upstream
fixes: `git fetch upstream && git checkout upstream/main -- <path>`.

## Local additions vs. upstream (pull carefully)
- `src/tau2/data_model/tasks.py` — `StructuredUserInstructions` carries one local field, the optional `user_preflight_requirements` (from `preflight_requirements.py`); re-do upstream pulls of this file carefully so the field is preserved.

See `PROBLEM_BELIEF_SPEC.md` for the deferred agent-belief-tracking design (the current pilot is paired re-scoring — see `README.md`).
