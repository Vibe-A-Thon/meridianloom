import { useState } from 'react';
import type { StudioDocumentInput } from '../../../../shared/ts/studio';
import type { LedgerEntry } from '../../../../shared/ts/bus-types';
import type { WorkbenchSnapshot } from '../../../../shared/ts/workbench';
import { Dialog } from '../Dialog';
import { getVsCodeApi } from '../../host/vscode-api';
import { buildJourney, emptyContent } from './model';
import s from '../studio.module.css';
import o from './organization.module.css';

export function ReportBuilder({
  snapshot,
  workspaceDir,
  ledger,
  ledgerStatus,
  busy,
  error,
  onClose,
  onSave,
}: {
  snapshot: WorkbenchSnapshot;
  workspaceDir?: string;
  ledger?: LedgerEntry[];
  ledgerStatus: string;
  busy: boolean;
  error?: string;
  onClose: () => void;
  onSave: (value: StudioDocumentInput) => Promise<void>;
}) {
  const [title, setTitle] = useState('Delivery journey');
  const [sections, setSections] = useState([
    'summary',
    'stories',
    'deliverables',
    'runs',
    'learning',
    'ledger',
  ]);
  const [preview, setPreview] = useState<string>();
  const [source, setSource] = useState({
    revision: snapshot.revision,
    deliverables: snapshot.deliverables.length,
  });
  const changed = () => setPreview(undefined);
  const document = () => {
    const content = emptyContent('report');
    content.fields.content = preview ?? '';
    content.fields.sections = sections.join(',');
    content.fields.summary = `Workspace revision ${source.revision}; ${source.deliverables} deliverables; generated from the selected evidence.`;
    return {
      kind: 'report' as const,
      title,
      body: JSON.stringify(content),
      tags: ['journey', 'generated'],
    };
  };
  return (
    <Dialog
      title="Build a journey report"
      description="Choose the facts to include, generate a preview, then save or export it. A signed evidence bundle remains available in the ledger."
      onClose={onClose}
      wide
    >
      <div className={s.form}>
        <label className={s.field}>
          Report title
          <input
            value={title}
            maxLength={160}
            onChange={(e) => {
              setTitle(e.target.value);
              changed();
            }}
          />
        </label>
        <fieldset className={s.formSection}>
          <legend>Report sections</legend>
          <div className={s.checkboxGroup}>
            {[
              'summary',
              'stories',
              'deliverables',
              'runs',
              'learning',
              'ledger',
            ].map((section) => (
              <label key={section} className={s.checkbox}>
                <input
                  type="checkbox"
                  checked={sections.includes(section)}
                  onChange={(e) => {
                    setSections((previous) =>
                      e.target.checked
                        ? [...previous, section]
                        : previous.filter((value) => value !== section),
                    );
                    changed();
                  }}
                />
                {section}
              </label>
            ))}
          </div>
        </fieldset>
        <p className={s.hint}>
          Ledger:{' '}
          {ledgerStatus === 'ready'
            ? `${ledger?.length ?? 0} entries in the current sample`
            : 'unavailable; the report will say so'}
          . No provider cost, test verdict, or approval is inferred from missing
          evidence.
        </p>
        <button
          className={s.button}
          disabled={!title.trim() || !sections.length}
          onClick={() => {
            setSource({
              revision: snapshot.revision,
              deliverables: snapshot.deliverables.length,
            });
            setPreview(
              buildJourney(
                snapshot,
                title.trim(),
                sections,
                ledger,
                workspaceDir,
              ),
            );
          }}
        >
          Generate report preview
        </button>
        {preview && (
          <>
            <pre className={o.report}>{preview}</pre>
            <div className={s.actions}>
              <button
                className={s.button}
                onClick={() =>
                  getVsCodeApi().postMessage({
                    type: 'download',
                    fileName: `${title.replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 80) || 'journey-report'}.md`,
                    content: preview,
                    mimeType: 'text/markdown',
                  })
                }
              >
                Export Markdown
              </button>
              <button
                className={s.primaryButton}
                disabled={busy}
                onClick={() => void onSave(document())}
              >
                Save report to workspace
              </button>
            </div>
          </>
        )}
        {error && (
          <p role="alert" className={s.error}>
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}
