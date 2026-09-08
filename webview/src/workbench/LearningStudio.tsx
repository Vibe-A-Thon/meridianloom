import { useState } from 'react';
import type { WorkbenchController } from './useWorkbench';
import { Dialog } from './Dialog';
import { Icon } from './Icon';
import s from './studio.module.css';

export function LearningStudio({
  controller,
  onNavigate,
}: {
  controller: WorkbenchController;
  onNavigate?: (route: string) => void;
}) {
  const { snapshot, execute, busy } = controller;
  const [selectedId, setSelectedId] = useState<string>();
  const [filter, setFilter] = useState('pending');
  const [error, setError] = useState<string>();
  const learners = snapshot?.agents.filter((agent) => agent.mode === 'learning') ?? [];
  const notes = snapshot?.learning ?? [];
  const selected = notes.find((note) => note.id === selectedId);
  const decide = async (decision: 'accepted' | 'dismissed') => {
    if (!selected) return;
    try {
      await execute('learning/review', { id: selected.id, decision });
      setSelectedId(undefined);
    } catch (cause) {
      setError((cause as Error).message);
    }
  };
  return (
    <div className={s.studio}>
      <header className={s.pageHeader}>
        <div>
          <span className={s.eyebrow}>INTELLIGENCE / LEARNING DOJO</span>
          <h1>Every outcome can teach.</h1>
          <p className={s.subtitle}>
            Turn delivery feedback into useful memory. Review what agents learn before it shapes
            their next task.
          </p>
        </div>
        <button className={s.button} onClick={() => onNavigate?.('agents')}>
          Manage agents <Icon name="arrow" size={14} />
        </button>
      </header>
      <section className={s.stats} aria-label="Learning statistics">
        {[
          ['Learning agents', learners.length],
          ['Awaiting review', notes.filter((note) => note.state === 'pending').length],
          ['Accepted memories', notes.filter((note) => note.state === 'accepted').length],
          ['Sources', new Set(notes.map((note) => note.deliverableId)).size],
        ].map(([label, value]) => (
          <div className={s.stat} key={label}>
            <span className={s.statLabel}>{label}</span>
            <strong className={s.statValue}>{snapshot ? value : '—'}</strong>
          </div>
        ))}
      </section>
      <div className={s.learningLayout}>
        <div>
          <div className={s.sectionHeader}>
            <h2>The learning cohort</h2>
            <span>{learners.length} agents</span>
          </div>
          <div className={s.learningList}>
            {learners.map((agent) => (
              <article className={s.learningCard} key={agent.id}>
                <span className={s.avatar} data-mode="learning">
                  {agent.name.slice(0, 2).toUpperCase()}
                </span>
                <div className={s.learningBody}>
                  <h3>{agent.name}</h3>
                  <p>
                    {agent.role} ·{' '}
                    {agent.trainable.includes('memory')
                      ? agent.learningState === 'review'
                        ? 'Feedback captured. Memory ready for review.'
                        : 'Waiting for feedback from a completed deliverable.'
                      : 'Memory frozen. Enable reviewed memory in agent settings.'}
                  </p>
                </div>
                <span className={s.badge} data-mode="learning">
                  Learning
                </span>
              </article>
            ))}
          </div>
          {learners.length === 0 && (
            <div className={s.empty}>
              <Icon name="learning" size={36} />
              <h2>A place to grow between tasks.</h2>
              <p>
                Deactivate an agent to move it into Learning. It leaves the delivery roster and can
                receive reviewable memory from future completed work.
              </p>
            </div>
          )}
          <div className={s.sectionHeader}>
            <h2>Memory review inbox</h2>
          </div>
          <div className={s.filters}>
            {['pending', 'accepted', 'dismissed'].map((state) => (
              <button
                className={s.filter}
                aria-pressed={filter === state}
                key={state}
                onClick={() => setFilter(state)}
              >
                {state === 'pending'
                  ? 'Awaiting review'
                  : state === 'accepted'
                    ? 'Accepted'
                    : 'Dismissed'}{' '}
                <span className={s.filterCount}>
                  {notes.filter((note) => note.state === state).length}
                </span>
              </button>
            ))}
          </div>
          <div className={s.learningList}>
            {notes
              .filter((note) => note.state === filter)
              .map((note) => (
                <article className={s.learningCard} key={note.id}>
                  <Icon name="evidence" size={20} />
                  <div className={s.learningBody}>
                    <h3>{note.title}</h3>
                    <p>
                      {snapshot?.agents.find((agent) => agent.id === note.agentId)?.name ??
                        note.agentId}{' '}
                      · Memory · {new Date(note.createdAt).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    className={s.button}
                    onClick={() => {
                      setSelectedId(note.id);
                      setError(undefined);
                    }}
                  >
                    {note.state === 'pending' ? 'Review note' : 'Read note'}
                  </button>
                </article>
              ))}
          </div>
          {!notes.some((note) => note.state === filter) && (
            <p className={s.notice}>
              No {filter === 'pending' ? 'pending' : filter} memory notes. Human feedback from
              completed deliverables supplies the learning inbox.
            </p>
          )}
        </div>
        <aside className={s.aside}>
          <section className={s.asidePanel}>
            <h2>Learning, with a clear source.</h2>
            <ol className={s.process}>
              <li>
                <strong>Finish and review a deliverable.</strong> Record what worked and what should
                change.
              </li>
              <li>
                <strong>Capture the lesson.</strong> Agents in Learning with memory enabled receive
                a proposed note.
              </li>
              <li>
                <strong>Accept or dismiss.</strong> You decide which notes become portable memory.
              </li>
              <li>
                <strong>Put it into practice.</strong> Accepted memory accompanies the agent’s next
                active task.
              </li>
            </ol>
          </section>
          <section className={s.asidePanel}>
            <h2>What changes?</h2>
            <p>
              Reviewed memory and task context. This workflow does not retrain model weights, edit
              executable code, or promote permissions.
            </p>
            <p>
              Learning is the agent’s participation mode. Waiting and review states show the actual
              work available.
            </p>
          </section>
        </aside>
      </div>
      {selected && (
        <Dialog
          title={selected.title}
          description={`Memory for ${snapshot?.agents.find((agent) => agent.id === selected.agentId)?.name ?? selected.agentId} · ${selected.state}`}
          wide
          onClose={() => setSelectedId(undefined)}
        >
          <pre className={s.code}>{selected.content}</pre>
          <p className={s.hint}>
            Source: {selected.deliverableId}. Accepted notes are included in the agent’s future task
            context and portable export.
          </p>
          {error && (
            <p className={s.error} role="alert">
              {error}
            </p>
          )}
          <div className={s.dialogFooter}>
            {selected.state === 'pending' ? (
              <>
                <button
                  className={s.button}
                  disabled={busy}
                  onClick={() => void decide('dismissed')}
                >
                  Dismiss
                </button>
                <button
                  className={s.primaryButton}
                  disabled={busy}
                  onClick={() => void decide('accepted')}
                >
                  Accept memory
                </button>
              </>
            ) : (
              <button className={s.button} onClick={() => setSelectedId(undefined)}>
                Close
              </button>
            )}
          </div>
        </Dialog>
      )}
    </div>
  );
}
