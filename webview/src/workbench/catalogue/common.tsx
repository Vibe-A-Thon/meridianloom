import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type React from "react";
import { Icon, type IconName } from "../Icon";
import s from "./catalogue.module.css";

/**
 * Primitives shared by the Agents, Skills, Instructions and Phases tabs.
 *
 * These four tabs are the same shape of problem — a catalogue of named things
 * you create, tag, enable, disable, import, export and delete — so they share
 * one set of parts rather than four near-copies. Consistency here is what
 * makes the interface learnable: a chip behaves the same everywhere, a
 * destructive action always asks, an empty state always says what to do next.
 */

export function Page({
  title,
  blurb,
  actions,
  children,
}: {
  title: string;
  blurb: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={s.page}>
      <header className={s.pageHead}>
        <div>
          <h1 className={s.pageTitle}>{title}</h1>
          <p className={s.pageBlurb}>{blurb}</p>
        </div>
        {actions ? <div className={s.pageActions}>{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

export function Panel({
  title,
  hint,
  action,
  accent,
  children,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  /** A CSS colour identifying this panel's subject, drawn as a top rule. */
  accent?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`${s.panel} ${accent ? s.panelAccent : ""}`}
      style={accent ? ({ ["--panel-accent"]: accent } as React.CSSProperties) : undefined}
    >
      <header className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>{title}</h2>
          {hint ? <p className={s.panelHint}>{hint}</p> : null}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

/**
 * An empty state is an invitation, never an apology: it says what this
 * surface is for and offers the one action that fills it.
 */
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={s.empty}>
      <p className={s.emptyTitle}>{title}</p>
      {children ? <p className={s.emptyBody}>{children}</p> : null}
      {action ? <div className={s.emptyAction}>{action}</div> : null}
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className={s.field}>
      <span className={s.fieldLabel}>{label}</span>
      {children}
      {hint ? <span className={s.fieldHint}>{hint}</span> : null}
    </label>
  );
}

/**
 * A multi-select rendered as toggle chips. Used for SDLC phases, skill
 * binding, instruction binding and permissions — every place the user picks
 * several things from a known set.
 *
 * Selection is carried by `aria-pressed` rather than colour alone, so the
 * state survives a colour-vision deficiency and a screen reader.
 */
export function ChipSelect<T extends string>({
  options,
  selected,
  onChange,
  disabled,
  emptyLabel,
}: {
  options: readonly { value: T; label: string; hint?: string }[];
  selected: readonly T[];
  onChange: (next: T[]) => void;
  disabled?: boolean;
  emptyLabel?: string;
}) {
  if (!options.length)
    return <p className={s.chipEmpty}>{emptyLabel ?? "Nothing to choose yet."}</p>;
  return (
    <div className={s.chipRow}>
      {options.map((option) => {
        const on = selected.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            className={s.chip}
            aria-pressed={on}
            disabled={disabled}
            title={option.hint}
            onClick={() =>
              onChange(
                on
                  ? selected.filter((entry) => entry !== option.value)
                  : [...selected, option.value],
              )
            }
          >
            <span className={s.chipMark} aria-hidden="true">
              {on ? "✓" : "+"}
            </span>
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** A read-only chip, for showing a binding that this surface does not edit. */
export function Tag({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "active" | "learning" | "warn";
}) {
  return <span className={`${s.tag} ${s[`tag_${tone}`]}`}>{children}</span>;
}

export function Toolbar({
  value,
  onChange,
  placeholder,
  right,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder: string;
  right?: ReactNode;
}) {
  return (
    <div className={s.toolbar}>
      <div className={s.search}>
        <Icon name="search" size={15} />
        <input
          type="search"
          value={value}
          placeholder={placeholder}
          aria-label={placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      {right ? <div className={s.toolbarRight}>{right}</div> : null}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  icon,
  disabled,
  type = "button",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "danger" | "quiet";
  icon?: IconName;
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
}) {
  return (
    <button
      type={type}
      className={`${s.button} ${s[`button_${variant}`]}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
    >
      {icon ? <Icon name={icon} size={15} /> : null}
      {children}
    </button>
  );
}

/**
 * Destructive actions ask first, and the confirmation states what will be
 * lost in the same words the user would use. Removing an agent is not
 * undoable from here, so it never happens on a single click.
 */
export function Confirm({
  title,
  detail,
  confirmLabel,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  title: string;
  detail: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Focus the dialog on open and return focus on close: keyboard users must
    // not be dropped back at the top of the page.
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, [onCancel]);
  return (
    <div className={s.scrim} role="presentation" onClick={onCancel}>
      <div
        ref={ref}
        className={s.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className={s.dialogTitle}>{title}</h2>
        <div className={s.dialogBody}>{detail}</div>
        {error ? (
          <p className={s.error} role="alert">
            {error}
          </p>
        ) : null}
        <div className={s.dialogActions}>
          <Button variant="quiet" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Filter a list by a free-text query across the fields the caller names. */
export function useFilter<T>(
  items: readonly T[],
  query: string,
  fields: (item: T) => (string | undefined)[],
): T[] {
  return useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [...items];
    return items.filter((item) =>
      fields(item).some((value) => value?.toLowerCase().includes(needle)),
    );
  }, [items, query, fields]);
}

/**
 * Run an async action, surfacing its error in place instead of throwing it
 * into a boundary. Returns the busy flag and the last error so a form can
 * disable itself and explain what went wrong without losing the user's input.
 */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  const run = async (task: () => Promise<unknown>, success?: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await task();
      if (alive.current && success) setNotice(success);
      return true;
    } catch (cause) {
      if (alive.current)
        setError(cause instanceof Error ? cause.message : String(cause));
      return false;
    } finally {
      if (alive.current) setBusy(false);
    }
  };
  return { busy, error, notice, run, setError, setNotice };
}

export function Notice({
  tone,
  children,
}: {
  tone: "error" | "success" | "info";
  children: ReactNode;
}) {
  if (!children) return null;
  return (
    <p
      className={`${s.notice} ${s[`notice_${tone}`]}`}
      role={tone === "error" ? "alert" : "status"}
    >
      {children}
    </p>
  );
}
