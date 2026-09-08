import type { WorkbenchController } from './useWorkbench';
import type { ScreenProps } from '../screens/registry';
import { Icon } from './Icon';
import { VendorTag } from '../components/VendorTag';
import s from './workbench.module.css';

export function Home({
  controller,
  sessions,
  onNavigate,
}: {
  controller: WorkbenchController;
  sessions: ScreenProps['sessions'];
  onNavigate: (route: string) => void;
}) {
  const data = controller.snapshot;
  const active = data?.agents.filter((agent) => agent.mode === 'active');
  const learning = data?.agents.filter((agent) => agent.mode === 'learning');
  const running = data?.runs.filter((run) => run.state === 'running');
  const review = data?.deliverables.filter((item) => item.state === 'review');
  const pending = data?.learning.filter((note) => note.state === 'pending').length ?? 0;
  return (
    <div className={s.page}>
      <header className={s.pageHeading}>
        <div>
          <p className={s.eyebrow}>YOUR ENGINEERING WORKSPACE</p>
          <h1>
            A little clarity. <br />A lot of possibility.
          </h1>
          <p>Bring your agents, ideas, and evidence into one place.</p>
        </div>
        <button className={s.primary} onClick={() => onNavigate('deliverables')}>
          <Icon name="plus" size={16} /> New deliverable
        </button>
      </header>
      <section className={s.hero} aria-label="How your team works">
        <div className={s.heroCopy}>
          <span className={s.heroLabel}>
            <span className={s.dot} /> BUILT TO WORK TOGETHER
          </span>
          <h2>
            Independent agents.
            <br />
            <span>One shared purpose.</span>
          </h2>
          <p>
            Your active team takes on the work. Agents in Learning collect reviewed knowledge for
            their next contribution. You stay in control of every handoff.
          </p>
          <button className={s.textButton} onClick={() => onNavigate('agents')}>
            Shape your team <Icon name="arrow" size={18} />
          </button>
        </div>
        <LoomIllustration />
      </section>
      <section className={s.metrics} aria-label="Workspace metrics">
        {[
          {
            label: 'Active agents',
            value: active?.length,
            icon: 'agents' as const,
            detail: `${running?.length ?? 0} running now`,
            route: 'agents',
            tone: 'green',
          },
          {
            label: 'In learning',
            value: learning?.length,
            icon: 'learning' as const,
            detail: `${pending} notes awaiting review`,
            route: 'learning',
            tone: 'purple',
          },
          {
            label: 'Deliverables',
            value: data?.deliverables.length,
            icon: 'delivery' as const,
            detail: `${data?.deliverables.filter((d) => d.state === 'completed').length ?? 0} completed`,
            route: 'deliverables',
            tone: '',
          },
          {
            label: 'Ready for review',
            value: review?.length,
            icon: 'evidence' as const,
            detail: 'Your judgment, before completion',
            route: 'deliverables',
            tone: 'amber',
          },
        ].map((metric) => (
          <button className={s.metric} key={metric.label} onClick={() => onNavigate(metric.route)}>
            <span className={s.metricLabel}>
              {metric.label}
              <Icon name={metric.icon} size={16} />
            </span>
            <strong data-tone={metric.tone}>{metric.value ?? '—'}</strong>
            <span className={s.metricDetail}>{metric.detail}</span>
          </button>
        ))}
      </section>
      <div className={s.homeGrid}>
        <section className={s.panel}>
          <div className={s.panelHeader}>
            <div>
              <span className={s.eyebrow}>FROM INTENT TO OUTCOME</span>
              <h2>The work in motion</h2>
            </div>
            <button className={s.textButton} onClick={() => onNavigate('deliverables')}>
              View board <Icon name="arrow" size={15} />
            </button>
          </div>
          {!data?.deliverables.length ? (
            <div className={s.empty}>
              <Icon name="layers" size={34} />
              <h3>Your first thread starts here.</h3>
              <p>
                Describe an outcome and its acceptance criteria. Choose when your active agents
                begin.
              </p>
              <button className={s.secondary} onClick={() => onNavigate('deliverables')}>
                Write a brief <Icon name="plus" size={14} />
              </button>
            </div>
          ) : (
            <div>
              {data.deliverables.slice(0, 4).map((item, index) => (
                <button
                  className={s.workRow}
                  key={item.id}
                  onClick={() => onNavigate('deliverables')}
                >
                  <span className={s.rowIndex}>{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <strong>{item.title}</strong>
                    <span>
                      {item.agentIds.length
                        ? `${item.agentIds.length} agents assigned`
                        : 'Brief ready · team assigned at dispatch'}
                    </span>
                    <div className={s.stageTrack} aria-label={`Status: ${item.state}`}>
                      {['draft', 'running', 'review', 'completed'].map((stage, i) => (
                        <i
                          key={stage}
                          data-filled={
                            ['draft', 'running', 'review', 'completed'].indexOf(item.state) >= i
                          }
                        />
                      ))}
                    </div>
                  </div>
                  <span className={s.statusBadge} data-state={item.state}>
                    {item.state}
                  </span>
                  <Icon name="chevron" size={14} />
                </button>
              ))}
            </div>
          )}
        </section>
        <section className={s.panel}>
          <div className={s.panelHeader}>
            <div>
              <span className={s.eyebrow}>THE PEOPLE BEHIND THE PROCESS</span>
              <h2>Your agent collective</h2>
            </div>
            <button
              className={s.iconButton}
              aria-label="Manage agents"
              onClick={() => onNavigate('agents')}
            >
              <Icon name="arrow" size={16} />
            </button>
          </div>
          {!data?.agents.length ? (
            <div className={s.empty}>
              <div className={s.emptyAvatars}>
                <span>A</span>
                <span>B</span>
                <span>+</span>
              </div>
              <h3>A team built your way.</h3>
              <p>
                Add an ACP agent with its own role, instructions, and portable launch configuration.
              </p>
              <button className={s.secondary} onClick={() => onNavigate('agents')}>
                Add your first agent
              </button>
            </div>
          ) : (
            <div className={s.roster}>
              {data.agents.slice(0, 5).map((agent) => (
                <button className={s.rosterRow} onClick={() => onNavigate('agents')} key={agent.id}>
                  <span className={s.avatar} data-mode={agent.mode}>
                    {agent.name.slice(0, 2).toUpperCase()}
                  </span>
                  <span className={s.rosterName}>
                    <strong>{agent.name}</strong>
                    <span>{agent.role}</span>
                  </span>
                  <span className={s.statusBadge} data-state={agent.mode}>
                    {agent.mode === 'learning'
                      ? 'Learning'
                      : agent.runtime === 'running'
                        ? 'Running'
                        : 'Active'}
                  </span>
                </button>
              ))}
            </div>
          )}
          <div className={s.panelFooter}>
            <Icon name="learning" size={15} />
            <span>Inactive agents stay in Learning until you activate them.</span>
          </div>
        </section>
      </div>
      <section className={s.bottomStrip}>
        <div>
          <Icon name="evidence" size={21} />
          <div>
            <strong>Keep the evidence close.</strong>
            <p>
              {sessions.status === 'ready'
                ? `${sessions.data.sessions.length} external sessions observed. Inspect the source and confidence behind each record.`
                : sessions.status === 'error'
                  ? 'Observation is unavailable. Open Runtime to diagnose the connection.'
                  : 'Waiting for observer data from your workspace.'}
            </p>
          </div>
        </div>
        <button className={s.secondary} onClick={() => onNavigate('evidence')}>
          Open evidence <Icon name="arrow" size={15} />
        </button>
      </section>
      {sessions.status === 'ready' && sessions.data.warnings.length > 0 && (
        <div className={s.warning} data-testid="observer-warnings">
          {sessions.data.warnings.join(' · ')}
        </div>
      )}
      {sessions.status === 'ready' && sessions.data.sessions.length > 0 && (
        <div className={s.sourceList} aria-label="Observed sources">
          {sessions.data.sessions.slice(0, 6).map((session) => (
            <VendorTag
              key={session.sessionId}
              vendor={session.vendor}
              confidence={session.confidence}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LoomIllustration() {
  return (
    <div className={s.loomArt} aria-hidden="true">
      <svg viewBox="0 0 450 280" fill="none">
        <defs>
          <pattern id="loom-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M24 0H0V24" stroke="currentColor" strokeWidth=".5" opacity=".18" />
          </pattern>
        </defs>
        <rect width="450" height="280" fill="url(#loom-grid)" />
        <g className={s.loomThreads}>
          <path d="M-20 80h100q35 0 35 35v20q0 30 35 30h150q30 0 30-30V70q0-30 30-30h100" />
          <path d="M-20 110h80q35 0 35 35v20q0 30 35 30h150q30 0 30-30V100q0-30 30-30h120" />
          <path d="M-20 140h60q35 0 35 35v20q0 30 35 30h150q30 0 30-30V130q0-30 30-30h140" />
          <path d="M-20 170h40q35 0 35 35v20q0 30 35 30h150q30 0 30-30V160q0-30 30-30h160" />
        </g>
        <g className={s.loomCross}>
          <path d="M130-20v80q0 30 30 30h25q30 0 30 30v180" />
          <path d="M160-20v50q0 30 30 30h25q30 0 30 30v210" />
          <path d="M190-20v20q0 30 30 30h25q30 0 30 30v240" />
        </g>
        <circle cx="115" cy="80" r="5" className={s.artNode} />
        <circle cx="310" cy="195" r="5" className={s.artNode} />
        <circle cx="245" cy="60" r="5" className={s.artNodePurple} />
      </svg>
      <span className={s.artTag}>
        <Icon name="layers" size={14} /> MANY THREADS. ONE LOOM.
      </span>
    </div>
  );
}
