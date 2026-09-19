import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { COMMANDS } from '../src/commands';
import { TREE_VIEWS, WORKBENCH_VIEW } from '../src/views';

const manifestPath = path.resolve(__dirname, '..', 'package.json');
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));

describe('extension manifest', () => {
  it('declares granular activation events and never "*" (FR-M1-01)', () => {
    const events: string[] = manifest.activationEvents;
    expect(Array.isArray(events)).toBe(true);
    expect(events.length).toBeGreaterThan(0);
    expect(events).not.toContain('*');
    for (const event of events) {
      expect(event).not.toBe('*');
      expect(event).not.toMatch(/^onLanguage$/);
    }
    expect(events).toContain('onStartupFinished');
    expect(events).toContain(`onView:${WORKBENCH_VIEW.id}`);
  });

  it('contributes one Activity Bar container (FR-M1-02)', () => {
    const containers = manifest.contributes.viewsContainers.activitybar;
    expect(containers).toHaveLength(1);
    expect(containers[0].id).toBe('meridian-loom');
  });

  it('contributes the workbench webview as the only view in the container (FR-M1-02)', () => {
    const views = manifest.contributes.views['meridian-loom'];
    // Selecting the plugin in the Activity Bar must open the product itself.
    // A single webview-typed view is what makes the container resolve
    // straight into the workbench, with no command in between.
    expect(views).toHaveLength(1);
    expect(views[0]).toMatchObject({
      type: 'webview',
      id: WORKBENCH_VIEW.id,
      name: WORKBENCH_VIEW.name,
    });
    // The five placeholder tree views are gone; their content is now tabs.
    expect(TREE_VIEWS).toHaveLength(0);
  });

  it('contributes the FR-M1-03 commands plus provenance hook, worktree, source-inspector, workbench and initiation commands', () => {
    const expected = [
      // The palette route to the workbench. The Activity Bar still reaches it
      // without any command; this is for keybindings and for reopening a
      // closed editor tab.
      'meridianLoom.open',
      'meridian.ingestStory',
      'meridian.openRecorder',
      'meridian.inspectSource',
      'meridian.installSkill',
      'meridian.onboardAgent',
      'meridian.exportAgent',
      'meridian.importAgent',
      'meridian.verifyChain',
      'meridian.haltAll',
      'meridian.steer',
      'meridian.dryRun',
      'meridian.abortStory',
      'meridian.doctor',
      // F0 Workstream E (FR-M36-03, D23): opt-in commit-msg trailer hook.
      'meridian.installHook',
      // F1 Workstream A task 5 (FR-M18-08): open a story worktree in a new window.
      'meridian.openWorktree',
      // MV2 (FR-M40-01/02): the command-palette door into run initiation.
      // Registered even below the Governor tier — the palette entry is
      // hidden by a `when` clause, but an unregistered id turns a keybinding
      // into a raw "command not found" instead of the disclosure X-28 asks
      // for. Absence is a property of the affordance, not of the id.
      'meridian.startRun',
    ];
    const contributed = manifest.contributes.commands.map(
      (c: { command: string }) => c.command,
    );
    expect(contributed).toHaveLength(expected.length);
    expect([...contributed].sort()).toEqual([...expected].sort());
    // Code and manifest share one source of truth.
    expect(COMMANDS.map((c) => c.id)).toEqual(contributed);
  });

  it('never repeats the category inside a command title', () => {
    // VS Code renders a palette entry as "Category: Title". A title that
    // already starts with the category shows it twice — which is exactly how
    // "Meridian Loom: Meridian Loom: Open Workbench" shipped. Ids were
    // checked against COMMANDS; titles were not checked at all.
    for (const entry of manifest.contributes.commands as Array<{
      command: string;
      title: string;
      category?: string;
    }>) {
      if (entry.category)
        expect(entry.title.startsWith(`${entry.category}:`)).toBe(false);
    }
  });

  it('keeps command titles in step with COMMANDS', () => {
    // commands.ts calls itself the single source of truth. That was only true
    // of ids; the titles could drift freely between the two files.
    const titles = new Map(
      (manifest.contributes.commands as Array<{ command: string; title: string }>).map(
        (entry) => [entry.command, entry.title],
      ),
    );
    for (const command of COMMANDS)
      expect(titles.get(command.id)).toBe(command.title);
  });

  it('is bundled by esbuild into dist/extension.js (FR-M1-10)', () => {
    expect(manifest.main).toBe('./dist/extension.js');
    expect(manifest.scripts['vscode:prepublish']).toBe('npm run build');
    expect(manifest.scripts.build).toContain('esbuild');
    expect(manifest.scripts.build).toContain('--external:vscode');
  });

  it('excludes sources, tests and dev assets via .vscodeignore (FR-M1-10)', () => {
    const ignore = readFileSync(
      path.resolve(__dirname, '..', '.vscodeignore'),
      'utf8',
    ).split(/\r?\n/);
    for (const pattern of ['src/**', 'test/**', '**/*.ts', '**/*.map']) {
      expect(ignore).toContain(pattern);
    }
  });
});

/**
 * Paths that must not exist and must not be tracked. Adding an entry is how a
 * regression of this class gets guarded for good; each one is repo-relative so
 * the same string works on disk, in `git ls-files`, and in the packager.
 */
const FORBIDDEN_PATHS = ['extension/extension'] as const;

const repoRoot = path.resolve(__dirname, '..', '..');

/** Files git tracks under `repoPath`, or [] when there are none. */
function tracked(repoPath: string): string[] {
  // Deliberately not tolerant of a missing git: this guard exists to answer a
  // question about what ships, and "git was unavailable so we assumed nothing
  // is tracked" is the same silent pass the filesystem check already gave us.
  const out = execFileSync('git', ['ls-files', '--', repoPath], {
    cwd: repoRoot,
    encoding: 'utf8',
  });
  return out.split('\n').filter((line) => line.trim().length > 0);
}

describe('what the package promises to ship', () => {
  const packager = readFileSync(
    path.join(__dirname, '..', '..', 'scripts', 'package-extension.mjs'),
    'utf8',
  );

  it('stages the open verifier into the VSIX (FR-M36-06 / SEC-29)', () => {
    // The product's central claim is that an exported audit bundle verifies
    // without Meridian installed. That claim was true of the repository and
    // false of the package: verifier/verify.py existed and was not shipped,
    // so a user who installed the extension had no way to check anything.
    // If this staging is ever removed, the README starts lying again.
    expect(packager).toContain("'verifier', 'verify.py'");
  });

  it('does not exclude the shipped library from the package', () => {
    // The library is what a new workspace is seeded from. Excluded from the
    // VSIX, every install would open to the empty catalogues the library
    // exists to fix — and nothing at runtime would say why, because an
    // unreadable library is deliberately not fatal.
    const ignore = readFileSync(
      path.resolve(__dirname, '..', '.vscodeignore'),
      'utf8',
    );
    for (const line of ignore.split(/\r?\n/)) {
      const rule = line.trim();
      if (!rule || rule.startsWith('#')) continue;
      expect(rule.startsWith('library')).toBe(false);
    }
    // And the files themselves are present to be shipped.
    expect(
      readdirSync(path.resolve(__dirname, '..', 'library', 'agents')).filter((name) =>
        name.endsWith('.md'),
      ).length,
    ).toBeGreaterThan(0);
  });

  it('ships an icon, so the Extensions view entry is identifiable', () => {
    // Without `icon` VS Code renders a blank placeholder — the first thing an
    // evaluator sees is an extension that looks unfinished.
    expect(manifest.icon).toBe('media/icon.png');
    expect(existsSync(path.resolve(__dirname, '..', manifest.icon))).toBe(true);
  });

  it('stages the documents an organisation reviews before installing', () => {
    // A VSIX sideloaded into an enterprise arrives without the repository, so
    // "the docs are in our repo" is not an answer when the repo is private.
    expect(packager).toContain('SECURITY-AND-DATA.md');
    expect(packager).toContain('DEPLOYMENT.md');
    for (const name of ['SECURITY-AND-DATA.md', 'DEPLOYMENT.md']) {
      expect(
        existsSync(path.resolve(__dirname, '..', '..', 'docs', name)),
      ).toBe(true);
    }
  });

  it('publishes a checksum, because the security document says it does', () => {
    // SECURITY-AND-DATA.md instructs an evaluator to compare a .sha256 before
    // installing. A document telling a reader to check something the build
    // never produces is worse than saying nothing at all.
    expect(packager).toContain('sha256');
    expect(packager).toContain('.sha256');
    const security = readFileSync(
      path.resolve(__dirname, '..', '..', 'docs', 'SECURITY-AND-DATA.md'),
      'utf8',
    );
    expect(security).toContain('.vsix.sha256');
  });

  it('has no nested extension/extension directory', () => {
    // A real regression, not a hypothetical one: a library-generation script
    // was once run from the wrong working directory and wrote a second copy
    // of the whole library to extension/extension/library/. It was committed
    // alongside the real one, so every VSIX shipped the library twice under
    // a path nothing ever reads — silent bloat, not a runtime symptom, which
    // is exactly why the earlier "count > 0" check above never caught it.
    expect(existsSync(path.resolve(__dirname, '..', 'extension'))).toBe(false);
  });

  it('has no forbidden path tracked in git, not merely absent from this checkout', () => {
    // The same regression came back, and this check is why it could. Asking
    // the filesystem whether extension/extension exists answers a question
    // about *this machine*: delete the folder and the assertion passes, even
    // though the 37 files are still at HEAD and the next clone — and so the
    // next VSIX — gets them back. That is exactly how it returned.
    //
    // A path that must never ship must be absent from both places. Disk
    // catches the generation script; the index catches the commit.
    for (const forbidden of FORBIDDEN_PATHS) {
      expect(tracked(forbidden)).toEqual([]);
    }
  });

  it('guards the same forbidden paths in the packager', () => {
    // Two lists that must agree, kept honest the way the rest of this file
    // keeps packager promises honest — by reading the packager's own text.
    // The test gate and the shipping gate drifting apart is how a guard ends
    // up protecting only the run nobody was worried about.
    for (const forbidden of FORBIDDEN_PATHS) {
      expect(packager).toContain(forbidden);
    }
  });

  it('ships the sidecar sources the extension resolves at runtime', () => {
    // Same class of promise: extension/src/layout.ts resolves <extension>/
    // sidecar, and an unstaged sidecar is an extension that cannot start.
    expect(packager).toContain("'core', 'meridian_core'");
    expect(packager).toContain("'shared', 'py'");
  });
});
