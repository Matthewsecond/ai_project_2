"""Shared launcher helpers for the test tree.

Convention (see tests/README.md):
  * The test tree mirrors src/jobs_intelligence_ai/ — one test package per module.
  * Each module/tier package has a __main__.py so it can be launched in isolation
    with `python -m tests.<...>`; a parent __main__ runs its children in order.
  * unit_tests/ and integration_tests/ hold pytest files `test_N_name.py`.
  * smoke_tests/ hold pytest files marked `@pytest.mark.smoke` (live OpenAI + MySQL),
    excluded from the default run.

The package is installed editable (`pip install -e .`), so tests import it directly
(`from jobs_intelligence_ai... import ...`). The src/ shim below only matters if a test
is launched via `python -m` from an environment where the package isn't installed.
"""
import runpy
import sys
from pathlib import Path

# Make src/ importable for `python -m` launches when the package isn't installed.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Tier folders, in the order a parent package runs them (fast → slow).
CATEGORY_ORDER = ["unit_tests", "integration_tests", "smoke_tests"]


def run_pytest(folder: Path, argv) -> int:
    """Run the pytest files in `folder`. Extra args pass through to pytest."""
    import pytest

    return pytest.main([str(folder), "-v", *argv])


def run_package(pkg_file: str, pkg_name: str, argv) -> int:
    """Dispatch a module __main__ to its child packages.

    Runs every immediate sub-package that has its own __main__ (tier folders and
    nested module packages), tiers first per CATEGORY_ORDER. Positional names
    select which children to run, e.g. `python -m tests.jobs_intelligence_ai.shared
    unit`; other args are forwarded to each child.
    """
    here = Path(pkg_file).resolve().parent
    children = [d for d in here.iterdir() if d.is_dir() and (d / "__main__.py").exists()]
    names = {d.name for d in children} | {d.name.removesuffix("_tests") for d in children}

    selectors = {a for a in argv if a in names}
    forward = [a for a in argv if a not in selectors]

    def sort_key(d: Path):
        return (CATEGORY_ORDER.index(d.name) if d.name in CATEGORY_ORDER else 99, d.name)

    rc = 0
    saved_argv = sys.argv
    try:
        for child in sorted(children, key=sort_key):
            if selectors and not (child.name in selectors
                                  or child.name.removesuffix("_tests") in selectors):
                continue
            module = f"{pkg_name}.{child.name}"
            print(f"\n########## {module} ##########", flush=True)
            sys.argv = [module, *forward]
            try:
                runpy.run_module(module, run_name="__main__")
            except SystemExit as exc:
                rc = rc or (exc.code or 0)
    finally:
        sys.argv = saved_argv
    return rc
