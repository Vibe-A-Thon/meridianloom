import path from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      vscode: path.resolve(__dirname, 'test/__mocks__/vscode.ts'),
    },
  },
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node',
    // One Meridian suite at a time, across languages: this takes the same
    // lock file core/tests/conftest.py takes. Capping workers below stops
    // this suite starving itself; the lock stops it starving, or being
    // starved by, the Python suite.
    globalSetup: ['./test/run-lock.ts'],
    // Several files spawn the real Python sidecar or a real ACP subprocess.
    // Unbounded file parallelism starves those startups on a loaded machine
    // and they fail as "sidecar exited during startup" — a resource problem
    // wearing a correctness problem's clothes. Cap the pool so the suite's
    // result reflects the code rather than the host's spare capacity.
    minWorkers: 1,
    maxWorkers: 4,
  },
});
