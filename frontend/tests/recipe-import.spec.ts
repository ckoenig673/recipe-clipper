// High-level smoke/regression tests.
// These intentionally test the real frontend import -> AI cleanup -> save flow
// against live recipe websites to catch parser/UI regressions.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const LOGIN_EMAIL = process.env.E2E_EMAIL;
const LOGIN_PASSWORD = process.env.E2E_PASSWORD;
const HOUSE_JAMBALAYA_FIXTURE = readFileSync(
  path.resolve(__dirname, '../../backend/tests/fixtures/paste_text_house_jambalaya/raw.txt'),
  'utf-8'
);

async function getVisibleAddButton(page: Page) {
  const mobileAddButton = page.locator('#mobile-add-button');
  const desktopAddButton = page.locator('#open-add-recipe-button');

  if (await mobileAddButton.isVisible()) return mobileAddButton;
  if (await desktopAddButton.isVisible()) return desktopAddButton;

  await expect
    .poll(async () => {
      if (await mobileAddButton.isVisible()) return 'mobile';
      if (await desktopAddButton.isVisible()) return 'desktop';
      return 'none';
    }, { timeout: 30_000 })
    .not.toBe('none');

  if (await mobileAddButton.isVisible()) return mobileAddButton;
  return desktopAddButton;
}

async function maybeLogin(page: Page) {
  const loginForm = page.locator('#login-form');
  if (await loginForm.isVisible()) {
    if (!LOGIN_EMAIL || !LOGIN_PASSWORD) {
      throw new Error('Login required. Set E2E_EMAIL and E2E_PASSWORD env vars.');
    }
    await page.fill('#login-email', LOGIN_EMAIL);
    await page.fill('#login-password', LOGIN_PASSWORD);
    await page.getByRole('button', { name: 'Log in' }).click();
  }
  await expect(page.locator('.app-shell')).toHaveCount(1, { timeout: 30_000 });
  await getVisibleAddButton(page);
}

async function openFreshApp(page: Page) {
  await page.goto('/');
  await page.evaluate(async () => {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));
    if ('caches' in window) {
      const cacheKeys = await caches.keys();
      await Promise.all(cacheKeys.map((cacheKey) => caches.delete(cacheKey)));
    }
  });
  await page.reload({ waitUntil: 'networkidle' });
}

async function importByUrl(page: Page, url: string) {
  await openFreshApp(page);
  await maybeLogin(page);
  const addButton = await getVisibleAddButton(page);
  await addButton.click();
  await page.locator('#browser-option-button').click();
  await page.locator('#url').fill(url);
  await page.locator('#submit-button').click();
  await expect(page.locator('#parsed-results')).toBeVisible();
}

async function ingredientValues(page: Page) {
  return page.locator('[data-testid="parsed-ingredient-row"] input').evaluateAll((els) =>
    els.map((el) => (el as HTMLInputElement).value.trim())
  );
}

async function instructionValues(page: Page) {
  return page.locator('[data-testid="parsed-instruction-row"] textarea').evaluateAll((els) =>
    els.map((el) => (el as HTMLTextAreaElement).value.trim())
  );
}

async function ingredientSectionValues(page: Page) {
  return page.locator('[data-testid="parsed-ingredient-row"] input[data-ingredient-section="true"]').evaluateAll((els) =>
    els.map((el) => (el as HTMLInputElement).value.trim())
  );
}

async function ingredientItemValues(page: Page) {
  return page.locator('[data-testid="parsed-ingredient-row"] input:not([data-ingredient-section="true"])').evaluateAll((els) =>
    els.map((el) => (el as HTMLInputElement).value.trim())
  );
}

async function detailIngredientValues(page: Page) {
  return page.locator('#detail-ingredients li').evaluateAll((els) =>
    els.map((el) => (el.textContent || '').trim()).filter(Boolean)
  );
}

function arrayContainsSubstring(values: string[], expected: string) {
  return values.some((value) =>
    value.toLowerCase().includes(expected.toLowerCase())
  );
}

function arrayNotContainsSubstring(values: string[], expected: string) {
  return !arrayContainsSubstring(values, expected);
}


async function waitForAiCleanupComplete(page: Page) {
  await expect(page.locator('#run-ai-cleanup-button')).toHaveText('Run AI Cleanup', {
    timeout: 240_000,
  });
}

test('Big Mac Bowls import + AI cleanup + save closes modal', async ({ page }) => {
  await importByUrl(page, 'https://ohsnapmacros.com/big-mac-bowls/');

  await expect(page.locator('#edit-title-input')).toHaveValue(/Big Mac Bowls/i);
  await expect
    .poll(async () => page.locator('[data-testid="parsed-ingredient-row"]').count(), { timeout: 30_000 })
    .toBeGreaterThanOrEqual(17);
  await expect
    .poll(async () => page.locator('[data-testid="parsed-instruction-row"]').count(), { timeout: 30_000 })
    .toBeGreaterThanOrEqual(6);

  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'Spray a large skillet'), { timeout: 30_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'Add the garlic powder'), { timeout: 30_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'In a small mixing bowl'), { timeout: 30_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'Bowl Assembly'), { timeout: 30_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'Meal Prep Assembly'), { timeout: 30_000 })
    .toBeTruthy();

  await page.locator('#run-ai-cleanup-button').click();
  await waitForAiCleanupComplete(page);

  await expect
    .poll(async () => page.locator('[data-testid="parsed-ingredient-row"]').count(), { timeout: 60_000 })
    .toBeGreaterThanOrEqual(17);
  await expect
    .poll(async () => page.locator('[data-testid="parsed-instruction-row"]').count(), { timeout: 60_000 })
    .toBeGreaterThanOrEqual(6);

  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'Spray a large skillet'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'Add the garlic powder'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'In a small mixing bowl'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'Bowl Assembly'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await instructionValues(page), 'Meal Prep Assembly'), { timeout: 60_000 })
    .toBeTruthy();

  await page.locator('#add-recipe-submit-button').click();
  await expect(page.locator('#add-recipe-modal')).toBeHidden({ timeout: 60_000 });
  await expect(page.locator('#open-add-recipe-button')).toBeVisible();
});

test('OPTAVIA Mini Mac import + AI cleanup + save closes modal', async ({ page }) => {
  await importByUrl(page, 'https://www.bigoven.com/recipe/optavia-mini-mac-in-a-bowl/2283923');

  await expect(page.locator('#edit-title-input')).toHaveValue(/OPTAVIA Mini Mac/i);
  await expect
    .poll(async () => arrayContainsSubstring(await ingredientValues(page), 'ground beef'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await ingredientValues(page), 'lettuce'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await ingredientValues(page), 'cheddar'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await ingredientValues(page), 'Dill Pickle'), { timeout: 60_000 })
    .toBeTruthy();

  await page.locator('#run-ai-cleanup-button').click();
  await waitForAiCleanupComplete(page);
  await expect
    .poll(async () => page.locator('[data-testid="parsed-instruction-row"]').count(), { timeout: 60_000 })
    .toBeGreaterThanOrEqual(1);
  await expect
    .poll(async () => arrayNotContainsSubstring(await ingredientValues(page), 'Big Mac Salad; 1 LEANER'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await ingredientValues(page), 'ground beef'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await ingredientValues(page), 'lettuce'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await ingredientValues(page), 'cheddar'), { timeout: 60_000 })
    .toBeTruthy();
  await expect
    .poll(async () => arrayContainsSubstring(await ingredientValues(page), 'Dill Pickle'), { timeout: 60_000 })
    .toBeTruthy();

  await page.locator('#add-recipe-submit-button').click();
  await expect(page.locator('#add-recipe-modal')).toBeHidden({ timeout: 60_000 });
  await expect(page.locator('#open-add-recipe-button')).toBeVisible();
});

test('Paste Full Recipe preserves rich House Jambalaya formatting', async ({ page }) => {
  await openFreshApp(page);
  await maybeLogin(page);
  const addButton = await getVisibleAddButton(page);
  await addButton.click();
  await page.locator('#paste-text-option-button').click();
  await page.locator('#paste-recipe-text').fill(HOUSE_JAMBALAYA_FIXTURE);
  await page.locator('#paste-text-import-button').click();

  await expect(page.locator('#parsed-results')).toBeVisible();
  await expect(page.locator('#edit-title-input')).toHaveValue('House Jambalaya');
  await expect(page.locator('#notes')).toHaveValue(
    "A bold, one-pot rice dinner loaded with sausage, chicken, and shrimp.\nBest served right from the Dutch oven.\n\nChef's Notes:\nRemove the bay leaves before serving.\nTaste and add more hot sauce if needed."
  );
  await expect.poll(async () => ingredientSectionValues(page), { timeout: 30_000 }).toEqual([
    'Meat',
    'For the Chicken',
    'Vegetables',
    'Pantry',
    'Seasonings',
    'For the Pot',
    'Optional Finishers',
  ]);
  await expect.poll(async () => ingredientItemValues(page), { timeout: 30_000 }).toEqual([
    '1 lb andouille sausage, sliced into rounds',
    '1 lb shrimp, peeled and deveined',
    '1 lb boneless skinless chicken thighs, diced',
    '1 large yellow onion, diced',
    '1 green bell pepper, diced',
    '2 celery ribs, diced',
    '3 garlic cloves, minced',
    '1 1/2 cups long-grain rice',
    '1 (14-ounce) can crushed tomatoes',
    '2 tsp Cajun seasoning',
    '1 tsp dried thyme',
    '2 bay leaves',
    '3 cups chicken stock',
    '2 green onions, thinly sliced',
    'Hot sauce, for serving',
  ]);
  await expect.poll(async () => instructionValues(page), { timeout: 30_000 }).toEqual([
    'Brown the sausage in a Dutch oven; transfer to a bowl.',
    'Add the chicken and cook until lightly browned.',
    'Stir in the onion, bell pepper, celery, and garlic until softened.',
    'Return the sausage to the pot with the rice, tomatoes, stock, Cajun seasoning, thyme, and bay leaves.',
    'Cover and simmer until the rice is tender.',
    'Fold in the shrimp and cook just until opaque.',
  ]);

  await page.locator('#add-recipe-submit-button').click();
  await expect(page.locator('#add-recipe-modal')).toBeHidden({ timeout: 60_000 });

  await page.getByRole('button', { name: /Open Uncategorized cookbook/i }).click();
  const savedRecipeCard = page.locator('[data-card-open-id]').filter({ hasText: 'House Jambalaya' }).first();
  await expect(savedRecipeCard).toBeVisible({ timeout: 60_000 });
  await savedRecipeCard.click();

  const expectedNotes = "A bold, one-pot rice dinner loaded with sausage, chicken, and shrimp.\nBest served right from the Dutch oven.\n\nChef's Notes:\nRemove the bay leaves before serving.\nTaste and add more hot sauce if needed.";
  await expect(page.locator('#detail-recipe-notes-section')).toBeVisible();
  await expect(page.locator('#detail-recipe-notes')).toHaveText(expectedNotes);
  await expect.poll(async () => detailIngredientValues(page), { timeout: 30_000 }).toEqual([
    'Meat',
    '1 lb andouille sausage, sliced into rounds',
    '1 lb shrimp, peeled and deveined',
    'For the Chicken',
    '1 lb boneless skinless chicken thighs, diced',
    'Vegetables',
    '1 large yellow onion, diced',
    '1 green bell pepper, diced',
    '2 celery ribs, diced',
    '3 garlic cloves, minced',
    'Pantry',
    '1 1/2 cups long-grain rice',
    '1 (14-ounce) can crushed tomatoes',
    'Seasonings',
    '2 tsp Cajun seasoning',
    '1 tsp dried thyme',
    '2 bay leaves',
    'For the Pot',
    '3 cups chicken stock',
    'Optional Finishers',
    '2 green onions, thinly sliced',
    'Hot sauce, for serving',
  ]);

  await page.locator('#detail-edit-button').click();
  await expect(page.locator('#notes')).toHaveValue(expectedNotes);
});
