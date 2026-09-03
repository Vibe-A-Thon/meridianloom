import * as vscode from 'vscode';

const PROBE_KEY = 'meridianLoom.secretStorageProbe';

/**
 * FR-M1-07: surfaced when SecretStorage cannot round-trip a value (notably
 * Linux without a keyring backend). The message tells the user what to
 * install; the extension refuses to start rather than falling back to
 * plaintext storage.
 */
export class SecretStorageUnavailableError extends Error {
  override readonly cause?: unknown;

  constructor(cause?: unknown) {
    super(
      'Meridian Loom cannot start: VS Code SecretStorage is unavailable. ' +
        'On Linux, install a keyring backend such as gnome-keyring or KWallet ' +
        '(via libsecret), then restart VS Code. Meridian Loom never stores ' +
        'credentials in plaintext.',
    );
    this.name = 'SecretStorageUnavailableError';
    this.cause = cause;
  }
}

/**
 * FR-M1-06: the single access point for credentials. All model credentials
 * live in context.secrets; nothing is written to settings, workspace files
 * or logs.
 */
export class SecretStore {
  constructor(private readonly secrets: vscode.SecretStorage) {}

  get(key: string): Thenable<string | undefined> {
    return this.secrets.get(key);
  }

  store(key: string, value: string): Thenable<void> {
    return this.secrets.store(key, value);
  }

  delete(key: string): Thenable<void> {
    return this.secrets.delete(key);
  }

  /**
   * Startup check: round-trip a probe value through SecretStorage. Any
   * failure — throw, hang-free reject, or a mismatched read — means no
   * usable keyring, and the caller must refuse to start.
   */
  static async verifyAvailable(secrets: vscode.SecretStorage): Promise<void> {
    const probe = `probe-${Date.now()}`;
    try {
      await secrets.store(PROBE_KEY, probe);
      const roundTrip = await secrets.get(PROBE_KEY);
      await secrets.delete(PROBE_KEY);
      if (roundTrip !== probe) {
        throw new Error('SecretStorage probe round-trip mismatch');
      }
    } catch (error) {
      throw new SecretStorageUnavailableError(error);
    }
  }
}
