import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import { activate, startRuntime } from '../src/extension';
import { SecretStorageUnavailableError, SecretStore } from '../src/secrets';

function mockContext(secrets: vscode.SecretStorage): vscode.ExtensionContext {
  return { subscriptions: [], secrets };
}

/** Behaves like a Linux session with no keyring backend: every call throws. */
class BrokenSecretStorage implements vscode.SecretStorage {
  onDidChange = new vscode.EventEmitter<{ key: string }>().event;

  async get(): Promise<string | undefined> {
    throw new Error('No keyring is installed');
  }

  async store(): Promise<void> {
    throw new Error('No keyring is installed');
  }

  async delete(): Promise<void> {
    throw new Error('No keyring is installed');
  }
}

/** Accepts writes but silently corrupts reads — an untrustworthy backend. */
class CorruptSecretStorage extends vscode.MemorySecretStorage {
  override async get(): Promise<string | undefined> {
    return 'not-what-was-stored';
  }
}

describe('SecretStore (FR-M1-06)', () => {
  beforeEach(() => {
    (vscode as unknown as { __reset(): void }).__reset();
  });

  it('delegates get/store/delete to context.secrets', async () => {
    const secrets = new vscode.MemorySecretStorage();
    const store = new SecretStore(secrets);
    await store.store('meridian.modelKey', 'sk-test');
    expect(await store.get('meridian.modelKey')).toBe('sk-test');
    await store.delete('meridian.modelKey');
    expect(await store.get('meridian.modelKey')).toBeUndefined();
  });

  it('passes verification against a working SecretStorage', async () => {
    await expect(
      SecretStore.verifyAvailable(new vscode.MemorySecretStorage()),
    ).resolves.toBeUndefined();
  });

  it('refuses to start when SecretStorage throws (FR-M1-07)', async () => {
    await expect(
      SecretStore.verifyAvailable(new BrokenSecretStorage()),
    ).rejects.toBeInstanceOf(SecretStorageUnavailableError);
  });

  it('refuses to start when SecretStorage cannot round-trip a value (FR-M1-07)', async () => {
    await expect(
      SecretStore.verifyAvailable(new CorruptSecretStorage()),
    ).rejects.toBeInstanceOf(SecretStorageUnavailableError);
  });

  it('the refusal error is actionable', async () => {
    const failure = await SecretStore.verifyAvailable(
      new BrokenSecretStorage(),
    ).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(SecretStorageUnavailableError);
    const message = (failure as Error).message;
    expect(message).toMatch(/keyring/i);
    expect(message).toMatch(/never stores credentials in plaintext/i);
  });

  it('startRuntime surfaces the error and does not half-start', async () => {
    await startRuntime(mockContext(new BrokenSecretStorage()));
    const shown = (vscode as unknown as { __shownErrors: string[] }).__shownErrors;
    expect(shown).toHaveLength(1);
    expect(shown[0]).toMatch(/SecretStorage is unavailable/);
  });

  it('activation defers the SecretStorage probe off the call stack (FR-M1-04)', async () => {
    const secrets = new vscode.MemorySecretStorage();
    let probeStarted = false;
    const originalStore = secrets.store.bind(secrets);
    secrets.store = async (key: string, value: string) => {
      probeStarted = true;
      return originalStore(key, value);
    };
    activate(mockContext(secrets));
    expect(probeStarted).toBe(false);
    await new Promise((resolve) => setImmediate(resolve));
    expect(probeStarted).toBe(true);
  });
});

describe('ledger signing key provisioning (FR-M10-04, SEC-06)', () => {
  beforeEach(() => {
    (vscode as unknown as { __reset(): void }).__reset();
  });

  it('creates a fresh 32-byte base64 seed and persists it', async () => {
    const secrets = new vscode.MemorySecretStorage();
    const seed = await SecretStore.getOrCreateLedgerSigningKey(secrets);
    expect(Buffer.from(seed, 'base64')).toHaveLength(32);
    // Persisted: a second call over the same backing sees it.
    const again = await SecretStore.getOrCreateLedgerSigningKey(secrets);
    expect(again).toBe(seed);
  });

  it('separate keychains get separate seeds', async () => {
    const a = await SecretStore.getOrCreateLedgerSigningKey(
      new vscode.MemorySecretStorage(),
    );
    const b = await SecretStore.getOrCreateLedgerSigningKey(
      new vscode.MemorySecretStorage(),
    );
    expect(a).not.toBe(b);
  });
});
