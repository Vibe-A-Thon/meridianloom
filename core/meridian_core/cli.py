"""The headless collector and verifier (FR-M43-12, FR-M43-13).

    python -m meridian_core.cli paths     --workspace .
    python -m meridian_core.cli export    --workspace . --out bundle.json
    python -m meridian_core.cli verify    bundle.json
    python -m meridian_core.cli erase     --workspace . --subject <id> --reason request
    python -m meridian_core.cli uninstall --workspace .
    python -m meridian_core.cli evidence-gate --workspace . --study study.json --out gate/
    python -m meridian_core.cli compare-evidence first.json second.json

Everything here works with no extension, no editor and no running sidecar. It
reads and writes the same ``.meridian/`` directory the extension uses, so a
customer can operate their own evidence — in CI, on a server, or on the day
they decide to stop using Meridian — without asking us for anything.

That last case is the one that matters most, and it is why *uninstall* and
*erase* are commands rather than instructions in a document. A tool that can
only be left by hand is a tool you cannot really leave.

**On signing.** Export and erase both append to or sign against the ledger, so
they need its signing key. If none is provided they **refuse** rather than
falling back to a throwaway key: a bundle signed by a key nobody has ever seen
verifies perfectly and proves nothing, which is worse than no bundle at all.
Supply it with ``--signing-key-file`` (32 raw bytes or 64 hex characters) or
``MERIDIAN_LEDGER_SIGNING_KEY`` in the environment.
"""

from __future__ import annotations

import argparse
import binascii
import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .childenv import child_environment
from .ledger import EphemeralSigningKeyProvider, Ledger  # noqa: F401  (re-export shape)
from .ledger import keys as ledger_keys
from .ledger.bundle import build_bundle

#: Everything Meridian writes into a workspace, with what each part is. Used
#: by `paths` and by `uninstall`, from one list, so the thing that tells you
#: what will be deleted cannot drift from the thing that deletes it.
WORKSPACE_ARTEFACTS: tuple[tuple[str, str], ...] = (
    (".meridian/ledger", "the hash-chained ledger, its blobs and signing metadata"),
    (".meridian/workbench", "agents, skills, instructions and run history"),
    (".meridian/policy", "this workspace's permission policy overrides"),
    (".meridian/worktrees", "isolated story worktrees, if any remain"),
    (".meridian/state", "pending commit-trailer records"),
)


class CliError(Exception):
    """A clean, user-actionable failure. Never a traceback."""


# -- shared helpers ------------------------------------------------------------


def _ledger_dir(workspace: Path) -> Path:
    return workspace / ".meridian" / "ledger"


def _signing_key_material(args: argparse.Namespace) -> bytes | None:
    """The raw key bytes a command was given, or None if it was given none.

    Separate from `_signing_provider` because `doctor` needs to *ask* whether
    a key is available without the refusal: a diagnostic that aborts on the
    condition it is reporting cannot report it.
    """
    if getattr(args, "signing_key_file", None):
        return Path(args.signing_key_file).read_bytes().strip()
    from_env = os.environ.get("MERIDIAN_LEDGER_SIGNING_KEY")
    if from_env:
        return from_env.strip().encode()
    return None


def _signing_provider(args: argparse.Namespace) -> Any:
    """The ledger signing key, or a refusal that explains itself."""
    raw = _signing_key_material(args)

    if raw is None:
        raise CliError(
            "no ledger signing key. Pass --signing-key-file, or set "
            "MERIDIAN_LEDGER_SIGNING_KEY.\n"
            "Refusing rather than signing with a throwaway key: a bundle "
            "signed by a key nobody has seen verifies cleanly and proves "
            "nothing, which is worse than no bundle."
        )

    if len(raw) == 64:
        try:
            raw = binascii.unhexlify(raw)
        except binascii.Error as error:
            raise CliError(f"signing key is not valid hex: {error}") from error
    if len(raw) != 32:
        raise CliError(
            f"signing key must be 32 raw bytes or 64 hex characters; got {len(raw)}"
        )
    return ledger_keys.ProvisionedSigningKeyProvider(raw)


def _open_ledger(workspace: Path, provider: Any) -> Ledger:
    directory = _ledger_dir(workspace)
    if not (directory / "ledger.db").is_file():
        raise CliError(
            f"no ledger at {directory}. Point --workspace at the folder you "
            "opened in the editor (the one containing .meridian)."
        )
    return Ledger(directory, provider)


def _reference_verifier() -> Path:
    """`verify.py`, in either the checkout or the installed extension."""
    here = Path(__file__).resolve().parent
    for candidate in (
        # Packaged: meridian_core sits at <extension>/sidecar/meridian_core,
        # so the verifier staged beside it is one level up.
        here.parent / "verify.py",
        # Development checkout: meridian_core is at <repo>/core/meridian_core,
        # so the repository root is two levels up, not three.
        here.parents[1] / "verifier" / "verify.py",
    ):
        if candidate.is_file():
            return candidate
    raise CliError(
        "the reference verifier (verify.py) is not beside this package. "
        "Reinstall the extension, or run from a repository checkout."
    )


# -- commands ------------------------------------------------------------------


def command_paths(args: argparse.Namespace) -> int:
    """What Meridian has written into this workspace, and how big it is."""
    workspace = Path(args.workspace).resolve()
    report: dict[str, Any] = {"workspace": str(workspace), "artefacts": []}
    for relative, description in WORKSPACE_ARTEFACTS:
        path = workspace / relative
        present = path.exists()
        size = 0
        if present and path.is_dir():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        elif present:
            size = path.stat().st_size
        report["artefacts"].append(
            {
                "path": str(path),
                "what": description,
                "present": present,
                "bytes": size,
            }
        )
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0


def command_export(args: argparse.Namespace) -> int:
    """Write a signed bundle, readable without Meridian (FR-M43-13)."""
    workspace = Path(args.workspace).resolve()
    ledger = _open_ledger(workspace, _signing_provider(args))
    try:
        params: dict[str, Any] = {}
        if args.from_sequence is not None:
            params["fromSequence"] = args.from_sequence
        if args.to_sequence is not None:
            params["toSequence"] = args.to_sequence
        if args.story:
            params["storyId"] = args.story
        bundle = build_bundle(ledger, params)
    finally:
        ledger.close()

    out = Path(args.out)
    out.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    entries = len(bundle.get("entries", []))
    sys.stderr.write(
        f"Wrote {entries} entries to {out}.\n"
        f"Schema version {bundle.get('schemaVersion')}; collection profile "
        f"{bundle.get('redaction', {}).get('defaultProfile')}.\n"
        "Verify it with: python -m meridian_core.cli verify "
        f"{out}\n"
    )
    return 0


def command_verify(args: argparse.Namespace) -> int:
    """Run the reference verifier — the same one an outsider would run."""
    verifier = _reference_verifier()
    # Deliberately the shipped standalone script, invoked as a subprocess
    # rather than imported: it is the artefact the claim is about, and running
    # something else here would verify a different program than the one a
    # third party is told to use.
    #
    # env=child_environment() even though verify.py is Meridian's own script
    # and needs no secret: SEC-27's rule is that nothing the sidecar spawns
    # inherits MERIDIAN_* variables, without carving out an exception for
    # code we happen to trust today. `--bundle` here can point anywhere on
    # disk, and the day this command's argument handling grows a way to
    # substitute a different verifier at that path is exactly the day this
    # scrub earns its keep.
    completed = subprocess.run(
        [sys.executable, str(verifier), str(args.bundle)],
        env=child_environment(),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode


def command_doctor(args: argparse.Namespace) -> int:
    """Is this installation actually working? (FR-M30-01, headless.)

    The same check registry the editor's Doctor command runs — imported, not
    reimplemented, because two diagnostics that can disagree about whether an
    installation is healthy are worse than one.

    Exists so a rollout across many machines can be validated in CI, where
    there is no editor to open and nobody watching a panel. Exit status is the
    answer: 0 every check passed, 1 something failed, so it can be the last
    line of a deployment job.
    """
    import time

    from . import doctor as doctor_mod

    workspace = Path(args.workspace).resolve()
    params: dict[str, Any] = {"workspaceDir": str(workspace)}
    if args.check:
        params["checks"] = list(args.check)

    # Only the probes a headless run can honestly answer. The signing key
    # lives in the editor's OS keychain and the ledger is opened per command
    # here, so without a key those probes stay absent rather than reporting a confident
    # wrong answer — the registry's not-installed path says so with
    # remediation, which is the truthful result for this context.
    context = doctor_mod.DoctorContext(started_at=time.time())
    if _signing_key_material(args) is not None:
        # Only claim to know when a key was actually handed to this command.
        # Without one the honest answer is "this context cannot tell you" —
        # the registry's absent-probe path — not "fail". Reporting a failure
        # because an optional flag was omitted would turn every CI doctor run
        # red for a reason that is not a fault.
        context = dataclasses.replace(context, signing_key_present=lambda: True)
        # MV4-T03: with a key in hand the ledger CAN be opened here, so the
        # chain is verified rather than reported as not initialised. Before
        # this, the probe was absent in every headless run, so a rollout check
        # against a workspace whose chain was broken exited 0. The docstring
        # above promises the exit status is the answer; for the one fault that
        # matters most, it was not.
        ledger_dir = _ledger_dir(workspace)
        if (ledger_dir / "ledger.db").is_file():

            def verify_ledger() -> tuple[bool, str]:
                try:
                    ledger = Ledger(
                        ledger_dir, _signing_provider(args), verify_on_open=False
                    )
                except Exception as error:  # noqa: BLE001
                    # A ledger that will not open is a failed ledger check, not
                    # a crashed doctor: the diagnostic must survive the fault
                    # it is diagnosing.
                    return False, f"the ledger could not be opened: {error}"
                try:
                    verdict = ledger.verify()
                finally:
                    ledger.close()
                return verdict.ok, verdict.detail

            context = dataclasses.replace(context, ledger_verifier=verify_ledger)

    try:
        report = doctor_mod.run_doctor(params, context)
    except doctor_mod.UnknownCheckError as error:
        raise CliError(
            f"{error}. Valid checks: {', '.join(doctor_mod.check_ids())}"
        ) from error

    sys.stdout.write(json.dumps(report, indent=2, default=str) + "\n")
    checks = report.get("checks", []) if isinstance(report, dict) else []
    failed = [c for c in checks if isinstance(c, dict) and c.get("status") == "fail"]
    if failed:
        sys.stderr.write(
            f"{len(failed)} of {len(checks)} checks failed: "
            + ", ".join(str(c.get("id")) for c in failed)
            + "\n"
        )
        return 1
    sys.stderr.write(f"All {len(checks)} checks passed.\n")
    return 0


def command_erase(args: argparse.Namespace) -> int:
    """Crypto-shred one subject's content, recorded in the chain."""
    from .ledger import privacy

    workspace = Path(args.workspace).resolve()
    ledger = _open_ledger(workspace, _signing_provider(args))
    try:
        controller = privacy.PrivacyController(ledger)
        controller.erase_subject(args.subject, reason=args.reason, actor=args.actor)
    finally:
        ledger.close()
    sys.stderr.write(
        f"Erased subject {args.subject!r}: its key is destroyed, so its content "
        "is unreadable for good.\n"
        "The entries themselves remain and the chain still verifies — that is "
        "the point of crypto-shredding rather than deletion.\n"
        "A backup taken before now still holds the key; replay this erasure "
        "into any restored copy.\n"
    )
    return 0


def command_uninstall(args: argparse.Namespace) -> int:
    """Say exactly what leaving costs, and do it only when told twice."""
    workspace = Path(args.workspace).resolve()
    present = [
        (workspace / relative, description)
        for relative, description in WORKSPACE_ARTEFACTS
        if (workspace / relative).exists()
    ]
    if not present:
        sys.stderr.write(f"Nothing of Meridian's is in {workspace}.\n")
        return 0

    for path, description in present:
        sys.stderr.write(f"  {path}\n      {description}\n")

    if not args.yes:
        sys.stderr.write(
            "\nNothing has been deleted. Export first if you want to keep the "
            "record:\n"
            f"  python -m meridian_core.cli export --workspace {workspace} "
            "--out bundle.json\n"
            "Then re-run this with --yes.\n"
            "Removing the extension is separate and is done in the editor; "
            "this command only removes what was written into the workspace.\n"
        )
        return 0

    for path, _ in present:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    meridian_dir = workspace / ".meridian"
    if meridian_dir.is_dir() and not any(meridian_dir.iterdir()):
        meridian_dir.rmdir()
    sys.stderr.write(f"Removed {len(present)} item(s) from {workspace}.\n")
    return 0


def _read_json(path: str, what: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise CliError(f"cannot read {what}: {error}") from error
    except ValueError as error:
        raise CliError(f"{what} is not valid JSON: {error}") from error


def command_evidence_gate(args: argparse.Namespace) -> int:
    """Score a study against the thresholds written before it ran (MV5).

    `docs/evidence-gate.md` is the preregistration and `metrics/evidence_gate.py`
    applies it. This command is how a study team uses them with no editor: it
    reads the workspace ledger and the team's study record, then writes the
    three things the gate's exit needs side by side. Those are the computed
    report, the raw ledger slice as a signed bundle, and a draft of the written
    decision carrying both files' digests.

    It writes a *draft*. The decision belongs to a person, so `DECISION.md` is
    never written or overwritten here.
    """
    import hashlib
    from datetime import datetime, timezone

    from .governance import roles as governance_roles
    from .metrics import evidence_decision, evidence_gate, evidence_study

    if args.print_schema:
        sys.stdout.write(json.dumps(evidence_study.STUDY_SCHEMA, indent=2) + "\n")
        return 0
    if args.print_preregistration:
        sys.stdout.write(json.dumps(evidence_gate.preregistration(), indent=2) + "\n")
        return 0
    if not args.study or not args.out:
        raise CliError(
            "--study and --out are required to score a study. Before the first "
            "story, --print-preregistration prints the digest to register."
        )

    record = _read_json(args.study, "the study record")
    problems = evidence_study.validate_study(record)
    if problems:
        shown = "\n  ".join(problems[:20])
        more = f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""
        raise CliError(f"the study record cannot be scored:\n  {shown}{more}")

    workspace = Path(args.workspace).resolve()
    ledger = _open_ledger(workspace, _signing_provider(args))
    try:
        pack = governance_roles.load_role_pack(
            [
                workspace / ".meridian" / "policy" / "roles.yaml",
                workspace / "policy" / "roles.yaml",
            ]
        )

        def assess(subject: str) -> list[str]:
            return governance_roles.assess_hygiene(ledger, pack, subject=subject)

        # A fail-closed pack assesses nothing and returns no warnings. Passing
        # it on would report "assessed, no signals", a clean bill from no check.
        report = evidence_gate.compute_evidence_gate(
            ledger,
            from_sequence=args.from_sequence,
            to_sequence=args.to_sequence,
            study=record,
            hygiene=None if pack.fail_closed else assess,
        )
        params: dict[str, Any] = {}
        if args.from_sequence is not None:
            params["fromSequence"] = args.from_sequence
        if args.to_sequence is not None:
            params["toSequence"] = args.to_sequence
        bundle = build_bundle(ledger, params)
    finally:
        ledger.close()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for name, payload in (
        ("evidence-gate-report.json", report),
        ("ledger-slice.json", bundle),
    ):
        data = (json.dumps(payload, indent=2, default=str) + "\n").encode("utf-8")
        (out / name).write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out / "DECISION-DRAFT.md").write_text(
        evidence_decision.decision_draft(report, digests, generated), encoding="utf-8"
    )

    recommendation = report["recommendation"]
    unmeasured = [m for m, v in report["measures"].items() if v["status"] == "unmeasured"]
    sys.stderr.write(
        f"Outcome under {evidence_gate.PREREGISTRATION_DOCUMENT} section 4: "
        f"{recommendation['verdict']}.\n"
        + (
            "The preregistration is not intact; publish this result as invalidated.\n"
            if recommendation.get("invalidated")
            else ""
        )
        + f"Unmeasured: {', '.join(unmeasured) if unmeasured else 'none'}.\n"
        f"Wrote evidence-gate-report.json, ledger-slice.json and DECISION-DRAFT.md to {out}.\n"
        "The draft is not a decision until a person writes one in it.\n"
    )
    return 0


def command_compare_evidence(args: argparse.Namespace) -> int:
    """Do two bundles verify, and do they carry the same evidence shape? (AC-50)

    AC-50 works the same change in two editors, merges it through two SCM
    providers, and needs both bundles to verify on a clean machine and carry
    the same evidence schema. Both halves are checked here, the first by the
    shipped verifier and the second by `ledger/shape.py`. The exit status is
    the answer: 0 only when both bundles verify and their shapes agree.
    """
    from .ledger.shape import evidence_shape, shape_differences

    verifier = _reference_verifier()
    results: list[dict[str, Any]] = []
    shapes: list[dict[str, Any]] = []
    for path in (args.first, args.second):
        bundle = _read_json(path, f"the bundle {path}")
        if not isinstance(bundle, dict):
            raise CliError(f"{path} is not a bundle: expected a JSON object")
        # The shipped verifier as a subprocess, scrubbed environment, exactly
        # as `verify` runs it (SEC-27).
        completed = subprocess.run(
            [sys.executable, str(verifier), str(path)],
            env=child_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        results.append(
            {
                "path": str(path),
                "verified": completed.returncode == 0,
                "verifierExit": completed.returncode,
                "verifierSaid": (completed.stdout + completed.stderr).strip().splitlines()[-5:],
            }
        )
        shapes.append(evidence_shape(bundle))

    differences = shape_differences(shapes[0], shapes[1])
    report = {
        "bundles": results,
        "sameShape": not differences,
        "differences": differences,
        "shapes": shapes,
    }
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    unverified = [r["path"] for r in results if not r["verified"]]
    if unverified:
        sys.stderr.write(f"Did not verify: {', '.join(unverified)}.\n")
    if differences:
        sys.stderr.write(
            f"The bundles differ in shape in {len(differences)} way(s); see differences.\n"
        )
    if unverified or differences:
        return 1
    sys.stderr.write("Both bundles verify and carry the same evidence shape.\n")
    return 0


# -- argument parsing ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meridian",
        description=(
            "Meridian's headless collector and verifier. Works with no "
            "extension, no editor and no running sidecar."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def with_workspace(command: argparse.ArgumentParser) -> argparse.ArgumentParser:
        command.add_argument(
            "--workspace",
            default=".",
            help="the folder containing .meridian (default: the current one)",
        )
        return command

    def with_key(command: argparse.ArgumentParser) -> argparse.ArgumentParser:
        command.add_argument(
            "--signing-key-file",
            help="32 raw bytes or 64 hex characters; "
            "or set MERIDIAN_LEDGER_SIGNING_KEY",
        )
        return command

    with_workspace(sub.add_parser("paths", help="what Meridian wrote, and where"))

    export = with_key(with_workspace(sub.add_parser("export", help="write a bundle")))
    export.add_argument("--out", required=True, help="file to write")
    export.add_argument("--from-sequence", type=int, help="first entry (inclusive)")
    export.add_argument("--to-sequence", type=int, help="last entry (inclusive)")
    export.add_argument("--story", help="only entries for this story id")

    verify = sub.add_parser("verify", help="verify a bundle with the reference verifier")
    verify.add_argument("bundle", help="the bundle file to verify")

    doctor = with_key(
        with_workspace(
            sub.add_parser("doctor", help="check this installation is working")
        )
    )
    doctor.add_argument(
        "--check",
        action="append",
        help="run only this check; repeatable (default: all)",
    )

    erase = with_key(with_workspace(sub.add_parser("erase", help="crypto-shred a subject")))
    erase.add_argument("--subject", required=True, help="the subject id to erase")
    erase.add_argument("--reason", required=True, help="why, recorded in the chain")
    erase.add_argument("--actor", default="data-controller", help="who asked")

    uninstall = with_workspace(
        sub.add_parser("uninstall", help="list, and with --yes remove, workspace data")
    )
    uninstall.add_argument(
        "--yes", action="store_true", help="actually delete; otherwise only lists"
    )

    gate = with_key(
        with_workspace(
            sub.add_parser(
                "evidence-gate",
                help="score a study against the thresholds written before it ran",
            )
        )
    )
    gate.add_argument("--study", help="the study record (JSON)")
    gate.add_argument(
        "--out", help="folder for the report, the ledger slice and the decision draft"
    )
    gate.add_argument("--from-sequence", type=int, help="first ledger entry of the study")
    gate.add_argument("--to-sequence", type=int, help="last ledger entry of the study")
    gate.add_argument(
        "--print-preregistration",
        action="store_true",
        help="print the thresholds digest a study registers before its first story",
    )
    gate.add_argument(
        "--print-schema", action="store_true", help="print the study record's JSON Schema"
    )

    compare = sub.add_parser(
        "compare-evidence",
        help="verify two bundles and compare their evidence shape (AC-50)",
    )
    compare.add_argument("first", help="the first bundle")
    compare.add_argument("second", help="the second bundle")
    return parser


_COMMANDS = {
    "paths": command_paths,
    "export": command_export,
    "verify": command_verify,
    "doctor": command_doctor,
    "erase": command_erase,
    "uninstall": command_uninstall,
    "evidence-gate": command_evidence_gate,
    "compare-evidence": command_compare_evidence,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except CliError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2
    except (OSError, ValueError) as error:
        # Everything a user can cause reads as a message, never a traceback.
        sys.stderr.write(f"error: {error}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
