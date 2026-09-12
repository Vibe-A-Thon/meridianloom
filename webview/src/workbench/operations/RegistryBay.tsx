import { useState } from "react";
import type {
  RegistryBrowseResult,
  RegistryInstallResult,
} from "../../../../shared/ts/workbench";
import { ErrorNotice } from "./shared";
import type { WorkbenchController } from "../useWorkbench";
import s from "./operations.module.css";

/**
 * The ACP Registry in the Adapter Bay — `FR-M34-03` (MV3-T02).
 *
 * `registry-source.ts` had been a working client with no user for as long as
 * it had existed. This is the user.
 *
 * Three things it must keep being true about:
 *
 *  - **It fetches only when pressed.** There is no `useEffect` here that
 *    loads on mount, and there must never be one: `docs/SECURITY-AND-DATA.md`
 *    §2 says Meridian does not phone home, and opening a tab that quietly
 *    reached somebody else's server would make that false.
 *  - **A listing is not a recommendation.** The registry lists; it does not
 *    vouch. The panel says so in the same register as the release `.sha256`
 *    paragraph — what it proves, and then what it does not.
 *  - **Five states, not one error** (`B2`). Never fetched, fetched, stale,
 *    unreachable and malformed are five different things to do next.
 */

export interface RegistryBayProps {
  controller: WorkbenchController;
  /** Refresh the roster after an install lands an agent in Learning. */
  onInstalled?: () => void;
}

/** The one line under the heading, per state. */
const STATE_SUMMARY: Record<RegistryBrowseResult["state"], string> = {
  idle: "Not fetched. Browsing reaches the network, so Meridian waits to be asked.",
  fresh: "Fetched just now.",
  "cached-stale": "Showing a cached copy — the registry could not be reached.",
  unreachable: "The registry could not be reached, and nothing was cached.",
  malformed: "The registry answered, and its index could not be read.",
};

export function RegistryBay({ controller, onInstalled }: RegistryBayProps) {
  const [result, setResult] = useState<RegistryBrowseResult | undefined>();
  const [installing, setInstalling] = useState<string | undefined>();
  const [installed, setInstalled] = useState<RegistryInstallResult["installed"]>();
  const [error, setError] = useState<string | undefined>();

  async function browse() {
    setError(undefined);
    setInstalled(undefined);
    try {
      setResult(await controller.execute("registry/browse", {}));
    } catch (cause) {
      setError((cause as Error).message);
    }
  }

  async function install(id: string) {
    setError(undefined);
    setInstalling(id);
    try {
      const outcome = await controller.execute("registry/install", { id });
      if (!outcome.ok) {
        setError(outcome.errors.join("; "));
        return;
      }
      setInstalled(outcome.installed);
      onInstalled?.();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setInstalling(undefined);
    }
  }

  return (
    <section className={s.panel} data-testid="registry-bay">
      <h2>ACP Registry</h2>
      <p>
        Agents published to the Agent Client Protocol registry. Meridian reads
        the index when you ask it to and installs an entry into Learning, with
        the same read/search/think floor an imported agent gets.
      </p>
      {/*
        MP5/G4: say what it proves, then say what it does not. A listing is a
        publication, not an endorsement, and a browse surface that omits that
        invites a reader to supply the missing reassurance themselves.
      */}
      <p className={s.notice} data-testid="registry-disclaimer">
        A registry listing establishes that somebody published an entry under
        that name. It is not a review, not a security assessment, and not an
        endorsement — neither by the registry nor by Meridian. Installed
        contents are pinned by digest so later changes are refused, which says
        nothing about whether the original contents were safe.
      </p>

      <div className={s.actions}>
        <button
          className={s.primary}
          disabled={controller.busy}
          onClick={() => void browse()}
          data-testid="registry-browse"
        >
          {result ? "Refresh the index" : "Browse the registry…"}
        </button>
      </div>

      <ErrorNotice error={error} />

      {installed && (
        <p className={s.notice} data-testid="registry-installed">
          Installed <strong>{installed.id}</strong> into Learning with{" "}
          {installed.permissions.join(", ")}. Pinned as {installed.pinDigest}.
          It cannot run until you bind and activate it.
        </p>
      )}

      {result && (
        <>
          <p data-testid="registry-state">
            <strong>{STATE_SUMMARY[result.state]}</strong>
            {result.fetchedAt ? ` (${result.fetchedAt})` : ""}
          </p>
          {result.notice && (
            <p className={s.notice} data-testid="registry-notice">
              {result.notice}
            </p>
          )}
          {result.entries.length === 0 ? (
            // Deliberately not an "empty registry" message: the reason the
            // list is empty is in the state above, and P26 says the unknown
            // is reported rather than absorbed into a zero.
            <p data-testid="registry-empty">
              No entries to show. See the state above for why.
            </p>
          ) : (
            <div className={s.grid}>
              {result.entries.map((entry) => (
                <section className={s.panel} key={entry.id}>
                  <h2>
                    {entry.name} <span className={s.badge}>{entry.version}</span>
                  </h2>
                  <p>{entry.description || "No description published."}</p>
                  <p>
                    {entry.authors.length
                      ? `Published by ${entry.authors.join(", ")}`
                      : "No publisher named"}
                    {entry.license ? ` · ${entry.license}` : ""}
                  </p>
                  <p>Launches via: {entry.distributions.join(", ") || "unstated"}</p>
                  {/*
                    FR-M44-01, said before the install rather than after. An
                    npx or uvx entry fetches its package at launch, so nothing
                    Meridian can digest identifies the agent that runs.
                  */}
                  <p data-testid={`registry-identity-${entry.id}`}>
                    {entry.identityVerifiable
                      ? "Ships a platform binary, so the agent that runs can be identified by digest."
                      : "Fetches its package at launch, so Meridian cannot identify which build runs. Attribution from it is recorded as unverified."}
                  </p>
                  <div className={s.actions}>
                    <button
                      disabled={controller.busy || installing === entry.id}
                      onClick={() => void install(entry.id)}
                      data-testid={`registry-install-${entry.id}`}
                    >
                      {installing === entry.id
                        ? "Installing…"
                        : "Install into Learning"}
                    </button>
                    {entry.website && (
                      <a href={entry.website} rel="noreferrer noopener">
                        Publisher's page
                      </a>
                    )}
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
