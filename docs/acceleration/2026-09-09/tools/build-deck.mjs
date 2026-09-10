import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const catalog = JSON.parse(readFileSync(join(root, 'source/machine/decisions.json'), 'utf8'));
const template = readFileSync(join(root, 'tools/deck.template.html'), 'utf8');
const data = JSON.stringify(catalog).replaceAll('<', '\\u003c');
if (template.split('__CATALOG__').length !== 2) throw new Error('Expected one catalog placeholder');
mkdirSync(join(root, 'decision-deck'), { recursive: true });
writeFileSync(join(root, 'decision-deck/index.html'), template.replace('__CATALOG__', data));
console.log(`Built offline deck with ${catalog.decisions.length} decisions.`);
