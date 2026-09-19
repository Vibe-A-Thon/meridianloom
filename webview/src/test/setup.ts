import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import { getVsCodeApi } from '../host/vscode-api';

afterEach(() => {
  cleanup();
  getVsCodeApi().setState(undefined);
  document.documentElement.removeAttribute('data-ml-theme');
  document.documentElement.removeAttribute('data-ml-density');
});
