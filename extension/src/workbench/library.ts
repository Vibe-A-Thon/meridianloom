/**
 * The library that ships in the box.
 *
 * Meridian shipped with nothing in it. A new workspace opened to four empty
 * catalogues — no agents, no skills, no instruction documents — and the only
 * route to a populated one was importing a package the user did not have yet.
 * A governance tool whose first screen is empty teaches nothing about what it
 * governs.
 *
 * The important decision here is that a built-in is **not a special kind of
 * record**. Every file under `library/` is ordinary markdown with ordinary
 * frontmatter, parsed by the same `agentFromMarkdown` / `skillFromMarkdown` /
 * `instructionFromMarkdown` that the import path uses. So the two ways of
 * getting content in — shipped and uploaded — are one mechanism with two
 * sources, rather than two systems that will drift. A shipped skill can be
 * read, edited, disabled, exported or deleted exactly like an imported one,
 * and once a user edits it, it is simply theirs.
 *
 * Seeding is *additive and once per entry*. The ids ever seeded are recorded,
 * so:
 *
 *  - deleting a built-in makes it stay deleted rather than reappearing on the
 *    next window reload, which would make the delete button a lie;
 *  - editing one is never overwritten by a later extension version;
 *  - a genuinely new entry in a later version still arrives.
 *
 * Shipped agents follow the same permission floor as imported ones: they
 * arrive in Learning mode with `read`, `search`, `think` and nothing else.
 * Something that came free in the box has not earned more trust than
 * something a person chose to install, and arguably less.
 */
import { readdir, readFile } from "node:fs/promises";
import * as path from "node:path";
import {
  agentFromMarkdown,
  instructionFromMarkdown,
  parseFrontmatter,
  skillFromMarkdown,
} from "./packages";
import type {
  WorkbenchAgentInput,
  WorkbenchInstructionInput,
  WorkbenchSkillInput,
} from "../../../shared/ts/workbench";

/** Directory name inside the extension, and inside the packaged VSIX. */
export const LIBRARY_DIRECTORY = "library";

export interface BuiltinLibrary {
  agents: WorkbenchAgentInput[];
  skills: WorkbenchSkillInput[];
  instructions: WorkbenchInstructionInput[];
}

/** Nothing shipped, or nothing readable. Never a reason to fail activation. */
export function emptyLibrary(): BuiltinLibrary {
  return { agents: [], skills: [], instructions: [] };
}

async function readMarkdownDirectory(
  directory: string,
): Promise<{ fileName: string; text: string }[]> {
  let entries: string[];
  try {
    entries = await readdir(directory);
  } catch {
    // A missing category is normal — a build may ship skills and no agents —
    // and an unreadable one is not worth failing activation over.
    return [];
  }
  const files = entries.filter((name) => name.toLowerCase().endsWith(".md")).sort();
  const out: { fileName: string; text: string }[] = [];
  for (const fileName of files) {
    try {
      out.push({
        fileName,
        text: await readFile(path.join(directory, fileName), "utf8"),
      });
    } catch {
      // One malformed file does not cost the user the other eighteen.
    }
  }
  return out;
}

/**
 * Read the shipped library from an extension directory.
 *
 * Never throws. A library that cannot be read leaves the catalogues as they
 * were, which is the behaviour before this existed — a degraded first run is
 * much better than an extension that will not start.
 */
export async function loadBuiltinLibrary(
  extensionPath: string,
): Promise<BuiltinLibrary> {
  const root = path.join(extensionPath, LIBRARY_DIRECTORY);
  const library = emptyLibrary();

  for (const { fileName, text } of await readMarkdownDirectory(
    path.join(root, "agents"),
  )) {
    try {
      library.agents.push(agentFromMarkdown(fileName, parseFrontmatter(text)));
    } catch {
      /* skip the one that will not parse */
    }
  }
  for (const { fileName, text } of await readMarkdownDirectory(
    path.join(root, "skills"),
  )) {
    try {
      library.skills.push(skillFromMarkdown(fileName, parseFrontmatter(text)));
    } catch {
      /* as above */
    }
  }
  for (const { fileName, text } of await readMarkdownDirectory(
    path.join(root, "instructions"),
  )) {
    try {
      library.instructions.push(
        instructionFromMarkdown(fileName, parseFrontmatter(text)),
      );
    } catch {
      /* as above */
    }
  }
  return library;
}

/** What a seeding pass actually added, for the caller to report or record. */
export interface SeedResult {
  agents: WorkbenchAgentInput[];
  skills: WorkbenchSkillInput[];
  instructions: WorkbenchInstructionInput[];
  /** Every id now considered seeded, including those seeded previously. */
  seeded: string[];
}

/**
 * Work out what to add, given what is already present and what was ever
 * seeded before.
 *
 * Pure: it decides, the caller applies. That keeps the policy — additive,
 * once per id, never overwriting — testable without a filesystem, a
 * workspace, or a clock.
 *
 * `present` is the ids currently in each catalogue. An id that is present is
 * skipped even if it was never recorded as seeded, so a user who authored a
 * skill called `python-service` does not have a shipped one land on top of
 * it.
 */
export function planSeed(
  library: BuiltinLibrary,
  present: { agents: string[]; skills: string[]; instructions: string[] },
  alreadySeeded: readonly string[],
): SeedResult {
  const seen = new Set(alreadySeeded);
  const key = (kind: string, id: string) => `${kind}:${id}`;
  const pick = <T extends { id: string }>(items: T[], kind: string, existing: string[]) => {
    const here = new Set(existing);
    return items.filter(
      (item) => !seen.has(key(kind, item.id)) && !here.has(item.id),
    );
  };

  const agents = pick(library.agents, "agent", present.agents);
  const skills = pick(library.skills, "skill", present.skills);
  const instructions = pick(
    library.instructions,
    "instruction",
    present.instructions,
  );

  const seeded = new Set(alreadySeeded);
  // Everything the library offers is marked seeded, not only what was added.
  // An entry skipped because the user already has that id must not come back
  // on the next load under a different code path.
  for (const item of library.agents) seeded.add(key("agent", item.id));
  for (const item of library.skills) seeded.add(key("skill", item.id));
  for (const item of library.instructions) seeded.add(key("instruction", item.id));

  return { agents, skills, instructions, seeded: [...seeded].sort() };
}
