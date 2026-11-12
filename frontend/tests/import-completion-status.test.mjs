import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve(process.cwd(), 'frontend/app.js');
const source = readFileSync(appJsPath, 'utf8');
const start = source.indexOf('function hasParsedCoreContent(');
const end = source.indexOf('async function enrichFromUrl(');

if (start === -1 || end === -1 || end <= start) {
  throw new Error('Could not locate import completion helpers in frontend/app.js');
}

const helperSource = `
function sanitizeIngredientGroups(groups) { return Array.isArray(groups) ? groups : []; }
function sanitizeInstructionGroups(groups) { return Array.isArray(groups) ? groups : []; }
${source.slice(start, end)}
globalThis.__importCompletionHelpers = { isNeedsReviewMetadataFallback, getImportFallbackMessage };
`;

const sandbox = { globalThis: {} };
vm.createContext(sandbox);
new vm.Script(helperSource, { filename: 'frontend/app.js' }).runInContext(sandbox);

const { isNeedsReviewMetadataFallback, getImportFallbackMessage } = sandbox.globalThis.__importCompletionHelpers;

test('metadata-only URL imports are routed to the actionable incomplete state', () => {
  const response = {
    status: 'incomplete',
    reason: 'We found page details but no ingredients or instructions. Try the recipe page directly or paste the recipe text.',
    title: 'Metadata Only',
    image_url: 'https://example.test/recipe.jpg',
    ingredients: [],
    instructions: [],
  };

  assert.equal(isNeedsReviewMetadataFallback(response), true);
  assert.match(getImportFallbackMessage('https://example.test/metadata-only', response), /no ingredients or instructions/i);
});

test('URL imports with recipe content remain eligible for review and save', () => {
  assert.equal(
    isNeedsReviewMetadataFallback({
      status: 'complete',
      title: 'Lemon Chicken and Orzo',
      ingredients: ['2 pounds chicken thighs'],
      instructions: ['Season the chicken.'],
    }),
    false,
  );
});
