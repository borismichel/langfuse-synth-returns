"""Returns Desk companion. Preview uses fixtures. Live runs one ticket or v1 against v2."""
from __future__ import annotations

from html import escape
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from langfuse_synth_core.companion import (
    CompanionAdapter,
    CompanionAdapterContract,
    parse_invocation,
)
from langfuse_synth_core.live import paths, theme

from ..golden_set import load_golden

HEALTH_PATH = "/healthz"
REQUIRES_SECRETS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LLM_API_KEY")
MODEL = "claude-sonnet-5-5"


def _preview_banner(preview: bool) -> str:
    if not preview:
        return ""
    return (
        "<aside role='status'><strong>Development preview</strong> — fixture data only. "
        "Live readiness and admission have not been checked.</aside>"
    )


def _footer() -> str:
    return (
        "<details class='note'><summary>Presenter controls</summary>"
        "<p>Only numbers from a live experiment go on screen. Seeded scores are prewritten.</p>"
        "<pre>synth skills-publish --config config/demo.yaml\n"
        "synth dataset-publish --config config/demo.yaml\n"
        "synth seed --config config/demo.yaml\n"
        "synth verify --config config/demo.yaml\n"
        "synth experiment --skill-version 1 --run-name returns-v1\n"
        "synth experiment --skill-version 2 --run-name returns-v2</pre>"
        "<p>Filter the seeded trace whose metadata archetype is shipping-loads-skill. "
        "On-camera install, in a folder other than .agents/skills:</p>"
        "<pre>npx @langfuse/cli skills install returns-and-refunds "
        "--label production --directory ./var/returns-skills\n"
        "synth experiment --skill-version 1 --install-dir ./var/returns-skills "
        "--run-name returns-v1-cli</pre>"
        "</details>"
    )


def _page(body: str, *, title: str, preview: bool) -> str:
    return theme.page(_preview_banner(preview) + body + _footer(), title=title, wide=True)


def _items() -> list[dict]:
    return load_golden()["items"]


def _worse(expected: dict) -> dict:
    amount = expected.get("refund_amount")
    if isinstance(amount, (int, float)):
        twisted = round(float(amount) - 1, 2)
        return {
            "decision": expected.get("decision"),
            "refund_amount": twisted,
            "reply": (
                f"Preview fixture for v1. The desk worked the amount out itself "
                f"and quoted EUR {twisted:.2f}."
            ),
            "loaded_skill": True,
            "files_read": [],
        }
    if expected.get("decision") == "not_applicable":
        return {
            "decision": "not_applicable",
            "refund_amount": None,
            "reply": (
                "Preview fixture for v1. The desk loaded the returns skill "
                "for a question that is not a return."
            ),
            "loaded_skill": True,
            "files_read": ["SKILL.md"],
        }
    return {
        "decision": expected.get("decision"),
        "refund_amount": expected.get("refund_amount"),
        "reply": (
            "Preview fixture for v1. The reply follows the vague skill and skips the calculator."
        ),
        "loaded_skill": True,
        "files_read": [],
    }


def _outline(loaded: bool, reference: str | None, calculated: bool) -> str:
    rows = ["returns-ticket", "  returns-desk (agent)", "    classify-intent"]
    if loaded:
        rows.append("    loadSkill")
    if reference:
        rows.append(f"    skill_read {reference}")
    if calculated:
        rows.append("    run_refund_calculator")
    rows.append("    draft-customer-reply")
    rows.append("    route-returns" if loaded else "    route-general")
    return "<pre>" + escape("\n".join(rows)) + "</pre>"


def _result_card(title: str, result: dict, *, reference: str | None, calculated: bool) -> str:
    amount = result.get("refund_amount")
    shown = "none" if amount is None else escape(str(amount))
    return (
        "<article class='card'>"
        f"<h2>{escape(title)}</h2>"
        f"<p class='kv'>decision <strong>{escape(str(result.get('decision')))}</strong></p>"
        f"<p class='kv'>amount <strong>{shown}</strong></p>"
        f"<p>{escape(str(result.get('reply') or ''))}</p>"
        + _outline(bool(result.get("loaded_skill")), reference, calculated)
        + "</article>"
    )


def _ticket_from_form(form: dict) -> tuple[dict | None, str | None]:
    chosen = (form.get("item") or "").strip()
    message = (form.get("message") or "").strip()
    match = next((row for row in _items() if row["id"] == chosen), None)
    if match is None and not message:
        return None, "Pick a golden ticket or type a message."
    if match is None:
        ticket = {
            "customer_message": message,
            "order": {"order_id": "KC-LIVE", "items": [], "today": "2026-10-20"},
            "customer_tier": "standard",
        }
        return {"input": ticket, "expected": {}, "metadata": {}, "id": "custom"}, None
    ticket = dict(match["input"])
    if message:
        ticket["customer_message"] = message
    return {**match, "input": ticket}, None


def _form(selected: str = "", message: str = "", label: str = "production") -> str:
    options = ["<option value=''>Custom message only</option>"]
    for row in _items():
        mark = " selected" if row["id"] == selected else ""
        text = row["input"]["customer_message"]
        short = text if len(text) <= 72 else text[:69] + "..."
        option = (
            f"<option value='{escape(row['id'])}'{mark}>"
            f"{escape(row['id'])} — {escape(short)}</option>"
        )
        options.append(option)
    prod = " selected" if label != "candidate" else ""
    cand = " selected" if label == "candidate" else ""
    return (
        f"<form method='post' action='{paths.local('/chat')}'>"
        f"<p><label>Golden ticket<br><select name='item'>{''.join(options)}</select></label></p>"
        f"<p><label>Message<br><textarea name='message' rows='4' cols='72'>"
        f"{escape(message)}</textarea></label></p>"
        "<p><label>Skill label<br>"
        f"<select name='label'><option value='production'{prod}>production (v1)</option>"
        f"<option value='candidate'{cand}>candidate (v2)</option></select></label></p>"
        "<p><button name='action' value='run'>Run ticket</button> "
        "<button name='action' value='compare'>Run v1 vs v2</button></p>"
        "</form>"
    )


def _fixture_column(row: dict, label: str) -> str:
    expected = row.get("expected") or {}
    meta = row.get("metadata") or {}
    if not expected.get("decision"):
        # A typed message with no golden row is a non-return question.
        expected = {"decision": "not_applicable", "refund_amount": None}
        meta = {"should_load_skill": label != "candidate", "needs_reference": None}
    reference = meta.get("needs_reference")
    if label == "candidate":
        result = {
            "decision": expected.get("decision"),
            "refund_amount": expected.get("refund_amount"),
            "reply": (
                "Preview fixture for v2. The checklist names the rule and the calculator "
                f"returns {expected.get('refund_amount')}."
            ),
            "loaded_skill": bool(meta.get("should_load_skill")),
            "files_read": [reference] if reference else [],
        }
        calculated = bool(meta.get("should_load_skill")) and expected.get("decision") not in {
            None,
            "not_applicable",
        }
    else:
        result = _worse(expected)
        reference = None
        calculated = False
    return _result_card(f"Fixture · {label}", result, reference=reference, calculated=calculated)


def create_app(adapter: CompanionAdapterContract, *, preview: bool = False) -> Any:
    """Build the surface. Construction does not touch the network."""
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def _root() -> str:
        body = (
            "<p class='eyebrow'>Kestrel &amp; Co</p>"
            "<h1>Returns <span class='mark'>Desk</span></h1>"
            "<p class='sub'>Version 1 of returns-and-refunds is in production: one long note "
            "that tells the model to work amounts out itself. Version 2 is the candidate: "
            "a short checklist, one reference per edge case, and the refund calculator.</p>"
            f"<p><a href='{paths.local('/chat')}'>Open a ticket</a></p>"
        )
        return _page(body, title="Returns Desk", preview=preview)

    @app.get("/chat", response_class=HTMLResponse)
    async def _chat() -> str:
        body = "<h1>Run a ticket</h1>" + _form()
        return _page(body, title="Returns Desk · ticket", preview=preview)

    @app.post("/chat", response_class=HTMLResponse)
    async def _submit(request: Request) -> str:
        form = dict(await request.form())
        action = str(form.get("action") or "run")
        row, error = _ticket_from_form({key: str(value) for key, value in form.items()})
        selected = str(form.get("item") or "")
        message = str(form.get("message") or "")
        label = str(form.get("label") or "production")
        if label not in {"production", "candidate"}:
            label = "production"
        body = "<h1>Run a ticket</h1>" + _form(selected, message, label)
        if error or row is None:
            note = escape(error or "Pick a golden ticket or type a message.")
            body += f"<p class='note'>{note}</p>"
            return _page(body, title="Returns Desk · ticket", preview=preview)
        if preview:
            if action == "compare":
                body += _fixture_column(row, "production") + _fixture_column(row, "candidate")
            else:
                body += _fixture_column(row, label)
            return _page(body, title="Returns Desk · ticket", preview=preview)
        try:
            body += _live(adapter, row, action=action, label=label)
        except Exception as exc:  # noqa: BLE001 — show the failure on the desk, not a stack
            kind = escape(type(exc).__name__)
            body += f"<p class='note'>The desk could not run this ticket: {kind}</p>"
        return _page(body, title="Returns Desk · ticket", preview=preview)

    return app


def _live(adapter, row: dict, *, action: str, label: str) -> str:
    from ..returns_agent.agent import run_ticket
    from ..returns_agent.tools import fetch_skill

    def once(skill_label: str) -> str:
        skill = fetch_skill(adapter.langfuse(), label=skill_label)
        llm = adapter.llm(MODEL)
        result = run_ticket(
            skill,
            row["input"],
            emitter=adapter.emitter(),
            anthropic_client=llm.bind(),
            model=llm.model,
            user_id=f"kc-{row.get('id', 'live')}",
            session_id=f"companion-{row.get('id', 'live')}-{skill_label}",
            metadata={"source": "companion", "label": skill_label, "item_id": str(row.get("id"))},
        )
        reference = (row.get("metadata") or {}).get("needs_reference")
        calculated = "scripts/calc_refund.py" in skill.files and bool(result.get("loaded_skill"))
        return _result_card(
            f"Live · {skill_label} · v{skill.version}",
            result,
            reference=reference if reference in (result.get("files_read") or []) else None,
            calculated=calculated and result.get("refund_amount") is not None,
        )

    if action == "compare":
        return once("production") + once("candidate")
    return once(label)


def main(argv: list[str] | None = None) -> int:
    from synth.config import load_config

    inv = parse_invocation(argv)
    cfg = load_config(inv.config)
    adapter = CompanionAdapter(cfg, requires_secrets=REQUIRES_SECRETS, health_path=HEALTH_PATH)
    adapter.run(create_app, host=inv.host, port=inv.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
