/**
 * The CycloneDX AI-BOM — `MVP-R7.3`, `FR-M50-04`, `NFR-48`, `SEC-44`,
 * `AC-62` (MV4-T08).
 *
 * The package ships 22 agents, a ten-pack skill catalogue, four instruction
 * documents and four ACP runtime presets, and published no bill of materials
 * for any of it. An enterprise that cannot enumerate what an extension
 * installed cannot approve it, and the fix is a build step rather than a
 * document somebody maintains.
 *
 * ## Generated from the package, never from the checkout
 *
 * Every component and every digest is read out of the built VSIX. That is
 * what makes `AC-62` — "every shipped component appears with a matching
 * digest" — true by construction rather than by diligence, and it is what
 * makes drift detectable at all: `--check` re-derives the document from the
 * artefact and compares. A hand-edited BOM fails. A VSIX rebuilt without
 * regenerating fails (`NFR-48`).
 *
 * ## What is in it, and what a reader should not conclude
 *
 * A shipped agent is **configuration**, not a model: a role, its permissions,
 * its bound skills, and — after a person binds one — a command naming
 * somebody else's runtime. CycloneDX has a `machine-learning-model` type and
 * this deliberately does not use it, because Meridian ships no model weights
 * and no inference code. Calling an agent card a model would be the same
 * category error as calling a recipe a meal, and in a bill of materials it
 * would send a reviewer looking for a model card that does not exist.
 *
 * ## SEC-44
 *
 * The document describes the package and nothing else. No workspace content,
 * no absolute paths from the build machine, no credentials, no customer
 * identifiers. The only inputs are the VSIX's own members and the licence
 * sweep's view of declared runtime dependencies.
 *
 * Usage:
 *   node scripts/generate-bom.mjs [path/to.vsix]     write dist/<name>.cdx.json
 *   node scripts/generate-bom.mjs --check [vsix]     fail on any drift
 */
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { findVsix, openZip } from './lib/vsix.mjs';
import { runLicenceSweep } from './check-licences.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** The spec this document claims to be. Stated, so a consumer can validate. */
const SPEC_VERSION = '1.6';

/**
 * Shipped things that are components in their own right, and how to read a
 * version out of each. Everything else in the package is a file of the
 * extension itself and is covered by the extension component's own digest.
 */
const LIBRARY_KINDS = [
  {
    prefix: 'extension/library/agents/',
    type: 'data',
    group: 'meridian.agents',
    // An agent card is a role description and a permission set, not a model.
    description: 'Shipped agent configuration: role, permissions, bound skills. No model weights and no inference code ship with it.',
  },
  {
    prefix: 'extension/library/skills/',
    type: 'data',
    group: 'meridian.skills',
    description: 'Skill pack: conventions, layout and build/test invocations for a stack.',
  },
  {
    prefix: 'extension/library/instructions/',
    type: 'data',
    group: 'meridian.instructions',
    description: 'Instruction document an agent is briefed from.',
  },
];

function readJson(text, where) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${where} is not JSON: ${error.message}`);
  }
}

/** Front matter or JSON `version`, else the package version. A guess is worse
 *  than the package version, which is at least true of the artefact. */
function versionOf(text, fallback) {
  const frontMatter = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  const body = frontMatter ? frontMatter[1] : text.slice(0, 2000);
  const match = /^\s*version:\s*["']?([^"'\r\n]+)["']?\s*$/m.exec(body);
  if (match) return match[1].trim();
  const json = /"version"\s*:\s*"([^"]+)"/.exec(text.slice(0, 2000));
  return json ? json[1] : fallback;
}

function titleOf(text, file) {
  const frontMatter = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  const body = frontMatter ? frontMatter[1] : '';
  const named = /^\s*(?:name|id|title):\s*["']?([^"'\r\n]+)["']?\s*$/m.exec(body);
  if (named) return named[1].trim();
  const heading = /^#\s+(.+)$/m.exec(text);
  if (heading) return heading[1].trim();
  return path.basename(file).replace(/\.[^.]+$/, '');
}

export function buildBom({ vsixPath, now } = {}) {
  const vsix = findVsix(vsixPath);
  if (!vsix || !existsSync(vsix)) {
    throw new Error(
      'no VSIX found in dist/. Run `npm run package` first — the BOM is generated ' +
        'from the artefact, not from the checkout.',
    );
  }
  const archive = openZip(vsix);
  const manifest = readJson(archive.read('extension/package.json'), 'extension/package.json');
  const version = manifest.version;
  const packageDigest = `sha256:${createHash('sha256')
    .update(readFileSync(vsix))
    .digest('hex')}`;

  const components = [];

  // -- the shipped library -------------------------------------------------
  for (const kind of LIBRARY_KINDS) {
    for (const name of archive.names.filter((entry) => entry.startsWith(kind.prefix)).sort()) {
      const text = archive.read(name);
      components.push({
        type: kind.type,
        'bom-ref': name,
        group: kind.group,
        name: titleOf(text, name),
        version: versionOf(text, version),
        description: kind.description,
        hashes: [{ alg: 'SHA-256', content: archive.digest(name).slice('sha256:'.length) }],
        properties: [{ name: 'meridian:path', value: name }],
      });
    }
  }

  // -- the ACP runtime presets ---------------------------------------------
  //
  // A preset is a command line pointing at somebody else's agent. It is
  // listed because a reviewer asking "what will this extension try to run?"
  // deserves the answer, and explicitly NOT as a dependency: the package does
  // not contain, fetch or vendor any of them.
  if (archive.names.includes('extension/library/runtimes.json')) {
    const text = archive.read('extension/library/runtimes.json');
    const presets = readJson(text, 'runtimes.json');
    const list = Array.isArray(presets) ? presets : (presets.runtimes ?? presets.presets ?? []);
    for (const preset of list) {
      components.push({
        type: 'application',
        'bom-ref': `runtime-preset:${preset.id ?? preset.name}`,
        group: 'meridian.runtime-presets',
        name: String(preset.name ?? preset.id),
        version: String(preset.version ?? 'unpinned'),
        description:
          'ACP runtime preset: a command line Meridian offers to bind. The package ' +
          'neither contains nor fetches this agent; a person installs and ' +
          'authenticates it themselves.',
        properties: [
          { name: 'meridian:command', value: String(preset.command ?? '') },
          { name: 'meridian:shipped', value: 'false' },
        ],
      });
    }
  }

  // -- declared runtime dependencies ---------------------------------------
  //
  // From the licence sweep, so the BOM and the no-copyleft claim in
  // docs/SECURITY-AND-DATA.md §7 read the same source. A dependency the sweep
  // could not resolve is listed with its licence unknown rather than omitted:
  // an absent row reads as "nothing there".
  for (const dep of runLicenceSweep().rows) {
    const ecosystem = dep.workspace === 'core' ? 'pypi' : 'npm';
    components.push({
      type: 'library',
      'bom-ref': `pkg:${ecosystem}/${dep.name}`,
      name: dep.name,
      version: 'declared',
      purl: `pkg:${ecosystem}/${dep.name}`,
      ...(dep.licence ? { licenses: [{ license: { name: dep.licence } }] } : {}),
      properties: [
        { name: 'meridian:workspace', value: dep.workspace },
        { name: 'meridian:licenceVerdict', value: dep.verdict },
      ],
    });
  }

  return {
    bomFormat: 'CycloneDX',
    specVersion: SPEC_VERSION,
    version: 1,
    metadata: {
      // A fixed timestamp when asked for one, so `--check` compares content
      // rather than clocks. A BOM that differs every time it is generated
      // cannot have drift detected in it.
      timestamp: (now ?? new Date()).toISOString(),
      tools: [{ vendor: 'Meridian Loom', name: 'generate-bom.mjs', version }],
      component: {
        type: 'application',
        'bom-ref': `meridian-loom@${version}`,
        name: manifest.name ?? 'meridian-loom',
        version,
        description:
          manifest.description ??
          'Meridian Loom: provenance and governance for agent-written code.',
        hashes: [{ alg: 'SHA-256', content: packageDigest.slice('sha256:'.length) }],
        properties: [
          { name: 'meridian:artefact', value: path.basename(vsix) },
          {
            name: 'meridian:scope',
            value:
              'Describes the contents of this package only. No workspace content, ' +
              'no credentials and no customer identifiers appear here (SEC-44).',
          },
        ],
      },
    },
    components,
  };
}

/** The path the BOM is published at, beside the VSIX and its checksum. */
export function bomPathFor(vsix) {
  return path.join(path.dirname(vsix), `${path.basename(vsix, '.vsix')}.cdx.json`);
}

/**
 * Everything except the timestamp, which is the only field allowed to differ
 * between two generations of the same package.
 */
function comparable(document) {
  const copy = JSON.parse(JSON.stringify(document));
  delete copy.metadata.timestamp;
  return JSON.stringify(copy);
}

export function checkBom({ vsixPath } = {}) {
  const vsix = findVsix(vsixPath);
  if (!vsix) return { ok: false, problems: ['no VSIX found in dist/'] };
  const published = bomPathFor(vsix);
  if (!existsSync(published)) {
    return {
      ok: false,
      problems: [
        `${path.basename(published)} is not published beside the package. ` +
          'Run `npm run bom` — the AI-BOM ships with the VSIX and its checksum.',
      ],
    };
  }
  const expected = buildBom({ vsixPath: vsix });
  let actual;
  try {
    actual = JSON.parse(readFileSync(published, 'utf8'));
  } catch (error) {
    return { ok: false, problems: [`${path.basename(published)} is not JSON: ${error.message}`] };
  }

  if (comparable(expected) === comparable(actual)) {
    return { ok: true, problems: [], components: expected.components.length, vsix, published };
  }

  // Name what differs, rather than "they differ". A reviewer holding a failed
  // build needs to know whether a component appeared, vanished, or changed.
  const problems = [];
  const index = (document) =>
    new Map(document.components.map((component) => [component['bom-ref'], component]));
  const before = index(actual);
  const after = index(expected);
  for (const [ref, component] of after) {
    if (!before.has(ref)) {
      problems.push(`the package ships ${ref}, which the published AI-BOM does not list`);
      continue;
    }
    if (JSON.stringify(before.get(ref)) !== JSON.stringify(component)) {
      const wasHash = before.get(ref).hashes?.[0]?.content;
      const nowHash = component.hashes?.[0]?.content;
      problems.push(
        wasHash && nowHash && wasHash !== nowHash
          ? `${ref} changed: the AI-BOM records sha256:${wasHash}, the package contains sha256:${nowHash}`
          : `${ref} differs between the AI-BOM and the package`,
      );
    }
  }
  for (const ref of before.keys()) {
    if (!after.has(ref)) {
      problems.push(`the AI-BOM lists ${ref}, which is not in the package`);
    }
  }
  if (JSON.stringify(before.size) !== JSON.stringify(after.size) && problems.length === 0) {
    problems.push('the component counts differ');
  }
  if (problems.length === 0) {
    problems.push('the AI-BOM metadata does not match the package');
  }
  return { ok: false, problems, vsix, published };
}

const invokedDirectly =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  const args = process.argv.slice(2);
  const check = args.includes('--check');
  const vsixPath = args.find((arg) => !arg.startsWith('--'));
  try {
    if (check) {
      const result = checkBom({ vsixPath });
      for (const problem of result.problems) console.error(`  ${problem}`);
      console.log(
        result.ok
          ? `ai-bom: ${result.components} components, every digest matching ${path.basename(result.vsix)}.`
          : `ai-bom: ${result.problems.length} discrepancy/discrepancies between the AI-BOM and the package.`,
      );
      process.exit(result.ok ? 0 : 1);
    }
    const vsix = findVsix(vsixPath);
    const document = buildBom({ vsixPath: vsix });
    const target = bomPathFor(vsix);
    writeFileSync(target, `${JSON.stringify(document, null, 2)}\n`, 'utf8');
    console.log(
      `ai-bom: ${document.components.length} components written to ${path.relative(root, target)}`,
    );
  } catch (error) {
    console.error(`  ${error.message}`);
    process.exit(1);
  }
}
