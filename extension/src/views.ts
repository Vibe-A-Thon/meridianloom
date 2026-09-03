import * as vscode from 'vscode';

/**
 * FR-M1-02: the five tree views contributed under the Meridian Loom
 * Activity Bar container. Ids here are the single source of truth; the
 * manifest test asserts package.json matches them.
 */
export const TREE_VIEWS = [
  { id: 'meridianLoom.agents', name: 'Agents' },
  { id: 'meridianLoom.stories', name: 'Stories' },
  { id: 'meridianLoom.loops', name: 'Loops' },
  { id: 'meridianLoom.skills', name: 'Skills' },
  { id: 'meridianLoom.ledger', name: 'Ledger' },
] as const;

export type TreeViewId = (typeof TREE_VIEWS)[number]['id'];

/**
 * Empty until the sidecar supplies state (Workstream B). Registration is
 * synchronous and cheap so activation never blocks the host (FR-M1-04).
 */
class MeridianTreeProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly changeEmitter = new vscode.EventEmitter<vscode.TreeItem | undefined>();
  readonly onDidChangeTreeData = this.changeEmitter.event;

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(): vscode.TreeItem[] {
    return [];
  }

  refresh(): void {
    this.changeEmitter.fire(undefined);
  }
}

export function registerViews(): vscode.Disposable[] {
  return TREE_VIEWS.map(({ id }) =>
    vscode.window.registerTreeDataProvider(id, new MeridianTreeProvider()),
  );
}
