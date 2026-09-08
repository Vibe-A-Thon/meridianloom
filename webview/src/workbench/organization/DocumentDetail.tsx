import { useState } from 'react';
import type { StudioDocument } from '../../../../shared/ts/studio';
import type { WorkbenchSnapshot } from '../../../../shared/ts/workbench';
import { parseContent, matchRoute, writebackPreview } from './model';
import s from '../studio.module.css';
import o from './organization.module.css';

export function DocumentDetail({
  document,
  snapshot,
  onNavigate,
}: {
  document: StudioDocument;
  snapshot: WorkbenchSnapshot;
  onNavigate: (view: string) => void;
}) {
  const content = parseContent(document);
  const [phase, setPhase] = useState('implementation');
  const [task, setTask] = useState('code-search');
  const [simulated, setSimulated] = useState(false);
  const [deliveryId, setDeliveryId] = useState(
    snapshot.deliverables[0]?.id ?? '',
  );
  const matched = matchRoute(content.rules, phase, task);
  const delivery = snapshot.deliverables.find((item) => item.id === deliveryId);
  const storyLinks = content.links
    .map((id) =>
      (snapshot.documents ?? []).find((d) => d.id === id && d.kind === 'story'),
    )
    .filter((d): d is StudioDocument => !!d);
  const linkedDeliverables = snapshot.deliverables.filter((d) =>
    content.links.includes(d.id),
  );
  const activeStories = storyLinks.filter(
    (story) => parseContent(story).fields.state === 'in-progress',
  ).length;
  return (
    <div className={o.stack}>
      <div className={o.metadata}>
        <span>Version {document.version}</span>
        <span>{document.id}</span>
        <span>Updated {new Date(document.updatedAt).toLocaleString()}</span>
        {document.tags.map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
      </div>
      {content.fields.summary && (
        <p className={s.description}>{content.fields.summary}</p>
      )}
      {document.kind === 'story' && (
        <>
          <div className={s.detailGrid}>
            {[
              'source',
              'externalId',
              'owner',
              'priority',
              'state',
              'complexity',
              'branch',
              'due',
            ].map((key) => (
              <div className={s.detailBlock} key={key}>
                <h3>
                  {(
                    {
                      externalId: 'External reference',
                      state: 'Planning status',
                      due: 'Target date',
                    } as Record<string, string>
                  )[key] || key}
                </h3>
                <p>{content.fields[key] || 'Not specified'}</p>
              </div>
            ))}
          </div>
          <p className={s.hint}>
            Planning status is human authored. Linked deliverable states below
            come from actual workspace execution.
          </p>
        </>
      )}
      {document.kind === 'specification' && (
        <section className={s.detailBlock}>
          <h3>Ambiguity register · {content.fields.resolution || 'open'}</h3>
          <p>{content.fields.ambiguities || 'No ambiguity recorded.'}</p>
          {content.fields.resolution === 'escalated' && (
            <button className={s.button} onClick={() => onNavigate('steering')}>
              Open Steer & Clarify
            </button>
          )}
        </section>
      )}
      {content.criteria.length > 0 && (
        <div className={o.tableWrap}>
          <table className={o.table}>
            <caption>
              Acceptance traceability ·{' '}
              {content.criteria.filter((c) => c.state === 'verified').length}/
              {content.criteria.length} verified by author
            </caption>
            <thead>
              <tr>
                <th>ID / requirement</th>
                <th>Acceptance condition</th>
                <th>Evidence</th>
                <th>Author assessment</th>
              </tr>
            </thead>
            <tbody>
              {content.criteria.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.id}</strong>
                    <br />
                    {row.requirement}
                  </td>
                  <td>{row.acceptance}</td>
                  <td>{row.evidence || 'Uncovered'}</td>
                  <td>{row.state}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {['story', 'specification'].includes(document.kind) && (
        <section className={o.panel}>
          <h2>Linked deliverables</h2>
          {linkedDeliverables.length === 0 ? (
            <p>
              No linked deliverables. Edit this document to link existing
              workspace work.
            </p>
          ) : (
            linkedDeliverables.map((item) => (
              <div className={o.queueRow} key={item.id}>
                <span>
                  <strong>{item.title}</strong>
                  <br />
                  <span className={o.muted}>
                    {item.id} · {item.agentIds.length} assigned agents ·{' '}
                    {new Date(item.updatedAt).toLocaleString()}
                  </span>
                </span>
                <span className={s.badge} data-state={item.state}>
                  {item.state}
                </span>
              </div>
            ))
          )}
          {content.links
            .filter((id) => !snapshot.deliverables.some((d) => d.id === id))
            .map((id) => (
              <p className={s.notice} key={id}>
                Linked deliverable {id} is unavailable.
              </p>
            ))}
          <button
            className={s.button}
            onClick={() => onNavigate('deliverables')}
          >
            Open work packet board
          </button>
        </section>
      )}
      {document.kind === 'story' && linkedDeliverables.length > 0 && (
        <section className={o.panel}>
          <h2>Recorded delivery timeline</h2>
          <ol className={o.timeline}>
            {linkedDeliverables
              .flatMap((d) => [
                {
                  id: `${d.id}-created`,
                  at: d.createdAt,
                  text: `${d.title}: draft created`,
                },
                {
                  id: `${d.id}-updated`,
                  at: d.updatedAt,
                  text: `${d.title}: latest state ${d.state}`,
                },
              ])
              .sort((a, b) => a.at.localeCompare(b.at))
              .map((event) => (
                <li key={event.id}>
                  <strong>{event.text}</strong>
                  <p>{new Date(event.at).toLocaleString()}</p>
                </li>
              ))}
          </ol>
          <p>
            Only creation and latest-update timestamps are available here;
            intermediate phase durations are not inferred.
          </p>
        </section>
      )}
      {document.kind === 'portfolio' && (
        <>
          <div className={s.stats}>
            {[
              ['Stories', storyLinks.length],
              ['In progress', activeStories],
              ['WIP limit', content.fields.wip],
              [
                'Available slots',
                Math.max(0, Number(content.fields.wip) - activeStories),
              ],
            ].map(([label, value]) => (
              <div className={s.stat} key={label}>
                <span className={s.statLabel}>{label}</span>
                <strong className={s.statValue}>{value}</strong>
              </div>
            ))}
          </div>
          {activeStories > Number(content.fields.wip) && (
            <p className={s.error}>
              The planning WIP limit is exceeded by{' '}
              {activeStories - Number(content.fields.wip)} stories.
            </p>
          )}
          <div className={o.tableWrap}>
            <table className={o.table}>
              <caption>
                Priority queue · {content.fields.owner || 'No owner'} ·{' '}
                {content.fields.client || 'No client'}
              </caption>
              <thead>
                <tr>
                  <th>Priority</th>
                  <th>Story</th>
                  <th>Planning status</th>
                  <th>Linked delivery</th>
                  <th>Due</th>
                </tr>
              </thead>
              <tbody>
                {storyLinks.map((story, index) => {
                  const c = parseContent(story);
                  const linked = snapshot.deliverables.filter((d) =>
                    c.links.includes(d.id),
                  );
                  return (
                    <tr key={story.id}>
                      <td>{index + 1}</td>
                      <td>{story.title}</td>
                      <td>{c.fields.state}</td>
                      <td>
                        {linked.filter((d) => d.state === 'completed').length}/
                        {linked.length} completed
                      </td>
                      <td>{c.fields.due || 'Not set'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {content.links
            .filter((id) => !storyLinks.some((story) => story.id === id))
            .map((id) => (
              <p key={id} className={s.notice}>
                Story {id} is unavailable; edit the portfolio to update this
                reference.
              </p>
            ))}
          <button className={s.button} onClick={() => onNavigate('stories')}>
            Open story hub
          </button>
        </>
      )}
      {['skill', 'instruction'].includes(document.kind) && (
        <>
          <div className={o.metadata}>
            {document.kind === 'skill' ? (
              <>
                <span>Package {content.fields.packageVersion}</span>
                <span>{content.fields.stack || 'Any stack'}</span>
                <span>Tools: {content.fields.tools || 'None declared'}</span>
              </>
            ) : (
              <>
                <span>Draft scope: {content.fields.scope}</span>
                <span>{content.fields.path}</span>
              </>
            )}
          </div>
          <pre className={o.report}>{content.fields.content}</pre>
          {content.fields.rationale && (
            <p className={s.description}>
              Change rationale: {content.fields.rationale}
            </p>
          )}
          <p className={s.notice}>
            Content is displayed as text and never executed. Applying to an
            agent copies the reviewed content into its instructions for future
            tasks; it does not install scripts or publish governed files.
          </p>
        </>
      )}
      {document.kind === 'connector' && (
        <>
          <div className={s.detailGrid}>
            <section className={s.detailBlock}>
              <h3>{content.fields.provider}</h3>
              <p>
                {content.fields.endpoint}
                <br />
                Project: {content.fields.project}
              </p>
            </section>
            <section className={s.detailBlock}>
              <h3>Connection state</h3>
              <p>
                Configuration draft · credentials not stored · no connection has
                been attempted.
              </p>
            </section>
          </div>
          <section className={o.panel}>
            <h2>Review a write-back proposal</h2>
            <label className={s.field}>
              Source deliverable
              <select
                value={deliveryId}
                onChange={(e) => setDeliveryId(e.target.value)}
              >
                <option value="">Choose a deliverable</option>
                {snapshot.deliverables.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </select>
            </label>
            {delivery ? (
              <>
                <pre className={s.code}>
                  {JSON.stringify(writebackPreview(content, delivery), null, 2)}
                </pre>
                <p className={s.notice}>
                  Review required. A Done transition must also follow completion
                  approval. This proposal has not been sent; the extension has
                  no configured connector transport.
                </p>
              </>
            ) : (
              <p>
                Choose an existing deliverable to preview its actual title,
                status, and brief through the mapping.
              </p>
            )}
          </section>
        </>
      )}
      {document.kind === 'routing' && (
        <>
          <div className={o.tableWrap}>
            <table className={o.table}>
              <caption>
                Draft routing rules · intended region{' '}
                {content.fields.region || 'unspecified'}
              </caption>
              <thead>
                <tr>
                  <th>Phase</th>
                  <th>Task class</th>
                  <th>Mode</th>
                  <th>Engine / fallback</th>
                  <th>Call ceiling</th>
                </tr>
              </thead>
              <tbody>
                {content.rules.map((rule, index) => (
                  <tr key={index}>
                    <td>{rule.phase}</td>
                    <td>{rule.task}</td>
                    <td>{rule.mode}</td>
                    <td>
                      {rule.engine}
                      <br />
                      <span className={o.muted}>
                        {rule.fallback || 'No fallback'}
                      </span>
                    </td>
                    <td>{rule.ceiling}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <section className={o.panel}>
            <h2>Local routing simulation</h2>
            <p>
              Evaluates the authored matrix without making a model call or
              changing runtime policy.
            </p>
            <div className={s.formRow}>
              <label className={s.field}>
                Simulation phase
                <input
                  value={phase}
                  onChange={(e) => {
                    setPhase(e.target.value);
                    setSimulated(false);
                  }}
                />
              </label>
              <label className={s.field}>
                Simulation task class
                <input
                  value={task}
                  onChange={(e) => {
                    setTask(e.target.value);
                    setSimulated(false);
                  }}
                />
              </label>
            </div>
            <button className={s.button} onClick={() => setSimulated(true)}>
              Simulate selection
            </button>
            {simulated && (
              <div className={o.result} role="status">
                {matched ? (
                  <>
                    <strong>{matched.engine}</strong> · {matched.mode}
                    <br />
                    Maximum model calls: {matched.ceiling}
                    <br />
                    Fallback: {matched.fallback || 'None specified'}
                    <br />
                    Matched {matched.phase} / {matched.task}. No provider call
                    was made.
                  </>
                ) : (
                  'No rule matches. This draft would leave the task unrouted.'
                )}
              </div>
            )}
          </section>
        </>
      )}
      {document.kind === 'report' && (
        <pre className={o.report}>
          {content.fields.content || 'This report has no Markdown content yet.'}
        </pre>
      )}
    </div>
  );
}
