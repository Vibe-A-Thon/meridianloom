# 1. The ledger entry schema

Normative column set of `ledger_entry` (FR-M10-01, Requirements_Final.md
§7.2, plus the v2.1 merge fields, the FR-M35-02/03 observation fields, the
FR-M40-02 `run_id`/`origin` amendment and the FR-M32-02 `simulated` marker).
`seq` is the 1-based, gapless primary key. All timestamps are ISO 8601 UTC
(`...Z`).

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `seq` | INTEGER | no | Sequence number, gapless from 1. Bound into the hash. |
| `ts_utc` | TEXT | no | Entry timestamp, ISO 8601 UTC. |
| `prev_hash` | BLOB (32 B) | no | Previous entry's `entry_hash`; 32 zero bytes for seq 1. |
| `entry_hash` | BLOB (32 B) | no | SHA-256 over the chain link — see §3. |
| `story_id` | TEXT | no | The story the work belongs to. |
| `phase` | TEXT | no | SDLC phase (nine-phase default; configurable per policy). |
| `loop_id` | TEXT | no | Loop instance id (`L2-task` for external tasks, …). |
| `loop_iteration` | INTEGER | no | Iteration within the loop. |
| `actor_id` | TEXT | no | Acting agent or human identity. |
| `actor_version` | TEXT | no | Actor version at capture. |
| `actor_kind` | TEXT | no | `orchestrator`/`role`/`stack`/`sub`/`xai`/`meta`/`external`. |
| `policy_version` | TEXT | no | Policy pack version governing the action. |
| `skill_id` / `skill_version` | TEXT | yes | Skill used, when applicable. |
| `model_id` / `model_version` | TEXT | yes | Model used, when applicable. |
| `action_type` | TEXT | no | `plan`/`prompt`/`tool_call`/`diff`/`test_run`/`review`/`scan`/`gate`/`approval`/`policy_update`/`export`. |
| `input_digest` | BLOB (32 B) | yes | SHA-256 of the **encrypted** input blob (§6). |
| `input_ref` | TEXT | yes | Blob store path, relative to the blob root. |
| `output_digest` | BLOB (32 B) | yes | SHA-256 of the **encrypted** output blob. |
| `output_ref` | TEXT | yes | Blob store path, relative to the blob root. |
| `tool_calls` | TEXT | yes | JSON array, stored as its serialized text (§2.4). |
| `confidence` | REAL | yes | Self-reported, uncalibrated at capture. |
| `decision` | TEXT | yes | `proposed`/`approved`/`rejected`/`reworked`. |
| `human_actor` | TEXT | yes | Approver identity (FR-M12-07: anonymous approval impossible). |
| `human_role` | TEXT | yes | Approver role (v2.1, M20). |
| `rework_reason` | TEXT | yes | Taxonomy reason (E-GR-03) when reworked. |
| `tokens_in` / `tokens_out` | INTEGER | yes | Token counts. |
| `cost_usd` | REAL | yes | Cost in USD (D12: per-workspace currency config). |
| `latency_ms` | INTEGER | yes | Action latency. |
| `signature` | BLOB (64 B) | yes | Optional per-entry Ed25519 signature; hex-projected in the hash payload. |
| `worktree_ref` | TEXT | yes | Worktree identity (FR-M18). |
| `repo_id` | TEXT | yes | Repository identity (M22). |
| `replay_of` | INTEGER | yes | Source `seq` for a replay fork (FR-M4-07). |
| `blob_key_id` | TEXT | yes | Per-subject blob key id, `bk:<subject>` (FR-M10-14). |
| `vendor` | TEXT | no | Agent vendor; `meridian` for native work, else e.g. `claude-code`. |
| `observation_confidence` | TEXT | no | `direct`/`telemetry`/`inferred` (FR-M35-02; `inferred` is the floor). |
| `external_session_id` | TEXT | yes | The vendor session this entry came from, when observed. |
| `run_id` | TEXT | yes | Run identifier (FR-M40-02; first entry of a run). |
| `origin` | TEXT | yes | Run initiation door: `ui`/`command`/`omnibar`/`chat`/`editor`/`file`/`connector`/`api`. |
| `simulated` | INTEGER | no | `0` or `1` — FR-M32-02: Simulation Core entries are marked, never hidden. |

Append-only is a database property (triggers abort UPDATE/DELETE of
`ledger_entry` and `tree_head` from any connection); a conforming store MUST
reject history mutation at the storage layer, not merely by convention. The
sole erasure story is crypto-shredding (§6): blob key rows are destroyed, no
entry is deleted, and the chain still verifies because it hashes ciphertext.
