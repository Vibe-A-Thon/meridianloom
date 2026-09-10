#!/usr/bin/env node
/**
 * Fake ACP agent — a test double of the WIRE, not of the host.
 *
 * Speaks real ACP (newline-delimited JSON-RPC 2.0 over stdio) per the
 * pinned @zed-industries/agent-client-protocol@0.4.5 schema: initialize,
 * session/new, session/load, session/prompt, session/cancel, and the
 * client methods reversed (session/update notifications,
 * session/request_permission, fs/read_text_file, fs/write_text_file,
 * terminal/*). It implements the actual protocol methods so the host is
 * exercised against a real subprocess channel, headless.
 *
 * Scenarios (argv flags) drive the scripted prompt turn:
 *   --protocol-version N  answer initialize with N (default 1)
 *   --refuse-version      answer initialize with 999 (unsupported)
 *   --no-load-session     do not advertise loadSession
 *   --crash               exit(1) mid-turn without answering the prompt
 *   --read-outside P      request fs/read_text_file at path P (escape probe)
 *   --steerable           the turn idles until a SECOND session/prompt
 *                         (steering) arrives mid-turn; the steering text is
 *                         acknowledged, echoed into output.txt, and the
 *                         original turn then completes (FR-M25-01)
 *   --ask-question        the turn poses a clarifying question as a
 *                         tool-permission-style ask: _meta.question with
 *                         proposed options and a recommendation
 *                         (FR-M25-02); the selected option is echoed into
 *                         output.txt
 *   --low-confidence      the permission request carries the ACP _meta
 *                         extension point with confidence 0.3 for class
 *                         execute (FR-M25-03)
 *
 * The turn script: message chunk → plan → tool_call → permission →
 * fs read → fs write → terminal run → final chunk → stopReason.
 * The content of output.txt records what actually happened so tests can
 * assert on real effects.
 */
import { createInterface } from 'node:readline';
import process from 'node:process';

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const opt = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const PROTOCOL_VERSION = flag('--refuse-version') ? 999 : Number(opt('--protocol-version') ?? '1');
const NO_LOAD = flag('--no-load-session');
const CRASH = flag('--crash');
const READ_OUTSIDE = opt('--read-outside');
const STEERABLE = flag('--steerable');
const ASK_QUESTION = flag('--ask-question');
const LOW_CONFIDENCE = flag('--low-confidence');

const SEP = process.platform === 'win32' ? '\\' : '/';
const WORKSPACE = process.cwd();

const rl = createInterface({ input: process.stdin, terminal: false });
const pending = new Map();
let nextAgentRequestId = 0;
let currentPrompt = null; // { id, sessionId } of the in-flight session/prompt
let permissionSettle = null; // settles the in-flight permission request
const steeringQueue = []; // guidance from a second session/prompt (FR-M25-01)
const steeringWaiters = [];

const send = (message) => process.stdout.write(JSON.stringify(message) + '\n');
const respond = (id, result) => send({ jsonrpc: '2.0', id, result });
const respondError = (id, code, message, data) =>
  send({ jsonrpc: '2.0', id, error: { code, message, data } });
const notify = (method, params) => send({ jsonrpc: '2.0', method, params });

/** Send a client request (agent → host) and track its settlement. */
function request(method, params) {
  const id = `agent-req-${nextAgentRequestId++}`;
  send({ jsonrpc: '2.0', id, method, params });
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

const sessions = new Set();

rl.on('line', (line) => {
  if (!line.trim()) return;
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }
  // Responses to our own requests.
  if (message.id !== undefined && ('result' in message || 'error' in message)) {
    const entry = pending.get(String(message.id));
    if (entry) {
      pending.delete(String(message.id));
      if (message.id === permissionSettle?.id) permissionSettle = null;
      if ('error' in message) entry.reject(new Error(JSON.stringify(message.error)));
      else entry.resolve(message.result);
    }
    return;
  }
  handleRequest(message).catch((error) => {
    if (message.id !== undefined) {
      respondError(message.id, -32603, String(error?.message ?? error));
    }
  });
});

async function handleRequest(message) {
  switch (message.method) {
    case 'initialize': {
      respond(message.id, {
        protocolVersion: PROTOCOL_VERSION,
        agentCapabilities: {
          loadSession: !NO_LOAD,
          promptCapabilities: { image: false, audio: false, embeddedContext: false },
        },
        agentInfo: { name: 'fake-acp-agent', version: '0.0.1' },
        authMethods: [],
      });
      return;
    }
    case 'session/new': {
      const sessionId = 'fake-session-1';
      sessions.add(sessionId);
      respond(message.id, { sessionId });
      return;
    }
    case 'session/load': {
      if (NO_LOAD) {
        respondError(message.id, -32601, 'method not found: session/load');
        return;
      }
      if (!sessions.has(message.params.sessionId)) {
        respondError(message.id, -32002, `no such session: ${message.params.sessionId}`);
        return;
      }
      respond(message.id, {});
      return;
    }
    case 'session/prompt': {
      const { sessionId } = message.params;
      if (currentPrompt) {
        // FR-M25-01: a prompt arriving while a turn is in flight IS
        // steering. Acknowledge the steering prompt on its own request,
        // queue the guidance for the running turn, and let that turn
        // finish (it echoes the steering into output.txt).
        const text = promptText(message.params);
        if (steeringWaiters.length > 0) {
          steeringWaiters.shift()(text);
        } else {
          steeringQueue.push(text);
        }
        respond(message.id, { stopReason: 'end_turn' });
        return;
      }
      currentPrompt = { id: message.id, sessionId };
      runTurn(sessionId, message.id).catch((error) => {
        respondError(message.id, -32603, String(error?.message ?? error));
      });
      return;
    }
    case 'session/cancel': {
      // Per the ACP cancellation rules: answer any pending permission with
      // the cancelled outcome, then finish the turn with stopReason
      // 'cancelled'.
      if (permissionSettle) {
        permissionSettle.entry.resolve({ outcome: 'cancelled' });
        pending.delete(permissionSettle.id);
        permissionSettle = null;
      }
      return;
    }
    default:
      respondError(message.id, -32601, `unknown method: ${message.method}`);
  }
}

function update(sessionId, update) {
  notify('session/update', { sessionId, update });
}

function promptText(params) {
  const blocks = Array.isArray(params?.prompt) ? params.prompt : [];
  return blocks
    .map((block) => (block && block.type === 'text' ? block.text : ''))
    .join('\n');
}

/** Resolve with the next steering message once one arrives mid-turn. */
function waitForSteering() {
  if (steeringQueue.length > 0) {
    return Promise.resolve(steeringQueue.shift());
  }
  return new Promise((resolve) => steeringWaiters.push(resolve));
}

async function runTurn(sessionId, promptId) {
  // Adversarial fixture: ask for a host effect without first asking the
  // cooperative session/request_permission question.
  const direct = opt('--direct-host-call');
  if (direct) {
    const call = JSON.parse(direct);
    await request(call.method, { ...call.params, sessionId });
    respond(promptId, { stopReason: 'end_turn' });
    currentPrompt = null;
    return;
  }
  const facts = [];
  update(sessionId, {
    sessionUpdate: 'agent_message_chunk',
    content: { type: 'text', text: 'Working on it.' },
  });
  update(sessionId, {
    sessionUpdate: 'plan',
    entries: [{ content: 'Do the scripted work', status: 'in_progress', priority: 'medium' }],
  });

  if (STEERABLE) {
    // FR-M25-01: idle mid-turn until the host steers the running session;
    // the steering text is the real effect the test asserts on.
    update(sessionId, {
      sessionUpdate: 'agent_message_chunk',
      content: { type: 'text', text: 'Idling; waiting for steering.' },
    });
    const steering = await waitForSteering();
    facts.push(`steered=${steering}`);
    update(sessionId, {
      sessionUpdate: 'agent_message_chunk',
      content: { type: 'text', text: `Steered: ${steering}` },
    });
    await request('fs/write_text_file', {
      sessionId,
      path: `${WORKSPACE}${SEP}output.txt`,
      content: facts.join('\n'),
    });
    update(sessionId, {
      sessionUpdate: 'agent_message_chunk',
      content: { type: 'text', text: 'Done.' },
    });
    respond(promptId, { stopReason: 'end_turn' });
    currentPrompt = null;
    return;
  }

  // 1. Tool call that requires host approval.
  update(sessionId, {
    sessionUpdate: 'tool_call',
    toolCallId: 'tc-permission',
    title: 'Run the test suite',
    kind: 'execute',
    status: 'pending',
  });
  const permissionRequest = {
    sessionId,
    toolCall: { toolCallId: 'tc-permission', title: 'Run the test suite', kind: 'execute' },
    options: [
      { optionId: 'allow-once', name: 'Allow once', kind: 'allow_once' },
      { optionId: 'allow-always', name: 'Always allow', kind: 'allow_always' },
      { optionId: 'reject-once', name: 'Reject', kind: 'reject_once' },
    ],
  };
  if (ASK_QUESTION) {
    // FR-M25-02: a clarifying question posed as a tool-permission-style
    // ask — proposed options, the recommendation marked on the wire.
    permissionRequest._meta = {
      question: true,
      questionText: 'Which backend should the cache use?',
      recommendation: 'opt-sqlite',
    };
    permissionRequest.options = [
      {
        optionId: 'opt-sqlite',
        name: 'SQLite (recommended)',
        kind: 'allow_once',
        _meta: { recommended: true },
      },
      { optionId: 'opt-memory', name: 'In-memory only', kind: 'allow_once' },
      { optionId: 'reject-once', name: 'Reject', kind: 'reject_once' },
    ];
  }
  if (LOW_CONFIDENCE) {
    // FR-M25-03: the agent states a below-threshold confidence via the
    // ACP _meta extension point.
    permissionRequest._meta = {
      ...(permissionRequest._meta ?? {}),
      confidence: 0.3,
      actionClass: 'execute',
    };
  }
  const permissionPromise = (async () => {
    const id = `agent-req-${nextAgentRequestId}`;
    const promise = request('session/request_permission', permissionRequest);
    permissionSettle = { id, entry: pending.get(id) };
    return promise;
  })();
  const permission = await permissionPromise;
  const allowed =
    permission.outcome && permission.outcome.outcome === 'selected'
      ? permission.outcome.optionId
      : 'cancelled';
  facts.push(`permission=${JSON.stringify(permission.outcome)}`);
  if (ASK_QUESTION && allowed !== 'cancelled') {
    facts.push(`answer=${allowed}`);
  }
  if (allowed === 'cancelled') {
    // The host cancelled the turn (session/cancel raced the approval).
    respond(promptId, { stopReason: 'cancelled' });
    currentPrompt = null;
    return;
  }
  if (CRASH) {
    process.stderr.write('fake agent crashing as requested\n');
    process.exit(1);
  }
  if (allowed === 'reject-once' || allowed === 'reject-always') {
    update(sessionId, {
      sessionUpdate: 'tool_call_update',
      toolCallId: 'tc-permission',
      status: 'failed',
    });
    update(sessionId, {
      sessionUpdate: 'agent_message_chunk',
      content: { type: 'text', text: 'Permission denied; stopping.' },
    });
    respond(promptId, { stopReason: 'refusal' });
    currentPrompt = null;
    return;
  }
  update(sessionId, {
    sessionUpdate: 'tool_call_update',
    toolCallId: 'tc-permission',
    status: 'completed',
  });

  // 2. Client-provided file system.
  try {
    const readPath = READ_OUTSIDE ?? `${WORKSPACE}${SEP}input.txt`;
    const read = await request('fs/read_text_file', { sessionId, path: readPath });
    facts.push(`read=${JSON.stringify(read.content)}`);
  } catch (error) {
    facts.push(`read_error=${error.message}`);
  }
  await request('fs/write_text_file', {
    sessionId,
    path: `${WORKSPACE}${SEP}output.txt`,
    content: facts.join('\n'),
  });

  // 3. Client-provided terminal.
  const terminal = await request('terminal/create', {
    sessionId,
    command: process.execPath,
    args: ['-e', 'console.log("hello-from-terminal")'],
    cwd: WORKSPACE,
  });
  const exit = await request('terminal/wait_for_exit', {
    sessionId,
    terminalId: terminal.terminalId,
  });
  facts.push(`terminal_exit=${exit.exitCode}`);
  await request('fs/write_text_file', {
    sessionId,
    path: `${WORKSPACE}${SEP}output.txt`,
    content: facts.join('\n'),
  });
  await request('terminal/release', { sessionId, terminalId: terminal.terminalId });

  update(sessionId, {
    sessionUpdate: 'agent_message_chunk',
    content: { type: 'text', text: 'Done.' },
  });
  respond(promptId, { stopReason: 'end_turn' });
  currentPrompt = null;
}
