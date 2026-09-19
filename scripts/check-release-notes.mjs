/**
 * Release notes that agree with everything else — MV4-T05, principle `MP5`.
 *
 * Release notes are the one document most likely to drift into marketing,
 * because they are the one written last and read first. This project's whole
 * argument is that its statements are checkable, so the notes are checked
 * against the documents they must not contradict:
 *
 *  - **`docs/SECURITY-AND-DATA.md` §6** — every limitation appears in the
 *    notes, in the same words. Not paraphrased: a softened limitation is the
 *    failure mode, and paraphrase is how softening happens without anyone
 *    deciding to soften anything.
 *  - **`mvp-req-final.md` §13** — the notes say plainly what the MVP does
 *    **not** claim.
 *  - **`DECISIONS.md`** — every `D<n>` the notes cite exists there. Citing a
 *    decision record that does not record the decision is worse than citing
 *    nothing.
 *  - **the tier set** — named, because "which tiers does this ship with" is
 *    the first question a buyer asks and the answer changes what the product
 *    does.
 *
 * Exit codes: 0 = the notes agree with the record; 1 = they do not, listed.
 */
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const NOTES = path.join(root, 'extension', 'CHANGELOG.md');
const SECURITY = path.join(root, 'docs', 'SECURITY-AND-DATA.md');
const REQUIREMENTS = path.join(root, 'mvp-req-final.md');
const DECISIONS = path.join(root, 'DECISIONS.md');

/** The three tiers. Naming them is the point; inventing a fourth would fail. */
const TIERS = ['Flight Recorder', 'Governor', 'Orchestra'];

/** Bold headline of each §6 limitation: `- **…**`. */
function limitationHeadlines(text) {
  const section = text.split('## 6. Limitations')[1]?.split('\n## ')[0] ?? '';
  return [...section.matchAll(/^- \*\*(.+?)\*\*/gm)].map((match) => match[1].trim());
}

function decisionIds(text) {
  return new Set([...text.matchAll(/\bD(\d+)\b/g)].map((match) => `D${match[1]}`));
}

export function runReleaseNotesCheck() {
  const problems = [];
  if (!existsSync(NOTES)) {
    return { ok: false, problems: ['extension/CHANGELOG.md does not exist.'] };
  }
  const notes = readFileSync(NOTES, 'utf8');
  const security = readFileSync(SECURITY, 'utf8');
  const requirements = readFileSync(REQUIREMENTS, 'utf8');
  const decisions = readFileSync(DECISIONS, 'utf8');

  // -- the limitations, unsoftened ----------------------------------------
  const limitations = limitationHeadlines(security);
  if (limitations.length === 0) {
    problems.push(
      'no limitations were found in docs/SECURITY-AND-DATA.md §6. Either the ' +
        'section moved or this check has stopped reading it — both need looking at.',
    );
  }
  for (const limitation of limitations) {
    // Compare on the sentence, whitespace-normalised. Anything else is a
    // rewrite, and a rewritten limitation is a softened one until proven
    // otherwise.
    const needle = limitation.replace(/\s+/g, ' ').trim();
    const haystack = notes.replace(/\s+/g, ' ');
    if (!haystack.includes(needle)) {
      problems.push(
        `the release notes do not state this limitation in its own words: "${needle}"`,
      );
    }
  }

  // -- what the MVP does not claim ----------------------------------------
  const disclaimed = /\*\*Claims the MVP does not make:\*\*\s*(.+?)\./s.exec(requirements);
  if (!disclaimed) {
    problems.push('mvp-req-final.md §13 no longer states what the MVP does not claim.');
  } else {
    // The four nouns §13 names. Requiring the whole sentence verbatim would
    // fail on a legitimate rewording; requiring all four means none of them
    // can be quietly dropped.
    for (const noun of ['delivery outcomes', 'defects', 'cost', 'productivity']) {
      if (!notes.includes(noun)) {
        problems.push(
          `the release notes do not say the MVP makes no claim about ${noun} ` +
            '(mvp-req-final.md §13).',
        );
      }
    }
  }

  // -- the tier set --------------------------------------------------------
  for (const tier of TIERS) {
    if (!notes.includes(tier)) {
      problems.push(`the release notes do not name the ${tier} tier.`);
    }
  }

  // -- every cited decision exists ----------------------------------------
  const known = decisionIds(decisions);
  const cited = [...notes.matchAll(/`(D\d+)`/g)].map((match) => match[1]);
  for (const id of new Set(cited)) {
    if (!known.has(id)) {
      problems.push(
        `the release notes cite ${id}, which DECISIONS.md does not record.`,
      );
    }
  }

  return {
    ok: problems.length === 0,
    problems,
    limitations: limitations.length,
    decisions: new Set(cited).size,
  };
}

const invokedDirectly =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  const result = runReleaseNotesCheck();
  for (const problem of result.problems) console.error(`  ${problem}`);
  console.log(
    result.ok
      ? `release-notes: ${result.limitations} limitations stated unsoftened, ` +
          `${result.decisions} cited decisions all recorded, the tier set named.`
      : `release-notes: ${result.problems.length} disagreement(s) with the record.`,
  );
  process.exit(result.ok ? 0 : 1);
}
