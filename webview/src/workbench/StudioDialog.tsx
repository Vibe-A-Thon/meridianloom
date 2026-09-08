import { useEffect, useId, useRef, type ReactNode } from 'react';
import styles from './studio.module.css';

/** All Studio flows share one keyboard boundary and restore their trigger. */
export function StudioDialog({
  title,
  description,
  children,
  onClose,
  busy = false,
  wide = false,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
  wide?: boolean;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const container = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  const busyRef = useRef(busy);
  closeRef.current = onClose;
  busyRef.current = busy;

  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const panel = container.current;
    const controls = () =>
      Array.from(
        panel?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]',
        ) ?? [],
      );
    // An input is more useful than the dismiss button for creation/editing.
    (
      panel?.querySelector<HTMLElement>('input, textarea, select') ??
      controls()[0] ??
      panel
    )?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busyRef.current) {
        event.preventDefault();
        event.stopPropagation();
        closeRef.current();
      }
      if (event.key !== 'Tab') return;
      const focusable = controls();
      if (!focusable.length) {
        event.preventDefault();
        panel?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (
        event.shiftKey &&
        (document.activeElement === first || document.activeElement === panel)
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || document.activeElement === panel)
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    panel?.addEventListener('keydown', onKey);
    return () => {
      panel?.removeEventListener('keydown', onKey);
      if (trigger?.isConnected) trigger.focus();
    };
  }, []);

  return (
    <div
      className={styles.backdrop}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <div
        ref={container}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={`${styles.dialog} ${wide ? styles.dialogWide : ''}`}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span className={styles.eyebrow}>AGENT STUDIO</span>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button
            type="button"
            className={styles.iconButton}
            onClick={onClose}
            disabled={busy}
            aria-label="Close dialog"
          >
            ×
          </button>
        </header>
        {description && (
          <p className={styles.dialogDescription} id={descriptionId}>
            {description}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}
