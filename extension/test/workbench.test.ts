import {
  mkdtemp,
  readFile,
  writeFile,
  mkdir,
  symlink,
  readdir,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  WorkbenchService,
  validateWorkbenchAgent,
  type WorkbenchServiceOptions,
} from "../src/workbench/service";
import type {
  WorkbenchAgentInput,
  WorkbenchSnapshot,
} from "../../shared/ts/workbench";
import type { AdapterSession } from "../src/adapters/launch";
import { hostedSessionRegistry } from "../src/governance/session-registry";

const input = (id: string): WorkbenchAgentInput => ({
  id,
  name: id.toUpperCase(),
  role: "developer",
  description: "Portable specialist",
  vendor: "custom",
  version: "1.0.0",
  command: "test-acp-agent",
  args: [],
  instructions: "Inspect and explain.",
  permissions: ["read", "search", "think"],
  trainable: ["memory"],
});
const services: WorkbenchService[] = [];
afterEach(() => {
  services.splice(0).forEach((service) => service.dispose());
});
async function setup(overrides: Partial<WorkbenchServiceOptions> = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "meridian-workbench-"));
  const prompts: Array<{ id: string; text: string }> = [];
  const stops: string[] = [];
  const service = new WorkbenchService({
    workspaceDir: () => root,
    trusted: () => true,
    enabledTiers: () => ["flight-recorder", "governor"],
    sidecar: () => ({ request: async () => ({ entries: [] }) }),
    humanApprover: async () => ({ outcome: "cancelled" }),
    launcher: (agent, options) => ({
      adapterId: agent.id,
      pid: undefined,
      start: async () => ({
        protocolVersion: 1,
        agentCapabilities: {},
        authMethods: [],
      }),
      newSession: async () => agent.id,
      prompt: async (_session, text) => {
        prompts.push({ id: agent.id, text });
        options.onUpdate?.({
          sessionId: agent.id,
          update: {
            sessionUpdate: "agent_message_chunk",
            content: { type: "text", text: `Result from ${agent.id}` },
          },
        });
        return "end_turn";
      },
      stop: () => {
        stops.push(agent.id);
      },
    }),
    ...overrides,
  });
  services.push(service);
  const snapshot = async () =>
    (await service.request({ action: "snapshot" })) as WorkbenchSnapshot;
  return { root, service, snapshot, prompts, stops };
}
const save = (service: WorkbenchService, id: string) =>
  service.request({ action: "agent/save", params: { agent: input(id) } });
const activate = (service: WorkbenchService, id: string) =>
  service.request({ action: "agent/mode", params: { id, mode: "active" } });

describe("versioned studio documents", () => {
  const draft = {
    kind: "specification",
    title: "Keyboard navigation",
    body: "Every action is reachable.",
    tags: ["accessibility"],
  };
  it("persists revisions, rejects stale edits, and restores content as a new version", async () => {
    const { service, root, snapshot } = await setup();
    await service.request({
      action: "document/save",
      params: { document: draft },
    });
    const first = (await snapshot()).documents![0];
    await service.request({
      action: "document/save",
      params: {
        document: {
          ...draft,
          id: first.id,
          expectedVersion: 1,
          body: "Updated acceptance criteria",
        },
      },
    });
    await expect(
      service.request({
        action: "document/save",
        params: {
          document: {
            ...draft,
            id: first.id,
            expectedVersion: 1,
            body: "Stale overwrite",
          },
        },
      }),
    ).rejects.toThrow(/changed|version|conflict/i);
    expect((await snapshot()).documents![0]).toMatchObject({
      version: 2,
      body: "Updated acceptance criteria",
    });
    await service.request({
      action: "document/restore",
      params: { id: first.id, version: 1, expectedVersion: 2 },
    });
    expect((await snapshot()).documents![0]).toMatchObject({
      version: 3,
      body: draft.body,
    });
    const stored = JSON.parse(
      await readFile(path.join(root, ".meridian/workbench/state.json"), "utf8"),
    );
    expect(
      stored.documentRevisions.map((doc: { version: number }) => doc.version),
    ).toEqual([1, 2]);
    const reloaded = await setup({ workspaceDir: () => root });
    expect((await reloaded.snapshot()).documents![0]).toMatchObject({
      version: 3,
      body: draft.body,
    });
    await expect(
      service.request({
        action: "document/remove",
        params: { id: first.id, expectedVersion: 2 },
      }),
    ).rejects.toThrow();
    await service.request({
      action: "document/remove",
      params: { id: first.id, expectedVersion: 3 },
    });
    expect((await snapshot()).documents).toEqual([]);
    expect((await snapshot()).documentRevisions).toEqual([]);
  });
  it("round-trips portable documents with a fresh identity and refuses unsupported or malformed content", async () => {
    const one = await setup();
    const two = await setup();
    await one.service.request({
      action: "document/save",
      params: { document: draft },
    });
    const first = (await one.snapshot()).documents![0];
    const exported = (await one.service.request({
      action: "document/export",
      params: { id: first.id },
    })) as { content: string };
    await two.service.request({
      action: "document/import",
      params: { content: exported.content },
    });
    const imported = (await two.snapshot()).documents![0];
    expect(imported).toMatchObject({ ...draft, version: 1 });
    expect(imported.id).not.toBe(first.id);
    for (const content of [
      "{}",
      "{",
      JSON.stringify({
        kind: "meridian-studio-document",
        schemaVersion: 2,
        document: draft,
      }),
      JSON.stringify({
        kind: "meridian-studio-document",
        schemaVersion: 1,
        document: { ...draft, kind: "executable" },
      }),
    ]) {
      await expect(
        two.service.request({ action: "document/import", params: { content } }),
      ).rejects.toThrow();
    }
    expect((await two.snapshot()).documents).toHaveLength(1);
  });
  it("migrates earlier workspace state and retains a bounded restoration history", async () => {
    const first = await setup();
    await save(first.service, "existing");
    const file = path.join(first.root, ".meridian/workbench/state.json");
    const prior = JSON.parse(await readFile(file, "utf8"));
    delete prior.documents;
    delete prior.documentRevisions;
    await writeFile(file, JSON.stringify(prior));
    const next = await setup({ workspaceDir: () => first.root });
    expect((await next.snapshot()).agents[0].id).toBe("existing");
    expect((await next.snapshot()).documents).toEqual([]);
    await next.service.request({
      action: "document/save",
      params: { document: draft },
    });
    const id = (await next.snapshot()).documents![0].id;
    for (let version = 1; version <= 22; version++)
      await next.service.request({
        action: "document/save",
        params: {
          document: {
            ...draft,
            id,
            expectedVersion: version,
            body: String(version),
          },
        },
      });
    expect((await next.snapshot()).documentRevisions).toHaveLength(20);
    expect((await next.snapshot()).documents![0].version).toBe(23);
  }, 15_000);
});

describe("hosted task steering", () => {
  it("records guidance before delivering a second turn to the same session and rejects finished tasks", async () => {
    let finishTurn!: (reason: "end_turn") => void;
    const prompts: string[] = [];
    const request = vi.fn(async (method: string) =>
      method === "steer.send" ? { accepted: true, sequence: 42 } : {},
    );
    const { service, snapshot } = await setup({
      sidecar: () => ({ request }),
      launcher: (agent) => ({
        adapterId: agent.id,
        pid: undefined,
        start: async () => ({
          protocolVersion: 1,
          agentCapabilities: {},
          authMethods: [],
        }),
        newSession: async () => "wire-session",
        stop: () => {},
        prompt: async (sessionId, text) => {
          expect(sessionId).toBe("wire-session");
          prompts.push(text);
          if (prompts.length === 1)
            return new Promise((resolve) => {
              finishTurn = resolve;
            });
          return "end_turn";
        },
      }),
    });
    await save(service, "atlas");
    await activate(service, "atlas");
    await service.request({
      action: "agent/run",
      params: { id: "atlas", prompt: "Inspect the code." },
    });
    await until(async () => prompts.length === 1);
    const run = (await snapshot()).runs[0];
    await service.request({
      action: "run/steer",
      params: { id: run.id, message: "Check keyboard access too." },
    });
    expect(prompts).toHaveLength(1);
    expect((await snapshot()).runs[0].steering![0]).toMatchObject({
      state: "queued",
      sequence: 42,
    });
    finishTurn("end_turn");
    await until(async () => (await snapshot()).runs[0].state === "completed");
    expect(prompts[1]).toContain("Human steering (ledger #42)");
    expect(prompts[1]).toContain("Check keyboard access too.");
    expect((await snapshot()).runs[0].steering![0].state).toBe("sent");
    expect(request.mock.calls.map(([method]) => method)).toEqual([
      "acp/sessionBegin",
      "steer.send",
      "acp/sessionEnd",
    ]);
    await expect(
      service.request({
        action: "run/steer",
        params: { id: run.id, message: "Too late" },
      }),
    ).rejects.toThrow(/accepting guidance/);
  });
});
async function until(check: () => Promise<boolean>) {
  await vi.waitFor(async () => expect(await check()).toBe(true), {
    timeout: 3000,
    interval: 15,
  });
}

describe("persisted agent workbench", () => {
  it("creates Learning agents, edits and removes only the selected profile, and reloads from disk", async () => {
    const { service, root, snapshot } = await setup();
    await save(service, "atlas");
    await save(service, "sage");
    expect((await snapshot()).agents.map((a) => a.mode)).toEqual([
      "learning",
      "learning",
    ]);
    await activate(service, "atlas");
    await service.request({
      action: "agent/save",
      params: { agent: { ...input("atlas"), name: "Atlas revised" } },
    });
    const reloaded = new WorkbenchService({
      workspaceDir: () => root,
      trusted: () => true,
      enabledTiers: () => [],
      sidecar: () => undefined,
    });
    services.push(reloaded);
    const loaded = (await reloaded.request({
      action: "snapshot",
    })) as WorkbenchSnapshot;
    expect(loaded.agents[0]).toMatchObject({
      name: "Atlas revised",
      mode: "active",
    });
    await service.request({ action: "agent/remove", params: { id: "atlas" } });
    expect((await snapshot()).agents.map((a) => a.id)).toEqual(["sage"]);
    expect(
      JSON.parse(
        await readFile(
          path.join(root, ".meridian/workbench/state.json"),
          "utf8",
        ),
      ).agents,
    ).toHaveLength(1);
  });
  it("rejects invalid manifests and unsafe IDs without changing the saved state", async () => {
    const { service, snapshot } = await setup();
    await save(service, "atlas");
    await expect(
      service.request({
        action: "agent/save",
        params: { agent: { ...input("../escape") } },
      }),
    ).rejects.toThrow("ID");
    await expect(
      service.request({
        action: "agent/save",
        params: { agent: { ...input("broken"), permissions: ["superuser"] } },
      }),
    ).rejects.toThrow("ACP tool kind");
    expect((await snapshot()).agents).toHaveLength(1);
    expect(() =>
      validateWorkbenchAgent({
        ...input("secret"),
        args: ["--api-key=private"],
      }),
    ).toThrow("credentials");
  });
  it("exports a portable profile, imports without activation, and rejects duplicate imports", async () => {
    const one = await setup();
    const two = await setup();
    await save(one.service, "atlas");
    await activate(one.service, "atlas");
    const document = (await one.service.request({
      action: "agent/export",
      params: { id: "atlas" },
    })) as { content: string };
    const raw = JSON.parse(document.content);
    expect(raw.agent).not.toHaveProperty("mode");
    expect(raw).not.toHaveProperty("runs");
    await two.service.request({
      action: "agent/import",
      params: { content: document.content },
    });
    expect((await two.snapshot()).agents[0]).toMatchObject({
      id: "atlas",
      mode: "learning",
    });
    await expect(
      two.service.request({
        action: "agent/import",
        params: { content: document.content },
      }),
    ).rejects.toThrow("already exists");
  });
  it.each(["trust", "governor", "sidecar"] as const)(
    "refuses execution when %s is unavailable",
    async (blocked) => {
      const { service, snapshot } = await setup({
        ...(blocked === "trust"
          ? { trusted: () => false }
          : blocked === "governor"
            ? { enabledTiers: () => ["flight-recorder"] }
            : { sidecar: () => undefined }),
      });
      await save(service, "atlas");
      await activate(service, "atlas");
      await expect(
        service.request({
          action: "agent/run",
          params: { id: "atlas", prompt: "Work" },
        }),
      ).rejects.toThrow();
      expect((await snapshot()).runs).toHaveLength(0);
    },
  );
  it("dispatches only active agents, sequentially, and creates reviewable feedback for Learning agents", async () => {
    const { service, snapshot, prompts } = await setup();
    await save(service, "atlas");
    await save(service, "nova");
    await save(service, "sage");
    await activate(service, "atlas");
    await activate(service, "nova");
    await service.request({
      action: "deliverable/save",
      params: {
        title: "An accessible dialog",
        brief: "Verify keyboard focus and labels.",
      },
    });
    const deliverable = (await snapshot()).deliverables[0];
    await service.request({
      action: "deliverable/dispatch",
      params: { id: deliverable.id },
    });
    await until(
      async () => (await snapshot()).deliverables[0].state === "review",
    );
    expect(prompts.map((p) => p.id)).toEqual(["atlas", "nova"]);
    expect((await snapshot()).deliverables[0].agentIds).toEqual([
      "atlas",
      "nova",
    ]);
    expect((await snapshot()).runs[0].output).toContain("Result from atlas");
    await service.request({
      action: "deliverable/complete",
      params: {
        id: deliverable.id,
        feedback: "Always return focus to the trigger.",
      },
    });
    const note = (await snapshot()).learning[0];
    expect(note).toMatchObject({
      agentId: "sage",
      state: "pending",
      surface: "memory",
    });
    expect(note.content).toContain("return focus");
    await service.request({
      action: "learning/review",
      params: { id: note.id, decision: "accepted" },
    });
    await activate(service, "sage");
    await service.request({
      action: "agent/run",
      params: { id: "sage", prompt: "Review another dialog." },
    }, 15_000);
    await until(async () => prompts.some((p) => p.id === "sage"));
    expect(prompts.find((p) => p.id === "sage")!.text).toContain(
      "Human-reviewed memory",
    );
    expect(prompts.find((p) => p.id === "sage")!.text).toContain(
      "return focus",
    );
  }, 15_000);
  it("deactivation stops the owned process, cancels queued work, and excludes future dispatch", async () => {
    let stopped = 0;
    let prompted = false;
    const launcher: WorkbenchServiceOptions["launcher"] = (agent) =>
      ({
        adapterId: agent.id,
        pid: undefined,
        start: async () => ({
          protocolVersion: 1,
          agentCapabilities: {},
          authMethods: [],
        }),
        newSession: async () => "s",
        prompt: async (_id, _text, options) =>
          new Promise((resolve) => {
            prompted = true;
            options?.signal?.addEventListener(
              "abort",
              () => resolve("cancelled"),
              { once: true },
            );
          }),
        stop: () => {
          stopped++;
        },
      }) as AdapterSession;
    const { service, snapshot } = await setup({ launcher });
    await save(service, "atlas");
    await activate(service, "atlas");
    await service.request({
      action: "agent/run",
      params: { id: "atlas", prompt: "Long task" },
    });
    await until(async () => prompted);
    await service.request({
      action: "agent/mode",
      params: { id: "atlas", mode: "learning" },
    });
    await until(async () => (await snapshot()).runs[0].state === "cancelled");
    expect((await snapshot()).agents[0].mode).toBe("learning");
    await expect(
      service.request({
        action: "agent/run",
        params: { id: "atlas", prompt: "Another task" },
      }),
    ).rejects.toThrow("Learning agents");
    expect(stopped).toBeGreaterThan(0);
  });
  it("recovers interrupted runs as cancelled without automatically restarting them", async () => {
    const { service, root } = await setup();
    await save(service, "atlas");
    const file = path.join(root, ".meridian/workbench/state.json");
    const state = JSON.parse(await readFile(file, "utf8"));
    state.runs = [
      {
        id: "stale-run",
        agentId: "atlas",
        agentName: "Atlas",
        prompt: "Work",
        state: "running",
        startedAt: new Date().toISOString(),
      },
    ];
    await writeFile(file, JSON.stringify(state));
    const reloaded = new WorkbenchService({
      workspaceDir: () => root,
      trusted: () => true,
      enabledTiers: () => ["flight-recorder"],
      sidecar: () => undefined,
    });
    services.push(reloaded);
    const recovered = (await reloaded.request({
      action: "snapshot",
    })) as WorkbenchSnapshot;
    expect(recovered.runs[0].state).toBe("cancelled");
    expect(recovered.agents[0].runtime).toBe("idle");
  });
  it("leaves corrupt storage untouched and surfaces the error", async () => {
    const root = await mkdtemp(
      path.join(os.tmpdir(), "meridian-workbench-corrupt-"),
    );
    await mkdir(path.join(root, ".meridian/workbench"), { recursive: true });
    const file = path.join(root, ".meridian/workbench/state.json");
    await writeFile(file, "{not json");
    const { service } = await setup({ workspaceDir: () => root });
    await expect(save(service, "atlas")).rejects.toThrow();
    expect(await readFile(file, "utf8")).toBe("{not json");
  });
  it("does not write through a workspace junction or create descendants outside the workspace", async () => {
    const { service, root } = await setup();
    const outside = await mkdtemp(
      path.join(os.tmpdir(), "meridian-workbench-outside-"),
    );
    await symlink(
      outside,
      path.join(root, ".meridian"),
      process.platform === "win32" ? "junction" : "dir",
    );
    await expect(save(service, "atlas")).rejects.toThrow(
      "inside the workspace",
    );
    expect(await readdir(outside)).toEqual([]);
  });
  it("refuses edits after the workspace changes or closes", async () => {
    const original = await mkdtemp(
      path.join(os.tmpdir(), "meridian-workbench-context-"),
    );
    let current: string | undefined = original;
    const { service } = await setup({ workspaceDir: () => current });
    await save(service, "atlas");
    const file = path.join(original, ".meridian/workbench/state.json");
    const saved = await readFile(file, "utf8");
    current = os.tmpdir();
    await expect(save(service, "sage")).rejects.toThrow("workspace changed");
    current = undefined;
    await expect(save(service, "sage")).rejects.toThrow("workspace was closed");
    expect(await readFile(file, "utf8")).toBe(saved);
  });
  it.each(["sidecar disconnected", "governance halt"])(
    "stops an owned running session on %s",
    async (cause) => {
      let connected = true;
      let prompted = false;
      const stop = vi.fn();
      const { service, snapshot } = await setup({
        sidecar: () =>
          connected ? { request: async () => ({ entries: [] }) } : undefined,
        launcher: (agent) => ({
          adapterId: agent.id,
          pid: undefined,
          start: async () => ({
            protocolVersion: 1,
            agentCapabilities: {},
            authMethods: [],
          }),
          newSession: async () => "governed-session",
          prompt: async (_id, _text, options) =>
            new Promise((resolve) => {
              prompted = true;
              options?.signal?.addEventListener(
                "abort",
                () => resolve("cancelled"),
                {
                  once: true,
                },
              );
            }),
          stop,
        }),
      });
      await save(service, "atlas");
      await activate(service, "atlas");
      await service.request({
        action: "agent/run",
        params: { id: "atlas", prompt: "Review" },
      });
      await until(async () => prompted);
      if (cause === "sidecar disconnected") {
        connected = false;
        await service.reconcile();
      } else
        expect(
          hostedSessionRegistry.halt("governed-session", "Gate rejected"),
        ).toBe(true);
      await until(async () => (await snapshot()).runs[0].state === "cancelled");
      expect(stop).toHaveBeenCalled();
      await until(
        async () => !hostedSessionRegistry.ids().includes("governed-session"),
      );
    },
  );
  it("withholds a granted permission when its audit record fails", async () => {
    let decision: unknown;
    const humanApprover = vi.fn(async () => ({
      outcome: "selected" as const,
      optionId: "allow",
    }));
    const { service, root, snapshot } = await setup({
      humanApprover,
      sidecar: () => ({
        request: async (method) => {
          if (method === "acp/permissionDecision")
            throw new Error("Ledger unavailable");
          return { entries: [] };
        },
      }),
      launcher: (agent, options) => ({
        adapterId: agent.id,
        pid: undefined,
        start: async () => ({
          protocolVersion: 1,
          agentCapabilities: {},
          authMethods: [],
        }),
        newSession: async () => "s",
        stop: () => {},
        prompt: async () => {
          decision = await options.approvePermission!(
            {
              sessionId: "s",
              toolCall: { toolCallId: "t", title: "Read", kind: "read" },
              options: [
                { optionId: "allow", name: "Allow once", kind: "allow_once" },
              ],
            },
            {},
          );
          return "end_turn";
        },
      }),
    });
    await mkdir(path.join(root, ".meridian/policy"), { recursive: true });
    await writeFile(
      path.join(root, ".meridian/policy/acp-permissions.yaml"),
      "version: 1\nadapters:\n  '*':\n    probation: [read]\n",
    );
    await save(service, "atlas");
    await activate(service, "atlas");
    await service.request({
      action: "agent/run",
      params: { id: "atlas", prompt: "Inspect" },
    });
    await until(async () => (await snapshot()).runs[0].state === "completed");
    expect(humanApprover).toHaveBeenCalledOnce();
    expect(decision).toEqual({ outcome: "cancelled" });
  });
  it.each(["refusal", "max_tokens", "max_turn_requests"])(
    "does not mark a %s stop as a completed deliverable",
    async (reason) => {
      const { service, snapshot } = await setup({
        launcher: (agent) => ({
          adapterId: agent.id,
          pid: undefined,
          start: async () => ({
            protocolVersion: 1,
            agentCapabilities: {},
            authMethods: [],
          }),
          newSession: async () => "s",
          prompt: async () => reason,
          stop: () => {},
        }),
      });
      await save(service, "atlas");
      await activate(service, "atlas");
      await service.request({
        action: "deliverable/save",
        params: { title: "Review", brief: "Inspect the change." },
      });
      await service.request({
        action: "deliverable/dispatch",
        params: { id: (await snapshot()).deliverables[0].id },
      });
      await until(
        async () => (await snapshot()).deliverables[0].state === "failed",
      );
      expect((await snapshot()).runs[0].error).toContain(reason);
      await expect(
        service.request({
          action: "deliverable/complete",
          params: {
            id: (await snapshot()).deliverables[0].id,
            feedback: "Accept",
          },
        }),
      ).rejects.toThrow("Review the completed agent turns");
    },
  );
  it("runs an independent ACP subprocess through real stdio, permission approval, output streaming, and persistence", async () => {
    const decisions: unknown[] = [];
    const { service, root, snapshot } = await setup({
      launcher: undefined,
      humanApprover: async (request) => ({
        outcome: "selected",
        optionId: request.options.find(
          (option) => option.kind === "allow_once",
        )!.optionId,
      }),
      sidecar: () => ({
        request: async (method, params) => {
          if (method === "acp/permissionDecision") decisions.push(params);
          return { entries: [] };
        },
      }),
    });
    await mkdir(path.join(root, ".meridian/policy"), { recursive: true });
    await writeFile(
      path.join(root, ".meridian/policy/acp-permissions.yaml"),
      "version: 1\nadapters:\n  '*':\n    probation: [read, edit, execute]\n",
    );
    await writeFile(path.join(root, "input.txt"), "real workspace input");
    await service.request({
      action: "agent/save",
      params: {
        agent: {
          ...input("wire-agent"),
          command: process.execPath,
          args: [path.resolve("test/fixtures/fake-acp-agent.mjs")],
          permissions: ["read", "edit", "execute"],
        },
      },
    });
    await activate(service, "wire-agent");
    await service.request({
      action: "agent/run",
      params: {
        id: "wire-agent",
        prompt: "Run the fixture task independently.",
      },
    });
    await vi.waitFor(
      async () => expect((await snapshot()).runs[0].state).toBe("completed"),
      {
        timeout: 15_000,
        interval: 100,
      },
    );
    expect((await snapshot()).runs[0].output).toContain("Working on it.Done.");
    expect(await readFile(path.join(root, "output.txt"), "utf8")).toContain(
      "real workspace input",
    );
    expect(decisions.length).toBeGreaterThan(0);
    expect(
      JSON.parse(
        await readFile(
          path.join(root, ".meridian/workbench/state.json"),
          "utf8",
        ),
      ).runs[0].state,
    ).toBe("completed");
  }, 25_000);
  it("round-trips exported profiles with more than 500 KB and 100 reviewed memory notes", async () => {
    const one = await setup();
    const two = await setup();
    await save(one.service, "atlas");
    const file = path.join(one.root, ".meridian/workbench/state.json");
    const stored = JSON.parse(await readFile(file, "utf8"));
    stored.learning = Array.from({ length: 101 }, (_, index) => ({
      id: `note-${index}`,
      agentId: "atlas",
      deliverableId: "source-delivery",
      title: `Lesson ${index}`,
      content: "Portable reviewed context. ".repeat(210),
      state: "accepted",
      createdAt: new Date().toISOString(),
      surface: "memory",
    }));
    await writeFile(file, JSON.stringify(stored));
    const source = new WorkbenchService({
      workspaceDir: () => one.root,
      trusted: () => true,
      enabledTiers: () => [],
      sidecar: () => undefined,
    });
    services.push(source);
    const portable = (await source.request({
      action: "agent/export",
      params: { id: "atlas" },
    })) as { content: string };
    expect(Buffer.byteLength(portable.content)).toBeGreaterThan(500_000);
    await two.service.request({
      action: "agent/import",
      params: { content: portable.content },
    });
    const imported = await two.snapshot();
    expect(imported.learning).toHaveLength(101);
    expect(imported.learning.every((note) => note.state === "pending")).toBe(
      true,
    );
    expect(imported.agents[0].mode).toBe("learning");
  }, 15_000);
});
