# Agents

This is a Demo Depot kit. `usecase.yaml` is the only portal contract.

- `synth seed` and `synth verify` must stay model-free. Do not import
  `anthropic` or `langfuse` from `materialize`, `seed`, or `verify`.
- History is prewritten v1. Do not put v2 traces in the Spool.
- The refund calculator ships only in v2. Seeded v1 traces must not contain
  `run_refund_calculator`. A reply amount, the rule, and the scores on that
  trace have to agree. v1 gets amounts wrong by working them out itself.
- Core is pinned to `@v5.2.0` in pyproject.toml (both extras) and publish.yml; keep all three in step.
- Skill bundles live under `skill_bundles/returns-and-refunds/`. v1 is a single
  `SKILL.md`. Do not add reference files to v1.
