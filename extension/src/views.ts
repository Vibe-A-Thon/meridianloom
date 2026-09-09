import * as vscode from 'vscode';

/**
 * The Meridian Loom Activity Bar container hosts exactly one view: the
 * workbench webview.
 *
 * This replaces the five placeholder tree views of the original `FR-M1-02`
 * reading. Those views were containers for Agents, Stories, Loops, Skills and
 * Ledger, and every one of them is now a tab inside the workbench — so
 * keeping them would mean two navigations to the same content, and would push
 * the interface into a strip below a stack of empty trees.
 *
 * The product requirement this serves: selecting Meridian Loom in the
 * Activity Bar opens the product. A `webview`-typed view resolved by
 * `RecorderViewProvider` is the only VS Code mechanism that does that without
 * a command in between.
 *
 * The view itself is registered in `extension.ts`; this module owns the id
 * and the tier the manifest test checks against.
 */
export const WORKBENCH_VIEW = {
  id: 'meridianLoom.workbench',
  name: 'Meridian Loom',
  /**
   * Flight Recorder, so the container opens at the base tier. Tier gating
   * happens inside the interface, per surface (X-28), rather than by hiding
   * the only view and leaving the user an empty container with no
   * explanation of why.
   */
  tier: 'flight-recorder',
} as const;

/**
 * No tree views remain. Kept as an explicit empty tuple so the manifest test
 * asserts their absence rather than silently passing when someone re-adds one.
 */
export const TREE_VIEWS = [] as const;

export type TreeViewId = never;

/**
 * Nothing to register: the workbench view is a `WebviewViewProvider`,
 * registered in `extension.ts` where the host dependencies live. Retained so
 * activation keeps a single, stable call shape.
 */
export function registerViews(): vscode.Disposable[] {
  return [];
}
