import { describe, expect, it } from 'vitest';
import { mkdtemp, mkdir, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { matchingCommittedLine, resolveWorkspaceSource } from '../src/editor-surfaces';

describe('editor provenance integrity', () => {
  const lines = ['first', 'second'].map((content, index) => ({ content, line: index + 1, path: 'source.ts', commit: 'abc123', authorName: 'Human', authorEmail: 'human@example.test', authorTime: '2026-09-08' }));
  it('uses committed authorship only when the whole working copy matches HEAD', () => {
    expect(matchingCommittedLine('first\r\nsecond\r\n', lines, 2)).toEqual(lines[1]);
    expect(matchingCommittedLine('inserted\nfirst\nsecond\n', lines, 2)).toBeUndefined();
    expect(matchingCommittedLine('changed\nsecond\n', lines, 2)).toBeUndefined();
    expect(matchingCommittedLine('first\nsecond\n', lines, 3)).toBeUndefined();
  });
  it('allows only canonical paths inside the current workspace, including junction resolution', async () => {
    const parent = await mkdtemp(path.join(os.tmpdir(), 'meridian-editor-'));
    const root = path.join(parent, 'workspace'); const outside = path.join(parent, 'outside');
    await mkdir(root); await mkdir(outside); await writeFile(path.join(root, 'source.ts'), 'safe'); await writeFile(path.join(outside, 'other.ts'), 'outside');
    expect(await resolveWorkspaceSource(root, 'source.ts')).toBe(path.join(root, 'source.ts'));
    await expect(resolveWorkspaceSource(root, '../outside/other.ts')).rejects.toThrow(/inside/);
    await symlink(outside, path.join(root, 'linked'), process.platform === 'win32' ? 'junction' : 'dir');
    await expect(resolveWorkspaceSource(root, 'linked/other.ts')).rejects.toThrow(/inside/);
  });
});
