#!/usr/bin/env python3
"""Install hermes-agent core dependencies that this interpreter is missing.

hermes-agent's pyproject.toml declares every core dependency with the marker
``python_version >= '3.14'``. The Docker image runs an older Python, so
``uv pip install -e .[all]`` skips all of them, and every package the agent
added after the venv was first built is absent (snowballstemmer broke tool
rounds; rich, prompt_toolkit and fire stop the ``hermes`` CLI from starting).

This reads the agent's own ``[project].dependencies``, evaluates each marker
as if the interpreter were 3.14 (so the version gate passes while platform
conditions still apply), and prints the exact ``name==version`` pins whose
distribution is not installed. Packages already present are left alone.

Usage: ensure_agent_core_deps.py PYPROJECT  -> prints missing pins, one per line
"""

from __future__ import annotations

import re
import sys
from importlib import metadata

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None

try:
    from packaging.requirements import Requirement
except ModuleNotFoundError:  # pip vendors packaging
    from pip._vendor.packaging.requirements import Requirement  # type: ignore

_ENV_314 = {"python_version": "3.14", "python_full_version": "3.14.0"}


def core_dependencies(pyproject_text: str) -> list[str]:
    if tomllib is not None:
        return list(tomllib.loads(pyproject_text).get("project", {}).get("dependencies", []))
    block = pyproject_text.split("\ndependencies = [", 1)[1].split("\n]", 1)[0]
    return re.findall(r'^\s*"([^"]+)"', block, re.M)


def missing_pins(dependencies: list[str]) -> list[str]:
    pins = []
    for spec in dependencies:
        try:
            req = Requirement(spec)
        except Exception:
            continue
        # evaluate() fills the rest of the environment (platform, implementation) from this machine.
        if req.marker is not None and not req.marker.evaluate(_ENV_314):
            continue
        try:
            metadata.distribution(req.name)
            continue
        except metadata.PackageNotFoundError:
            pass
        extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
        pins.append(f"{req.name}{extras}{req.specifier}")
    return pins


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        for pin in missing_pins(core_dependencies(fh.read())):
            print(pin)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
