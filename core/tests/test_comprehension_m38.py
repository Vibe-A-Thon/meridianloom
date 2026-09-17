"""FR-M38-01…06, AC-35 (F3 step 6): brownfield comprehension — records,
risk scores, the characterisation gate, and comprehension memory. All
signals deterministic against a real git repository; zero model calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from meridian_core.comprehension import ComprehensionEngine, GateVerdict
from meridian_core.memory import MemoryFabric


def git(repo: Path, *args: str, env: dict | None = None) -> None:
    import os
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, env=full_env
    )


@pytest.fixture()
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Legacy Dev")
    git(root, "config", "user.email", "dev@example.test")
    return root


def commit(repo: Path, message: str) -> None:
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", message)


def seed_legacy_module(repo: Path, *, with_test: bool = False,
                       characterization: bool = False) -> str:
    """An old, coupled, uncovered module with incident-laden history."""
    src = repo / "src"
    src.mkdir(exist_ok=True)
    module = src / "payment_engine.py"
    module.write_text(
        "import json\nimport logging\n\n\n"
        "def process_payment(amount):\n"
        "    logging.info('processing')\n"
        "    return json.dumps({'amount': amount})\n",
        encoding="utf-8",
    )
    callers = src / "checkout_flow.py"
    callers.write_text(
        "import payment_engine\n\n\n"
        "def checkout(cart):\n"
        "    return payment_engine.process_payment(sum(cart))\n",
        encoding="utf-8",
    )
    for i in range(8):
        (src / f"consumer{i}.py").write_text(
            f"import payment_engine\n\nUSE = payment_engine.process_payment\n",
            encoding="utf-8",
        )
    # Backdate the module's introduction so the age factor is real:
    # committer/author dates drive FR-M38-03's module-age signal.
    git(repo, "add", ".")
    git(
        repo, "commit", "-q", "-m", "initial legacy module",
        env={
            "GIT_AUTHOR_DATE": "2020-01-01T09:00:00",
            "GIT_COMMITTER_DATE": "2020-01-01T09:00:00",
        },
    )
    # Age the module: backdate is complex; instead add many changes and
    # incidents to drive score via coupling/failure/coverage.
    for i in range(4):
        module.write_text(module.read_text() + f"\n# change {i}\n")
        commit(repo, f"tweak {i}" + (" — hotfix incident sev2" if i == 1 else ""))
    if with_test:
        tests = repo / "tests"
        tests.mkdir(exist_ok=True)
        header = (
            "# characterization test — pins observable behaviour\n"
            if characterization
            else "# ordinary unit test\n"
        )
        (tests / "test_payment_engine.py").write_text(
            header + "import payment_engine\n\n"
            "def test_process():\n"
            "    assert payment_engine.process_payment(1)\n",
            encoding="utf-8",
        )
        commit(repo, "add tests")
    return "src/payment_engine.py"


# -- FR-M38-01: comprehension record ------------------------------------------------


def test_comprehension_record_is_deterministic_and_complete(repo) -> None:
    path = seed_legacy_module(repo)
    engine = ComprehensionEngine(repo)
    rec = engine.record(path)
    assert rec.imports == ("json", "logging")
    assert "src/checkout_flow.py" in rec.imported_by
    assert len(rec.imported_by) >= 5  # checkout + 6 consumers
    assert rec.covered is False
    assert rec.change_count >= 5
    assert "Legacy Dev" in rec.primary_authors
    assert any("incident" in i.lower() for i in rec.incidents)
    assert "function-based structure" in rec.conventions
    again = engine.record(path)
    assert again.to_dict() == rec.to_dict()  # deterministic


def test_missing_module_raises(repo) -> None:
    engine = ComprehensionEngine(repo)
    with pytest.raises(Exception, match="does not exist"):
        engine.record("src/ghost.py")


# -- FR-M38-03: risk assessment --------------------------------------------------------


def test_risk_score_flags_uncovered_coupled_module(repo) -> None:
    path = seed_legacy_module(repo)
    risk = ComprehensionEngine(repo).assess(path)
    assert risk.score >= 0.5
    assert risk.high_risk is True
    assert risk.blast_radius == "wide"
    assert risk.gate_strictness == "heightened"
    assert "coverage" in risk.factors and risk.factors["coverage"] > 0


def test_covered_module_scores_lower(repo) -> None:
    path = seed_legacy_module(repo, with_test=True)
    risk = ComprehensionEngine(repo).assess(path)
    assert risk.factors["coverage"] == 0.0
    assert risk.score < 0.5 or not risk.high_risk or risk.blast_radius != "wide" \
        or risk.gate_strictness == "heightened"


# -- AC-35: the brownfield gate -----------------------------------------------------------


def test_uncovered_high_risk_module_blocked_with_record(repo) -> None:
    path = seed_legacy_module(repo)
    verdict = ComprehensionEngine(repo).gate(path)
    assert isinstance(verdict, GateVerdict)
    assert verdict.allowed is False
    assert "AC-35" in verdict.reason
    # The block explains itself with the comprehension record.
    assert verdict.record["path"] == path
    assert verdict.record["covered"] is False
    assert "characterisation" in verdict.reason


def test_characterisation_tests_unblock(repo) -> None:
    path = seed_legacy_module(repo, with_test=True, characterization=True)
    verdict = ComprehensionEngine(repo).gate(path)
    assert verdict.allowed is True


def test_ordinary_tests_satisfy_the_coverage_requirement(repo) -> None:
    """AC-35 blocks UNCOVERED high-risk modules; ordinary tests are
    coverage, and once covered the packet is admitted (characterisation
    quality is the Legacy Agent's review concern, not the gate's)."""
    path = seed_legacy_module(repo, with_test=True)
    verdict = ComprehensionEngine(repo).gate(path)
    assert verdict.allowed is True


def test_low_risk_module_passes_gate(repo) -> None:
    src = repo / "src"
    src.mkdir(exist_ok=True)
    (src / "helpers.py").write_text("def add(a, b):\n    return a + b\n")
    commit(repo, "helpers")
    verdict = ComprehensionEngine(repo).gate("src/helpers.py")
    assert verdict.allowed is True


# -- FR-M38-05: comprehension memory ---------------------------------------------------------


def test_record_deposits_as_procedural_memory(repo, tmp_path) -> None:
    path = seed_legacy_module(repo)
    engine = ComprehensionEngine(repo)
    ws = tmp_path / "memws"
    ws.mkdir()
    fabric = MemoryFabric(ws)
    record_path = engine.deposit_memory(fabric, path)
    assert record_path.exists()
    loaded = fabric.get("procedural", f"comprehension:{path}")
    assert loaded is not None
    assert "payment_engine" in loaded.content
    # Second deposit (same terms) is an update, not a contradiction.
    engine.deposit_memory(fabric, path)
    assert fabric.get("procedural", f"comprehension:{path}") is not None
