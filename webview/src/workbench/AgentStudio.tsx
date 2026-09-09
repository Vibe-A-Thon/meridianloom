import { useEffect, useState, type FormEvent } from 'react';
import type {
  WorkbenchAgent,
  WorkbenchAgentInput,
  AgentPermission,
} from '../../../shared/ts/workbench';
import type { WorkbenchController } from './useWorkbench';
import { Dialog } from './Dialog';
import { Icon } from './Icon';
import { getVsCodeApi } from '../host/vscode-api';
import s from './studio.module.css';

const EMPTY: WorkbenchAgentInput = {
  id: '',
  name: '',
  role: 'Developer',
  description: '',
  vendor: '',
  version: '1.0.0',
  command: '',
  args: [],
  instructions: '',
  permissions: ['read', 'search', 'think'],
  trainable: ['memory'],
  phases: [],
  skillIds: [],
  instructionIds: [],
  integrationIds: [],
};
const PERMISSIONS: AgentPermission[] = [
  'read',
  'search',
  'think',
  'edit',
  'execute',
  'delete',
  'move',
  'other',
  'unknown',
];
export function AgentStudio({
  controller,
  onNavigate,
  initialSelection,
}: {
  controller: WorkbenchController;
  onNavigate?: (route: string) => void;
  initialSelection?: string;
}) {
  const { snapshot, busy, execute } = controller;
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<WorkbenchAgentInput | null>(null);
  const [isNew, setIsNew] = useState(true);
  const [selectedId, setSelectedId] = useState<string>();
  const [removing, setRemoving] = useState<WorkbenchAgent>();
  const [importing, setImporting] = useState(false);
  const [importText, setImportText] = useState('');
  const [prompt, setPrompt] = useState('');
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const agents = snapshot?.agents ?? [];
  const selected = agents.find((agent) => agent.id === selectedId);
  const shown = agents.filter(
    (agent) =>
      (filter === 'all' || agent.mode === filter) &&
      `${agent.name} ${agent.role} ${agent.vendor} ${agent.id}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const perform = async (task: () => Promise<unknown>, done?: () => void) => {
    setError(undefined);
    setNotice(undefined);
    try {
      await task();
      done?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };
  const add = () => {
    setIsNew(true);
    setEditing({ ...EMPTY, args: [], permissions: [...EMPTY.permissions], trainable: ['memory'] });
    setError(undefined);
  };
  useEffect(() => {
    if (initialSelection === 'new') add();
    else if (initialSelection === 'import') setImporting(true);
    else if (initialSelection) setSelectedId(initialSelection);
  }, [initialSelection]);
  return (
    <div className={s.studio}>
      <header className={s.pageHeader}>
        <div>
          <span className={s.eyebrow}>WORKSPACE / AGENT STUDIO</span>
          <h1>A team with its own character.</h1>
          <p className={s.subtitle}>
            Portable by design. Give each agent a role, a launch configuration, and a place in your
            workflow.
          </p>
        </div>
        <div className={s.headerActions}>
          <button
            className={s.button}
            onClick={() => {
              setImporting(true);
              setError(undefined);
            }}
          >
            Import agent
          </button>
          <button
            className={s.primaryButton}
            onClick={add}
            disabled={!snapshot?.capabilities.workspaceOpen}
          >
            <Icon name="plus" size={15} /> Add agent
          </button>
        </div>
      </header>
      <section className={s.stats} aria-label="Agent statistics">
        {[
          ['Total agents', snapshot ? agents.length : '—', 'Independent, portable configurations'],
          [
            'Active',
            snapshot ? agents.filter((a) => a.mode === 'active').length : '—',
            'Included in the next deliverable',
          ],
          [
            'Learning',
            snapshot ? agents.filter((a) => a.mode === 'learning').length : '—',
            'Excluded from delivery work',
          ],
          [
            'Running',
            snapshot ? agents.filter((a) => a.runtime === 'running').length : '—',
            'Actual ACP sessions in progress',
          ],
        ].map(([label, value, hint]) => (
          <div className={s.stat} key={label}>
            <span className={s.statLabel}>{label}</span>
            <strong className={s.statValue}>{value}</strong>
            <span className={s.statHint}>{hint}</span>
          </div>
        ))}
      </section>
      {error && !editing && !importing && !selected && !removing && (
        <p className={s.error} role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className={s.notice} role="status">
          {notice}
        </p>
      )}
      <div className={s.toolbar}>
        <div className={s.filters} aria-label="Filter agents">
          {['all', 'active', 'learning'].map((value) => (
            <button
              key={value}
              className={s.filter}
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {value === 'all' ? 'All agents' : value === 'active' ? 'Active' : 'Learning'}
              <span className={s.filterCount}>
                {agents.filter((agent) => value === 'all' || agent.mode === value).length}
              </span>
            </button>
          ))}
        </div>
        <label className={s.search}>
          <Icon name="search" size={15} />
          <input
            aria-label="Search agents"
            placeholder="Search name, role, or vendor…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
      </div>
      <div className={s.grid}>
        {shown.map((agent) => (
          <article className={s.card} key={agent.id}>
            <div className={s.cardTop}>
              <span className={s.avatar} data-mode={agent.mode}>
                {agent.name.slice(0, 2).toUpperCase()}
              </span>
              <span className={s.badge} data-mode={agent.mode}>
                {agent.mode === 'learning'
                  ? 'Learning'
                  : agent.runtime === 'running'
                    ? 'Running'
                    : 'Active'}
              </span>
            </div>
            <div className={s.cardTitle}>
              <h2>{agent.name}</h2>
              <span className={s.version}>v{agent.version}</span>
            </div>
            <p className={s.role}>
              {agent.role} · {agent.vendor || 'Custom agent'}
            </p>
            <p className={s.description}>
              {agent.description ||
                'An independent agent with its own instructions and launch configuration.'}
            </p>
            <div className={s.tags}>
              <span className={s.tag}>ACP</span>
              <span className={s.tag}>Portable</span>
              <span className={s.tag}>{agent.permissions.length} declared permissions</span>
            </div>
            <div className={s.cardFoot}>
              <div className={s.modeNote}>
                <span>
                  {agent.mode === 'learning'
                    ? agent.learningState === 'review'
                      ? 'Memory notes ready for review'
                      : 'Waiting for reviewed feedback'
                    : agent.runtime === 'running'
                      ? 'Working on an assigned task'
                      : 'Eligible for delivery'}
                </span>
              </div>
              <div className={s.cardActions}>
                <button
                  className={s.button}
                  onClick={() => {
                    setSelectedId(agent.id);
                    setError(undefined);
                    setPrompt('');
                  }}
                  aria-label={`Inspect ${agent.name}`}
                >
                  Inspect <Icon name="arrow" size={13} />
                </button>
                <button
                  className={s.button}
                  disabled={busy}
                  onClick={() =>
                    void perform(() =>
                      execute('agent/mode', {
                        id: agent.id,
                        mode: agent.mode === 'active' ? 'learning' : 'active',
                      }),
                    )
                  }
                  aria-label={`${agent.mode === 'active' ? 'Deactivate' : 'Activate'} ${agent.name}`}
                >
                  {agent.mode === 'active' ? 'Deactivate' : 'Activate'}
                </button>
              </div>
            </div>
          </article>
        ))}
        <button
          className={s.addCard}
          onClick={add}
          disabled={!snapshot?.capabilities.workspaceOpen}
        >
          <span className={s.addGlyph}>+</span>
          <strong>Add your next specialist</strong>
          <span>Connect an independent ACP agent. Build the team your project needs.</span>
        </button>
      </div>
      {search && shown.length === 0 && (
        <p className={s.notice}>
          No agents match “{search}”. Try a different name or clear the filter.
        </p>
      )}
      <p className={s.footnote}>
        <Icon name="learning" size={17} />
        <span>
          Deactivating an agent stops its queued or running tasks and moves it to Learning.
          Activation controls participation; permissions still apply.{' '}
          <button className={s.quietButton} onClick={() => onNavigate?.('learning')}>
            Explore the dojo →
          </button>
        </span>
      </p>
      {editing && (
        <AgentEditor
          agent={editing}
          isNew={isNew}
          busy={busy}
          error={error}
          onClose={() => setEditing(null)}
          onSave={(input) =>
            void perform(
              () => execute('agent/save', { agent: input }),
              () => {
                setEditing(null);
                setNotice(`${input.name} saved. New agents begin in Learning.`);
              },
            )
          }
        />
      )}
      {importing && (
        <Dialog
          title="Bring an agent with you"
          description="Import a portable Meridian agent document. Imported agents start in Learning; imported memory needs your review."
          onClose={() => setImporting(false)}
        >
          <form
            className={s.form}
            onSubmit={(event) => {
              event.preventDefault();
              void perform(
                () => execute('agent/import', { content: importText }),
                () => {
                  setImporting(false);
                  setImportText('');
                  setNotice('Agent imported into Learning.');
                },
              );
            }}
          >
            <label className={s.field}>
              Choose a JSON file
              <input
                type="file"
                accept=".json,application/json"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    if (file.size > 20_000_000) setError('Choose a JSON file smaller than 20 MB.');
                    else
                      void file
                        .text()
                        .then(setImportText)
                        .catch(() => setError('The file could not be read.'));
                  }
                }}
              />
            </label>
            <label className={s.field}>
              Portable agent JSON
              <textarea
                className={s.codeInput}
                required
                rows={10}
                value={importText}
                onChange={(event) => setImportText(event.target.value)}
                spellCheck={false}
              />
            </label>
            {error && (
              <p className={s.error} role="alert">
                {error}
              </p>
            )}
            <div className={s.dialogFooter}>
              <button type="button" className={s.button} onClick={() => setImporting(false)}>
                Cancel
              </button>
              <button
                className={s.primaryButton}
                disabled={busy || !snapshot?.capabilities.workspaceOpen}
              >
                Import into Learning
              </button>
            </div>
          </form>
        </Dialog>
      )}
      {selected && (
        <Dialog
          title={selected.name}
          description={`${selected.role} · ${selected.id}`}
          wide
          onClose={() => setSelectedId(undefined)}
        >
          <div className={s.detailIdentity}>
            <span className={s.avatar} data-mode={selected.mode}>
              {selected.name.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <span className={s.badge} data-mode={selected.mode}>
                {selected.mode === 'learning' ? 'Learning' : 'Active'}
              </span>
              <p>{selected.description}</p>
            </div>
          </div>
          <div className={s.actions}>
            <button
              className={s.button}
              disabled={busy || selected.runtime === 'running'}
              onClick={() => {
                setEditing(selected);
                setIsNew(false);
                setSelectedId(undefined);
              }}
            >
              Edit agent
            </button>
            <button
              className={s.button}
              onClick={() =>
                void perform(async () => {
                  const document = await execute('agent/export', { id: selected.id });
                  getVsCodeApi().postMessage({
                    type: 'download',
                    mimeType: 'application/json',
                    ...document,
                  });
                  setNotice('Portable agent prepared. Choose a destination in the save dialog.');
                })
              }
            >
              Export portable agent
            </button>
            <button
              className={s.dangerButton}
              onClick={() => {
                setRemoving(selected);
                setSelectedId(undefined);
              }}
            >
              Remove
            </button>
          </div>
          <h3>Independent launch configuration</h3>
          <pre className={s.code}>
            {JSON.stringify({ command: selected.command, args: selected.args }, null, 2)}
          </pre>
          <p className={s.hint}>
            Use this command and argument array in another ACP host with the agent’s runtime
            installed. The portable document carries instructions and reviewed memory; it does not
            bundle the executable.
          </p>
          <div className={s.detailGrid}>
            <div className={s.detailBlock}>
              <h3>Instructions</h3>
              <pre className={s.code}>{selected.instructions || 'No additional instructions.'}</pre>
            </div>
            <div className={s.detailBlock}>
              <h3>Declared permissions</h3>
              <div className={s.tags}>
                {selected.permissions.map((permission) => (
                  <span className={s.tag} key={permission}>
                    {permission}
                  </span>
                ))}
              </div>
              <p>Workspace policy and human approval determine which requests can proceed.</p>
            </div>
          </div>
          <form
            className={s.form}
            onSubmit={(event) => {
              event.preventDefault();
              void perform(
                () => execute('agent/run', { id: selected.id, prompt }),
                () => {
                  setPrompt('');
                  setNotice('Independent task queued.');
                },
              );
            }}
          >
            <label className={s.field}>
              Run an independent task
              <textarea
                required
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="Describe the result you want this agent to produce…"
                rows={3}
              />
            </label>
            {selected.mode === 'learning' ? (
              <p className={s.notice}>
                Activate this agent before assigning a task. It currently belongs to Learning.
              </p>
            ) : (
              !snapshot?.capabilities.executionReady && (
                <p className={s.notice}>{snapshot?.capabilities.executionBlockedReason}</p>
              )
            )}
            {error && (
              <p className={s.error} role="alert">
                {error}
              </p>
            )}
            <button
              className={s.primaryButton}
              disabled={
                busy ||
                selected.mode !== 'active' ||
                selected.runtime === 'running' ||
                !snapshot?.capabilities.executionReady
              }
            >
              <Icon name="play" size={14} /> Run this agent
            </button>
          </form>
          <h3>Recent runs</h3>
          {snapshot?.runs
            .filter((run) => run.agentId === selected.id)
            .slice(-5)
            .reverse()
            .map((run) => (
              <div key={run.id} className={s.detailBlock}>
                <div className={s.sectionHeader}>
                  <span>
                    {run.state} · {new Date(run.startedAt).toLocaleString()}
                  </span>
                  {['running', 'queued'].includes(run.state) && (
                    <button
                      className={s.dangerButton}
                      onClick={() => void perform(() => execute('run/cancel', { id: run.id }))}
                    >
                      Stop run
                    </button>
                  )}
                </div>
                <p>{run.prompt}</p>
                {run.error && (
                  <p role="alert" className={s.error}>
                    {run.error}
                  </p>
                )}
                {run.output && <pre className={s.code}>{run.output}</pre>}
              </div>
            ))}
        </Dialog>
      )}
      {removing && (
        <Dialog
          title={`Remove ${removing.name}?`}
          description="This stops its tasks and removes its workspace profile and learning notes. Run history is retained. Export the portable agent first if you want to keep its configuration."
          onClose={() => setRemoving(undefined)}
        >
          {error && (
            <p className={s.error} role="alert">
              {error}
            </p>
          )}
          <div className={s.dialogFooter}>
            <button className={s.button} onClick={() => setRemoving(undefined)}>
              Keep agent
            </button>
            <button
              className={s.dangerButton}
              disabled={busy}
              onClick={() =>
                void perform(
                  () => execute('agent/remove', { id: removing.id }),
                  () => setRemoving(undefined),
                )
              }
            >
              Remove agent
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function AgentEditor({
  agent,
  isNew,
  busy,
  error,
  onClose,
  onSave,
}: {
  agent: WorkbenchAgentInput;
  isNew: boolean;
  busy: boolean;
  error?: string;
  onClose: () => void;
  onSave: (input: WorkbenchAgentInput) => void;
}) {
  const [value, setValue] = useState(agent);
  const [args, setArgs] = useState(JSON.stringify(agent.args));
  const [localError, setLocalError] = useState<string>();
  const field = (key: keyof WorkbenchAgentInput, text: string) =>
    setValue((previous) => ({ ...previous, [key]: text }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      const parsed: unknown = JSON.parse(args);
      if (!Array.isArray(parsed) || parsed.some((entry) => typeof entry !== 'string'))
        throw new Error('Arguments must be a JSON array of strings.');
      if (value.permissions.length === 0) throw new Error('Declare at least one permission.');
      onSave({ ...value, args: parsed });
      setLocalError(undefined);
    } catch (cause) {
      setLocalError((cause as Error).message);
    }
  };
  return (
    <Dialog
      title={isNew ? 'Meet your next agent.' : `Edit ${agent.name}`}
      description="Every agent has its own identity, instructions, and executable. New agents begin in Learning; activate them when they are ready to contribute."
      onClose={onClose}
      wide
    >
      <form className={s.form} onSubmit={submit}>
        <div className={s.formRow}>
          <label className={s.field}>
            Agent name
            <input
              autoFocus
              required
              maxLength={120}
              value={value.name}
              onChange={(event) => {
                field('name', event.target.value);
                if (
                  isNew &&
                  (!value.id ||
                    value.id ===
                      value.name
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, '-')
                        .replace(/^-|-$/g, ''))
                )
                  field(
                    'id',
                    event.target.value
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, '-')
                      .replace(/^-|-$/g, ''),
                  );
              }}
              placeholder="e.g. Atlas"
            />
          </label>
          <label className={s.field}>
            Portable ID
            <input
              required
              disabled={!isNew}
              maxLength={100}
              pattern="[a-z0-9][a-z0-9-]*"
              value={value.id}
              onChange={(event) => field('id', event.target.value)}
              placeholder="atlas-developer"
            />
          </label>
        </div>
        <div className={s.formRow}>
          <label className={s.field}>
            Role
            <input
              required
              maxLength={120}
              value={value.role}
              onChange={(event) => field('role', event.target.value)}
              list="agent-roles"
            />
            <datalist id="agent-roles">
              {[
                'Developer',
                'Architect',
                'Code reviewer',
                'Test engineer',
                'Security reviewer',
                'Documentation',
                'Delivery lead',
              ].map((role) => (
                <option key={role} value={role} />
              ))}
            </datalist>
          </label>
          <label className={s.field}>
            Vendor
            <input
              maxLength={120}
              value={value.vendor}
              onChange={(event) => field('vendor', event.target.value)}
              placeholder="Your agent provider"
            />
          </label>
        </div>
        <label className={s.field}>
          Description
          <textarea
            rows={2}
            maxLength={2000}
            value={value.description}
            onChange={(event) => field('description', event.target.value)}
            placeholder="What does this agent bring to your team?"
          />
        </label>
        <div className={s.formSection}>
          <h3>Portable runtime · ACP</h3>
          <div className={s.formRow}>
            <label className={s.field}>
              Executable
              <input
                aria-label="Executable"
                required
                value={value.command}
                onChange={(event) => field('command', event.target.value)}
                placeholder="Absolute executable path or command"
              />
              <span className={s.hint}>
                An installed ACP-compatible program. Commands are launched directly, without a
                shell.
              </span>
            </label>
            <label className={s.field}>
              Version
              <input
                required
                pattern="[0-9]+\.[0-9]+\.[0-9]+"
                value={value.version}
                onChange={(event) => field('version', event.target.value)}
              />
            </label>
          </div>
          <label className={s.field}>
            Arguments (JSON array)
            <input
              aria-label="Arguments (JSON array)"
              className={s.codeInput}
              required
              value={args}
              onChange={(event) => setArgs(event.target.value)}
              placeholder='["--acp"]'
              spellCheck={false}
            />
            <span className={s.hint}>
              Keep API keys and credentials in the agent’s credential store or environment.
            </span>
          </label>
          <label className={s.field}>
            Agent instructions
            <textarea
              rows={4}
              maxLength={40000}
              value={value.instructions}
              onChange={(event) => field('instructions', event.target.value)}
              placeholder="Define expertise, constraints, and what a good result looks like…"
            />
          </label>
        </div>
        <fieldset className={s.formSection}>
          <legend>Declared permissions</legend>
          <div className={s.checkboxGroup}>
            {PERMISSIONS.map((permission) => (
              <label key={permission} className={s.checkbox}>
                <input
                  type="checkbox"
                  checked={value.permissions.includes(permission)}
                  onChange={(event) =>
                    setValue((previous) => ({
                      ...previous,
                      permissions: event.target.checked
                        ? [...previous.permissions, permission]
                        : previous.permissions.filter((p) => p !== permission),
                    }))
                  }
                />
                {permission}
              </label>
            ))}
          </div>
          <p className={s.hint}>
            Declarations never grant access by themselves. Workspace policy and tool approval still
            apply.
          </p>
        </fieldset>
        <label className={s.checkbox}>
          <input
            type="checkbox"
            checked={value.trainable.includes('memory')}
            onChange={(event) =>
              setValue((previous) => ({
                ...previous,
                trainable: event.target.checked
                  ? [...previous.trainable, 'memory']
                  : previous.trainable.filter((surface) => surface !== 'memory'),
              }))
            }
          />
          Allow reviewed memory notes while in Learning
        </label>
        {(error || localError) && (
          <p className={s.error} role="alert">
            {localError || error}
          </p>
        )}
        <div className={s.dialogFooter}>
          <button type="button" className={s.button} onClick={onClose}>
            Cancel
          </button>
          <button className={s.primaryButton} disabled={busy}>
            {busy ? 'Saving…' : isNew ? 'Create agent' : 'Save changes'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
