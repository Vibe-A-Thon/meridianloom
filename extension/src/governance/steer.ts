/**
 * Steer & clarify over hosted ACP sessions (FR-M25-01/02/03/04/06;
 * F1 Workstream D tasks 17-18).
 *
 * The HostedSteerController is the extension-host half of the M25 steering
 * surface. The sidecar owns the durable record (governor.steer RPCs, each
 * ledger-recorded before it returns — FR-M10-08); this controller owns the
 * wire and the liveness truth:
 *
 *  - beginSession wires a hosted ACP session into the HostedSessionRegistry
 *    for real (task 11's gate/halt seam becomes a real process kill) and
 *    reports the session facts (incl. the FR-M25-06 dry-run mode) to the
 *    sidecar; endSession unregisters and closes the ledger record;
 *  - steer() ledger-records the steering act FIRST, then injects the
 *    guidance into the RUNNING session over the real ACP wire — a second
 *    session/prompt on the same connection, the pinned
 *    @zed-industries/agent-client-protocol 0.4.5 turn-injection method
 *    (connection.prompt, already guarded by AcpClient.prompt);
 *  - clarifyingApprover() wraps the human approval path: a question-shaped
 *    permission request (ACP `_meta.question`, FR-M25-02) is ledger-recorded
 *    before the human sees it, the answer is recorded before it is released
 *    to the waiting agent — the loop resumes on answer;
 *  - confidence annotations on the wire (ACP `_meta.confidence` /
 *    `_meta.actionClass`, the protocol's extension point) below the
 *    per-class threshold raise a ledger-recorded escalation surfaced via
 *    onEscalation (FR-M25-03; the UI surface is workstream H);
 *  - accept()/acceptanceStatus() are partial acceptance per file/hunk
 *    (FR-M25-04); recordPlan() stores dry-run planner output (FR-M25-06);
 *  - status() is the honest capability payload (task 18): hosted is true
 *    only while THIS host runs the session process, so an observe-only
 *    session can never be offered a steer/clarify/halt control that does
 *    nothing. Attempts to steer a non-hosted session throw the structured
 *    NotHostedSessionError — an honest refusal, never a silent failure.
 *
 * Governor tier (FR-M36-05/G5): beginSession refuses when the governor
 * tier is disabled, mirroring createAcpClient. No model client of any
 * kind lives here (FR-M36-07 holds by nature).
 */
import { assertAcpHostEnabled } from '../acp/index';
import type { AcpClient, PermissionApprover } from '../acp/client';
import type { RequestPermissionRequest } from '../acp/protocol';
import type { TierName } from '../../../shared/ts/tiers';
import type { SessionMode } from '../adapters/permission-gate';
import type { HostedSessionRegistry } from './session-registry';

/** The sidecar surface the controller records through. */
export interface SteerSidecar {
  request(method: string, params: unknown): Promise<unknown>;
}

/** A resolved steer/question/... ack from the sidecar. */
interface SteerAck {
  accepted: boolean;
  sequence: number;
}

/** Structured, honest refusal: the session is observed, not hosted (task 18). */
export const NOT_HOSTED_CODE = 'NOT_HOSTED';

export class NotHostedSessionError extends Error {
  constructor(readonly sessionId: string) {
    super(
      `Session '${sessionId}' is observed, not hosted — Meridian did not launch ` +
        `this agent, so it cannot be steered or clarified at the session level. ` +
        `Observation and merge gating continue; steer and clarify are available ` +
        `for ACP sessions Meridian hosts.`,
    );
    this.name = 'NotHostedSessionError';
  }

  /** Mirrors the sidecar's NOT_HOSTED error data so both halves agree. */
  get data(): Record<string, unknown> {
    return {
      code: NOT_HOSTED_CODE,
      sessionId: this.sessionId,
      hosted: false,
      observedOnly: true,
      remediation:
        'Steering requires a hosted ACP session (one Meridian launched). ' +
        'For an observed agent, governance can still block its merge path (gate.halt, scope observe-only).',
    };
  }
}

export interface ClarifyingQuestionOption {
  optionId: string;
  name: string;
  recommended: boolean;
}

/** What the host surfaces (blocking) when an agent poses a question. */
export interface ClarifyingQuestionEvent {
  sessionId: string;
  question: string;
  options: ClarifyingQuestionOption[];
  /** The agent's own recommendation, when it stated one (FR-M25-02). */
  recommendation: string | undefined;
  toolCallId: string | undefined;
  /** Ledger sequence of the durable question — answers bind to it. */
  sequence: number;
}

/** What the host surfaces when stated confidence falls below the threshold. */
export interface EscalationEvent {
  sessionId: string;
  actionClass: string;
  confidence: number;
  threshold: number;
  toolCallId: string | undefined;
  sequence: number;
}

/**
 * Per-class confidence thresholds (FR-M25-03). Destructive classes demand
 * more certainty; an unknown class falls back to DEFAULT_THRESHOLD.
 */
export const DEFAULT_CONFIDENCE_THRESHOLDS: Readonly<Record<string, number>> = {
  read: 0.5,
  search: 0.5,
  think: 0.5,
  edit: 0.8,
  move: 0.9,
  execute: 0.9,
  delete: 0.95,
  unknown: 0.8,
  other: 0.8,
};
export const DEFAULT_CONFIDENCE_THRESHOLD = 0.8;

export function thresholdFor(
  actionClass: string,
  overrides?: Readonly<Record<string, number>>,
): number {
  const value = overrides?.[actionClass] ?? DEFAULT_CONFIDENCE_THRESHOLDS[actionClass];
  return typeof value === 'number' ? value : DEFAULT_CONFIDENCE_THRESHOLD;
}

/** ACP `_meta` extension point — how an agent marks a permission ask as a question. */
interface QuestionMeta {
  question?: unknown;
  questionText?: unknown;
  recommendation?: unknown;
}

function readQuestionMeta(request: RequestPermissionRequest): QuestionMeta | undefined {
  return request._meta as QuestionMeta | undefined;
}

/** A permission request is a clarifying question when the agent says so on
 * the wire (`_meta.question`); the tool-permission shape carries the
 * proposed options and the recommendation rides `_meta` / option `_meta`. */
export function isClarifyingQuestion(request: RequestPermissionRequest): boolean {
  return readQuestionMeta(request)?.question === true;
}

export function questionOptions(request: RequestPermissionRequest): ClarifyingQuestionOption[] {
  const meta = readQuestionMeta(request);
  const recommended = typeof meta?.recommendation === 'string' ? meta.recommendation : undefined;
  return request.options.map((option) => ({
    optionId: option.optionId,
    name: option.name,
    recommended:
      option.optionId === recommended ||
      (option._meta as { recommended?: unknown } | undefined)?.recommended === true,
  }));
}

export function questionText(request: RequestPermissionRequest): string {
  const meta = readQuestionMeta(request);
  return typeof meta?.questionText === 'string' && meta.questionText.trim()
    ? meta.questionText
    : (request.toolCall.title ?? 'The hosted agent asks for a decision.');
}

/** Stated confidence on the wire (ACP `_meta` extension point), when present. */
export function statedConfidence(request: RequestPermissionRequest): {
  actionClass: string;
  confidence: number;
} | undefined {
  const meta = request._meta as
    | { confidence?: unknown; actionClass?: unknown }
    | undefined;
  if (typeof meta?.confidence !== 'number') {
    return undefined;
  }
  return {
    actionClass: typeof meta.actionClass === 'string' ? meta.actionClass : 'unknown',
    confidence: meta.confidence,
  };
}

export interface HostedSteerControllerOptions {
  registry: HostedSessionRegistry;
  sidecar: SteerSidecar;
  /** The workspace's effective enabled tiers (governor gate, G5). */
  enabledTiers: () => readonly TierName[];
  /** Blocking question surface (vscode prompt in prod; workstream H renders). */
  onQuestion?: (event: ClarifyingQuestionEvent) => void;
  /** Escalation surface (FR-M25-03; UI is workstream H). */
  onEscalation?: (event: EscalationEvent) => void;
}

interface HostedRecord {
  client: AcpClient;
  adapterId: string;
  sessionId: string;
  mode: SessionMode;
  unregister: () => void;
}

export class HostedSteerController {
  private readonly records = new Map<string, HostedRecord>();

  constructor(private readonly options: HostedSteerControllerOptions) {}

  /** True while THIS host runs the session process (live hosted truth). */
  hosted(sessionId: string): boolean {
    return this.records.has(sessionId);
  }

  /**
   * Wire a hosted session into the registry for real: begin → registered
   * with the client handle (halt kills the process tree, so task 11's
   * gate/halt terminates an actually-running session); end → unregistered.
   */
  async beginSession(init: {
    client: AcpClient;
    sessionId: string;
    adapterId: string;
    cwd: string;
    mode?: SessionMode;
    agentVersion?: string;
  }): Promise<void> {
    assertAcpHostEnabled(this.options.enabledTiers());
    const mode = init.mode ?? 'normal';
    const unregister = this.options.registry.register(init.sessionId, {
      halt: (reason) => {
        void reason;
        // FR-M12-06: the registry owns the kill; the controller drops its
        // record in the same beat so post-halt capability answers
        // (status().hosted, steer) are honest immediately.
        this.records.delete(init.sessionId);
        init.client.stop();
      },
    });
    this.records.set(init.sessionId, {
      client: init.client,
      adapterId: init.adapterId,
      sessionId: init.sessionId,
      mode,
      unregister,
    });
    await this.options.sidecar.request('acp/sessionBegin', {
      agentId: init.adapterId,
      agentVersion: init.agentVersion,
      sessionId: init.sessionId,
      cwd: init.cwd,
      ...(mode !== 'normal' ? { mode } : {}),
    });
  }

  /** Unregister and close the ledger record. Safe to call twice. */
  async endSession(
    sessionId: string,
    end: { stopReason?: string; agentId?: string } = {},
  ): Promise<void> {
    const record = this.records.get(sessionId);
    this.records.delete(sessionId);
    record?.unregister();
    await this.options.sidecar.request('acp/sessionEnd', {
      sessionId,
      ...(end.agentId ?? record?.adapterId
        ? { agentId: end.agentId ?? record?.adapterId }
        : {}),
      ...(end.stopReason ? { stopReason: end.stopReason } : {}),
    });
  }

  private requireHosted(sessionId: string): HostedRecord {
    const record = this.records.get(sessionId);
    if (!record) {
      throw new NotHostedSessionError(sessionId);
    }
    return record;
  }

  /**
   * FR-M25-01: steer a running hosted session. The steering act is
   * ledger-recorded BEFORE the wire injection (FR-M10-08), then the
   * guidance enters the running session's context as a second
   * session/prompt on the live ACP connection.
   */
  async steer(
    sessionId: string,
    message: string,
  ): Promise<{ accepted: boolean; sequence: number; stopReason: string | undefined }> {
    const record = this.requireHosted(sessionId);
    const ack = (await this.options.sidecar.request('steer.send', {
      sessionId,
      message,
    })) as SteerAck;
    const stopReason = await record.client.prompt(sessionId, message);
    return { accepted: ack.accepted, sequence: ack.sequence, stopReason };
  }

  /**
   * FR-M25-02 + FR-M25-03: wrap the human approval path. Question-shaped
   * asks are recorded before the human sees them and their answers are
   * recorded before they are released to the waiting agent; stated
   * confidence below the per-class threshold raises an escalation first —
   * the agent asks rather than acting.
   */
  clarifyingApprover(sessionId: string, humanApprover: PermissionApprover): PermissionApprover {
    return async (request, context) => {
      const stated = statedConfidence(request);
      if (stated) {
        const threshold = thresholdFor(stated.actionClass);
        if (stated.confidence < threshold) {
          const ack = (await this.options.sidecar.request('steer/escalate', {
            sessionId,
            actionClass: stated.actionClass,
            confidence: stated.confidence,
            threshold,
            ...(request.toolCall.toolCallId
              ? { toolCallId: request.toolCall.toolCallId }
              : {}),
          })) as SteerAck & { escalated: boolean };
          this.options.onEscalation?.({
            sessionId,
            actionClass: stated.actionClass,
            confidence: stated.confidence,
            threshold,
            toolCallId: request.toolCall.toolCallId,
            sequence: ack.sequence,
          });
        }
      }

      if (!isClarifyingQuestion(request)) {
        return humanApprover(request, context);
      }

      // The question is durable BEFORE the human sees it.
      const asked = (await this.options.sidecar.request('steer/question', {
        sessionId,
        question: questionText(request),
        options: questionOptions(request),
        ...(request.toolCall.toolCallId ? { toolCallId: request.toolCall.toolCallId } : {}),
      })) as SteerAck;
      this.options.onQuestion?.({
        sessionId,
        question: questionText(request),
        options: questionOptions(request),
        recommendation:
          questionOptions(request).find((option) => option.recommended)?.optionId ?? undefined,
        toolCallId: request.toolCall.toolCallId,
        sequence: asked.sequence,
      });

      const decision = await humanApprover(request, context);

      // The answer is durable BEFORE it resumes the session.
      await this.options.sidecar.request('steer/answer', {
        sessionId,
        questionSequence: asked.sequence,
        ...(decision.outcome === 'selected' ? { selectedOptionId: decision.optionId } : {}),
        ...(decision.outcome === 'cancelled' ? { cancelled: true } : {}),
      });
      return decision;
    };
  }

  /** FR-M25-04: accept some hunks, rework others — one recorded action. */
  async accept(
    sessionId: string,
    accepted: { file: string; hunks: { index: number; digest?: string }[] }[],
    rejected: { file: string; hunks: { index: number; digest?: string }[] }[],
  ): Promise<SteerAck> {
    this.requireHosted(sessionId);
    return (await this.options.sidecar.request('steer/accept', {
      sessionId,
      accepted,
      rejected,
    })) as SteerAck;
  }

  /** FR-M25-04: the recorded acceptance state, from the ledger. */
  async acceptanceStatus(sessionId: string): Promise<unknown> {
    return this.options.sidecar.request('steer/acceptanceStatus', { sessionId });
  }

  /** FR-M25-06: dry-run planner output — the provable plan + cost. */
  async recordPlan(
    sessionId: string,
    entries: unknown[],
    costEstimate?: Record<string, unknown>,
  ): Promise<SteerAck> {
    this.requireHosted(sessionId);
    return (await this.options.sidecar.request('steer/plan', {
      sessionId,
      entries,
      ...(costEstimate ? { costEstimate } : {}),
    })) as SteerAck;
  }

  /**
   * Task 18: the capability payload session controls render from. hosted
   * is the live truth (this host runs the process); steerable is what a
   * control binds to. An observe-only session answers hosted: false — a
   * dead control is impossible by construction.
   */
  async status(sessionId: string): Promise<{
    sessionId: string;
    hosted: boolean;
    steerable: boolean;
    mode?: SessionMode;
    recorded: unknown;
  }> {
    const record = this.records.get(sessionId);
    const recorded = await this.options.sidecar.request('steer/status', { sessionId });
    return {
      sessionId,
      hosted: record !== undefined,
      steerable: record !== undefined,
      ...(record ? { mode: record.mode } : {}),
      recorded,
    };
  }
}
