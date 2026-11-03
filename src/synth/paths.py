"""Locate the kit root both in a checkout and inside the depot image."""
from __future__ import annotations

from pathlib import Path


def kit_root() -> Path:
    """Directory that contains ``usecase.yaml``.

    An installed copy lives in site-packages, so walking from this file reaches
    the checkout during tests and misses in the image. The image working
    directory is ``/app``, which is where the Dockerfile copies the bundles.
    """
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "usecase.yaml").is_file():
            return candidate
    cwd = Path.cwd()
    if (cwd / "usecase.yaml").is_file():
        return cwd
    return Path("/app")
