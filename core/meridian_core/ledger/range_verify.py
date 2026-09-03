"""FR-M10-09 parallel verification: per-range worker process entry point.

Deliberately light imports (stdlib + canonical only) so multiprocessing
spawn children start fast and never touch the cryptography stack.

Each worker opens its own read-only connection and verifies a contiguous
sequence range against the STORED chain: the first row's stored prev_hash
is the range's link-in (the parent checks the boundary linkage between
ranges), then every subsequent row must continue the recomputed chain.
No row data crosses process boundaries — only small result tuples.
"""

from __future__ import annotations

import sqlite3

from .canonical import make_verify_hasher


def verify_range(
    args: tuple[str, int, int],
) -> tuple[bool, int | None, int, bytes]:
    """Verify rows lo..hi inclusive.

    Single-tuple signature so ProcessPoolExecutor.map can dispatch it.
    Returns (ok, first_divergent_sequence, rows_checked, last_computed_hash).
    `first_divergent_sequence` is global (range-absolute), None when ok.
    """
    db_path, lo, hi = args
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        cursor = conn.execute(
            "SELECT * FROM ledger_entry WHERE seq >= ? AND seq <= ? ORDER BY seq",
            (lo, hi),
        )
        columns = [d[0] for d in cursor.description]
        hasher = make_verify_hasher(columns)
        i_seq = columns.index("seq")
        i_prev = columns.index("prev_hash")
        i_hash = columns.index("entry_hash")

        expected_seq = lo
        expected_prev: bytes | None = None
        checked = 0
        last_computed = b""
        for values in cursor:
            if expected_prev is None:
                expected_prev = values[i_prev]
            seq = values[i_seq]
            if seq != expected_seq:
                return False, expected_seq, checked, last_computed
            if values[i_prev] != expected_prev:
                return False, seq, checked, last_computed
            recomputed = hasher(expected_prev, values)
            if recomputed != values[i_hash]:
                return False, seq, checked, last_computed
            expected_prev = recomputed
            expected_seq += 1
            checked += 1
            last_computed = recomputed
        return True, None, checked, last_computed
    finally:
        conn.close()
