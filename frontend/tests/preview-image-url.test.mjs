import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve(process.cwd(), 'frontend/app.js');
const source = readFileSync(appJsPath, 'utf8');
const start = source.indexOf('function normalizeHostname(');
const end = source.indexOf('function getImportFallbackMessage(');

if (start === -1 || end === -1 || end <= start) {
  throw new Error('Could not locate preview image URL helper block in frontend/app.js');
}

const helperSource = `${source.slice(start, end)}
globalThis.__frontendPreviewImageHelpers = {
  normalizePreviewImageUrl
};`;

const sandbox = { URL, globalThis: {} };
vm.createContext(sandbox);
new vm.Script(helperSource, { filename: 'frontend/app.js' }).runInContext(sandbox);

const { normalizePreviewImageUrl } = sandbox.globalThis.__frontendPreviewImageHelpers;

test('preview image helper preserves supported remote and blob urls', () => {
  assert.equal(normalizePreviewImageUrl('https://example.com/image.png'), 'https://example.com/image.png');
  assert.equal(normalizePreviewImageUrl('  http://example.com/image.jpg?size=large  '), 'http://example.com/image.jpg?size=large');
  assert.equal(normalizePreviewImageUrl('blob:https://example.com/550e8400-e29b-41d4-a716-446655440000'), 'blob:https://example.com/550e8400-e29b-41d4-a716-446655440000');
});

test('preview image helper preserves supported data image urls', () => {
  assert.equal(
    normalizePreviewImageUrl('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA'),
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA'
  );
  assert.equal(
    normalizePreviewImageUrl('data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22/%3E'),
    'data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22/%3E'
  );
});

test('preview image helper rejects malformed urls', () => {
  assert.equal(normalizePreviewImageUrl('not-a-url'), '');
  assert.equal(normalizePreviewImageUrl('https://'), '');
  assert.equal(normalizePreviewImageUrl('blob:not a valid blob url'), '');
});

test('preview image helper rejects unsupported or unsafe schemes', () => {
  assert.equal(normalizePreviewImageUrl('javascript:alert(1)'), '');
  assert.equal(normalizePreviewImageUrl('file:///C:/secret.png'), '');
  assert.equal(normalizePreviewImageUrl('ftp://example.com/image.png'), '');
  assert.equal(normalizePreviewImageUrl('data:text/plain,hello'), '');
  assert.equal(normalizePreviewImageUrl('data:text/html,<img src=x onerror=alert(1)>'), '');
});
