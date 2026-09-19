"""No private route into the runtime — FR-M40-01, MV2-T01.

The requirement is not "there is a RunRequest". It is that **no path has a
private route**: every door constructs the contract and goes through the one
entry point. That is a property of the whole package, not of any one call
site, and a property nobody can hold in their head across eight doors and a
year.

So it is a guard, in the same shape as the spawn guard in `test_childenv.py`
— an AST walk rather than a text search, because the text scanners in this
suite had to be narrowed twice after matching prose in docstrings, and a
multi-line call is invisible to a line-based check anyway.

The guard and its own negative control live together: a guard that cannot
fail proves nothing, so it is made to fail once on a planted probe.
"""

from __future__ import annotations

import ast
from pathlib import Path

import meridian_core

PACKAGE = Path(meridian_core.__file__).parent

#: The one entry point. Anything that starts a run goes through it.
ENTRY_POINT = "start_run"

#: Functions that begin real work and must therefore never be reached
#: without a RunRequest having been built and authorised first.
RUNTIME_STARTERS = {
    "start_run",
    "dispatch_run",
}


def _run_starts_without_a_request(root: Path | None = None) -> list[str]:
    """Calls into a runtime starter that do not pass a `request`.

    The contract is positional-or-keyword `request`, so a call that supplies
    neither is a door that built no RunRequest — which is exactly the
    private route FR-M40-01 forbids.

    `root` is a parameter so the negative control can plant its probe in a
    tmp dir. The first version of this guard planted inside the package,
    copying the spawn guard — and that pattern had already made an unrelated
    guard fail with FileNotFoundError under `-n auto`, when one worker walked
    the package while another's probe was being deleted. A test that makes
    another test flaky is not a test anyone can trust.
    """
    base = root or PACKAGE
    offenders: list[str] = []
    for path in base.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else None
            )
            if name not in RUNTIME_STARTERS:
                continue
            passes_request = any(
                keyword.arg == "request" for keyword in node.keywords
            ) or bool(node.args)
            if not passes_request:
                offenders.append(f"{path.relative_to(base)}:{node.lineno}")
    return sorted(offenders)


def test_no_door_reaches_the_runtime_without_a_run_request():
    offenders = _run_starts_without_a_request()
    assert not offenders, (
        "these start a run without passing a RunRequest, which means they "
        "skipped preflight, authority and the origin record: "
        f"{', '.join(offenders)}. FR-M40-01: every initiation path constructs "
        "one RunRequest and invokes one entry point; no path has a private "
        "route into the runtime."
    )


def test_the_guard_actually_detects_a_private_route(tmp_path):
    """A guard that cannot fail proves nothing — so make it fail once.

    Planted in a tmp dir, not in the package: see `_run_starts_without_a_request`.
    """
    (tmp_path / "_planted_initiation_probe.py").write_text(
        "def sneak(runtime):\n    runtime.start_run()\n",
        encoding="utf-8",
    )
    hits = _run_starts_without_a_request(tmp_path)
    assert any("_planted_initiation_probe.py" in hit for hit in hits), (
        "the guard did not notice a call that starts a run with no "
        "RunRequest; it would not have noticed a real one either"
    )


def test_the_entry_point_exists_and_takes_a_request():
    """The guard checks callers. This checks there is something to call.

    Without it the guard would pass vacuously on a package where nobody can
    start a run at all — green for the wrong reason, which is the failure
    mode every check in this repository has had at least once.
    """
    from meridian_core import initiation

    assert hasattr(initiation, "start_run"), (
        "FR-M40-01's single entry point is missing; the guard above would "
        "pass because there is nothing to call, not because nothing bypasses it"
    )
    import inspect

    signature = inspect.signature(initiation.start_run)
    assert "request" in signature.parameters
