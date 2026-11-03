"""Kit config model + loader, and the canonical `target_traces` derivation hook.

The load-and-override mechanism lives in ``langfuse_synth_core.config``. This
module is the kit's shape. Volume defaults to 84 traces, about three tickets a
day across four weeks. The golden gate overrides that down to 24.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from langfuse_synth_core.config import load_config as _load_config
from langfuse_synth_core.derivation import identity_derivation
from langfuse_synth_core.timegen import parse_as_of_date

DEFAULT_TARGET_TRACES = 84


@dataclass
class Target:
    """The Langfuse instance a run points at (the library reads `base_url`).

    `host` is the committed default and `LANGFUSE_BASE_URL` overrides it.
    """

    host: str = "http://localhost:3000"
    project_hint: str = "demo"

    @property
    def base_url(self) -> str:
        return os.environ.get("LANGFUSE_BASE_URL", self.host).rstrip("/")


@dataclass
class Generation:
    seed: int = 42
    target_traces: int = DEFAULT_TARGET_TRACES
    as_of_date: date | None = None


@dataclass
class Config:
    target: Target
    generation: Generation


def _model_factory(raw: dict) -> Config:
    raw = raw or {}
    target = raw.get("target") or {}
    generation = raw.get("generation") or {}
    return Config(
        target=Target(
            host=str(target.get("host", "http://localhost:3000")),
            project_hint=str(target.get("project_hint", "demo")),
        ),
        generation=Generation(
            seed=int(generation.get("seed", 42)),
            target_traces=int(generation.get("target_traces", DEFAULT_TARGET_TRACES)),
            as_of_date=parse_as_of_date(generation.get("as_of_date")),
        ),
    )


def load_config(path: str | Path, overrides: list[str] | None = None) -> Config:
    """Read the YAML config, apply `--set dotted.key=value` overrides, and build `Config`."""
    return _load_config(path, _model_factory, overrides)


DERIVATION_HOOK = identity_derivation
