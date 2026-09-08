import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import styles from './dialog.module.css';

/** The native dialog owns focus containment, Escape and background inertness. */
export function Dialog({
  title,
  description,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current!;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    return () => {
      dialog.close?.();
      previous?.focus();
    };
  }, []);
  return createPortal(
    <dialog
      ref={ref}
      className={`${styles.dialog} ${wide ? styles.wide : ''}`}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onKeyDown={(event) => {
        if (event.key !== 'Tab') return;
        const focusable = Array.from(
          ref.current!.querySelectorAll<HTMLElement>(
            'button, input, select, textarea, a[href], [tabindex]',
          ),
        ).filter(
          (element) =>
            !element.hasAttribute('disabled') &&
            element.tabIndex >= 0 &&
            element.getClientRects().length > 0,
        );
        const first = focusable[0];
        const last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) {
          const box = ref.current!.getBoundingClientRect();
          if (
            event.clientX < box.left ||
            event.clientX > box.right ||
            event.clientY < box.top ||
            event.clientY > box.bottom
          )
            onClose();
        }
      }}
    >
      <header className={styles.header}>
        <div>
          <h2 id={titleId}>{title}</h2>
          {description && <p id={descriptionId}>{description}</p>}
        </div>
        <button type="button" aria-label="Close dialog" onClick={onClose} className={styles.close}>
          ×
        </button>
      </header>
      <div className={styles.content}>{children}</div>
    </dialog>,
    document.body,
  );
}
