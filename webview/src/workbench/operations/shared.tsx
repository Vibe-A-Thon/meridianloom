import {
  useEffect,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { TierName } from "../../../../shared/ts/bus-types";
import type { WorkbenchController } from "../useWorkbench";
import type { WebviewRpcClient } from "../../rpc/client";
import { getVsCodeApi, readUiState, writeUiState } from "../../host/vscode-api";
import { DEFAULT_DENSITY, DEFAULT_THEME } from "../../theme/themes";
import s from "./operations.module.css";

export interface OperationsProps {
  view: string;
  controller: WorkbenchController;
  client: WebviewRpcClient;
  ready: boolean;
  workspaceDir?: string;
  enabledTiers: readonly TierName[];
  onNavigate: (route: string) => void;
}
export function useViewState<T>(
  key: string,
  initial: T,
): [T, Dispatch<SetStateAction<T>>] {
  const api = getVsCodeApi();
  const [value, setValue] = useState<T>(() => {
    const saved = readUiState(api)?.view?.[key];
    if (Array.isArray(initial))
      return Array.isArray(saved) &&
        saved.every((item) => typeof item === "string")
        ? (saved as T)
        : initial;
    return typeof saved === typeof initial && saved !== null
      ? (saved as T)
      : initial;
  });
  useEffect(() => {
    const old = readUiState(api);
    writeUiState(api, {
      theme: old?.theme ?? DEFAULT_THEME,
      density: old?.density ?? DEFAULT_DENSITY,
      view: { ...old?.view, [key]: value },
    });
  }, [api, key, value]);
  return [value, setValue];
}
export function StudioPage({
  section,
  title,
  description,
  actions,
  children,
}: {
  section: string;
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={s.page}>
      <header className={s.heading}>
        <div>
          <p className={s.eyebrow}>{section}</p>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <div className={s.actions}>{actions}</div>
      </header>
      {children}
    </div>
  );
}
export function exportText(
  fileName: string,
  content: string,
  mimeType = "application/json",
) {
  getVsCodeApi().postMessage({ type: "download", fileName, mimeType, content });
}
export function csv(rows: unknown[][]) {
  return rows
    .map((row) =>
      row
        .map((value) => {
          let text = String(value ?? "");
          if (/^[=+@\-\t\r]/.test(text)) text = `'${text}`;
          return `"${text.replaceAll('"', '""')}"`;
        })
        .join(","),
    )
    .join("\r\n");
}
export function ErrorNotice({ error }: { error?: string | null }) {
  return error ? (
    <p role="alert" className={s.error}>
      {error}
    </p>
  ) : null;
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className={s.empty}>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}
export function stamp(value?: string) {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}
