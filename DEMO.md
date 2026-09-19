# Demonstrating Meridian Loom

A live walkthrough, end to end, on a real repository. Roughly twenty minutes
the first time.

This document is deliberately specific about what Meridian supplies and what
you supply, because the distinction is the product: **Meridian does not
contain an AI.** It governs one you already have. Everything here is real —
real ACP over stdio to a real agent process, a real hash-chained ledger, and
an evidence bundle that verifies with a script that does not import Meridian.

---

## What you need before you start

| Thing | Why | How to check |
| --- | --- | --- |
| VS Code 1.95+ | The host | `code --version` |
| Python 3.11+ | The sidecar (governance, ledger, metrics) | `python --version` |
| Node.js 20+ | Building the extension, and launching agents via `npx` | `node --version` |
| A git repository to open | Meridian records against a workspace | `git status` |
| **An ACP agent, with your own account** | The thing being governed | see below |

That last row is the one people are surprised by. Meridian is a governance
layer: it convenes, briefs, permissions and records somebody else's agent.
Four are shipped as one-click presets:

| Preset | Launches | You provide |
| --- | --- | --- |
| Claude Agent | `npx -y @zed-industries/claude-agent-acp` | An Anthropic account, or `ANTHROPIC_API_KEY` in your environment |
| Gemini CLI | `npx -y @google/gemini-cli --experimental-acp` | `gemini auth`, or `GEMINI_API_KEY` |
| Codex CLI | `npx -y @zed-industries/codex-acp` | Codex CLI authentication |
| Minion Code | `uvx minion-code acp` | Minion Code configuration |

Meridian never asks for a credential, never stores one, and never puts one on
a command line. You authenticate with the agent, in that agent's own way,
before you start.

---

## 1. Build and install

```console
npm ci
npm run build
npm run package
```

That produces a `.vsix` in `dist/`. Install it:

```console
code --install-extension dist/meridian-loom-*.vsix
```

Then open the repository you want to demonstrate against, and **trust the
workspace** when VS Code asks. Meridian does nothing in an untrusted
workspace, by design.

## 2. Open the workbench

Click **Meridian Loom** in the Activity Bar. The workbench opens as an editor
tab — no command, no second click.

> Prefer it docked in the side bar? Set `meridianLoom.surface` to `sidebar`.
> The editor is the default because the workbench is nine SDLC phases, agent
> rosters, ledger tables and metric envelopes, and a 300-pixel rail makes all
> of that look like less than it is.

On first open the workspace is seeded from the shipped library. You should
see, with no setup at all:

- **Agents** — 22. Twelve Role Agents (`vision.md` §2.3): Analyst, Solution
  Architect, Tech Lead, Developer, Frontend, QA Engineer, QA Lead, Reviewer,
  Security, Release, SRE, Scrum Master. Plus ten ready-made **Stack Agents**
  — Java · Spring Boot, Java Full Stack, Python, Go, Node, .NET, React, AWS
  Cloud, Database Migration, API Contract.
- **Skills** — the ten packs of the §2.4 GA catalogue.
- **Instructions** — engineering standards, definition of done, review
  checklist, security baseline.

All marked **Built-in**. They are ordinary records: edit, disable, export or
delete any of them, and a deleted one stays deleted across reloads.

Twenty-two is too many to scan at once, so the roster has a filter: **All**,
**Roles**, **Specialists** and **Added by you**, each with a count. The split
is the product's own definition, not a label — a specialist is any agent with
a skill pack bound — so binding a pack to a plain role moves it from Roles to
Specialists. That is a good moment to show the mechanic live.

## 3. Enable the Governor tier

Settings → `meridian.tiers` → add `governor`.

Running an agent *from* Meridian is a Governor capability, because a run is a
session whose permission decisions get recorded. With only Flight Recorder
enabled you can observe agents you start yourself, but the Run button will
tell you it is blocked. No reinstall and no reload — the tier flip takes
effect immediately.

## 4. Give an agent a runtime

Open **Agents** and pick one — say **Java · Spring Boot Engineer**.

It carries a notice: *No agent runtime bound yet*, with a button for each
shipped preset. Click **Claude Agent**. Meridian sets the command and tells
you what still has to be true: that you need Node.js, and that you
authenticate with Anthropic yourself.

Notice what it did **not** do. It did not install anything, sign you in, or
ask for a key. If you are not authenticated with that agent, the run fails
with that agent's own error — which is the honest outcome.

> **Talking point.** Open the agent's Edit panel. Its skill binding is
> `java-spring-gradle` and nothing else. This agent *is* the Developer role
> plus one pack. Unbind the pack and you have the plain Developer back; bind
> `golang-service` instead and the same agent is a Go engineer. Edit the pack
> and every agent bound to it changes together. That is the §2.4 mechanic,
> and it is the highest-leverage idea in the product: the identity is data,
> not code.

### 4b. Or install one from the registry

The preset route binds an agent you already have. The other route brings one
you do not.

In **Agents → Adapter bay**, press **Browse the registry…**. Note what
happened when you opened the workspace a minute ago: *nothing*. Meridian did
not fetch this in the background, does not phone home, and the index arrives
only because you just asked for it.

Read the panel above the list before installing anything. A listing
establishes that somebody published an entry under that name — it is not a
review, not a security assessment, and not an endorsement, by the registry or
by Meridian.

Each entry says how it launches, and whether that means its identity can be
checked:

- an entry shipping a **platform binary** can be identified by digest;
- an entry that launches through **npx** or **uvx** fetches its package when
  it runs, so what Meridian can digest is the fetcher and not the agent. The
  listing says so *before* you install, not after.

**Install into Learning.** It lands with `read`, `search` and `think` and
nothing else — the same floor an imported agent gets, because a registry
listing buys no privilege — and it is pinned by content digest. Nothing runs
until you bind and activate it.

> **Talking point.** Edit one byte of the installed adapter's `manifest.yaml`
> and reload. It will not load, and the refusal names the digest recorded at
> install and the digest on disk. That is the difference between an integrity
> check and a log line: an operator can tell their own edit from an attack.

## 5. Activate it, and tag its phases

**Activate** moves it out of Learning so it can receive deliverables. Confirm
its SDLC phase tags — the Java engineer ships tagged to **Implementation**.

A Learning agent takes no delivery work and collects reviewable memory notes
instead. That is the default for everything shipped or imported, deliberately.

## 6. Widen the permission floor — only if you want writes

A new agent is on **probation**, and the shipped policy grants probationary
agents `read` and `search` only. If your demo has the agent edit a file, it
will refuse until you say otherwise.

That refusal is worth demonstrating on purpose: ask for an edit first, let it
refuse, then widen the policy **for this workspace** and ask again. Create
`.meridian/policy/acp-permissions.yaml` in the repository you are
demonstrating against:

```yaml
version: 1
adapters:
  '*':
    probation: [read, search, edit, execute]
```

It is read before the shipped default, so it takes effect on the next run
with no reload. Do not edit the copy inside the installed extension — it is
not yours, and the next update replaces it. The workspace file is: it is
versioned and reviewed with the rest of the repository, which is the point.

The refusal is the product working, and it makes the point better than the
success does.

## 6b. Start a governed run — the preflight

This is the shortest way to show what Meridian is for, and it takes a minute.

Open **Launch** in the Loom Bar. (It is not there with only Flight Recorder
enabled — not greyed out, *not there*. That is the tiering working: a tier
you have not bought should look like a product that was never designed around
it.) Or run **Meridian Loom: Start Run** from the Command Palette — same
contract, different door.

Type something small and concrete, and press **Preflight…**.

Nothing has been created yet. What comes back answers four questions and one
more:

- **what** — your intent, echoed back
- **who** — which agent fills which role for this run
- **where** — the repository, the base branch, and the branch and worktree
  that *would* be created. Your working tree is untouched, and the dialog
  says so where the decision is being made rather than in documentation
- **how much** — the estimate and the ceiling. If nobody could price it, it
  says **not estimated** — never `$0.00`
- **where it will stop** — the gates this run must pass

Two things to try before you confirm:

**Press Cancel.** Then check: `git branch --list` shows no `meridian/run_…`
branch, and `.meridian/worktrees/` has nothing new in it. The cancellation
*is* recorded — a run that vanished without a trace would be
indistinguishable from one that never reached preflight — but nothing else
exists. That is not a cleanup path that ran; nothing was created in the first
place, which is why the promise survives a crash.

**Then start one for real.** The notice names who authorised it and at what
assurance: `asserted` for a git identity, which is a claim and not a
verification. A run authorised by a name in `git config` never reads later as
one that was verified.

Every door records which door it was — palette, workbench, chat, API. Open
the **Ledger** and filter by the run id: the first entry carries `run_id` and
`origin`, and it was written *before* the worktree existed.

## 7. Dispatch a deliverable

Go to **Deliverables**, write a brief — something genuinely small, like
*"Add input validation to the order endpoint and a test that fails without
it"* — and **Dispatch**.

Watch **Runs**. You will see the agent convened, the session begin, output
streaming in, and permission prompts as the agent asks to read, edit or
execute. Approve or deny them live. This is real ACP: a real subprocess on
the other end of a real protocol.

## 8. Show the briefing — the part most tools cannot show

Open the run and read its **prompt**. This is the exact text the agent
received, recorded verbatim: the brief, the role, the SDLC phase and its
purpose, the bound instruction documents in precedence order, the bound skill
pack, the connected systems (never their credentials), and any accepted
memory.

It is worth dwelling on. The briefing is composed once, recorded, and sent
unchanged — so the record is the thing that happened, not a reconstruction of
it.

## 8b. Read the pull request before you merge it

**Evidence → Pull request**, and name a PR under gate
(`pr:<repo>#<number>`).

The card answers six things, and one of them is not on anybody else's
dashboard: **the revision actually tested**. A checks-passed badge means the
checks passed on *some* revision. If the branch has moved since, that badge
describes code that is not what you would merge — and the card says so
instead of showing a tick.

The rest: change risk, driven by whether two agents edited the same region;
where attribution runs out; which gates blocked; what it cost; and, in a
sentence at the top, what a human has to do next.

Two things it will not do. It will not show `$0.00` for a cost nobody
recorded, and it will not show an unmeasured risk in the same visual language
as a measured low. And there is no approve button on it — approving is a
governed action bound to your identity, and it happens in the Gate Room.

## 8c. If another provenance tool is already here

Open **Evidence → Audit ledger** and scroll to **Other tools' records**.

If the repository carries git notes from another tool — aider, Continue,
GitButler — Meridian reads them. It does not claim them: each is attributed
to the tool that wrote it and recorded at `inferred`, because Meridian read a
file claiming work happened rather than watching it happen.

Press **Notarise their digests**. Meridian writes the *digest* of each record
into the signed ledger — not the content, because copying it would make
Meridian the custodian of another tool's data.

Now do the demonstration that makes the point. Rewrite one of those notes:

```console
git notes --ref refs/notes/aider add -f -m '{"tool":"aider","model":"something-else"}' HEAD
```

Press **Check for alteration**. Meridian names the record, the digest it had
when it read it, and the digest now.

> **Talking point.** Every tool in this space captures something. None of them
> makes its own capture provable afterwards — a note is a mutable blob, and
> whoever can write the repository can rewrite what it says about last March.
> Meridian is not competing with that record. It is signing it. And it signs
> the digest, not the claim: it did not see the work, and it says so.

## 9. Take the evidence away

**Evidence** → export a bundle. Then verify it with no Meridian involved:

```console
python <extension>/sidecar/verify.py my-bundle.json
```

That verifier is one file of Python standard library only — the Ed25519 check
is a pure-Python RFC 8032 implementation — so an auditor who has never heard
of this tool can check the hash chain, the Merkle inclusion proofs, the
tree-head signature and the bundle signature themselves.

For the strongest version of the demo, tamper first: change one character in
a field of the exported JSON and run the verifier again. It fails, and names
the field.

## 10. Feed it back

Complete the deliverable with feedback. Agents in Learning turn that into
reviewable memory notes on the **Learning** tab. Nothing enters an agent's
briefing until a human accepts it — there is no silent training loop.

---

## What to say about the limits

Demonstrate these rather than hoping nobody asks.

- **There is no AI in here.** Meridian convenes, briefs, gates and records
  somebody else's agent. If that agent is bad, Meridian will faithfully record
  it being bad.
- **A witness is not configured by default.** Signature verification detects a
  changed entry and a broken chain link. It does not, on its own, detect
  wholesale ledger replacement by a machine administrator — a re-signed fork
  still verifies. The verifier says so in its own output rather than letting
  you infer more than it proved.
- **Some measures are unavailable, and say so.** Coverage envelopes report
  `insufficient_evidence` instead of a zero, and truncation disables
  projections. A number that is not measurable is reported as not measurable.
- **Every integration is read-only.** Nothing creates an issue, triggers a
  pipeline, posts a message or restarts a workload.

---

## If something does not work

| Symptom | Cause | Fix |
| --- | --- | --- |
| Run button blocked | Governor tier not enabled | `meridian.tiers` → add `governor` |
| No **Launch** entry in the Loom Bar | Governor tier not enabled — initiation is absent below it, by design | `meridian.tiers` → add `governor` |
| Preflight says a run "cannot start yet" | One of the six answers is unsettled — it names which | Bind an agent runtime (step 4); set an estimate and ceiling |
| "not permitted to start a live run" | The role is read-only in `roles.yaml`; a dry run writes nothing and is allowed, a live run is not | Use a role that is not `readOnly`, or run dry |
| "No agent runtime bound" | Shipped agents ship without a command, deliberately | Click a preset on the agent card |
| Agent starts then exits | Not authenticated with that agent | Authenticate that agent itself, outside Meridian |
| `npx` not found | Node.js missing or not on PATH | Install Node 20+ |
| Agent refuses to edit | Probation floor: `read`, `search` | Create `.meridian/policy/acp-permissions.yaml` in the workspace (step 6) |
| Nothing in the catalogues | Library not packaged | `npm run package` rather than a hand-built VSIX |
| Registry says "could not be reached" | No network, or a proxy | The cached index is used when there is one; otherwise connect and retry |
| Registry says its index "could not be read" | The registry published something malformed | Not your network. Retry later; nothing was installed |
| An adapter stops loading after you edited it | Digest pinning refused it | Reinstall it to re-pin, or restore the file. The refusal names both digests |
| "Other tools' records" is empty | No other provenance tool has written here | The usual case, and not a fault |
| Sidecar will not start | Python not found | Set `meridian.python.interpreterPath` |

Run **Meridian Loom: Doctor** from the Command Palette first — it checks the
interpreter, the sidecar, the workspace and the hooks, and names what is
wrong rather than making you guess.
