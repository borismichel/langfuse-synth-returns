"""Returns Desk companion. Preview uses fixtures. Live runs one chat turn at a time."""
from __future__ import annotations

import json
import re
import secrets
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


_CHAT_CSS = """
<style>
.transcript{display:flex;flex-direction:column;gap:12px;margin:18px 0 8px}
.bubble{max-width:86%;padding:12px 14px;border:1px solid var(--line-structure);
  border-radius:var(--radius);background:var(--surface-bg);font-size:15px}
.bubble.customer{margin-left:auto;background:var(--surface-beige)}
.bubble.desk{margin-right:auto}
.bubble .who{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--text-tertiary);margin-bottom:6px}
.composer button.send{margin-top:12px}
.row{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.row button{width:auto;margin:0;padding:8px 12px;background:transparent}
.row button:hover{background:var(--active-tint)}
details.trace{margin-top:8px}
details.trace summary{cursor:pointer;font-family:var(--font-mono);font-size:11px;
  color:var(--text-tertiary)}
.bubble .meta{font-family:var(--font-mono);font-size:12px;color:var(--text-tertiary);margin:8px 0 0}
.bubble .meta strong{color:var(--text-primary)}
</style>
"""
STARTERS = (
    ("parcel", "Where is my parcel? The tracking has not moved since Monday."),
    ("shirt", "Hi, I would like to return the navy t-shirt. It is unused. The price was 29.99."),
    (
        "dress",
        "The sale dress does not suit me. I bought it on sale five days ago and have not worn it.",
    ),
    (
        "mugs",
        "The mug set arrived cracked. I am attaching a photo. "
        "Please refund the mugs and the postage.",
    ),
)
_SESSION_RE = re.compile(r"^kc-[a-f0-9]{16}$")


def _turn(
    *,
    decision: str,
    amount,
    loaded: bool,
    calculated: bool,
    reply: str,
    reference: str | None = None,
) -> dict:
    return {
        "decision": decision,
        "refund_amount": amount,
        "loaded": loaded,
        "calculated": calculated,
        "reference": reference,
        "text": reply,
    }


def _preview_turn(message: str, prior: list[dict], label: str) -> dict:
    """Fixture reply. Production guesses; candidate follows the checklist."""
    low = message.lower()
    follow = bool(prior)
    postage = "postage" in low or "shipping" in low
    send_back = "send it back" in low or "how do i send" in low
    when_refund = "refund land" in low or "when does the refund" in low
    parcelish = any(
        word in low for word in ("parcel", "tracking", "where is", "invoice", "address")
    )
    shirt = "t-shirt" in low or "tshirt" in low
    dress = "dress" in low
    mugs = "mug" in low or "cracked" in low
    is_return = shirt or dress or mugs or any(
        word in low for word in ("return", "refund", "money back")
    )
    candidate = label == "candidate"
    if follow and postage:
        if candidate:
            return _turn(
                decision="not_applicable", amount=None, loaded=False, calculated=False,
                reply=(
                    "Postage is refunded only when the item arrived damaged and you sent a photo. "
                    "A standard return refunds the item price."
                ),
            )
        return _turn(
            decision="not_applicable", amount=None, loaded=True, calculated=False,
            reply=(
                "Preview fixture for v1. The desk loaded the returns skill again "
                "and worked the postage out itself."
            ),
        )
    if follow and (send_back or when_refund):
        if candidate:
            return _turn(
                decision="not_applicable", amount=None, loaded=False, calculated=False,
                reply=(
                    "Print the returns label in your Kestrel account and drop the parcel off "
                    "within fourteen days. The refund lands on the original card three to five "
                    "business days after we scan it."
                ),
            )
        return _turn(
            decision="not_applicable", amount=None, loaded=True, calculated=False,
            reply=(
                "Preview fixture for v1. The desk loaded the returns skill again. "
                "Send the parcel back and the refund should appear on your card."
            ),
        )
    if parcelish and not is_return:
        if candidate:
            return _turn(
                decision="not_applicable", amount=None, loaded=False, calculated=False,
                reply=(
                    "Preview fixture for v2. This is not a return, so the returns skill "
                    "stays closed. "
                    "The parcel is still in transit."
                ),
            )
        return _turn(
            decision="not_applicable", amount=None, loaded=True, calculated=False,
            reply=(
                "Preview fixture for v1. The desk loaded the returns skill "
                "for a question that is not a return."
            ),
        )
    if shirt:
        if candidate:
            return _turn(
                decision="approve_full", amount=29.99, loaded=True, calculated=True,
                reply=(
                    "Preview fixture for v2. The checklist names the rule "
                    "and the calculator returns 29.99."
                ),
            )
        return _turn(
            decision="approve_full", amount=28.99, loaded=True, calculated=False,
            reply=(
                "Preview fixture for v1. The prepaid returns label is EUR 1.00, "
                "so the desk quoted EUR 28.99."
            ),
        )
    if dress:
        if candidate:
            return _turn(
                decision="store_credit", amount=40.0, loaded=True, calculated=True,
                reference="references/sale-items.md",
                reply="Preview fixture for v2. Sale items come back as store credit of EUR 40.00.",
            )
        return _turn(
            decision="store_credit", amount=39.0, loaded=True, calculated=False,
            reply=(
                "Preview fixture for v1. Sale credit is the price paid minus the "
                "EUR 1.00 returns label, so the desk quoted EUR 39.00."
            ),
        )
    if mugs:
        if candidate:
            return _turn(
                decision="approve_full", amount=36.95, loaded=True, calculated=True,
                reference="references/damaged-goods.md",
                reply=(
                    "Preview fixture for v2. The calculator returns EUR 36.95, "
                    "the mugs plus postage."
                ),
            )
        return _turn(
            decision="approve_full", amount=36.95, loaded=True, calculated=False,
            reply=(
                "Preview fixture for v1. The photo is on the ticket. "
                "The desk quoted EUR 36.95 without the calculator."
            ),
        )
    if candidate:
        return _turn(
            decision="not_applicable", amount=None, loaded=False, calculated=False,
            reply="Preview fixture for v2. The checklist does not treat this as a return.",
        )
    return _turn(
        decision="not_applicable", amount=None, loaded=True, calculated=False,
        reply=(
            "Preview fixture for v1. The desk loaded the returns skill "
            "for a question that is not a return."
        ),
    )


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


_MAX_MESSAGES = 24
_MESSAGE_LIMIT = 2000
_STARTER_LABELS = {
    "parcel": "Where is my parcel?",
    "shirt": "Return the t-shirt",
    "dress": "Sale dress",
    "mugs": "Cracked mugs",
}


def _session_id(raw: str) -> str:
    text = (raw or "").strip()
    if _SESSION_RE.fullmatch(text):
        return text
    return "kc-" + secrets.token_hex(8)


def _read_history(raw: str) -> list[dict]:
    try:
        data = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    clean: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()[:_MESSAGE_LIMIT]
        if not content:
            continue
        kept: dict[str, Any] = {"role": role, "content": content}
        if role == "user":
            item_id = item.get("item_id")
            if isinstance(item_id, str) and re.fullmatch(r"rr-\d{3}", item_id):
                kept["item_id"] = item_id
        else:
            amount = item.get("refund_amount")
            reference = item.get("reference")
            kept["decision"] = str(item.get("decision") or "not_applicable")[:40]
            kept["refund_amount"] = amount if isinstance(amount, (int, float)) else None
            kept["loaded"] = bool(item.get("loaded"))
            kept["calculated"] = bool(item.get("calculated"))
            if item.get("label") in {"production", "candidate"}:
                kept["label"] = item["label"]
            if isinstance(reference, str) and len(reference) < 120:
                kept["reference"] = reference
        clean.append(kept)
    return clean[-_MAX_MESSAGES:]


def _match_item(message: str) -> dict | None:
    low = " ".join(message.lower().split())
    if len(low) < 12:
        return None
    head = low[:40]
    for row in _items():
        golden = " ".join(row["input"]["customer_message"].lower().split())
        if head in golden or golden[:40] in low:
            return row
    return None


def _ticket_for(message: str, history: list[dict]) -> tuple[dict, str | None]:
    row = _match_item(message)
    if row is None:
        for turn in reversed(history):
            item_id = turn.get("item_id")
            if item_id:
                row = next((item for item in _items() if item["id"] == item_id), None)
                break
    if row is None:
        ticket = {
            "customer_message": message,
            "order": {"order_id": "KC-LIVE", "items": [], "today": "2026-10-20"},
            "customer_tier": "standard",
        }
        return ticket, None
    ticket = dict(row["input"])
    ticket["customer_message"] = message
    return ticket, str(row["id"])


def _record_turn(reply: dict, label: str) -> dict:
    recorded = {
        "role": "assistant",
        "content": str(reply["text"])[:_MESSAGE_LIMIT],
        "decision": reply["decision"],
        "refund_amount": reply["refund_amount"],
        "loaded": bool(reply["loaded"]),
        "calculated": bool(reply["calculated"]),
        "label": label,
    }
    if reply.get("reference"):
        recorded["reference"] = reply["reference"]
    return recorded


def _bubble(turn: dict) -> str:
    customer = turn["role"] == "user"
    desk = turn.get("label") or "desk"
    who = "You" if customer else "Returns Desk · " + escape(str(desk))
    body = f"<p>{escape(turn['content'])}</p>"
    extra = ""
    if not customer:
        amount = turn.get("refund_amount")
        shown = "none" if amount is None else escape(str(amount))
        extra = (
            f"<p class='meta'>decision <strong>{escape(str(turn.get('decision')))}</strong>"
            f" · amount <strong>{shown}</strong></p>"
            "<details class='trace'><summary>This turn</summary>"
            + _outline(
                bool(turn.get("loaded")),
                turn.get("reference"),
                bool(turn.get("calculated")),
            )
            + "</details>"
        )
    klass = "customer" if customer else "desk"
    return f"<article class='bubble {klass}'><div class='who'>{who}</div>{body}{extra}</article>"


def _transcript(history: list[dict]) -> str:
    if not history:
        return "<p class='sub'>Ask about a return, or pick a starter below.</p>"
    bubbles = "".join(_bubble(turn) for turn in history)
    return f"<div class='transcript'>{bubbles}</div>"


def _composer(*, history: list[dict], session_id: str, label: str, note: str = "") -> str:
    blob = escape(json.dumps(history, separators=(",", ":"), ensure_ascii=False))
    prod = " selected" if label != "candidate" else ""
    cand = " selected" if label == "candidate" else ""
    starters = "".join(
        f"<button type='submit' name='starter' value='{escape(key)}'>"
        f"{escape(_STARTER_LABELS[key])}</button>"
        for key, _text in STARTERS
    )
    warning = f"<p class='note'>{escape(note)}</p>" if note else ""
    return (
        f"<form class='composer' method='post' action='{paths.local('/chat')}'>"
        f"<input type='hidden' name='history' value='{blob}'>"
        f"<input type='hidden' name='session_id' value='{escape(session_id)}'>"
        "<p><label>Skill label<br>"
        f"<select name='label'><option value='production'{prod}>production (v1)</option>"
        f"<option value='candidate'{cand}>candidate (v2)</option></select></label></p>"
        "<p><label>Message<br>"
        "<textarea name='message' rows='3' cols='72' "
        "placeholder='Ask a follow-up, or describe the return'></textarea></label></p>"
        f"{warning}"
        "<p class='row'>"
        f"{starters}"
        "</p>"
        "<p><button class='send' type='submit'>Send</button></p>"
        "</form>"
    )


def _chat_page(
    *,
    history: list[dict],
    session_id: str,
    label: str,
    preview: bool,
    note: str = "",
) -> str:
    fresh = paths.local("/chat")
    body = (
        _CHAT_CSS
        + "<p class='eyebrow'>Kestrel &amp; Co</p>"
        + "<h1>Returns <span class='mark'>Desk</span></h1>"
        + "<p class='sub'>One conversation is one Langfuse session. "
        + "Each message is its own trace. New chat starts a new session.</p>"
        + f"<p class='kv'>session <strong>{escape(session_id)}</strong> · "
        + f"<a class='back' href='{fresh}'>New chat</a></p>"
        + _transcript(history)
        + _composer(history=history, session_id=session_id, label=label, note=note)
    )
    return _page(body, title="Returns Desk · chat", preview=preview)


def _live_turn(adapter, message: str, history: list[dict], label: str, session_id: str) -> dict:
    from ..returns_agent.agent import run_ticket
    from ..returns_agent.tools import fetch_skill

    ticket, _item_id = _ticket_for(message, history)
    prior = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in history
        if turn.get("role") in {"user", "assistant"}
    ]
    skill = fetch_skill(adapter.langfuse(), label=label)
    llm = adapter.llm(MODEL)
    result = run_ticket(
        skill,
        ticket,
        history=prior,
        emitter=adapter.emitter(),
        anthropic_client=llm.bind(),
        model=llm.model,
        user_id="kc-" + session_id.split("-", 1)[-1][:8],
        session_id=session_id,
        metadata={"source": "companion", "label": label, "turn": str(len(prior) // 2 + 1)},
    )
    files = [str(path) for path in (result.get("files_read") or [])]
    reference = next((path for path in files if path.startswith("references/")), None)
    amount = result.get("refund_amount")
    return _turn(
        decision=str(result.get("decision") or "not_applicable"),
        amount=amount if isinstance(amount, (int, float)) else None,
        loaded=bool(result.get("loaded_skill")),
        calculated=bool(result.get("calculated")),
        reference=reference,
        reply=str(result.get("reply") or ""),
    )


def create_app(adapter: CompanionAdapterContract, *, preview: bool = False) -> Any:
    """Build the surface. Construction does not touch the network."""
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def _root() -> str:
        body = (
            "<p class='eyebrow'>Kestrel &amp; Co</p>"
            "<h1>Returns <span class='mark'>Desk</span></h1>"
            "<p class='sub'>Version 1 of returns-and-refunds is in production: one long note "
            "that deducts a EUR 1.00 returns label and tells the model to work the amount "
            "out itself. Version 2 is the candidate: a short checklist, one reference per "
            "edge case, and the refund calculator.</p>"
            f"<p><a href='{paths.local('/chat')}'>Open the desk</a></p>"
        )
        return _page(body, title="Returns Desk", preview=preview)

    @app.get("/chat", response_class=HTMLResponse)
    async def _chat() -> str:
        return _chat_page(
            history=[],
            session_id=_session_id(""),
            label="production",
            preview=preview,
        )

    @app.post("/chat", response_class=HTMLResponse)
    async def _submit(request: Request) -> str:
        form = {key: str(value) for key, value in (await request.form()).items()}
        label = form.get("label") or "production"
        if label not in {"production", "candidate"}:
            label = "production"
        posted_session = form.get("session_id") or ""
        session_id = _session_id(posted_session)
        history = _read_history(form.get("history") or "") if _SESSION_RE.fullmatch(
            posted_session
        ) else []
        starter = form.get("starter") or ""
        message = dict(STARTERS).get(starter) or (form.get("message") or "")
        message = message.strip()[:_MESSAGE_LIMIT]
        if not message:
            return _chat_page(
                history=history,
                session_id=session_id,
                label=label,
                preview=preview,
                note="Type a message.",
            )
        _ticket, item_id = _ticket_for(message, history)
        try:
            if preview:
                reply = _preview_turn(message, history, label)
            else:
                reply = _live_turn(adapter, message, history, label, session_id)
        except Exception as exc:  # noqa: BLE001 — type name only, never a stack or payload
            kind = type(exc).__name__
            return _chat_page(
                history=history,
                session_id=session_id,
                label=label,
                preview=preview,
                note=f"The desk could not answer this turn: {kind}",
            )
        if not str(reply.get("text") or "").strip():
            return _chat_page(
                history=history,
                session_id=session_id,
                label=label,
                preview=preview,
                note=(
                    "The desk could not answer this turn: the model stopped "
                    "before it wrote a reply."
                ),
            )
        user_turn: dict[str, Any] = {"role": "user", "content": message}
        if item_id:
            user_turn["item_id"] = item_id
        history = [*history, user_turn, _record_turn(reply, label)][-_MAX_MESSAGES:]
        return _chat_page(history=history, session_id=session_id, label=label, preview=preview)

    return app


def build_adapter(cfg) -> CompanionAdapter:
    """Live adapter. Readiness reports the kit model, not core's fallback."""
    return CompanionAdapter(
        cfg,
        requires_secrets=REQUIRES_SECRETS,
        health_path=HEALTH_PATH,
        llm_model_default=MODEL,
    )


def main(argv: list[str] | None = None) -> int:
    from synth.config import load_config

    inv = parse_invocation(argv)
    cfg = load_config(inv.config)
    adapter = build_adapter(cfg)
    adapter.run(create_app, host=inv.host, port=inv.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
