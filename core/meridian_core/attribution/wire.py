"""Engine result -> bus wire shape for the attrib/* methods.

Field names are camelCase on the wire (generated bus types in
``shared/py/bus_types.py``); the engine uses snake_case dataclasses. This
module is the only translation point, mirroring ``ledger/wire.py``.

FR-M41-01/02 (N1 Workstream B T10): the provenance answers (blame,
symbol) also carry a per-field ``provenance`` record — source, capture
method, contract version, capture timestamp and one of
observed|inferred|unknown|redacted — built here from
:mod:`attribution.provenance`.
"""

from __future__ import annotations

from typing import Any

from . import blame as blame_mod
from . import diff as diff_mod
from .provenance import ProvenanceField, captured_now


def blame_provenance(repo_path: str, ref: str) -> dict[str, Any]:
    """The FR-M41-01 per-field provenance of an attrib/blame answer.

    Every field is read directly from git (porcelain parse / rev-parse),
    so every field is ``observed`` — this answer surface never infers.
    """
    captured_at = captured_now()
    git_blame = "git blame --porcelain -M -C"
    return {
        "repoPath": ProvenanceField.observed(
            repo_path,
            source="git",
            capture_method="git rev-parse --show-toplevel",
            captured_at=captured_at,
        ).to_dict(),
        "ref": ProvenanceField.observed(
            ref,
            source="rpc params",
            capture_method="caller-supplied ref echo",
            captured_at=captured_at,
        ).to_dict(),
        "lines": ProvenanceField.observed(
            None,
            source="git",
            capture_method=git_blame,
            captured_at=captured_at,
        ).to_dict(),
    }


def symbol_provenance(
    path: str,
    line: int,
    language: str | None,
    symbol: str | None,
) -> dict[str, Any]:
    """The FR-M41-01 per-field provenance of an attrib/symbol answer.

    ``path``/``line`` are the caller's own arguments (observed by echo);
    ``language``/``symbol`` are the symbols engine's verdict — observed
    when resolved, honestly ``unknown`` when the language is unregistered
    or no enclosing definition exists (G3: degradation never overclaims).
    """
    captured_at = captured_now()
    provenance: dict[str, Any] = {
        "path": ProvenanceField.observed(
            path,
            source="rpc params",
            capture_method="worktree-relative path normalisation",
            captured_at=captured_at,
        ).to_dict(),
        "line": ProvenanceField.observed(
            line,
            source="rpc params",
            capture_method="caller-supplied line echo",
            captured_at=captured_at,
        ).to_dict(),
    }
    if language is None:
        provenance["language"] = ProvenanceField.unknown(
            source="symbols engine",
            capture_method="language registry lookup",
            captured_at=captured_at,
        ).to_dict()
    else:
        provenance["language"] = ProvenanceField.observed(
            language,
            source="symbols engine",
            capture_method="language registry lookup",
            captured_at=captured_at,
        ).to_dict()
    if symbol is None:
        provenance["symbol"] = ProvenanceField.unknown(
            source="symbols engine",
            capture_method="tree-sitter enclosing-scope walk",
            captured_at=captured_at,
        ).to_dict()
    else:
        provenance["symbol"] = ProvenanceField.observed(
            symbol,
            source="symbols engine",
            capture_method="tree-sitter enclosing-scope walk",
            captured_at=captured_at,
        ).to_dict()
    return provenance


def blame_lines_to_wire(lines: list[blame_mod.BlameLine]) -> list[dict[str, Any]]:
    return [
        {
            "path": line.path,
            "line": line.line,
            "commit": line.commit,
            "authorName": line.author_name,
            "authorEmail": line.author_email,
            "authorTime": line.author_time,
            "content": line.content,
        }
        for line in lines
    ]


def file_diffs_to_wire(files: list[diff_mod.FileDiff]) -> list[dict[str, Any]]:
    return [
        {
            "path": file.path,
            "oldPath": file.old_path,
            "status": file.status,
            "hunks": [
                {
                    "oldStart": hunk.old_start,
                    "oldCount": hunk.old_count,
                    "newStart": hunk.new_start,
                    "newCount": hunk.new_count,
                    "lines": [
                        {
                            "kind": line.kind,
                            "oldLine": line.old_line,
                            "newLine": line.new_line,
                            "content": line.content,
                            "commit": line.commit,
                            "authorName": line.author_name,
                            "authorEmail": line.author_email,
                            "authorTime": line.author_time,
                        }
                        for line in hunk.lines
                    ],
                }
                for hunk in file.hunks
            ],
        }
        for file in files
    ]
