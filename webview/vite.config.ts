import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    // The extension host serves the bundle through asWebviewUri under a CSP
    // nonce (VIGUIX_Final §17); a single hashed bundle keeps that trivially
    // correct — every resource it references is also hashed and same-origin.
    assetsInlineLimit: 0,
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
  },
});
