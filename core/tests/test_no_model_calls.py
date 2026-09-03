"""Zero-model-call assertion (FR-M36-07; F0 Workstream C task 16).

Flight Recorder runs with zero model calls and zero model credentials. This
test scans every Python module reachable from core/meridian_core for
model-client patterns and FAILS on any hit:

* provider imports: openai / anthropic / vertexai / boto3 (Bedrock) /
  botocore / azure
* client call shapes: ``chat.completions``, ``completion(``
* credential reads: ``MERIDIAN_MODEL_API_KEY``

Allow-list convention (there are NO F0 justifications today): a hit is
permitted only when the same line carries a comment naming the FR that
justifies it, e.g.

    client = openai.OpenAI()  # zero-model-calls: allowlisted for FR-M33-09

The scanner also runs against a synthetic violating tree (positive control)
so this test cannot silently pass with a broken pattern list.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = CORE_ROOT / "meridian_core"

_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+"
    r"(openai|anthropic|vertexai|google\.cloud\.aiplatform|boto3|botocore|azure)"
    r"(?:\s|\.)",
    re.MULTILINE,
)
_CALL_RE = re.compile(r"chat\.completions|\bcompletion\(")
_CREDENTIAL_RE = re.compile(r"MERIDIAN_MODEL_API_KEY")
# Allow-list: a comment on the same line must name the justifying FR.
_ALLOW_RE = re.compile(r"#.*allow.*FR-[A-Z0-9]+-\d+", re.IGNORECASE)


def _line_starts(text: str) -> list[int]:
    """Byte offsets of line starts, for offset -> line-number mapping."""
    starts = [0]
    for match in re.finditer(r"\n", text):
        starts.append(match.end())
    return starts


def _line_number(starts: list[int], offset: int) -> int:
    # Binary search without importing bisect in the assertion path clarity.
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1  # 1-based


def find_violations(root: Path) -> list[str]:
    """Every model-client pattern hit under ``root``, allow-list applied."""
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        starts = _line_starts(text)
        lines = text.splitlines()
        for pattern in (_IMPORT_RE, _CALL_RE, _CREDENTIAL_RE):
            for match in pattern.finditer(text):
                line_no = _line_number(starts, match.start())
                line = lines[line_no - 1]
                if _ALLOW_RE.search(line):
                    continue
                violations.append(f"{path.relative_to(root)}:{line_no}: {line.strip()}")
    return violations


class TestFlightRecorderHasZeroModelCalls:
    def test_meridian_core_package_is_clean(self):
        violations = find_violations(PACKAGE_ROOT)
        assert violations == [], (
            "FR-M36-07 violated — model-client patterns found:\n"
            + "\n".join(violations)
        )

    def test_every_module_is_reachable_and_scanned(self):
        # Guard against a future packaging move silently shrinking the scan.
        modules = sorted(PACKAGE_ROOT.rglob("*.py"))
        assert len(modules) >= 20, f"expected the full package, found {len(modules)}"
        assert (PACKAGE_ROOT / "attribution" / "heuristics.py") in modules


class TestScannerPositiveControl:
    """Prove the assertion can actually fail (a broken pattern list must not
    pass silently)."""

    def _write(self, tmp_path: Path, content: str) -> Path:
        target = tmp_path / "fake_core"
        target.mkdir()
        (target / "agent.py").write_text(content, encoding="utf-8")
        return target

    @pytest.mark.parametrize(
        "snippet",
        [
            "import openai\n",
            "from anthropic import Anthropic\n",
            "import vertexai\n",
            "import boto3\nclient = boto3.client('bedrock-runtime')\n",
            "from azure.ai.inference import ChatCompletionsClient\n",
            "response = client.chat.completions.create()\n",
            "text = model.completion(prompt)\n",
            "key = os.environ['MERIDIAN_MODEL_API_KEY']\n",
        ],
    )
    def test_violation_detected(self, tmp_path, snippet):
        root = self._write(tmp_path, snippet)
        violations = find_violations(root)
        assert len(violations) == 1, violations
        assert "agent.py:1" in violations[0]

    def test_allowlisted_line_passes_with_fr_name(self, tmp_path):
        root = self._write(
            tmp_path,
            "client = openai.OpenAI()  # zero-model-calls: allowlisted for FR-M33-09\n",
        )
        assert find_violations(root) == []

    def test_bare_allow_comment_without_fr_fails(self, tmp_path):
        root = self._write(tmp_path, "import openai  # allow\n")
        assert len(find_violations(root)) == 1

    def test_clean_tree_has_no_violations(self, tmp_path):
        root = self._write(tmp_path, "import json\nprint('hi')\n")
        assert find_violations(root) == []
