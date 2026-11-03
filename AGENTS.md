# Agents

This is a Demo Depot kit. `usecase.yaml` is the only portal contract.

- `synth seed` and `synth verify` must stay model-free. Do not import
  `anthropic` or `langfuse` from `materialize`, `seed`, or `verify`.
- History is prewritten v1. Do not put v2 traces in the Spool.
- The refund calculator that ships in v2 is the source of truth for amounts.
  History may show that script's JSON on `run_refund_calculator` while the
  reply quotes a different figure. That is the v1 failure, not a bug.
- Re-pin `langfuse-synth-core` to `@v5.2.0` in `pyproject.toml` (both extras)
  and in `.github/workflows/publish.yml` once the tag exists. Until then the
  pin is commit `539bb30109d9aa5a2fddbc8e32880654b7505077`.
- Skill bundles live under `skill_bundles/returns-and-refunds/`. v1 is a single
  `SKILL.md`. Do not add reference files to v1.
