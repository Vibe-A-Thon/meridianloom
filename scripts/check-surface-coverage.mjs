/**
 * Surface-coverage orphan check — FR-M46-01/02, AC-43 (status.md G-02).
 *
 * Enumerates every RPC method in the capability registry
 * (shared/schema/tiers.json), greps the interface consumers (webview/src and
 * extension/src, tests/mocks/fixtures excluded) for callers of each method
 * string, and fails on any orphan that is not declared in the reviewed
 * allowlist (shared/schema/unsurfaced.json).
 *
 * Allowlist entry schema (see shared/schema/unsurfaced.json):
 *   { method, reason, reviewed: "YYYY-MM-DD", mustSurface?: boolean }
 * - `mustSurface: true` marks an instrument that MUST gain an interface
 *   consumer (the check keeps failing until one exists) — the blocking gate
 *   for the GUI session (AC-43).
 * - Entries without `mustSurface` declare the method unsurfaced-yet-
 *   acceptable; `reason` must name the phase that will surface it or state
 *   that none is planned by design (FR-M46-01).
 *
 * Exit codes: 0 = clean; 1 = undeclared orphans, pending mustSurface
 * instruments, or allowlist schema errors.
 *
 * Machine-readable output for downstream consumers (the GUI session):
 *   node scripts/check-surface-coverage.mjs --json .meridian/surface-coverage.json
 */
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function parseArgs(argv) {
  const args = {
    registry: path.join(root, 'shared', 'schema', 'tiers.json'),
    methods: path.join(root, 'shared', 'schema', 'methods.json'),
    allowlist: path.join(root, 'shared', 'schema', 'unsurfaced.json'),
    roots: ['webview/src', 'extension/src'],
    json: undefined,
    quiet: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = () => {
      i += 1;
      if (i >= argv.length) fail(`missing value for ${arg}`);
      return argv[i];
    };
    if (arg === '--registry') args.registry = path.resolve(root, value());
    else if (arg === '--methods') args.methods = path.resolve(root, value());
    else if (arg === '--allowlist') args.allowlist = path.resolve(root, value());
    else if (arg === '--roots') args.roots = value().split(',').map((r) => r.trim()).filter(Boolean);
    else if (arg === '--json') args.json = path.resolve(root, value());
    else if (arg === '--quiet') args.quiet = true;
    else if (arg === '--help' || arg === '-h') {
      console.log('usage: node scripts/check-surface-coverage.mjs [--json <path>] [--quiet]');
      console.log('       [--registry <tiers.json>] [--methods <methods.json>]');
      console.log('       [--allowlist <unsurfaced.json>] [--roots <csv>]');
      process.exit(0);
    } else fail(`unknown argument: ${arg}`);
  }
  return args;
}

function fail(message) {
  console.error(`surface-coverage: ${message}`);
  process.exit(2);
}

function readJson(file, what) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch (error) {
    fail(`cannot read ${what} at ${file}: ${error.message}`);
  }
}

const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx', '.mts', '.cts', '.mjs', '.cjs']);
const EXCLUDED_SEGMENTS = ['__tests__', '__mocks__', 'fixtures'];

/** Recursively collect interface source files (absolute paths) under a consumer root. */
function collectSources(dir, into = []) {
  if (!existsSync(dir)) return into;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!EXCLUDED_SEGMENTS.includes(entry.name)) collectSources(full, into);
      continue;
    }
    if (!SOURCE_EXTENSIONS.has(path.extname(entry.name))) continue;
    if (/\.(test|spec)\.[^.]+$/.test(entry.name)) continue;
    into.push(full);
  }
  return into;
}

/** Best-effort display path relative to the repo root (absolute when cross-drive). */
function displayPath(rootDir, file) {
  const rel = path.relative(rootDir, file);
  return rel.startsWith('..') ? file : rel.split(path.sep).join('/');
}

/** Load the capability registry: every rpcMethod of every capability. */
function loadRegistry(registryPath) {
  const tiers = readJson(registryPath, 'capability registry (tiers.json)');
  const capabilities = tiers?.['x-tiers']?.capabilities;
  if (!Array.isArray(capabilities)) {
    fail(`registry at ${registryPath} has no x-tiers.capabilities array`);
  }
  const methods = new Map();
  for (const capability of capabilities) {
    if (!Array.isArray(capability.rpcMethods)) continue;
    for (const method of capability.rpcMethods) {
      methods.set(method, {
        method,
        capability: capability.id ?? 'unknown',
        tier: capability.tier ?? 'unknown',
      });
    }
  }
  return methods;
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Validate the allowlist; returns { entries: Map, errors: [] }. */
function loadAllowlist(allowlistPath, registry) {
  const empty = { entries: new Map(), errors: [] };
  if (!existsSync(allowlistPath)) return empty;
  const raw = readJson(allowlistPath, 'unsurfaced allowlist');
  // Accept either a bare array or a documented file wrapping its entries.
  const list = Array.isArray(raw) ? raw : raw?.entries;
  if (!Array.isArray(list)) {
    return { ...empty, errors: [`allowlist at ${allowlistPath} must be a JSON array or an object with an 'entries' array`] };
  }
  const entries = new Map();
  const errors = [];
  list.forEach((entry, index) => {
    const where = `allowlist[${index}]`;
    if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
      errors.push(`${where}: entry must be an object`);
      return;
    }
    if (typeof entry.method !== 'string' || !entry.method) {
      errors.push(`${where}: 'method' must be a non-empty string`);
      return;
    }
    if (!registry.has(entry.method)) {
      errors.push(`${where}: '${entry.method}' is not a registry method`);
    }
    if (typeof entry.reason !== 'string' || !entry.reason.trim()) {
      errors.push(`${where} (${entry.method}): 'reason' must be a non-empty string`);
    }
    if (typeof entry.reviewed !== 'string' || !DATE_RE.test(entry.reviewed)) {
      errors.push(`${where} (${entry.method}): 'reviewed' must be a YYYY-MM-DD date`);
    }
    if (entry.mustSurface !== undefined && typeof entry.mustSurface !== 'boolean') {
      errors.push(`${where} (${entry.method}): 'mustSurface' must be a boolean when present`);
    }
    if (entries.has(entry.method)) {
      errors.push(`${where}: duplicate entry for '${entry.method}'`);
    }
    if (!entries.has(entry.method)) entries.set(entry.method, entry);
  });
  return { entries, errors };
}

export function runSurfaceCoverage(options) {
  const args = options ?? parseArgs(process.argv.slice(2));
  const registry = loadRegistry(args.registry);
  const sources = args.roots
    .map((r) => path.resolve(root, r))
    .flatMap((dir) => collectSources(dir));

  /**
   * Source with comments removed.
   *
   * A bare substring match counted prose as a caller. `governance/
   * enforcementPoints` stopped being reported as an orphan the moment a
   * JSDoc block and an error message mentioned it by name — so the gate
   * that exists to keep an unreachable instrument visible (J6) was
   * silenced by a comment describing the very problem.
   */
  const withoutComments = (content) =>
    content
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|[^:])\/\/.*$/gm, '$1 ');

  const contents = new Map();
  const callersOf = (method) => {
    // A caller passes the method as a complete quoted string — that is what
    // `controller.execute('trust/score', …)` looks like. Requiring the whole
    // token rejects a method named *inside* a longer sentence, which is how
    // an error message that says "fetch it from governance/enforcementPoints"
    // was read as fetching it.
    const quoted = new RegExp(
      `(['"\`])${method.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')}\\1`,
    );
    const hits = [];
    for (const abs of sources) {
      let content = contents.get(abs);
      if (content === undefined) {
        content = withoutComments(readFileSync(abs, 'utf8'));
        contents.set(abs, content);
      }
      if (quoted.test(content)) hits.push(displayPath(root, abs));
    }
    return hits.sort();
  };

  // Cross-reference the interface contract (informational; methods.json may
  // carry notification aliases that are not consumer-facing RPC methods).
  let contractWarnings = [];
  if (existsSync(args.methods)) {
    const contract = readJson(args.methods, 'method contract (methods.json)');
    const contractMethods = new Set(Object.keys(contract?.['x-methods'] ?? {}));
    contractWarnings = [...registry.keys()]
      .filter((m) => !contractMethods.has(m))
      .map((m) => `${m} is in the capability registry but absent from methods.json`);
  }

  const { entries, errors: allowlistErrors } = loadAllowlist(args.allowlist, registry);

  const methods = [];
  const undeclaredOrphans = [];
  const mustSurfaceViolations = [];
  const staleEntries = [];
  const resolvedMustSurface = [];

  for (const meta of [...registry.values()].sort((a, b) => a.method.localeCompare(b.method))) {
    const callers = callersOf(meta.method);
    const entry = entries.get(meta.method);
    const row = {
      ...meta,
      callerCount: callers.length,
      callers,
      ...(entry ? { declared: { reason: entry.reason, reviewed: entry.reviewed, mustSurface: entry.mustSurface === true } } : {}),
    };
    methods.push(row);
    if (callers.length === 0) {
      if (!entry) {
        undeclaredOrphans.push(meta.method);
      } else if (entry.mustSurface === true) {
        mustSurfaceViolations.push({ method: meta.method, reason: entry.reason, reviewed: entry.reviewed });
      }
    } else if (entry) {
      if (entry.mustSurface === true) resolvedMustSurface.push(meta.method);
      else staleEntries.push(meta.method);
    }
  }

  const report = {
    $schema: 'meridian-loom/surface-coverage@1',
    generatedAt: new Date().toISOString(),
    registry: displayPath(root, args.registry),
    allowlist: displayPath(root, args.allowlist),
    roots: args.roots,
    methods,
    summary: {
      total: registry.size,
      surfaced: methods.filter((m) => m.callerCount > 0).length,
      declared: entries.size,
      undeclaredOrphans: undeclaredOrphans.length,
      mustSurfacePending: mustSurfaceViolations.length,
      mustSurfaceResolved: resolvedMustSurface.length,
    },
    problems: {
      undeclaredOrphans,
      mustSurfaceViolations,
      staleAllowlistEntries: staleEntries,
      resolvedMustSurface,
      allowlistErrors,
      contractWarnings,
    },
  };
  return { report, ok: undeclaredOrphans.length === 0 && mustSurfaceViolations.length === 0 && allowlistErrors.length === 0 };
}

function printHuman(report, ok) {
  const { summary, problems } = report;
  for (const method of report.methods) {
    if (method.callerCount === 0) {
      const tag = method.declared?.mustSurface ? 'MUST-SURFACE' : method.declared ? 'declared' : 'ORPHAN';
      console.log(`  ${method.method.padEnd(28)} 0 callers  [${tag}]`);
    }
  }
  console.log(
    `surface-coverage: ${summary.surfaced}/${summary.total} registry methods have interface consumers; ` +
      `${summary.declared} declared unsurfaced.`,
  );
  for (const m of problems.undeclaredOrphans) console.error(`  UNDECLARED ORPHAN: ${m}`);
  for (const v of problems.mustSurfaceViolations) console.error(`  MUST-SURFACE (no consumer yet): ${v.method} — ${v.reason}`);
  for (const e of problems.allowlistErrors) console.error(`  ALLOWLIST: ${e}`);
  for (const m of problems.staleAllowlistEntries) console.warn(`  note: ${m} now has consumers; its allowlist entry can be removed.`);
  for (const w of problems.contractWarnings) console.warn(`  note: ${w}`);
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const args = parseArgs(process.argv.slice(2));
  const { report, ok } = runSurfaceCoverage(args);
  if (args.json) {
    writeFileSync(args.json, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    if (!args.quiet) console.log(`surface-coverage: JSON report written to ${path.relative(root, args.json)}`);
  }
  if (!args.quiet) printHuman(report, ok);
  process.exit(ok ? 0 : 1);
}
