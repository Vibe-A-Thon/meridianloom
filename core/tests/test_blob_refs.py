"""Where a blob reference is allowed to point.

A blob ref is content-addressed and fully determined: two hex characters of
the digest, a separator, the full digest, ``.blob``. Nothing else is ever
produced. But refs are *read* from two places this process does not control:

* rows in a ledger database, which may have been restored from a backup;
* ``manifest.json`` files in cold storage, which is customer-controlled by
  design — that is the point of FR-M43 receipt storage.

Both were joined onto a root and then written through
``mkdir(parents=True)`` followed by ``write_bytes``. A ref of ``../../../x``
was an arbitrary-file write, and an absolute ref replaced the root outright.
The digest checks around those writes do not help: they constrain the
*content* written, never the path it is written to.

These tests pin the allow-list that closed it, and the portability bug found
alongside it — refs used to be built with ``str(Path.relative_to(...))``,
which emits the local separator, so an archive written on Windows named files
no POSIX machine could find.
"""

from __future__ import annotations

import pytest

from meridian_core.ledger.blobs import BlobRefInvalid, normalise_ref

BACKSLASH = chr(92)
DIGEST = "762c5f1e6b2ad1de68f569c6bceb092afed9f40dcf762577229ea58c3e1a7629"
VALID = f"76/{DIGEST}.blob"


class TestItAcceptsWhatTheStoreIssues:
    def test_the_posix_form_round_trips(self):
        assert normalise_ref(VALID) == VALID

    def test_a_windows_written_archive_is_readable_on_posix(self):
        # The portability half. Older archives carry backslashes because the
        # ref was built from the local separator; refusing them would make
        # every such archive unreadable, and cold storage that only its
        # machine of origin can read is not the receipt store it claims to be.
        assert normalise_ref(f"76{BACKSLASH}{DIGEST}.blob") == VALID


class TestItRefusesEverythingElse:
    """An allow-list, not a hunt for ``..``.

    The set of ways to escape a directory is open-ended — parent traversal,
    absolute paths, drive-relative paths on Windows, UNC roots, NUL
    truncation — while the set of valid refs is exactly one shape. Enumerating
    the escapes means shipping the ones nobody thought of.
    """

    @pytest.mark.parametrize(
        "ref",
        [
            "../../../etc/passwd",
            "/etc/passwd",
            "C:/Windows/System32/x.blob",
            f"76/..{BACKSLASH}..{BACKSLASH}x.blob",
            "76/../../x.blob",
            f"..{BACKSLASH}..{BACKSLASH}x.blob",
            BACKSLASH * 2 + f"server{BACKSLASH}share{BACKSLASH}x.blob",
            "",
            "76/" + "z" * 64 + ".blob",  # right shape, not hex
            f"AB/{DIGEST}.blob",  # uppercase prefix is not what put() emits
            f"76/76/{DIGEST}.blob",  # an extra segment
            f"{VALID}/..",
            f"{VALID}\x00.txt",  # NUL truncation
            f"{DIGEST}.blob",  # no prefix directory
            f"76/{DIGEST}",  # no suffix
        ],
    )
    def test_it_is_not_a_blob_reference(self, ref):
        with pytest.raises(BlobRefInvalid):
            normalise_ref(ref)

    def test_the_error_names_what_was_rejected(self):
        # An operator seeing this in a log needs the offending value, because
        # the interesting case is a manifest somebody wrote by hand.
        with pytest.raises(BlobRefInvalid) as caught:
            normalise_ref("../../../etc/passwd")
        assert "../../../etc/passwd" in str(caught.value)


def test_no_call_site_joins_an_unvalidated_ref_onto_a_root():
    """The assertion that keeps the fix from eroding.

    Adding ``root / ref`` somewhere reintroduces exactly the write primitive
    this closed, and nothing would notice until a crafted manifest wrote
    outside a ledger directory.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "meridian_core"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path.name == "blobs.py":
            continue  # where normalise_ref is defined and applied
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # The shape of a pathlib join: a slash, whitespace, then the name.
            # Narrowed twice, both times because prose tripped it — first the
            # substring "/ ref" matched "generative / executed / refused", then
            # a word boundary still matched "repoPath/ref/since", a git ref in
            # a docstring. Requiring whitespace after the slash separates the
            # expression `blob_root / ref` from both. A guard that cries wolf
            # gets deleted rather than fixed, so it is worth narrowing.
            if re.search(r"/\s+(?:archived\.)?ref\b", stripped) and (
                "normalise_ref" not in stripped
            ):
                offenders.append(f"{path.relative_to(root)}:{number}")
    assert not offenders, (
        "these join a blob reference onto a path without validating it, so a "
        "crafted ledger row or archive manifest can steer the write outside "
        f"the ledger directory: {', '.join(sorted(set(offenders)))}. "
        "Use meridian_core.ledger.blobs.normalise_ref."
    )


# -- cold storage is untrusted input, and so is its manifest -------------------


class TestTheArchiveManifestIsUntrustedInput:
    """Cold storage is customer-controlled by design (FR-M43 receipts).

    Everything read back from it is input, including the manifest that says
    what is in it.
    """

    def _store(self, tmp_path, manifest_text: str):
        from meridian_core.ledger.archive import ArchiveStore, MANIFEST_NAME

        batch = tmp_path / "cold" / "2026-01-01T00-00-00Z-1"
        batch.mkdir(parents=True)
        (batch / MANIFEST_NAME).write_text(manifest_text, encoding="utf-8")
        return ArchiveStore(tmp_path / "cold")

    def test_an_oversized_manifest_is_refused_unread(self, tmp_path, monkeypatch):
        from meridian_core.ledger import archive as archive_mod

        # Shrunk rather than writing 64 MiB of JSON: the assertion is that the
        # size is checked *before* the read, which the limit value does not
        # change.
        monkeypatch.setattr(archive_mod, "MAX_MANIFEST_BYTES", 32)
        store = self._store(tmp_path, '{"formatVersion": 1, "files": []}' + " " * 64)
        with pytest.raises(archive_mod.ArchiveError, match="too large"):
            store.manifests()

    def test_a_corrupt_manifest_names_the_file(self, tmp_path):
        from meridian_core.ledger.archive import ArchiveError

        store = self._store(tmp_path, "{not json at all")
        with pytest.raises(ArchiveError) as caught:
            store.manifests()
        # Without the path an operator has a hundred batches and no clue.
        assert "manifest.json" in str(caught.value)

    def test_a_manifest_missing_its_fields_is_an_archive_error(self, tmp_path):
        from meridian_core.ledger.archive import ArchiveError

        # Valid JSON, wrong shape: this used to escape as a bare KeyError.
        store = self._store(tmp_path, '{"formatVersion": 1}')
        with pytest.raises(ArchiveError, match="unreadable"):
            store.manifests()
