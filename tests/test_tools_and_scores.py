"""Tool dispatch and the three exact scores. The judge is not called."""
import json
from pathlib import Path

from synth.returns_agent.evaluators import amount_correct, decision_correct, skill_load_correct
from synth.returns_agent.tools import (
    FetchedSkill,
    dispatch,
    load_installed,
    run_refund_calculator,
)

V2 = Path(__file__).resolve().parents[1] / "skill_bundles" / "returns-and-refunds" / "v2"


def _v2() -> FetchedSkill:
    files = {
        path.relative_to(V2).as_posix(): path.read_text(encoding="utf-8")
        for path in V2.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    return FetchedSkill(name="returns-and-refunds", version=2, files=files, label="candidate")


def test_v2_calculator_runs_the_fetched_script():
    skill = _v2()
    result = run_refund_calculator(skill, {
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "TEE",
            "category": "apparel",
            "price": "29.99",
            "delivery_date": "2026-10-10",
            "condition_reported": "unused",
            "return": True,
        }],
    })
    assert result["decision"] == "approve_full"
    assert result["refund_amount"] == 29.99
    assert result["policy_rule"] == "R1-30-day-window"


def test_v1_has_no_script_and_a_missing_reference_is_not_null():
    skill = FetchedSkill(
        name="returns-and-refunds",
        version=1,
        files={
            "SKILL.md": (
                "---\nname: returns-and-refunds\n"
                "description: Helps with customer orders\n---\nbody\n"
            )
        },
    )
    missing = json.loads(
        dispatch(
            skill,
            "skill_read",
            {"skillName": skill.name, "path": "references/sale-items.md"},
        )
    )
    assert missing["status"] == "not_in_this_version"
    calc = dispatch(skill, "run_refund_calculator", {"today": "2026-10-20", "items": []})
    assert calc["error"]
    loaded = dispatch(skill, "loadSkill", {"name": "returns-and-refunds"})
    assert "Helps with customer orders" in loaded


def test_install_dir_reads_the_lock_version(tmp_path):
    folder = tmp_path / "returns-and-refunds"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: returns-and-refunds\n"
        "description: Use only when a customer asks to return an item or get money back\n"
        "---\n# Hi\n",
        encoding="utf-8",
    )
    lock = {
        "lockVersion": 1,
        "skills": [{
            "path": "returns-and-refunds",
            "name": "returns-and-refunds",
            "selector": {"label": "production"},
            "version": 1,
        }],
    }
    (tmp_path / "langfuse-skills.lock").write_text(json.dumps(lock), encoding="utf-8")
    skill = load_installed(tmp_path)
    assert skill.version == 1
    assert skill.description().startswith("Use only when")


def test_exact_scores_do_not_need_a_model():
    output = {
        "decision": "approve_full",
        "refund_amount": 29.99,
        "loaded_skill": True,
        "files_read": [],
    }
    expected = {"decision": "approve_full", "refund_amount": 29.99}
    assert decision_correct(output=output, expected_output=expected).value == 1
    assert amount_correct(output=output, expected_output=expected).value == 1
    assert amount_correct(
        output={"refund_amount": None},
        expected_output={"refund_amount": None},
    ).value == 1
    assert amount_correct(
        output={"refund_amount": 28.99},
        expected_output={"refund_amount": 29.99},
    ).value == 0
    meta = {"should_load_skill": True, "needs_reference": "references/sale-items.md"}
    assert skill_load_correct(output=output, metadata=meta).value == 0
    output["files_read"] = ["references/sale-items.md"]
    assert skill_load_correct(output=output, metadata=meta).value == 1
    assert skill_load_correct(
        output={"loaded_skill": True, "files_read": []},
        metadata={"should_load_skill": False},
    ).value == 0
