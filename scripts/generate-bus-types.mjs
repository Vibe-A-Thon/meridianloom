/**
 * Generates the shared message-bus types from shared/schema/ (FR-M32-09).
 *
 *   node scripts/generate-bus-types.mjs          regenerate in place
 *   node scripts/generate-bus-types.mjs --check  fail if outputs are stale
 *
 * Outputs:
 *   shared/ts/bus-types.ts   — TypeScript interfaces/unions (extension, webview)
 *   shared/py/bus_types.py   — Python TypedDicts/Literals (core, simulation)
 *
 * Supported schema dialect (deliberately small — extend here, not ad hoc):
 * type (string|integer|number|boolean|object|array, or a list of those),
 * properties/required/additionalProperties, enum, const, items, $ref
 * ("#/…" local or "file.json#/…" cross-file), and an empty schema {} for
 * "any JSON value". Custom keys: x-protocol-version, x-error-codes,
 * x-methods.
 *
 * Output is deterministic (schema declaration order, stable formatting) so
 * --check is a byte comparison after line-ending normalisation.
 */
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const schemaDir = path.join(root, 'shared', 'schema');
const tsOut = path.join(root, 'shared', 'ts', 'bus-types.ts');
const pyOut = path.join(root, 'shared', 'py', 'bus_types.py');
const checkMode = process.argv.includes('--check');

// ---- schema loading --------------------------------------------------------

const schemas = new Map();
for (const name of readdirSync(schemaDir).filter((n) => n.endsWith('.json')).sort()) {
  schemas.set(name, JSON.parse(readFileSync(path.join(schemaDir, name), 'utf8')));
}

// Synthesise MethodName/NotificationName from x-methods so envelopes can
// $ref them like ordinary types; TierName likewise from x-tiers.
for (const schema of schemas.values()) {
  if (schema['x-tiers']) {
    schema.$defs.TierName = {
      description: 'The three product tiers (FR-M36-05), base first.',
      enum: schema['x-tiers'].tiers,
    };
  }
  if (!schema['x-methods']) {
    continue;
  }
  const requestNames = [];
  const notificationNames = [];
  for (const [name, def] of Object.entries(schema['x-methods'])) {
    (def.notification ? notificationNames : requestNames).push(name);
  }
  schema.$defs.MethodName = {
    description: 'Every request/response method on the bus.',
    enum: requestNames,
  };
  schema.$defs.NotificationName = {
    description: 'Every notification method on the bus.',
    enum: notificationNames,
  };
}

function resolveRef(ref) {
  const match = ref.match(/^(?:(\w[\w.-]*\.json))?#\/\$defs\/(\w+)$/);
  if (!match) {
    throw new Error(`unsupported $ref form: ${ref}`);
  }
  const file = match[1];
  const name = match[2];
  const schema = file ? schemas.get(file) : undefined;
  if (file && !schema) {
    throw new Error(`$ref to unknown schema file: ${ref}`);
  }
  return { file, name };
}

// ---- type model ------------------------------------------------------------
// A named type is emitted once per (file, $defs key); refs produce the name.

function pyStringLiteral(value) {
  return JSON.stringify(value);
}

function tsType(schema, currentFile) {
  if (!schema || Object.keys(schema).length === 0) {
    return 'unknown';
  }
  if (schema.$ref) {
    return resolveRef(schema.$ref).name;
  }
  if ('const' in schema) {
    return typeof schema.const === 'string' ? pyStringLiteral(schema.const) : String(schema.const);
  }
  if (schema.enum) {
    return schema.enum
      .map((v) => (typeof v === 'string' ? pyStringLiteral(v) : String(v)))
      .join(' | ');
  }
  const types = Array.isArray(schema.type) ? schema.type : [schema.type];
  if (types.length > 1) {
    return types.map((t) => tsType({ ...schema, type: t }, currentFile)).join(' | ');
  }
  switch (types[0]) {
    case 'string':
      return 'string';
    case 'integer':
    case 'number':
      return 'number';
    case 'boolean':
      return 'boolean';
    case 'array':
      return `${tsType(schema.items ?? {}, currentFile)}[]`;
    case 'object': {
      if (!schema.properties || Object.keys(schema.properties).length === 0) {
        return schema.additionalProperties === false ? 'Record<string, never>' : 'Record<string, unknown>';
      }
      const fields = Object.entries(schema.properties).map(([key, prop]) => {
        const optional = (schema.required ?? []).includes(key) ? '' : '?';
        return `${JSON.stringify(key)}${optional}: ${tsType(prop, currentFile)}`;
      });
      return `{ ${fields.join('; ')} }`;
    }
    default:
      throw new Error(`unsupported schema type: ${JSON.stringify(schema.type)}`);
  }
}

function pyType(schema, currentFile) {
  if (!schema || Object.keys(schema).length === 0) {
    return 'Any';
  }
  if (schema.$ref) {
    return resolveRef(schema.$ref).name;
  }
  if ('const' in schema) {
    return `Literal[${pyRepr(schema.const)}]`;
  }
  if (schema.enum) {
    return `Literal[${schema.enum.map(pyRepr).join(', ')}]`;
  }
  const types = Array.isArray(schema.type) ? schema.type : [schema.type];
  if (types.length > 1) {
    return types.map((t) => pyType({ ...schema, type: t }, currentFile)).join(' | ');
  }
  switch (types[0]) {
    case 'string':
      return 'str';
    case 'integer':
      return 'int';
    case 'number':
      return 'float';
    case 'boolean':
      return 'bool';
    case 'array':
      return `list[${pyType(schema.items ?? {}, currentFile)}]`;
    case 'object': {
      if (!schema.properties || Object.keys(schema.properties).length === 0) {
        return 'dict[str, Any]';
      }
      // Inline anonymous objects are not expressible as TypedDict fields;
      // require named $defs for nested objects.
      throw new Error(
        `anonymous nested object in ${currentFile}; hoist it into $defs`,
      );
    }
    default:
      throw new Error(`unsupported schema type: ${JSON.stringify(schema.type)}`);
  }
}

function pyRepr(value) {
  if (value === true) return 'True';
  if (value === false) return 'False';
  return JSON.stringify(value);
}

/** Python literal for plain JSON data (dicts, lists, strings). */
function pyLiteral(value, indent = 0) {
  if (Array.isArray(value)) {
    return `[${value.map((v) => pyLiteral(v, indent)).join(', ')}]`;
  }
  if (value !== null && typeof value === 'object') {
    const fields = Object.entries(value).map(
      ([key, v]) => `${JSON.stringify(key)}: ${pyLiteral(v, indent)}`,
    );
    return `{${fields.join(', ')}}`;
  }
  return pyRepr(value);
}

/** Python tuple literal; a single element needs a trailing comma. */
function pyTuple(items) {
  return `(${items.map((item) => JSON.stringify(item)).join(', ')}${items.length === 1 ? ',' : ''})`;
}

// ---- TypeScript emission -----------------------------------------------------

function emitTs() {
  const lines = [
    '// Generated by scripts/generate-bus-types.mjs from shared/schema/. DO NOT EDIT.',
    '// FR-M32-09: extension, webview, Simulation Core and the production',
    '// sidecar all consume these types; npm run check:contracts fails on drift.',
    '',
  ];
  const protocol = schemas.get('protocol.json');
  lines.push(`export const PROTOCOL_VERSION = ${protocol['x-protocol-version']} as const;`);
  lines.push('');
  lines.push('/** Standard JSON-RPC 2.0 codes plus the Meridian -320xx range. */');
  lines.push('export const ErrorCode = {');
  for (const [name, code] of Object.entries(protocol['x-error-codes'])) {
    lines.push(`  ${name}: ${code},`);
  }
  lines.push('} as const;');
  lines.push('export type ErrorCodeValue = (typeof ErrorCode)[keyof typeof ErrorCode];');
  lines.push('');

  for (const [file, schema] of schemas) {
    for (const [name, def] of Object.entries(schema.$defs ?? {})) {
      if (def.description) {
        lines.push(`/** ${def.description} */`);
      }
      if (def.type === 'object' && def.properties && Object.keys(def.properties).length > 0) {
        lines.push(`export interface ${name} {`);
        for (const [key, prop] of Object.entries(def.properties)) {
          if (prop.description) {
            lines.push(`  /** ${prop.description} */`);
          }
          const optional = (def.required ?? []).includes(key) ? '' : '?';
          lines.push(`  ${JSON.stringify(key)}${optional}: ${tsType(prop, file)};`);
        }
        lines.push('}');
      } else {
        lines.push(`export type ${name} = ${tsType(def, file)};`);
      }
      lines.push('');
    }
    if (schema['x-tiers']) {
      // FR-M36-05: the tier registry as runtime constants, so the extension
      // host and the webview filter on the same data the sidecar enforces.
      const xTiers = schema['x-tiers'];
      lines.push('/** FR-M36-05: all tiers, base first. */');
      lines.push(`export const TIERS = ${JSON.stringify(xTiers.tiers)} as const;`);
      lines.push('');
      lines.push('/** FR-M36-05: enabled tiers when nothing is configured — Flight Recorder only. */');
      lines.push(`export const DEFAULT_ENABLED_TIERS: readonly TierName[] = ${JSON.stringify(xTiers.defaultEnabled)};`);
      lines.push('');
      lines.push('/** FR-M36-05: capability registry; every capability is owned by exactly one tier. */');
      lines.push(`export const CAPABILITIES: readonly CapabilityDefinition[] = ${JSON.stringify(xTiers.capabilities)};`);
      lines.push('');
    }
  }

  const methods = schemas.get('methods.json')['x-methods'];
  lines.push('/** Params/result pairing for every request method. */');
  lines.push('export interface MethodMap {');
  for (const [name, def] of Object.entries(methods)) {
    if (def.notification) {
      continue;
    }
    lines.push(
      `  ${JSON.stringify(name)}: { params: ${tsType(def.params, 'methods.json')}; result: ${tsType(def.result, 'methods.json')} };`,
    );
  }
  lines.push('}');
  lines.push('export type RequestMethod = keyof MethodMap;');
  lines.push('');
  lines.push('/** Runtime list of every request method (for tier/ownership checks). */');
  lines.push(`export const REQUEST_METHODS = ${JSON.stringify(Object.keys(methods).filter((n) => !methods[n].notification))} as const;`);
  lines.push('');
  lines.push('/** Runtime list of every notification method. */');
  lines.push(`export const NOTIFICATION_METHODS = ${JSON.stringify(Object.keys(methods).filter((n) => methods[n].notification))} as const;`);
  lines.push('');
  lines.push('export interface NotificationMap {');
  for (const [name, def] of Object.entries(methods)) {
    if (!def.notification) {
      continue;
    }
    lines.push(`  ${JSON.stringify(name)}: ${tsType(def.params, 'methods.json')};`);
  }
  lines.push('}');
  lines.push('');
  return lines.join('\n');
}

// ---- Python emission ---------------------------------------------------------

function emitPy() {
  const lines = [
    '# Generated by scripts/generate-bus-types.mjs from shared/schema/. DO NOT EDIT.',
    '# FR-M32-09: the Simulation Core, the production sidecar and the extension',
    '# consume these types; npm run check:contracts fails on drift.',
    'from __future__ import annotations',
    '',
    'from typing import Any, Literal, TypedDict',
    'from typing import NotRequired',
    '',
  ];
  const protocol = schemas.get('protocol.json');
  lines.push(`PROTOCOL_VERSION: Literal[${protocol['x-protocol-version']}] = ${protocol['x-protocol-version']}`);
  lines.push('');
  lines.push('# Standard JSON-RPC 2.0 codes plus the Meridian -320xx range.');
  for (const [name, code] of Object.entries(protocol['x-error-codes'])) {
    lines.push(`${name}: int = ${code}`);
  }
  lines.push('');

  for (const [file, schema] of schemas) {
    for (const [name, def] of Object.entries(schema.$defs ?? {})) {
      const isClosedEmptyObject =
        def.type === 'object' &&
        def.additionalProperties === false &&
        (!def.properties || Object.keys(def.properties).length === 0);
      if ((def.type === 'object' && def.properties && Object.keys(def.properties).length > 0) || isClosedEmptyObject) {
        if (def.description) {
          lines.push(`# ${def.description}`);
        }
        lines.push(`class ${name}(TypedDict):`);
        const required = def.required ?? [];
        const entries = Object.entries(def.properties ?? {});
        if (entries.length === 0) {
          lines.push('    pass');
        }
        for (const [key, prop] of entries) {
          const wrapped = required.includes(key)
            ? pyType(prop, file)
            : `NotRequired[${pyType(prop, file)}]`;
          const comment = prop.description ? `  # ${prop.description}` : '';
          lines.push(`    ${key}: ${wrapped}${comment}`);
        }
      } else {
        if (def.description) {
          lines.push(`# ${def.description}`);
        }
        lines.push(`${name} = ${pyType(def, file)}`);
      }
      lines.push('');
    }
    if (schema['x-tiers']) {
      // FR-M36-05: the tier registry as runtime constants; the sidecar
      // enforces it, the extension host filters on the same data.
      const xTiers = schema['x-tiers'];
      lines.push('# FR-M36-05: all tiers, base first.');
      lines.push(`TIERS: tuple[str, ...] = ${pyTuple(xTiers.tiers)}`);
      lines.push('');
      lines.push('# FR-M36-05: enabled tiers when nothing is configured — Flight Recorder only.');
      lines.push(`DEFAULT_ENABLED_TIERS: tuple[str, ...] = ${pyTuple(xTiers.defaultEnabled)}`);
      lines.push('');
      lines.push('# FR-M36-05: capability registry; every capability is owned by exactly one tier.');
      lines.push('CAPABILITIES: tuple[CapabilityDefinition, ...] = (');
      for (const capability of xTiers.capabilities) {
        lines.push(`    ${pyLiteral(capability)},`);
      }
      lines.push(')');
      lines.push('');
    }
  }

  const methods = schemas.get('methods.json')['x-methods'];
  const requestNames = Object.keys(methods).filter((n) => !methods[n].notification);
  const notificationNames = Object.keys(methods).filter((n) => methods[n].notification);
  lines.push(`REQUEST_METHODS: tuple[str, ...] = ${pyTuple(requestNames)}`);
  lines.push(`NOTIFICATION_METHODS: tuple[str, ...] = ${pyTuple(notificationNames)}`);
  lines.push('');
  lines.push('# Runtime pairing of method name -> params/result TypedDicts.');
  lines.push('METHOD_CONTRACT: dict[str, dict[str, Any]] = {');
  for (const [name, def] of Object.entries(methods)) {
    if (def.notification) {
      continue;
    }
    lines.push(
      `    ${JSON.stringify(name)}: {"params": ${resolveRef(def.params.$ref).name}, "result": ${resolveRef(def.result.$ref).name}},`,
    );
  }
  lines.push('}');
  lines.push('');
  return lines.join('\n');
}

// ---- write or check -----------------------------------------------------------

const outputs = new Map([
  [tsOut, emitTs()],
  [pyOut, emitPy()],
]);

const normalize = (text) => text.replace(/\r\n/g, '\n');

let stale = [];
for (const [file, content] of outputs) {
  let current = null;
  try {
    current = normalize(readFileSync(file, 'utf8'));
  } catch {
    current = null;
  }
  if (checkMode) {
    if (current !== normalize(content)) {
      stale.push(path.relative(root, file));
    }
  } else if (current !== normalize(content)) {
    writeFileSync(file, content, 'utf8');
    console.log(`wrote ${path.relative(root, file)}`);
  }
}

if (checkMode) {
  if (stale.length > 0) {
    console.error(
      'Generated bus types are stale vs shared/schema/:\n  ' +
        stale.join('\n  ') +
        '\nRun `npm run build` (or node scripts/generate-bus-types.mjs) and commit the result.',
    );
    process.exit(1);
  }
  console.log('bus types are up to date with shared/schema/');
}
