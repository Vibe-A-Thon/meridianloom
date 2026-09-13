# Reporting a security problem

**Contact:** open a [private security advisory][advisory] on the repository.
If that is unavailable to you, open a public issue saying only *"security
report, please contact me"* and nothing about the problem itself.

[advisory]: https://github.com/meridianloom/meridian-loom/security/advisories/new

## What we promise, and it is deliberately small

This project is maintained by **one person, part-time**. The response below
is what that can actually sustain. A twenty-four-hour commitment would read
better and would be an unbacked claim with a deadline attached, which is
exactly the kind of statement the rest of this product exists to avoid.

| | Commitment |
| --- | --- |
| Acknowledgement | Within **10 working days** |
| First assessment — is it a vulnerability, and how bad | Within **20 working days** of acknowledgement |
| Fix for a confirmed high-severity issue | Best effort, with a **status update at least every 30 days** until it closes |
| Credit | Named in the release notes if you want to be; anonymous if you prefer |

If a deadline is going to slip, you will be told it is slipping rather than
left waiting. That is the part worth relying on.

## In scope

Anything in this repository that ships in the package:

- the VS Code extension and its webview;
- the Python sidecar, including the ledger, its signing and its verifier;
- the provenance hook, the worktree machinery and the ACP permission gate;
- the shipped agent, skill and instruction library;
- the build and release scripts, and the artefacts they publish.

**Especially in scope**, because the whole product rests on them:

- anything that lets a ledger entry be altered, removed or forged without
  the chain or the signature detecting it;
- anything that lets an agent act outside the permissions the policy granted
  it, or a permission decision go unrecorded;
- anything that lets a credential reach the workspace, an export, a log or a
  child process's environment;
- anything that makes a control **appear** enforced where it is not.

## Out of scope

- **Agents themselves.** Meridian convenes and records somebody else's
  agent. A flaw in Claude Code, Copilot or Gemini belongs to its vendor. If
  Meridian *mis-records* what one of them did, that is in scope.
- **The ACP Registry's contents.** A registry listing is not an endorsement
  (`docs/SECURITY-AND-DATA.md` §7). A malicious published agent is the
  publisher's doing; Meridian failing to pin it, or claiming an identity it
  did not verify, is ours.
- **Findings that require an attacker who already has write access to the
  workspace**, unless the point of the control was to survive exactly that.
  The ledger, the pin index and the notarisation record are all in that
  category and are therefore in scope.
- Missing hardening with no demonstrated impact, and scanner output with no
  reproduction.

## Things we already know and have written down

Please read `docs/SECURITY-AND-DATA.md` §6 first. Several limitations are
deliberate, documented, and not findings:

- **Without a witness, a re-signed fork of the whole ledger still verifies.**
  Signature verification detects an altered entry and a broken link; it does
  not detect wholesale replacement by a machine administrator.
- **The commit trailer is editable.** It is a pointer, not a proof.
- **Identity is asserted, not verified, by default** — a git name and email
  is a claim, and is labelled `asserted` wherever it appears.
- **Enforcement is in the editor, not the SCM** in v1. Every control declares
  where it actually binds.
- **The package is unsigned.** VS Code does not sign sideloaded VSIX files;
  the published `.sha256` proves transit, not authorship.

Reporting one of these back is not wasted — if a document overstates a
guarantee, that *is* a finding, and we would like to know.

## Disclosure posture

Coordinated. We would like to ship a fix before details are public. Given the
timelines above, **90 days** from acknowledgement is a reasonable default and
we will not ask you to wait longer without giving you a reason. If a problem
is being exploited, tell us and publish — do not wait for us.

There is no bounty. There is no budget for one, and saying otherwise would be
the same kind of unbacked promise as an unmeetable SLA.
