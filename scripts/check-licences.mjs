/**
 * Runtime licence sweep — MV0-T05, ECO-03, principle MP5.
 *
 * `docs/SECURITY-AND-DATA.md` §7 tells a security reviewer: "No runtime
 * dependency is copyleft; all are Apache-2.0, MIT, BSD or ISC. Bundled fonts
 * are SIL OFL-1.1 (attribution only)."
 *
 * That was an assertion with a manual check behind it, which is the same shape
 * as every other defect the freeze audit found: true on the day someone looked,
 * unguarded afterwards. This makes it a claim that fails the build when it
 * stops being true.
 *
 * Runtime only. Dev dependencies do not ship, so their licences are a
 * different (and much weaker) question — conflating the two is how a sweep
 * ends up either noisy or dishonest.
 *
 * Python licences are read from installed distribution metadata, so the check
 * reports `skipped` rather than `ok` when the sidecar's environment is not
 * present. A sweep that silently passes because it could not look is worse
 * than one that says so.
 *
 * Exit codes: 0 = every resolvable runtime licence is permitted; 1 = a
 * copyleft or unknown licence, listed.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Permitted for anything that ships. */
const PERMITTED = [/apache-2/i, /\bmit\b/i, /\bbsd\b/i, /\bisc\b/i];
/** Fonts are attribution-only and permitted, but called out separately. */
const FONT_LICENCE = /ofl-1\.1|open font license/i;
/** Any of these in a runtime dependency is a stop. */
const COPYLEFT = /\b(a?gpl|lgpl|mpl|epl|cddl|sspl|cc-by-sa)\b/i;

function nodeRuntimeDeps() {
  const found = [];
  for (const workspace of ['extension', 'webview']) {
    const manifest = path.join(root, workspace, 'package.json');
    if (!existsSync(manifest)) continue;
    const deps = JSON.parse(readFileSync(manifest, 'utf8')).dependencies ?? {};
    for (const name of Object.keys(deps)) found.push({ name, workspace });
  }
  return found;
}

function nodeLicence(name) {
  for (const base of [root, path.join(root, 'extension'), path.join(root, 'webview')]) {
    const manifest = path.join(base, 'node_modules', name, 'package.json');
    if (!existsSync(manifest)) continue;
    const pkg = JSON.parse(readFileSync(manifest, 'utf8'));
    const licence = pkg.license ?? pkg.licenses;
    if (typeof licence === 'string') return licence;
    if (Array.isArray(licence)) return licence.map((l) => l.type ?? l).join(' OR ');
    if (licence?.type) return licence.type;
  }
  return undefined;
}

function pythonRuntimeDeps() {
  const pyproject = path.join(root, 'core', 'pyproject.toml');
  if (!existsSync(pyproject)) return [];
  const text = readFileSync(pyproject, 'utf8');
  // The first `dependencies = [ ... ]` is the runtime set; the optional
  // extras live under [project.optional-dependencies] and are not shipped.
  const block = text.split('dependencies = [')[1]?.split(']')[0] ?? '';
  return [...block.matchAll(/"([^"]+)"/g)]
    .map((m) => m[1].split(/[=<>~!]/)[0].trim())
    .filter(Boolean)
    .map((name) => ({ name, workspace: 'core' }));
}

function pythonLicences(names) {
  if (names.length === 0) return {};
  const script = [
    'import importlib.metadata as md, json',
    'out={}',
    `for n in ${JSON.stringify(names)}:`,
    '    try:',
    '        m=md.metadata(n)',
    "        lic=(m.get('License-Expression') or m.get('License') or '').strip()",
    '        if not lic or len(lic)>60:',
    "            cls=[c for c in (m.get_all('Classifier') or []) if c.startswith('License ::')]",
    "            lic=cls[0].split('::')[-1].strip() if cls else ''",
    '        out[n]=lic',
    '    except Exception:',
    '        out[n]=None',
    'print(json.dumps(out))',
  ].join('\n');
  for (const exe of ['python', 'python3']) {
    try {
      return JSON.parse(execFileSync(exe, ['-c', script], { encoding: 'utf8' }));
    } catch {
      /* try the next interpreter */
    }
  }
  return {};
}

function classify(licence) {
  if (!licence) return 'unknown';
  if (COPYLEFT.test(licence)) return 'copyleft';
  if (FONT_LICENCE.test(licence)) return 'font';
  if (PERMITTED.some((re) => re.test(licence))) return 'permitted';
  return 'unknown';
}

export function runLicenceSweep() {
  const rows = [];
  for (const dep of nodeRuntimeDeps()) {
    const licence = nodeLicence(dep.name);
    rows.push({ ...dep, licence, verdict: licence ? classify(licence) : 'skipped' });
  }
  const pyDeps = pythonRuntimeDeps();
  const pyLicences = pythonLicences(pyDeps.map((d) => d.name));
  for (const dep of pyDeps) {
    const licence = pyLicences[dep.name] || undefined;
    const present = Object.prototype.hasOwnProperty.call(pyLicences, dep.name);
    rows.push({
      ...dep,
      licence,
      verdict: !present || (present && pyLicences[dep.name] === null) ? 'skipped' : classify(licence),
    });
  }
  const blocking = rows.filter((r) => r.verdict === 'copyleft' || r.verdict === 'unknown');
  return { ok: blocking.length === 0, rows, blocking };
}

const isMain =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const { ok, rows, blocking } = runLicenceSweep();
  for (const r of rows) {
    console.log(
      `  ${r.workspace.padEnd(10)} ${r.name.padEnd(42)} ${(r.licence ?? '—').padEnd(34)} ${r.verdict}`,
    );
  }
  const skipped = rows.filter((r) => r.verdict === 'skipped').length;
  if (ok) {
    console.log(
      `licences: ${rows.length - skipped} runtime dependencies resolved, none copyleft` +
        (skipped ? `; ${skipped} skipped (metadata not installed here)` : '') +
        '. docs/SECURITY-AND-DATA.md §7 holds.',
    );
  } else {
    for (const b of blocking) {
      console.error(`  ${b.name}: ${b.licence ?? 'licence not resolvable'} (${b.verdict})`);
    }
    console.error(
      'licences: a runtime dependency is copyleft or unidentifiable. ' +
        'docs/SECURITY-AND-DATA.md §7 says otherwise — fix the dependency or the document.',
    );
  }
  process.exit(ok ? 0 : 1);
}
