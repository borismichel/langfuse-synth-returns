# Returns Desk

A Demo Depot kit for Langfuse skill management. Kestrel & Co is fictional.
`returns-and-refunds` v1 is a single long skill. It tells the model to work
refund amounts out itself, and the rule it states is an older one: a EUR 1.00
prepaid returns label comes off ordinary refunds and off sale credit. v2 is a
checklist, one reference per edge case, and `scripts/calc_refund.py`, which
pays the shelf price. Seeded history is v1 only. v2 shows up in live
experiments.

## Feature previews

Turn on **V4 Preview** and **Skill Management** under the account menu →
Feature Preview, if those toggles are present. Langfuse Cloud from v4.73.0 has
skill management on by default; the docs still mention the toggle, so check
the menu before a dry run.

## Setup

Python 3.11+. Core is pinned to commit `539bb30109d9aa5a2fddbc8e32880654b7505077`
(the untagged 5.2.0 skills support) in both the runtime extra and the authoring
extra, and the publish workflow uses the same commit. Re-pin all three to
`@v5.2.0` once that tag exists.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Environment for anything that talks to Langfuse or Anthropic:

| Variable | Role |
| --- | --- |
| `LANGFUSE_PUBLIC_KEY` | project public key |
| `LANGFUSE_SECRET_KEY` | project secret key |
| `LANGFUSE_BASE_URL` or `LANGFUSE_HOST` | project host. Overrides `target.host` in `config/demo.yaml`. |
| `ANTHROPIC_API_KEY` | model key. The portal injects this for the `LLM_API_KEY` sentinel. |
| `LLM_API_KEY` | accepted as a fallback by the experiment command |
| `LLM_MODEL` | optional. Default `claude-sonnet-5-5` for the desk and the judge. |

`synth seed` and `synth verify` do not call a model and do not need the Anthropic key.
They do need the Langfuse keys when they are not a dry run.

## Rerun

From the kit root, against a project whose name matches `target.project_hint`
(`demo` unless you change it):

```bash
synth skills-publish --config config/demo.yaml
synth dataset-publish --config config/demo.yaml
synth seed --config config/demo.yaml
synth verify --config config/demo.yaml
synth experiment --skill-version 1 --run-name returns-v1
synth experiment --skill-version 2 --run-name returns-v2
```

Publish v1 first. A fresh project then has version 1 labelled `production` and
version 2 labelled `candidate`. If those version numbers are already taken by
different files, the publish command stops and asks for a fresh project.

The seeded window ends on `generation.as_of_date` when the portal passes it, at
noon UTC. With no as-of date the window ends at the time of the run. Volume is
`generation.target_traces` (default 84 turns, grouped into sessions of one to
four messages across about four weeks). The same seed and as-of date rewrite
the same Spool file.
Importing that file again **appends**. OTLP does not upsert. Re-seed into a
cleared project.

`generation-report.json` and `DEMO_SCRIPT.md` land in `SYNTH_OUT_DIR`
(`/app/out` in the depot image).

## Companion

```bash
synth companion --config config/demo.yaml --host 0.0.0.0 --port 8080
```

`/chat` is a multi-turn desk. One conversation is one Langfuse session, and
each message is one trace. The production / candidate toggle picks the skill
label. New chat starts another session. Presenter commands sit in the footer.
Offline preview, fixture data only:

```bash
python -m synth.companion.preview --port 8765
```

Preview does not check readiness. `/healthz` on the preview is 503. The live
process serves readiness on `/healthz` and the desk on `/`.

## CLI install

The on-camera path uses the Langfuse CLI and a directory that is not
`.agents/skills`:

```bash
npx @langfuse/cli skills install returns-and-refunds --label production --directory ./var/returns-skills
synth experiment --skill-version 1 --install-dir ./var/returns-skills --run-name returns-v1-cli
```

`--install-dir` reads `langfuse-skills.lock` (the directory, then the working
directory, or `--lockfile`) and runs the files that were installed.

## What is checked without keys

`pytest`, `ruff check`, and `synth-authoring validate`, `conformance`, and
`check` run offline. `scripts/calc_refund.py` reproduces every golden amount.
The golden Spool is byte-identical for seed 42, 24 traces, as-of 2026-10-20.

Live checks that need a project are listed in the pull request: both skill
versions and their per-file diff, the 16-item dataset, both experiment runs in
Compare, tool observations for `SKILL.md` / a reference / the script, and the
measured deltas from at least two runs of each version.
