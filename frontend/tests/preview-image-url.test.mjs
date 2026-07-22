import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve(process.cwd(), 'frontend/app.js');
const source = readFileSync(appJsPath, 'utf8');
const helperStart = source.indexOf('function normalizeHostname(');
const helperEnd = source.indexOf('function getImportFallbackMessage(');
const renderStart = source.indexOf('function renderEditImagePreview() {');
const renderEnd = source.indexOf('function startEdit(recipe) {');

if (helperStart === -1 || helperEnd === -1 || helperEnd <= helperStart || renderStart === -1 || renderEnd === -1 || renderEnd <= renderStart) {
  throw new Error('Could not locate preview image helper/render blocks in frontend/app.js');
}

const helperSource = `${source.slice(helperStart, helperEnd)}
${source.slice(renderStart, renderEnd)}
let editImagePreview = null;
let editImagePlaceholder = null;
let clearEditImageButton = null;
let imageUrlInput = null;
globalThis.__frontendPreviewImageHelpers = {
  normalizePreviewImageUrl,
  renderEditImagePreview,
  setPreviewElements(nextElements) {
    editImagePreview = nextElements.editImagePreview;
    editImagePlaceholder = nextElements.editImagePlaceholder;
    clearEditImageButton = nextElements.clearEditImageButton;
    imageUrlInput = nextElements.imageUrlInput;
  }
};`;

const sandbox = {
  URL,
  document: { baseURI: 'https://recipes.example/app/' },
  globalThis: {}
};
vm.createContext(sandbox);
new vm.Script(helperSource, { filename: 'frontend/app.js' }).runInContext(sandbox);

const { normalizePreviewImageUrl, renderEditImagePreview, setPreviewElements } =
  sandbox.globalThis.__frontendPreviewImageHelpers;

function createToggleRecorder() {
  const calls = [];
  return {
    calls,
    toggle(name, value) {
      calls.push([name, value]);
    }
  };
}

test('preview image helper preserves supported absolute, relative, protocol-relative, and blob urls', () => {
  assert.equal(normalizePreviewImageUrl('https://example.com/image.png'), 'https://example.com/image.png');
  assert.equal(normalizePreviewImageUrl('  http://example.com/image.jpg?size=large  '), 'http://example.com/image.jpg?size=large');
  assert.equal(normalizePreviewImageUrl('/images/example.jpg'), 'https://recipes.example/images/example.jpg');
  assert.equal(normalizePreviewImageUrl('//cdn.example.com/image.jpg'), 'https://cdn.example.com/image.jpg');
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
  assert.equal(normalizePreviewImageUrl('https://'), '');
  assert.equal(normalizePreviewImageUrl('http://exa mple.com/image.png'), '');
  assert.equal(normalizePreviewImageUrl('blob:not a valid blob url'), '');
});

test('preview image helper rejects unsupported or unsafe schemes', () => {
  assert.equal(normalizePreviewImageUrl('javascript:alert(1)'), '');
  assert.equal(normalizePreviewImageUrl('file:///C:/secret.png'), '');
  assert.equal(normalizePreviewImageUrl('ftp://example.com/image.png'), '');
  assert.equal(normalizePreviewImageUrl('data:text/plain,hello'), '');
  assert.equal(normalizePreviewImageUrl('data:text/html,<img src=x onerror=alert(1)>'), '');
});

test('renderEditImagePreview removes src when the preview url is invalid', () => {
  const imagePreviewClasses = createToggleRecorder();
  const placeholderClasses = createToggleRecorder();
  const buttonClasses = createToggleRecorder();
  const editImagePreview = {
    src: 'https://example.com/old.png',
    classList: imagePreviewClasses,
    removeAttributeCalls: [],
    removeAttribute(name) {
      this.removeAttributeCalls.push(name);
      if (name === 'src') {
        this.src = '';
      }
    }
  };
  const clearEditImageButton = {
    classList: buttonClasses,
    disabled: false
  };
  setPreviewElements({
    editImagePreview,
    editImagePlaceholder: { classList: placeholderClasses },
    clearEditImageButton,
    imageUrlInput: { value: 'javascript:alert(1)' }
  });

  renderEditImagePreview();

  assert.deepEqual(editImagePreview.removeAttributeCalls, ['src']);
  assert.equal(editImagePreview.src, '');
  assert.deepEqual(imagePreviewClasses.calls.at(-1), ['hidden', true]);
  assert.deepEqual(placeholderClasses.calls.at(-1), ['hidden', false]);
  assert.deepEqual(buttonClasses.calls.at(-1), ['hidden', false]);
  assert.equal(clearEditImageButton.disabled, false);
});

test('renderEditImagePreview keeps src for supported relative urls', () => {
  const imagePreviewClasses = createToggleRecorder();
  const placeholderClasses = createToggleRecorder();
  const buttonClasses = createToggleRecorder();
  const editImagePreview = {
    src: '',
    classList: imagePreviewClasses,
    removeAttribute() {
      throw new Error('removeAttribute should not be called for valid preview urls');
    }
  };
  const clearEditImageButton = {
    classList: buttonClasses,
    disabled: true
  };
  setPreviewElements({
    editImagePreview,
    editImagePlaceholder: { classList: placeholderClasses },
    clearEditImageButton,
    imageUrlInput: { value: '/images/example.jpg' }
  });

  renderEditImagePreview();

  assert.equal(editImagePreview.src, 'https://recipes.example/images/example.jpg');
  assert.deepEqual(imagePreviewClasses.calls.at(-1), ['hidden', false]);
  assert.deepEqual(placeholderClasses.calls.at(-1), ['hidden', true]);
  assert.deepEqual(buttonClasses.calls.at(-1), ['hidden', false]);
  assert.equal(clearEditImageButton.disabled, false);
});
