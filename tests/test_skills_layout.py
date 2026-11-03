"""v1 is one vague file. v2 is the checklist, the references, and the script."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "skill_bundles" / "returns-and-refunds"


def _frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _lead, meta, body = text.split("---", 2)
    return yaml.safe_load(meta), body


def test_v1_is_a_single_vague_skill():
    files = [
        path.relative_to(ROOT / "v1").as_posix()
        for path in (ROOT / "v1").rglob("*")
        if path.is_file()
    ]
    assert files == ["SKILL.md"]
    meta, body = _frontmatter(ROOT / "v1" / "SKILL.md")
    assert meta["name"] == "returns-and-refunds"
    assert meta["description"] == "Helps with customer orders"
    words = body.split()
    assert 2300 <= len(words) <= 2800
    assert "Work the refund amount out yourself." in body
    assert "Do not use a script" in body


def test_v2_points_at_one_reference_per_edge_and_the_script():
    meta, body = _frontmatter(ROOT / "v2" / "SKILL.md")
    assert meta["name"] == "returns-and-refunds"
    assert (
        meta["description"]
        == "Use only when a customer asks to return an item or get money back"
    )
    assert "R1" in body and "R2" in body and "R3" in body and "R9" in body
    assert "references/sale-items.md" in body
    assert "references/damaged-goods.md" in body
    assert "references/digital-and-subscriptions.md" in body
    assert "scripts/calc_refund.py" in body
    for relative in (
        "references/returns-policy.md",
        "references/sale-items.md",
        "references/damaged-goods.md",
        "references/digital-and-subscriptions.md",
        "templates/customer-reply.md",
        "scripts/calc_refund.py",
    ):
        assert (ROOT / "v2" / relative).is_file()
    template = (ROOT / "v2" / "templates" / "customer-reply.md").read_text(encoding="utf-8")
    placeholders = (
        "{customer_name}",
        "{decision_sentence}",
        "{refund_amount}",
        "{policy_rule}",
        "{next_steps}",
    )
    for placeholder in placeholders:
        assert placeholder in template
    policy = (ROOT / "v2" / "references" / "returns-policy.md").read_text(encoding="utf-8")
    rules = (
        "R1-30-day-window",
        "R4-sale-store-credit",
        "R5-damaged-on-arrival",
        "R7-subscription-pro-rata",
        "R9-approval-limit",
    )
    for rule in rules:
        assert rule in policy
