import { useState } from 'react';
import { Icon } from './Icon';
import s from './workbench.module.css';
import form from './studio.module.css';

/** Explicit coverage, not a promise that a navigation target implements an entire specification. */
export const SURFACE_COVERAGE: Array<[number, string, string | null, string]> = [
  [1, 'Command Center', 'overview', 'Live roster, deliverables, learning counts, and evidence entry points. Cost forecasts and global orchestration remain pending.'],
  [2, 'The Loom Floor', 'agents', 'Agent cards expose participation and actual run state. Spatial floor rendering remains pending.'],
  [3, 'The Weave', 'flight-recorder', 'Existing evidence weave plus the delivery board. Full story and loop visualization remains pending.'],
  [4, 'Agents Watch', 'agents', 'Searchable roster, independent agent details, participation controls, and run history.'],
  [5, 'Agents Dojo', 'learning', 'Inactive agents show Learning; human feedback creates reviewable memory notes. Model training and evaluations remain pending.'],
  [6, 'Gate Room', null, 'Policy gate services exist; a complete approval inbox and gate configuration interface remain pending.'],
  [7, 'Ledger / Selvage Viewer', 'ledger', 'Recorded entries, chain verification, provenance inspection, and signed bundle export.'],
  [8, 'CodeMap Viewer', 'flight-recorder', 'Any-line attribution and symbol lookup are available. Graph exploration remains pending.'],
  [9, 'Loop Graph Viewer', null, 'Canonical loop visualization and orchestration services remain pending.'],
  [10, 'Architecture & C4 Viewer', null, 'Architecture graph extraction, editing, and validation remain pending.'],
  [11, 'UML Studio', null, 'Modeling, code links, synchronization, and diagram export remain pending.'],
  [12, 'Flow Diagram Viewer', null, 'Flow generation, editing, and execution overlays remain pending.'],
  [13, 'Config Portal', 'settings', 'Seven theme choices, density, workspace state, and native extension settings. Full policy/model configuration remains pending.'],
  [14, 'Skill Forge', 'agents', 'Per-agent instructions can be edited. Versioned skill packages and evaluation tooling remain pending.'],
  [15, 'Onboarding Wizard', 'agents', 'Validated agent creation and portable import. Automated probation evaluations remain pending.'],
  [16, 'Agent Inspector', 'agents', 'Identity, mode, instructions, permissions, runtime configuration, independent tasks, and results.'],
  [17, 'Diff Theater', 'external-agents', 'Existing attributed diffs. Hunk acceptance and merge-conflict editing remain pending.'],
  [18, 'Spec Studio', 'deliverables', 'Editable delivery briefs and acceptance criteria. Formal requirement extraction and trace matrices remain pending.'],
  [19, 'Work Packet Board', 'deliverables', 'Draft, dispatch, sequential active roster, review, completion, and failed-run inspection. Full packet orchestration remains pending.'],
  [20, 'Verification Board', 'ledger', 'Cryptographic evidence verification is available. Product test evidence and acceptance gates remain separate, pending UI work.'],
  [21, 'Security Assurance', 'runtime', 'Workspace trust, execution readiness, and diagnostic signals. Vulnerability triage and attestation workflows remain pending.'],
  [22, 'KPI Observatory', 'overview', 'Actual roster, delivery, review, and learning counts. Quality, latency, spend, and calibrated trust metrics remain pending.'],
  [23, 'Exchange', 'agents', 'Portable profile and reviewed-memory export/import; signed evidence export through the ledger. Full organisation exchange remains pending.'],
  [24, 'Focus Mode', 'settings', 'Focus toggle in the top bar and keyboard shortcut; restored with the panel.'],
  [25, 'Story Hub', 'deliverables', 'Local delivery briefs and status board. External story synchronization and full story lifecycle remain pending.'],
  [26, 'Portfolio', null, 'Cross-project portfolio and multi-tenant controls remain pending.'],
  [27, 'Decision Stream', 'ledger', 'Recorded evidence and workbench activity are inspectable. Unified typed decision stream remains pending.'],
  [28, 'Steer & Clarify', null, 'Live task steering, checkpoints, and clarification replies remain pending.'],
  [29, 'Replay & Time-Travel', null, 'Deterministic replay and historical workspace views remain pending.'],
  [30, 'Memory Studio', 'learning', 'Source-linked memory review, accept/dismiss, portability, and next-task context. Retrieval tuning and broader memory stores remain pending.'],
  [31, 'Model Routing Observatory', null, 'Routing rules, cost allocation, fallbacks, and evaluation-driven selection remain pending.'],
  [32, 'Human Roles & Approvals', null, 'Native tool permission prompts remain in place. Organisation role administration and approval queues remain pending.'],
  [33, 'Connectors & Write-back', null, 'External connector setup, synchronization, and write-back previews remain pending.'],
  [34, 'Delivery Pipeline', null, 'CI evidence, protected-branch merge, promotion, and release workflows remain pending.'],
  [35, 'Repositories & Worktrees', 'runtime', 'Open workspace and execution readiness are visible. Worktree services exist separately; workbench runs are sequential in the open workspace.'],
  [36, 'Documentation & Journey Report', 'ledger', 'Portable signed evidence export is available. Narrative journey report generation remains pending.'],
  [37, 'Calibration & Trust', 'external-agents', 'Observation sources and confidence are retained. Model calibration and trust analytics UI remain pending.'],
  [38, 'Runtime & Operations', 'runtime', 'Live health, execution readiness, diagnostics, and stop controls for workbench-owned tasks.'],
  [39, 'Notification Center', 'overview', 'The top-bar activity panel shows run history, errors, and pending learning reviews.'],
  [40, 'First-Run & Guided Setup', 'setup', 'Persistent, explicitly opened recorder setup: connect, observe, inspect, and export.'],
  [41, 'Keyboard Map & Help', 'settings', 'Searchable command palette, shortcut reference, keyboard dialogs, and evidence tab navigation.'],
  [42, 'Editor-Resident Surfaces', null, 'Inline annotations, lenses, and persistent editor inspectors remain pending.'],
  [43, 'Adapter Bay', 'agents', 'Portable ACP launch profiles and independent execution. Registry browsing, installation, and automated graduation remain pending.'],
  [44, 'Instruction Library', 'agents', 'Editable, portable per-agent instructions. Shared versioned instruction packages remain pending.'],
  [45, 'Flight Recorder', 'flight-recorder', 'Existing real observer, weave, any-line attribution, and export surfaces retained.'],
  [46, 'External Agents', 'external-agents', 'Existing live session and observer-health view with vendor and observation confidence.'],
  [47, 'Trust Observatory', null, 'Rejection-measurement services exist; a full trust dashboard remains pending.'],
  [48, 'Comprehension Studio', null, 'Code comprehension, ownership, and handover workflows remain pending.'],
  [49, 'Cross-Vendor Spend', null, 'Provider billing inputs, estimates, allocations, and budgets remain pending.'],
  [50, 'Unlock', 'settings', 'Tier configuration is available through native extension settings; readiness explains prerequisites.'],
  [51, 'Launch', 'deliverables', 'Brief creation, active-roster preview, explicit dispatch, run inspection, and human completion. Full M40 preflight and isolated execution remain pending.'],
];

export function GuideStudio({ onNavigate }: { onNavigate: (route: string) => void }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const shown = SURFACE_COVERAGE.filter(([id, label, route, detail]) => `${id} ${label} ${detail}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || (filter === 'connected' ? route !== null : route === null)));
  return <div className={s.page}><header className={s.pageHeading}><div><p className={s.eyebrow}>SYSTEM / WORKSPACE GUIDE</p><h1>Find the thread you need.</h1><p>Every specified surface has a place here, with its current implementation scope stated explicitly.</p></div></header><div className={s.warning}>This workbench extends the existing recorder. Connected views may cover part of a larger specification; pending capabilities do not execute or display fabricated results.</div><div className={form.toolbar}><label className={form.search}><Icon name="search" size={15} /><input aria-label="Search capability coverage" value={query} onChange={event => setQuery(event.target.value)} placeholder="Find a feature or specification…" /></label><select className={s.select} aria-label="Coverage filter" value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All 51 surfaces</option><option value="connected">Connected entry points</option><option value="pending">Pending interfaces</option></select></div><section className={s.panel} aria-label="Specification coverage">{shown.map(([id, label, route, detail]) => <div className={s.checkRow} key={id}><span className={s.statusBadge}>10.{id}</span><div><strong>{label}</strong><p>{detail}</p></div>{route ? <button className={s.textButton} onClick={() => onNavigate(route)}>Explore <Icon name="arrow" size={14} /></button> : <span className={s.statusBadge}>Pending</span>}</div>)}{shown.length === 0 && <div className={s.empty}><p>No surfaces match this search.</p></div>}</section></div>;
}
