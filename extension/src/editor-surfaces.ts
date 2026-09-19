import * as vscode from "vscode";
import * as path from "node:path";
import { realpath } from "node:fs/promises";
import type {
  AttribBlameLine,
  AttribBlameResult,
  AttribSymbolResult,
} from "../../shared/ts/bus-types";

export async function resolveWorkspaceSource(
  root: string,
  file: string,
): Promise<string> {
  const canonicalRoot = await realpath(root);
  const target = await realpath(path.resolve(canonicalRoot, file));
  const relative = path.relative(canonicalRoot, target);
  if (
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  )
    throw new Error("Choose a source file inside the open workspace.");
  return target;
}

/** Blame at HEAD cannot safely annotate edited or shifted working-copy lines. */
export function matchingCommittedLine(
  text: string,
  lines: AttribBlameLine[],
  line: number,
): AttribBlameLine | undefined {
  const normalize = (value: string) =>
    value.replace(/\r\n/g, "\n").replace(/\n$/, "");
  if (
    normalize(text) !==
    normalize(
      [...lines]
        .sort((a, b) => a.line - b.line)
        .map((entry) => entry.content)
        .join("\n"),
    )
  )
    return undefined;
  return lines.find((entry) => entry.line === line);
}

interface EditorDeps {
  workspaceDir: () => string | undefined;
  request: (
    method: "attrib/blame" | "attrib/symbol",
    params: unknown,
    signal: AbortSignal,
  ) => Promise<unknown>;
}
export function createEditorSurfaces(deps: EditorDeps): {
  disposables: vscode.Disposable[];
  inspect: () => Promise<void>;
} {
  const cache = new Map<
    string,
    { time: number; result: Promise<AttribBlameResult> }
  >();
  let channel: vscode.OutputChannel | undefined;
  const read = async (
    document: vscode.TextDocument,
    position: vscode.Position,
    token?: vscode.CancellationToken,
  ) => {
    const root = deps.workspaceDir();
    if (!root || document.uri.scheme !== "file")
      throw new Error("Open a source file in the current workspace.");
    if (document.lineCount > 20000 || document.getText().length > 2_000_000)
      throw new Error(
        "Use the workbench evidence view for files larger than 20,000 lines or 2 MB.",
      );
    const target = await resolveWorkspaceSource(root, document.uri.fsPath);
    if (token?.isCancellationRequested) return undefined;
    const canonicalRoot = await realpath(root);
    const relative = path.relative(canonicalRoot, target).replaceAll("\\", "/");
    const key = `${root}:${target}:${document.version}`;
    let cached = cache.get(key);
    if (!cached || Date.now() - cached.time > 10000) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      const result = deps
        .request(
          "attrib/blame",
          { repoPath: canonicalRoot, paths: [relative] },
          controller.signal,
        )
        .then((value) => value as AttribBlameResult)
        .finally(() => clearTimeout(timer));
      cached = { time: Date.now(), result };
      cache.set(key, cached);
      if (cache.size > 30) cache.delete(cache.keys().next().value!);
      void result.catch(() => cache.delete(key));
    }
    const blame = await cached.result;
    if (token?.isCancellationRequested) return undefined;
    return {
      root: canonicalRoot,
      relative,
      line: position.line + 1,
      entry: matchingCommittedLine(
        document.getText(),
        blame.lines,
        position.line + 1,
      ),
    };
  };
  const disposables: vscode.Disposable[] = [];
  // Providers are absent in headless hosts; command inspection remains independently callable.
  if (vscode.languages?.registerHoverProvider)
    disposables.push(
      vscode.languages.registerHoverProvider(
        { scheme: "file" },
        {
          async provideHover(document, position, token) {
            if (
              vscode.workspace
                .getConfiguration("meridian")
                .get<boolean>("editor.provenance", true) === false
            )
              return undefined;
            try {
              const data = await read(document, position, token);
              if (!data || token.isCancellationRequested) return undefined;
              const markdown = new vscode.MarkdownString();
              markdown.isTrusted = false;
              markdown.appendText("Meridian · Git provenance\n\n");
              if (data.entry)
                markdown.appendText(
                  `${data.entry.authorName}\n${data.entry.authorTime}\nCommit ${data.entry.commit}\n\nGit authorship does not identify which agent produced a change.`,
                );
              else
                markdown.appendText(
                  "The working copy differs from the committed file. Line authorship is unavailable for this version. Inspect the attributed diff in Meridian Loom.",
                );
              return new vscode.Hover(
                markdown,
                document.lineAt(position.line).range,
              );
            } catch {
              return undefined;
            } // Hover must remain quiet while the runtime connects.
          },
        },
      ),
    );
  if (vscode.languages?.registerCodeLensProvider)
    disposables.push(
      vscode.languages.registerCodeLensProvider(
        { scheme: "file" },
        {
          provideCodeLenses(document) {
            if (
              !deps.workspaceDir() ||
              vscode.workspace
                .getConfiguration("meridian")
                .get<boolean>("editor.provenance", true) === false
            )
              return [];
            return [
              new vscode.CodeLens(new vscode.Range(0, 0, 0, 0), {
                title: "Meridian: inspect source provenance",
                command: "meridian.inspectSource",
              }),
            ];
          },
        },
      ),
    );
  disposables.push({
    dispose: () => {
      cache.clear();
      channel?.dispose();
    },
  });
  return {
    disposables,
    inspect: async () => {
      try {
        const editor = vscode.window.activeTextEditor;
        if (!editor)
          throw new Error("Open a source file and place the cursor on a line.");
        const data = await read(editor.document, editor.selection.active);
        if (!data) return;
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 8000);
        let symbol: AttribSymbolResult | undefined;
        try {
          symbol = (await deps.request(
            "attrib/symbol",
            { repoPath: data.root, path: data.relative, line: data.line },
            controller.signal,
          )) as AttribSymbolResult;
        } finally {
          clearTimeout(timer);
        }
        channel ??= vscode.window.createOutputChannel(
          "Meridian Source Evidence",
        );
        channel.clear();
        channel.appendLine(`${data.relative}:${data.line}`);
        channel.appendLine(`Symbol: ${symbol?.symbol ?? "Not resolved"}`);
        channel.appendLine(
          data.entry
            ? `Git author: ${data.entry.authorName}\nCommit: ${data.entry.commit}\nRecorded at: ${data.entry.authorTime}`
            : "Working copy differs from HEAD; committed line authorship is unavailable for this version.",
        );
        channel.appendLine(
          "Git authorship is separate from agent attribution. Use the workbench for recorded session evidence and attributed diffs.",
        );
        channel.show(true);
      } catch (error) {
        await vscode.window.showWarningMessage(
          `Meridian source evidence: ${(error as Error).message}`,
        );
      }
    },
  };
}
