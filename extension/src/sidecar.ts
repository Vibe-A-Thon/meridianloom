/**
 * Boundary to the sidecar process. The real framed JSON-RPC-over-stdio
 * client lands in Workstream B; until then this interface is the seam every
 * host-side caller programs against.
 *
 * FR-M1-04: all orchestration executes behind this boundary, never on the
 * extension host thread.
 * FR-M1-09: every request carries an AbortSignal; aborting it must cancel
 * the corresponding work in the sidecar loop.
 */
export interface SidecarClient {
  request<TResponse>(
    method: string,
    params: unknown,
    signal: AbortSignal,
  ): Promise<TResponse>;
}
