import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, cpSync, rmSync, appendFileSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { root, readJSON, validateGraph, validateSelection, validateContent, buildManifest, validateManifest, renderPlan } from './bundle.mjs';

const catalog = readJSON(join(root, 'source/machine/decisions.json'));
const blank = () => ({ schema_version: '1.0', repository: catalog.snapshot.repository, snapshot_sha: catalog.snapshot.snapshot_sha, selections: {}, notes: {} });
test('recovered content and embedded deck agree', () => assert.equal(validateContent().decisions, 20));
test('defaults are valid recommendations', () => assert.equal(Object.keys(validateSelection(readJSON(join(root, 'source/machine/default-selections.json')), catalog).selections).length, 20));
test('empty selection leaves every decision unresolved', () => {
  const plan = renderPlan(blank(), catalog);
  assert.equal(plan.match(/UNRESOLVED/g).length, 20);
  assert.ok(!plan.includes('Selected:'));
});
test('one answer leaves nineteen unresolved and preserves notes', () => {
  const doc = blank(); doc.selections.D01 = catalog.decisions[0].recommended; doc.notes.D01 = 'Owner constraint <script>alert(1)</script>';
  const plan = renderPlan(doc, catalog);
  assert.equal(plan.match(/UNRESOLVED/g).length, 19); assert.ok(plan.includes(doc.notes.D01));
});
test('unknown decision is rejected', () => { const doc = blank(); doc.selections.X99 = 'unknown'; assert.throws(() => validateSelection(doc, catalog), /Unknown/); });
test('unknown option is rejected', () => { const doc = blank(); doc.selections.D01 = 'unknown'; assert.throws(() => validateSelection(doc, catalog), /Unknown/); });
test('foreign repository is rejected', () => { const doc = blank(); doc.repository = 'other/repo'; assert.throws(() => validateSelection(doc, catalog), /repository/); });
test('wrong snapshot is rejected', () => { const doc = blank(); doc.snapshot_sha = 'f'.repeat(40); assert.throws(() => validateSelection(doc, catalog), /snapshot/); });
test('malformed notes are rejected', () => { const doc = blank(); doc.notes = []; assert.throws(() => validateSelection(doc, catalog), /notes/); });
test('oversized notes are rejected', () => { const doc = blank(); doc.notes.D01 = 'x'.repeat(20001); assert.throws(() => validateSelection(doc, catalog), /note/); });
test('cycles are rejected', () => assert.throws(() => validateGraph([{ id: 'A', depends_on: ['B'] }, { id: 'B', depends_on: ['A'] }]), /cycle/));
test('unknown dependencies are rejected', () => assert.throws(() => validateGraph([{ id: 'A', depends_on: ['B'] }]), /Unknown/));
test('duplicate tasks are rejected', () => assert.throws(() => validateGraph([{ id: 'A', depends_on: [] }, { id: 'A', depends_on: [] }]), /Duplicate/));
test('manifest detects modification and extra files', () => {
  const dir = mkdtempSync(join(tmpdir(), 'extract-bundle-'));
  try {
    cpSync(root, dir, { recursive: true }); buildManifest(dir); assert.equal(validateManifest(dir).recovered_files, 26);
    const p = join(dir, 'README.md'), before = readFileSync(p);
    appendFileSync(p, '\nchanged\n'); assert.throws(() => validateManifest(dir), /Integrity/);
    writeFileSync(p, before); writeFileSync(join(dir, 'unexpected.txt'), 'extra'); assert.throws(() => validateManifest(dir), /file set/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
