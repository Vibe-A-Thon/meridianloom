"""Engine result -> bus wire shape for the attrib/* methods.

Field names are camelCase on the wire (generated bus types in
``shared/py/bus_types.py``); the engine uses snake_case dataclasses. This
module is the only translation point, mirroring ``ledger/wire.py``.
"""

from __future__ import annotations

from typing import Any

from . import blame as blame_mod
from . import diff as diff_mod


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
