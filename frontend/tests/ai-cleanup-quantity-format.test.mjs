import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve(process.cwd(), 'frontend/app.js');
const source = readFileSync(appJsPath, 'utf8');
const start = source.indexOf('function formatAiCleanupQuantity(');
const end = source.indexOf('function normalizeAiCleanupIngredientParts(');

if (start === -1 || end === -1 || end <= start) {
  throw new Error('Could not locate AI cleanup quantity formatter in frontend/app.js');
}

const helperSource = `${source.slice(start, end)}
globalThis.__formatAiCleanupQuantity = formatAiCleanupQuantity;`;
const sandbox = { globalThis: {} };
vm.createContext(sandbox);
new vm.Script(helperSource, { filename: 'frontend/app.js' }).runInContext(sandbox);

const formatAiCleanupQuantity = sandbox.globalThis.__formatAiCleanupQuantity;

test('AI cleanup quantity formatter uses culinary eighth fractions', () => {
  assert.equal(formatAiCleanupQuantity(0.125), '1/8');
  assert.equal(formatAiCleanupQuantity(0.375), '3/8');
  assert.equal(formatAiCleanupQuantity(0.625), '5/8');
  assert.equal(formatAiCleanupQuantity(0.875), '7/8');
});

test('AI cleanup quantity formatter preserves non-culinary decimals', () => {
  assert.equal(formatAiCleanupQuantity(0.025), '0.025');
});
