import { readFileSync, writeFileSync, readdirSync, lstatSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

export const root = dirname(dirname(fileURLToPath(import.meta.url)));
const manifestName = 'BUNDLE_MANIFEST.json';
export const readJSON = path => JSON.parse(readFileSync(path, 'utf8'));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const check = (condition, message) => { if (!condition) throw new Error(message); };

export function files(dir = root) {
  const found = [];
  for (const name of readdirSync(dir).sort()) {
    const path = join(dir, name), stat = lstatSync(path);
    check(!stat.isSymbolicLink(), 'Symlinks are not allowed: ' + path);
    if (stat.isDirectory()) found.push(...files(path));
    else if (stat.isFile()) found.push(path);
    else throw new Error('Unsupported file: ' + path);
  }
  return found;
}

export function validateGraph(tasks) {
  check(Array.isArray(tasks), 'Expected task list');
  const ids = tasks.map(t => t.id), byId = new Map(tasks.map(t => [t.id, t]));
  check(ids.length === byId.size, 'Duplicate task ID');
  const visiting = new Set(), done = new Set();
  function visit(id) {
    check(byId.has(id), 'Unknown dependency: ' + id);
    check(!visiting.has(id), 'Dependency cycle at ' + id);
    if (done.has(id)) return;
    visiting.add(id);
    const task = byId.get(id);
    check(Array.isArray(task.depends_on), 'Missing dependencies: ' + id);
    for (const dep of task.depends_on) visit(dep);
    visiting.delete(id); done.add(id);
  }
  ids.forEach(visit);
}

export function validateSelection(doc, catalog) {
  check(doc && typeof doc === 'object' && !Array.isArray(doc), 'Expected selection object');
  check(doc.schema_version === '1.0', 'Unsupported selection version');
  check(doc.repository === catalog.snapshot.repository, 'Wrong repository');
  check(doc.snapshot_sha === catalog.snapshot.snapshot_sha, 'Wrong snapshot');
  check(doc.selections && typeof doc.selections === 'object' && !Array.isArray(doc.selections), 'Expected selections object');
  const byId = new Map(catalog.decisions.map(d => [d.id, d]));
  const selections = {}, notes = {};
  for (const [id, option] of Object.entries(doc.selections)) {
    check(byId.has(id) && byId.get(id).options.some(o => o.id === option), 'Unknown decision or option: ' + id);
    selections[id] = option;
  }
  const inputNotes = doc.notes ?? {};
  check(inputNotes && typeof inputNotes === 'object' && !Array.isArray(inputNotes), 'Expected notes object');
  for (const [id, note] of Object.entries(inputNotes)) {
    check(byId.has(id) && typeof note === 'string' && note.length <= 20000, 'Invalid note: ' + id);
    notes[id] = note;
  }
  return { selections, notes };
}

export function validateContent(base = root) {
  const catalog = readJSON(join(base, 'source/machine/decisions.json'));
  const defaults = readJSON(join(base, 'source/machine/default-selections.json'));
  const tasks = readJSON(join(base, 'source/machine/agent-task-manifest.json')).tasks;
  check(catalog.decisions.length === 20, 'Expected 20 recovered decisions');
  const ids = catalog.decisions.map(d => d.id);
  check(new Set(ids).size === ids.length, 'Duplicate decision ID');
  for (const d of catalog.decisions) {
    check(d.options.length > 0, 'No options: ' + d.id);
    check(new Set(d.options.map(o => o.id)).size === d.options.length, 'Duplicate option: ' + d.id);
    check(d.options.some(o => o.id === d.recommended), 'Invalid recommendation: ' + d.id);
  }
  validateSelection(defaults, catalog);
  check(tasks.length === 42, 'Expected 42 recovered tasks');
  validateGraph(tasks);
  const inventory = readJSON(join(base, 'RECOVERY_INVENTORY.json'));
  check(inventory.files.length === 26, 'Expected 26 recovered files');
  for (const row of inventory.files) {
    check(digest(readFileSync(join(base, 'source', row.path))) === row.packaged_sha256, 'Recovered file changed: ' + row.path);
  }
  const html = readFileSync(join(base, 'decision-deck/index.html'), 'utf8');
  const match = html.match(/<script id="catalog" type="application\/json">([\s\S]*?)<\/script>/);
  check(match && JSON.stringify(JSON.parse(match[1])) === JSON.stringify(catalog), 'Deck catalog does not match source');
  check(!html.includes('__CATALOG__'), 'Unresolved deck placeholder');
  check(!/<script[^>]+src=|<link[^>]+href=/i.test(html), 'External assets in offline deck');
  return { recovered_files: 26, decisions: 20, proposed_tasks: 42 };
}

export function buildManifest(base = root) {
  validateContent(base);
  const entries = files(base).filter(p => relative(base, p) !== manifestName).map(p => {
    const bytes = readFileSync(p);
    return { path: relative(base, p).replaceAll('\\', '/'), bytes: bytes.length, sha256: digest(bytes) };
  });
  const manifest = { schema_version: '1.0', repository: 'Chris0Jeky/extract-api', snapshot_sha: 'aeacafa63685af3b47030375d13b2b5c1d5979f9', packaged_on: '2026-09-09', scope: 'Recovered planning material and newly completed offline decision/handoff tooling; no production changes', files: entries };
  writeFileSync(join(base, manifestName), JSON.stringify(manifest, null, 2) + '\n');
  return entries.length;
}

export function validateManifest(base = root) {
  const report = validateContent(base), manifest = readJSON(join(base, manifestName));
  const expected = manifest.files.map(f => f.path), actual = files(base).map(p => relative(base, p).replaceAll('\\', '/')).filter(p => p !== manifestName);
  check(expected.length === new Set(expected).size, 'Duplicate manifest path');
  check(JSON.stringify([...expected].sort()) === JSON.stringify(actual.sort()), 'Manifest file set differs from disk');
  for (const entry of manifest.files) {
    const bytes = readFileSync(join(base, entry.path));
    check(bytes.length === entry.bytes && digest(bytes) === entry.sha256, 'Integrity mismatch: ' + entry.path);
  }
  return { ...report, files: manifest.files.length + 1 };
}

export function renderPlan(doc, catalog) {
  const { selections, notes } = validateSelection(doc, catalog);
  const lines = ['# extract-api decision handoff', '', `Repository: ${catalog.snapshot.repository}`, `Snapshot: ${catalog.snapshot.snapshot_sha}`, '', 'Planning input only. Revalidate live HEAD, current owner decisions and open work.', 'No paid-call, fixture-promotion, guardrail, issue-mutation, publication or merge permission is granted here.', 'The 42-task source manifest is advisory and must be reconciled with these choices, not executed wholesale.', ''];
  for (const d of catalog.decisions) {
    const option = d.options.find(o => o.id === selections[d.id]);
    lines.push(`## ${d.id}: ${d.title}`, '', option ? `Selected: ${option.label}` : 'UNRESOLVED. No default was substituted.', '');
    if (option) {
      lines.push(option.summary, '', `Trade-off: ${option.tradeoffs}`, '', 'Agent preparation:');
      for (const action of option.agent_actions ?? []) lines.push('- ' + action);
      lines.push('', 'Human review:');
      for (const action of option.human_actions ?? []) lines.push('- ' + action);
      lines.push('');
    }
    if (notes[d.id]) lines.push('Owner note:', '', notes[d.id], '');
  }
  return lines.join('\n').trimEnd() + '\n';
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const [command, input, output] = process.argv.slice(2);
    if (command === 'manifest') console.log(`Manifest written for ${buildManifest()} payload files.`);
    else if (command === 'validate') console.log('Bundle validation passed: ' + JSON.stringify(validateManifest()));
    else if (command === 'plan' && input) {
      const plan = renderPlan(readJSON(input), readJSON(join(root, 'source/machine/decisions.json')));
      if (output) writeFileSync(output, plan, { flag: 'wx' });
      else process.stdout.write(plan);
    } else throw new Error('Usage: node tools/bundle.mjs manifest | validate | plan <answers.json> [new-output.md]');
  } catch (error) {
    console.error(error.message); process.exitCode = 1;
  }
}
