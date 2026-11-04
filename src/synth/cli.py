"""The kit's `synth` CLI.

Pipeline verbs accept `--config` and repeatable `--set`. `experiment` is the
live comparison and does not take `--set`. `companion` is dispatched before
argparse so the adapter can reject a pipeline override itself.
"""
from __future__ import annotations

import argparse
import sys

from .config import load_config
from .seed import run_seed
from .verify import run_verify


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("skill version must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("skill version must be a positive integer")
    return number


def _add_config_args(parser: argparse.ArgumentParser, *, default: str | None = None) -> None:
    parser.add_argument(
        "--config", required=default is None, default=default, help="kit config YAML"
    )
    parser.add_argument(
        "--set",
        action="append",
        metavar="dotted.key=value",
        help="override a config value (repeatable); applied before validation",
    )


def _cmd_seed(args: argparse.Namespace) -> int:
    cfg = load_config(args.config, overrides=args.set)
    run_seed(cfg, dry_run=args.dry_run)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    cfg = load_config(args.config, overrides=args.set)
    return 0 if run_verify(cfg).ok else 1


def _cmd_skills(args: argparse.Namespace) -> int:
    from .returns_agent.skills_publish import langfuse_client, publish_returns_skills

    cfg = load_config(args.config, overrides=args.set)
    published = publish_returns_skills(langfuse_client(cfg.target.base_url))
    print(
        f"production version {published['production']['version']} "
        f"candidate version {published['candidate']['version']}"
    )
    return 0


def _cmd_dataset(args: argparse.Namespace) -> int:
    from .returns_agent.dataset_publish import publish_golden_dataset
    from .returns_agent.skills_publish import langfuse_client

    cfg = load_config(args.config, overrides=args.set)
    published = publish_golden_dataset(langfuse_client(cfg.target.base_url))
    print(
        f"dataset {published['name']} hash {published['content_hash']} "
        f"version {published['dataset_version']} wrote {published['written']}"
    )
    return 0


def _cmd_experiment(args: argparse.Namespace) -> int:
    from .returns_agent.experiment import run_skill_experiment

    cfg = load_config(args.config, overrides=None)
    run_skill_experiment(
        cfg,
        args.skill_version,
        skill_label=args.skill_label,
        run_name=args.run_name,
        install_dir=args.install_dir,
        lockfile=args.lockfile,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synth", description="Returns Desk synth kit.")
    sub = parser.add_subparsers(dest="command", metavar="<verb>")

    seed = sub.add_parser("seed", help="generate + ingest the backdated demo data")
    _add_config_args(seed)
    seed.add_argument("--dry-run", action="store_true", help="spool only; no network")
    seed.set_defaults(func=_cmd_seed)

    verify = sub.add_parser("verify", help="read the data back and assert the floor checks")
    _add_config_args(verify)
    verify.set_defaults(func=_cmd_verify)

    skills = sub.add_parser(
        "skills-publish", help="publish skill v1 as production and v2 as candidate"
    )
    _add_config_args(skills)
    skills.set_defaults(func=_cmd_skills)

    dataset = sub.add_parser("dataset-publish", help="publish the 16-item golden dataset")
    _add_config_args(dataset)
    dataset.set_defaults(func=_cmd_dataset)

    experiment = sub.add_parser(
        "experiment", help="run the golden set against a production or candidate skill"
    )
    experiment.add_argument("--config", default="config/demo.yaml", help="kit config YAML")
    experiment.add_argument(
        "--skill-label",
        choices=("production", "candidate"),
        default=None,
        help=(
            "load the version wearing this label. "
            "Omit it and a run name containing v2 or candidate selects candidate; "
            "every other run selects production."
        ),
    )
    experiment.add_argument(
        "--skill-version",
        type=_positive_int,
        default=None,
        help="pin this version number when --skill-label is omitted",
    )
    experiment.add_argument("--run-name", default=None)
    experiment.add_argument(
        "--install-dir",
        default=None,
        help="read a langfuse skills install directory instead of the API (not .agents/skills)",
    )
    experiment.add_argument("--lockfile", default=None, help="langfuse-skills.lock path")
    experiment.set_defaults(func=_cmd_experiment)
    return parser


def main(argv: list[str] | None = None) -> int:
    _argv = sys.argv[1:] if argv is None else argv
    if _argv[:1] == ["companion"]:
        from .companion.app import main as companion_main

        return companion_main(_argv[1:])
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
