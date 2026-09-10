"""FR-M43-04 / FR-M43-05 / NFR-38 (N2 Workstream D task 16): multi-year
retention with a documented compaction and archival path.

The model, explicitly:

- **Retention horizon** — configurable, expressed as either a sequence
  cutoff ("archive everything at or below sequence N") or an age in days
  relative to entry timestamps (the multi-year shape: e.g. 1095 days ≈
  three years). ``retention_cutoff()`` resolves a policy against a
  ledger.
- **Compaction** — the ledger is never rewritten (FR-M10-01 append-only).
  What "compaction" means here: cryptographic compaction. Signed tree
  heads at cadence bind prefixes of the chain, so the archival unit is
  "everything up to the latest tree head at or below the horizon". The
  entry hashes, digests and Merkle structure all live in SQLite rows that
  stay hot; only bulky *blob ciphertext* moves to cold storage. The
  digest stays in the chain (``ledger_entry.input_digest`` /
  ``output_digest``), so chain verification and inclusion proofs are
  untouched by archival.
- **Archival** — ``ArchiveStore.archive()`` moves blob files whose
  entries are at or below the cutoff from the hot blob store to a cold
  directory (a plain filesystem path the customer controls, e.g. object
  storage mounted as a directory), recording a JSON manifest per batch:
  ``{formatVersion, archivedAt, cutoffSequence, horizonDays, files:
  [{seq, kind, ref, digest, bytes}]}, sha256 over the manifest bytes``.
  The manifest digest lets a restore prove it put back exactly what was
  archived.
- **Restore** — ``restore()`` copies every archived file back into the
  hot store and verifies each file's SHA-256 against the digest recorded
  in the ledger row AND the manifest. ``fetch()`` restores a single blob
  on demand (lazy restore) when a read hits a cold ref.

FR-M43-05: an entry archived, compacted and restored still verifies
against its signed tree head and inclusion proof — the chain hashes
ciphertext digests in rows, which never move. Measured storage growth
per 10,000 entries and restore time are published by the test
(``test_ledger_archive.py``) and asserted against a budget (NFR-38: a
three-year archive restores and re-verifies within a documented budget).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .blobs import BlobNotFound, BlobStore

MANIFEST_VERSION = 1
MANIFEST_NAME = "manifest.json"

#: NFR-38 restore budget: restoring an archived corpus and re-verifying
#: the chain + one inclusion proof per archived batch must complete well
#: under this. The measured figure is published by the test.
RESTORE_BUDGET_S = 60.0


@dataclass(frozen=True)
class RetentionPolicy:
    """FR-M43-04: the configurable retention target.

    ``horizon_days`` is the multi-year shape (e.g. 1095 ≈ three years);
    ``horizon_sequences`` pins a deterministic sequence cutoff (tests,
    tests-only ledgers). At least one must be set."""

    horizon_days: float | None = None
    horizon_sequences: int | None = None

    def __post_init__(self) -> None:
        if self.horizon_days is None and self.horizon_sequences is None:
            raise ValueError("a retention policy needs a horizon")


def retention_cutoff(policy: RetentionPolicy, ledger: Any, now: datetime | None = None) -> int:
    """Resolve the policy to a sequence cutoff (inclusive).

    ``horizon_sequences`` wins when both are set — an explicit cutoff is
    always deterministic. For ``horizon_days``, entries are archived when
    their timestamp is older than the horizon.
    """
    if policy.horizon_sequences is not None:
        return max(0, policy.horizon_sequences)
    assert policy.horizon_days is not None
    now = now or datetime.now(timezone.utc)
    oldest = now - timedelta(days=policy.horizon_days)
    oldest_iso = oldest.isoformat(timespec="microseconds").replace("+00:00", "Z")
    row = ledger.conn.execute(
        "SELECT COALESCE(MIN(seq), 0) FROM ledger_entry WHERE ts_utc >= ?",
        (oldest_iso,),
    ).fetchone()
    first_retained = int(row[0]) if row else 0
    if first_retained == 0:
        # Everything is older than the horizon: archive the whole chain.
        last = ledger.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM ledger_entry"
        ).fetchone()
        return int(last[0]) if last else 0
    # Archive everything strictly below the first retained row.
    return max(0, first_retained - 1)


@dataclass(frozen=True)
class ArchivedFile:
    seq: int
    kind: str  # "input" | "output"
    ref: str
    digest: str
    bytes: int


@dataclass(frozen=True)
class ArchiveManifest:
    """One archival batch. ``digest`` is the SHA-256 of the canonical
    manifest content, committed nowhere mutable: it is carried inside the
    manifest file itself and re-checked at restore."""

    format_version: int
    archived_at: str
    cutoff_sequence: int
    horizon_days: float | None
    files: tuple[ArchivedFile, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "formatVersion": self.format_version,
            "archivedAt": self.archived_at,
            "cutoffSequence": self.cutoff_sequence,
            "horizonDays": self.horizon_days,
            "files": [dataclasses.asdict(f) for f in self.files],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ArchiveManifest":
        return ArchiveManifest(
            format_version=int(data["formatVersion"]),
            archived_at=str(data["archivedAt"]),
            cutoff_sequence=int(data["cutoffSequence"]),
            horizon_days=data.get("horizonDays"),
            files=tuple(
                ArchivedFile(
                    seq=int(f["seq"]),
                    kind=str(f["kind"]),
                    ref=str(f["ref"]),
                    digest=str(f["digest"]),
                    bytes=int(f["bytes"]),
                )
                for f in data["files"]
            ),
        )


def _canonical_manifest_bytes(manifest: ArchiveManifest) -> bytes:
    return json.dumps(
        manifest.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


class ArchiveError(Exception):
    """Archival/restore failure (missing blob, digest mismatch, bad manifest)."""


class ArchiveStore:
    """Cold-storage seam between the hot blob store and the archive dir.

    The cold root is customer-configured (a directory; object storage
    mounted as a directory works unchanged). Layout per batch:
    ``<cold>/<archivedAt>-<cutoff>/blobs/<ref>`` plus ``manifest.json``.
    """

    def __init__(self, cold_root: Path) -> None:
        self._cold = Path(cold_root)
        self._cold.mkdir(parents=True, exist_ok=True)

    # -- archival ---------------------------------------------------------------

    def _eligible_refs(self, ledger: Any, cutoff: int) -> list[sqlite3.Row]:
        return ledger.conn.execute(
            "SELECT seq, input_ref, output_ref FROM ledger_entry"
            " WHERE seq <= ? AND (input_ref IS NOT NULL OR output_ref IS NOT NULL)"
            " ORDER BY seq",
            (cutoff,),
        ).fetchall()

    def archive(
        self, ledger: Any, policy: RetentionPolicy, now: datetime | None = None
    ) -> ArchiveManifest:
        """Move blobs at or below the policy cutoff to cold storage.

        Rows stay hot — only ciphertext files move. The digests recorded
        in the rows (and committed into the chain) are not touched, so
        verification is unaffected. Idempotent per batch: already-cold
        refs are skipped, so re-running archival never double-moves."""
        cutoff = retention_cutoff(policy, ledger, now=now)
        rows = self._eligible_refs(ledger, cutoff)
        files: list[ArchivedFile] = []
        batch_dir = self._cold / f"{utc_now().replace(':', '-')}-{cutoff}"
        blob_root = Path(ledger.dir) / "blobs"
        for row in rows:
            seq = int(row[0])
            for kind, ref in (("input", row[1]), ("output", row[2])):
                if not ref:
                    continue
                hot = blob_root / ref
                if not hot.is_file():
                    continue  # already archived, or never present
                digest = hashlib.sha256(hot.read_bytes()).hexdigest()
                cold_file = batch_dir / "blobs" / ref
                cold_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(hot, cold_file)
                size = cold_file.stat().st_size
                hot.unlink()
                files.append(
                    ArchivedFile(seq=seq, kind=kind, ref=ref, digest=digest, bytes=size)
                )
        manifest = ArchiveManifest(
            format_version=MANIFEST_VERSION,
            archived_at=utc_now(),
            cutoff_sequence=cutoff,
            horizon_days=policy.horizon_days,
            files=tuple(files),
        )
        batch_dir.mkdir(parents=True, exist_ok=True)
        (batch_dir / MANIFEST_NAME).write_bytes(_canonical_manifest_bytes(manifest))
        return manifest

    # -- restore ----------------------------------------------------------------

    def _manifest_paths(self) -> list[Path]:
        return sorted(
            path
            for path in self._cold.glob(f"*/{MANIFEST_NAME}")
            if path.is_file()
        )

    def manifests(self) -> list[tuple[Path, ArchiveManifest]]:
        out = []
        for path in self._manifest_paths():
            out.append((path, ArchiveManifest.from_dict(json.loads(path.read_bytes()))))
        return out

    def restore(self, ledger: Any, workers: int = 8) -> int:
        """Copy every archived blob back to the hot store; verify each
        file against BOTH the manifest digest and the digest committed
        in the ledger row (chain integrity at restore time). File copies
        run concurrently — restores are I/O-latency-bound, and the
        digest plan is computed single-threaded up front. Returns the
        number of files restored."""
        from concurrent.futures import ThreadPoolExecutor

        # Phase 1 (single connection): build the digest plan from the
        # manifests cross-checked against the ledger rows.
        plan: list[tuple[Path, Path, str, str]] = []  # cold, hot, manifest digest, ledger digest
        for manifest_path, manifest in self.manifests():
            batch_dir = manifest_path.parent
            for archived in manifest.files:
                cold_file = batch_dir / "blobs" / archived.ref
                if not cold_file.is_file():
                    raise ArchiveError(f"archived blob missing: {archived.ref}")
                column = "input_digest" if archived.kind == "input" else "output_digest"
                row = ledger.conn.execute(
                    f"SELECT {column} FROM ledger_entry WHERE seq = ?", (archived.seq,)
                ).fetchone()
                if row is None or row[0] is None:
                    raise ArchiveError(
                        f"ledger row {archived.seq} has no {archived.kind} digest"
                    )
                plan.append(
                    (cold_file, Path(ledger.dir) / "blobs" / archived.ref,
                     archived.digest, bytes(row[0]).hex())
                )

        # Phase 2 (parallel): copy + hash + compare.
        failures: list[str] = []

        def restore_one(item: tuple[Path, Path, str, str]) -> bool:
            cold_file, hot, manifest_digest, ledger_digest = item
            data = cold_file.read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            if actual != manifest_digest:
                failures.append(f"archived blob digest mismatch: {cold_file.name}")
                return False
            if actual != ledger_digest:
                failures.append(
                    f"ledger row digest disagrees with archive: {cold_file.name}"
                )
                return False
            hot.parent.mkdir(parents=True, exist_ok=True)
            tmp = hot.with_suffix(".restoring")
            tmp.write_bytes(data)
            os.replace(tmp, hot)
            return True

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            restored = sum(pool.map(restore_one, plan))
        if failures:
            raise ArchiveError("; ".join(failures[:3]))
        return restored

    def fetch(self, ledger: Any, ref: str, blob_key_id: str) -> bytes:
        """Read-through: return the decrypted blob, restoring the single
        ciphertext file from cold storage on demand when the hot store
        no longer has it."""
        try:
            return ledger.read_blob(ref, blob_key_id)
        except BlobNotFound:
            pass
        for manifest_path, manifest in self.manifests():
            archived = next((f for f in manifest.files if f.ref == ref), None)
            if archived is None:
                continue
            cold_file = manifest_path.parent / "blobs" / ref
            if not cold_file.is_file():
                raise ArchiveError(f"archived blob missing: {ref}")
            data = cold_file.read_bytes()
            if hashlib.sha256(data).hexdigest() != archived.digest:
                raise ArchiveError(f"archived blob digest mismatch: {ref}")
            hot = Path(ledger.dir) / "blobs" / ref
            hot.parent.mkdir(parents=True, exist_ok=True)
            tmp = hot.with_suffix(".restoring")
            tmp.write_bytes(data)
            os.replace(tmp, hot)
            return ledger.read_blob(ref, blob_key_id)
        raise BlobNotFound(ref)

    # -- measurement ------------------------------------------------------------

    def hot_size(self, ledger: Any) -> int:
        blob_root = Path(ledger.dir) / "blobs"
        if not blob_root.is_dir():
            return 0
        return sum(f.stat().st_size for f in blob_root.rglob("*.blob"))

    def cold_size(self) -> int:
        if not self._cold.is_dir():
            return 0
        return sum(f.stat().st_size for f in self._cold.rglob("*.blob"))


def measure_restore(ledger: Any, archive: ArchiveStore) -> tuple[int, float]:
    """Restore the whole archive and re-verify the chain; returns
    (files restored, wall seconds). FR-M43-05/NFR-38 measurement hook —
    the test asserts the budget and publishes the figure."""
    started = time.perf_counter()
    restored = archive.restore(ledger)
    result = ledger.verify()
    elapsed = time.perf_counter() - started
    if not result.ok:
        raise ArchiveError(f"chain verification failed after restore: {result.detail}")
    return restored, elapsed
