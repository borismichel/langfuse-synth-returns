# Returns Desk — presenter runbook

Kestrel & Co is fictional. Prices are EUR. The production skill is
`returns-and-refunds` version 1: one long note, description "Helps with customer
orders", and it tells the model to work amounts out itself. Version 2 is the
candidate: a short checklist, one reference per edge case, and
`scripts/calc_refund.py`.

Only numbers from a live experiment go on screen. Seeded scores are prewritten
so the history is stable. Do not read a seeded cost or score out as if the model
had just produced it.

The desk companion keeps the same commands in a muted footer on `/` and `/chat`.

## 1. The v1 cost problem

Open the seeded project and filter traces whose metadata `archetype` is
`shipping-loads-skill`. That turn asks where a parcel is. The trace is
`returns-other`. Under the `returns-desk` agent, `loadSkill` still ran, and the
reply generation carries a large input-token count because version 1 pastes the
whole policy into context.

About three in five non-return decision turns do the same. Follow-up turns in
the same session are separate and are not part of that count. Refund turns
work the amount out in the reply, with no calculator observation, and sometimes
quote a nearby but wrong amount (the navy t-shirt is the next beat: EUR 28.99
against a EUR 29.99 price).

## 2. Skill loads in the trace

Open that shipping trace, then open a refund trace whose archetype is
`damaged-reference` or `sale-reference`.

- On a generation, the Preview shows the skill version that was available
  (`returns-and-refunds` version 1). The same attribute is on `loadSkill` and
  on `skill_read`.
- `loadSkill` is a tool observation under the agent, next to the generation
  that asked for it, not inside it.
- `skill_read` of `references/sale-items.md` (and the other edge-case files)
  returns a not-in-this-version result. Version 1 is a single `SKILL.md`.
  A Gold ticket reads `SKILL.md` itself.
- The Usage tab on a loaded generation shows input tokens, output tokens, and
  a cost. The cost uses the Sonnet-class placeholder in the kit, because this
  model has no published price card.
- Seeded v1 traces do not call `run_refund_calculator`. That tool is version 2.
  On the damaged-goods turn the photo check and the reply both say EUR 36.95
  under rule R5, and the scores on that trace are 1. A wrong amount, such as
  the t-shirt, is the desk working it out itself. The calculator observation
  shows up on a live version 2 turn, not in this history.
- Trace metadata on the root is `archetype`, which is the filter above. Channel,
  tier, skill version, and the turn number sit on the root observation only.
  Child observations carry the step they are (`tool` or `step`), so the side
  panel is not a copy of the trace.

## Sessions

Seeded history is conversations, not one trace per ticket. A session has one
to four turns: the opening ask, sometimes a clarification, the decision, and
a follow-up such as postage or how to send it back. Those turns share
`session_id` and `user_id`. The later turns start seconds to minutes after the
first, so Sessions shows a conversation.

The window is the weeks before the as-of date. The frozen golden spool is the
four weeks up to 2026-10-20, the story's today. A live seed with no as-of date
uses the time of the run, so a fresh import looks recent.

## 3. v2, compare, promote

Run the live experiment for version 1 and version 2 (commands in Developer mode
below). In Langfuse, open Experiments and Compare the two runs of
`returns-desk`. The scores are `decision_correct`, `amount_correct`,
`skill_load_correct`, and `policy_faithful`. Cost and latency are on the runs.

Version 2 should load the skill only for returns, open one reference when the
case needs it, and take `refund_amount` from the calculator. The companion is
a chat: each conversation keeps one `session_id`, and each message is one
trace with the same nesting (agent, classify, loadSkill or skill_read, the
calculator on v2, then the reply). Earlier turns are on the agent input.
Start a new chat to mint another session, and use the production / candidate
toggle to show v1 against v2. Move the `production` label from version 1 to
version 2, then send the same question in a new chat. Rollback is moving that
label back. `latest` stays on the newest version either way; do not present
`latest` as the switch.

## Developer mode — rerun from a shell

These commands are for a keyboard, not for the click-through above. Run them
from the kit root. Re-seeding appends; OTLP does not upsert. Clear the project
first if you need a clean history.

```bash
synth skills-publish --config config/demo.yaml
synth dataset-publish --config config/demo.yaml
synth seed --config config/demo.yaml
synth verify --config config/demo.yaml
synth experiment --skill-version 1 --run-name returns-v1
synth experiment --skill-version 2 --run-name returns-v2
```

On-camera install into a directory other than `.agents/skills`:

```bash
npx @langfuse/cli skills install returns-and-refunds --label production --directory ./var/returns-skills
synth experiment --skill-version 1 --install-dir ./var/returns-skills --run-name returns-v1-cli
```

Filter the seeded shipping trace on metadata `archetype` = `shipping-loads-skill`.
The trace id for seed 42 is in `generation-report.json` after `synth seed`.
