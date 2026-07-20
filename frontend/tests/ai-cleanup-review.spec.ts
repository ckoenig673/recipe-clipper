import { expect, test, type Page } from '@playwright/test';

const LOGIN_EMAIL = process.env.E2E_EMAIL;
const LOGIN_PASSWORD = process.env.E2E_PASSWORD;

function buildRecipe(seed: string) {
  return {
    title: `Weeknight Tacos ${seed}`,
    url: '',
    original_source_url: '',
    resolved_recipe_url: '',
    content_source: 'manual',
    image_url: '',
    source_app: 'Playwright',
    source_type: 'Manual',
    notes: 'Serve with lime wedges.',
    tags: '',
    needs_review: false,
    review_status: 'none',
    servings: '4',
    prep_time: '10 mins',
    cook_time: '20 mins',
    total_time: '30 mins',
    prep_minutes: 10,
    cook_minutes: 20,
    total_minutes: 30,
    ingredient_groups: [
      { title: 'For the tacos', items: ['1 lb ground beef', '8 corn tortillas'] }
    ],
    ingredients: ['1 lb ground beef', '8 corn tortillas'],
    instruction_groups: [
      { title: 'Instructions', steps: ['Brown the beef.', 'Warm the tortillas.'] }
    ],
    instructions: ['Brown the beef.', 'Warm the tortillas.']
  };
}

function buildFacebookTranscriptRecipe(seed: string) {
  return {
    ...buildRecipe(seed),
    title: `Facebook Transcript Biscuits ${seed}`,
    url: 'https://www.facebook.com/reel/1234567890123456',
    original_source_url: 'https://www.facebook.com/reel/1234567890123456',
    resolved_recipe_url: '',
    content_source: 'facebook',
    source_app: 'Facebook',
    source_type: 'Social Transcript',
    ingredient_groups: [
      {
        title: '',
        items: ["'white lily all-purpose flour', 2.25, 'cups'", '1 teaspoon kosher salt']
      }
    ],
    ingredients: ["'white lily all-purpose flour', 2.25, 'cups'", '1 teaspoon kosher salt'],
    instruction_groups: [
      { title: 'Instructions', steps: ['Whisk the dry ingredients.', 'Bake until golden.'] }
    ],
    instructions: ['Whisk the dry ingredients.', 'Bake until golden.']
  };
}

function buildCleanupPreview(recipe: ReturnType<typeof buildRecipe>) {
  return {
    title: recipe.title.replace('Weeknight Tacos', 'Weeknight Beef Tacos'),
    notes: 'Serve with lime wedges and chopped cilantro.',
    servings: recipe.servings,
    prep_time: recipe.prep_time,
    cook_time: recipe.cook_time,
    total_time: recipe.total_time,
    ingredient_groups: [
      { title: 'Taco Filling', items: ['1 lb lean ground beef', '8 warm corn tortillas'] }
    ],
    ingredients: ['1 lb lean ground beef', '8 warm corn tortillas'],
    instruction_groups: [
      { title: 'Taco Steps', steps: ['Brown the beef with seasoning.', 'Warm the tortillas and serve.'] }
    ],
    instructions: ['Brown the beef with seasoning.', 'Warm the tortillas and serve.']
  };
}

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

async function getRequestUser(page: Page) {
  const response = await page.request.get('/api/auth/me');
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<{ id: number; email: string }>;
}

async function getBrowserUser(page: Page) {
  return page.evaluate(async () => {
    const response = await fetch('/api/auth/me', { credentials: 'same-origin' });
    if (!response.ok) {
      throw new Error(`Browser auth check failed with ${response.status}`);
    }
    return response.json() as Promise<{ id: number; email: string }>;
  });
}

async function maybeLogin(page: Page) {
  const appShell = page.locator('.app-shell');
  const visibleLoginForm = page.locator('#login-form:visible');

  // After reload, the login form may flash briefly while authentication is restored.
  // Give the authenticated application a chance to finish loading first.
  try {
    await expect(appShell).toBeVisible({ timeout: 5_000 });
    await getVisibleAddButton(page);
    return;
  } catch {
    // Continue only when a real visible login form remains.
  }

  await expect(visibleLoginForm).toBeVisible({ timeout: 15_000 });

  if (!LOGIN_EMAIL || !LOGIN_PASSWORD) {
    throw new Error('Login required. Set E2E_EMAIL and E2E_PASSWORD env vars.');
  }

  await visibleLoginForm.locator('#login-email').fill(LOGIN_EMAIL);
  await visibleLoginForm.locator('#login-password').fill(LOGIN_PASSWORD);
  await visibleLoginForm.getByRole('button', { name: 'Log in' }).click();

  await expect(appShell).toBeVisible({ timeout: 30_000 });
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

async function createRecipe(page: Page, recipe: ReturnType<typeof buildRecipe>, log: (message: string) => void) {
  const requestUser = await getRequestUser(page);
  const browserUser = await getBrowserUser(page);
  log(`authenticated request user: ${requestUser.email} (#${requestUser.id})`);
  log(`authenticated browser user: ${browserUser.email} (#${browserUser.id})`);
  expect(requestUser.id).toBe(browserUser.id);

  const response = await page.request.post('/api/recipes', { data: recipe });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  log(`POST /api/recipes status: ${response.status()}`);
  log(`created recipe id: ${String(body.id)}`);
  expect(typeof body.id).toBe('number');
  return body.id as number;
}

async function fetchRecipes(page: Page) {
  const response = await page.request.get('/api/recipes');
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<Array<{ id: number; title?: string; notes?: string; ingredients?: string[]; instructions?: string[] }>>;
}

async function fetchRecipeFromList(page: Page, recipeId: number) {
  const recipes = await fetchRecipes(page);
  const recipe = recipes.find((entry: { id: number }) => entry.id === recipeId);
  expect(recipe).toBeTruthy();
  return recipe;
}

async function triggerSavedRecipeAiCleanup(page: Page, recipeId: number, log: (message: string) => void) {
  const responsePromise = page.waitForResponse((response) =>
    response.url().includes(`/api/recipes/${recipeId}/ai-cleanup`) && response.request().method() === 'POST'
  );

  await page.locator('#detail-ai-cleanup-button').click();

  const response = await responsePromise;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  log(`POST /api/recipes/${recipeId}/ai-cleanup status: ${response.status()}`);
  log(`POST /api/recipes/${recipeId}/ai-cleanup body: ${JSON.stringify(body)}`);
  expect(response.ok()).toBeTruthy();

  return body as {
    message?: string;
    payload_source?: string;
    no_changes?: boolean;
    preview?: Record<string, unknown>;
  };
}

async function openUncategorizedCookbook(page: Page, log: (message: string) => void) {
  // The browser is already authenticated and on the Cookbooks dashboard.
  // Avoid a second page.goto('/'), which can stall while the app's background
  // requests are active.
  await maybeLogin(page);

  const uncategorizedButton = page
    .locator('button[data-cookbook-name="Uncategorized"]')
    .first();

  log(`Uncategorized cookbook controls found: ${await uncategorizedButton.count()}`);
  await expect(uncategorizedButton).toBeVisible({ timeout: 10_000 });

  log('clicking Uncategorized cookbook');
  await uncategorizedButton.click({ timeout: 10_000 });

  // The recipe grid should replace the cookbook dashboard after the click.
  await expect(page.locator('[data-card-open-id]').first()).toBeVisible({
    timeout: 15_000
  });
  log('Uncategorized cookbook opened');
}

async function openRecipeCard(page: Page, recipeId: number, log: (message: string) => void) {
  // The recipe was created through page.request, so the already-loaded frontend
  // still has its previous in-memory recipe list. Reload once to fetch the new row.
  log('reloading app to refresh recipe list');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await maybeLogin(page);

  log('opening Uncategorized cookbook');
  await openUncategorizedCookbook(page, log);

  const selector = `[data-card-open-id="${recipeId}"]`;
  const recipeCard = page.locator(selector);
  log(`searching for selector: ${selector}`);

  await expect(recipeCard).toHaveCount(1, { timeout: 15_000 });

  const visibleRecipeCount = await page.locator('[data-card-open-id]').count();
  log(`recipe count after cookbook opened: ${visibleRecipeCount}`);

  await expect(recipeCard).toBeVisible({ timeout: 10_000 });
  await recipeCard.click({ timeout: 10_000 });

  await expect(page.locator('#detail-title')).toBeVisible({ timeout: 10_000 });
  log(`opened recipe id: ${recipeId}`);
}

async function seedRecipe(page: Page, seed: string, log: (message: string) => void) {
  const recipe = buildRecipe(seed);
  const recipeId = await createRecipe(page, recipe, log);
  await expect
    .poll(async () => {
      const recipes = await fetchRecipes(page);
      const exists = recipes.some((entry) => entry.id === recipeId);
      log(`API recipe count after creation poll: ${recipes.length}`);
      return exists;
    }, { timeout: 30_000 })
    .toBeTruthy();
  return { recipe, recipeId };
}

test.beforeEach(async ({ page, context }) => {
  await context.clearCookies();
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  await openFreshApp(page);
  await maybeLogin(page);
});

test('saved recipe AI cleanup review can be canceled without saving', async ({ page }, testInfo) => {
  const log = (message: string) => console.log(`[ai-cleanup-review:${testInfo.title}] ${message}`);
  const seeded = await seedRecipe(page, `${testInfo.workerIndex}-${Date.now()}`, log);
  const preview = buildCleanupPreview(seeded.recipe);

  await page.route(`**/api/recipes/${seeded.recipeId}/ai-cleanup`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'AI cleanup ready for review',
        payload_source: 'ai_cleanup',
        preview
      })
    });
  });

  await openRecipeCard(page, seeded.recipeId, log);
  await expect(page.locator('#detail-title')).toHaveText(seeded.recipe.title);

  await page.locator('#detail-ai-cleanup-button').click();

  await expect(page.locator('#ai-cleanup-review-modal')).toBeVisible();
  await expect(page.locator('[data-ai-cleanup-field="title"]')).toBeVisible();
  await expect(page.locator('[data-ai-cleanup-field="title"] .ai-cleanup-review-explanation')).toContainText('more specific');
  await expect(page.locator('[data-ai-cleanup-field="notes"]')).toBeVisible();
  await expect(page.locator('[data-ai-cleanup-field="notes"] .ai-cleanup-review-explanation')).toContainText('Notes');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toBeVisible();
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"] .ai-cleanup-review-explanation')).toContainText('ingredient sections');
  await expect(page.locator('[data-ai-cleanup-field="instruction_groups"]')).toBeVisible();
  await expect(page.locator('[data-ai-cleanup-field="instruction_groups"] .ai-cleanup-review-explanation')).toContainText('instruction sections');
  await expect(page.locator('[data-ai-cleanup-field="ingredients"]')).toHaveCount(0);
  await expect(page.locator('[data-ai-cleanup-field="instructions"]')).toHaveCount(0);
  await expect(page.locator('[data-ai-cleanup-field="prep_time"]')).toHaveCount(0);

  await page.locator('#cancel-ai-cleanup-review-button').click();

  await expect(page.locator('#ai-cleanup-review-modal')).toBeHidden();
  await expect(page.locator('#detail-ai-cleanup-status')).toContainText('Recipe unchanged');
  await expect(page.locator('#detail-title')).toHaveText(seeded.recipe.title);

  const savedRecipe = await fetchRecipeFromList(page, seeded.recipeId);
  expect(savedRecipe.title).toBe(seeded.recipe.title);
  expect(savedRecipe.notes).toBe(seeded.recipe.notes);
});

test('saved recipe AI cleanup review applies structured changes only after accept', async ({ page }, testInfo) => {
  const log = (message: string) => console.log(`[ai-cleanup-review:${testInfo.title}] ${message}`);
  const seeded = await seedRecipe(page, `${testInfo.workerIndex}-${Date.now()}`, log);
  const preview = buildCleanupPreview(seeded.recipe);

  await page.route(`**/api/recipes/${seeded.recipeId}/ai-cleanup`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'AI cleanup ready for review',
        payload_source: 'ai_cleanup',
        preview
      })
    });
  });

  await openRecipeCard(page, seeded.recipeId, log);
  await page.locator('#detail-ai-cleanup-button').click();
  await expect(page.locator('#ai-cleanup-review-modal')).toBeVisible();
  await expect(page.locator('.ai-cleanup-review-explanation')).toHaveCount(4);

  await page.locator('#accept-ai-cleanup-review-button').click();

  await expect(page.locator('#ai-cleanup-review-modal')).toBeHidden();
  await expect(page.locator('#detail-ai-cleanup-status')).toContainText('changes applied');
  await expect(page.locator('#detail-title')).toHaveText(preview.title);
  await expect(page.locator('#detail-recipe-notes')).toContainText('chopped cilantro');
  await expect(page.locator('#detail-ingredients')).toContainText('1 lb lean ground beef');

  const savedRecipe = await fetchRecipeFromList(page, seeded.recipeId);
  expect(savedRecipe.title).toBe(preview.title);
  expect(savedRecipe.notes).toBe(preview.notes);
  expect(savedRecipe.ingredients).toEqual(preview.ingredients);
  expect(savedRecipe.instructions).toEqual(preview.instructions);
});

test('saved recipe AI cleanup can recommend no changes', async ({ page }, testInfo) => {
  const log = (message: string) => console.log(`[ai-cleanup-review:${testInfo.title}] ${message}`);
  const seeded = await seedRecipe(page, `${testInfo.workerIndex}-${Date.now()}`, log);

  await page.route(`**/api/recipes/${seeded.recipeId}/ai-cleanup`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'No meaningful improvements recommended.',
        payload_source: 'ai_cleanup',
        no_changes: true,
        preview: seeded.recipe
      })
    });
  });

  await openRecipeCard(page, seeded.recipeId, log);
  await page.locator('#detail-ai-cleanup-button').click();

  await expect(page.locator('#ai-cleanup-review-modal')).toBeHidden();
  await expect(page.locator('#detail-ai-cleanup-status')).toContainText('No meaningful improvements recommended.');
  await expect(page.locator('#detail-title')).toHaveText(seeded.recipe.title);

  const savedRecipe = await fetchRecipeFromList(page, seeded.recipeId);
  expect(savedRecipe.title).toBe(seeded.recipe.title);
  expect(savedRecipe.notes).toBe(seeded.recipe.notes);
});

test('saved Facebook transcript recipe cleanup can be reviewed and applied', async ({ page }, testInfo) => {
  const log = (message: string) => console.log(`[ai-cleanup-review:${testInfo.title}] ${message}`);
  const recipe = buildFacebookTranscriptRecipe(`${testInfo.workerIndex}-${Date.now()}`);
  const recipeId = await createRecipe(page, recipe, log);
  const preview = {
    ...recipe,
    ingredient_groups: [
      {
        title: 'Dry Ingredients',
        items: ['2 1/4 cups White Lily all-purpose flour', '1 teaspoon kosher salt']
      }
    ],
    ingredients: ['2 1/4 cups White Lily all-purpose flour', '1 teaspoon kosher salt']
  };

  await page.route(`**/api/recipes/${recipeId}/ai-cleanup`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'AI cleanup ready for review',
        payload_source: 'ai_cleanup',
        preview
      })
    });
  });

  await openRecipeCard(page, recipeId, log);
  await expect(page.locator('#detail-title')).toHaveText(recipe.title);

  const cleanupResponse = await triggerSavedRecipeAiCleanup(page, recipeId, log);
  expect(cleanupResponse).toMatchObject({
    message: 'AI cleanup ready for review',
    payload_source: 'ai_cleanup'
  });
  expect(cleanupResponse.no_changes).not.toBeTruthy();
  expect(cleanupResponse.preview).toMatchObject({
    ingredient_groups: [
      {
        title: 'Dry Ingredients',
        items: ['2 1/4 cups White Lily all-purpose flour', '1 teaspoon kosher salt']
      }
    ]
  });

  await expect(page.locator('#ai-cleanup-review-modal')).toBeVisible();
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toContainText('Dry Ingredients');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toContainText('2 1/4 cups White Lily all-purpose flour');
  await expect(page.locator('[data-ai-cleanup-field="ingredients"]')).toHaveCount(0);

  await page.locator('#accept-ai-cleanup-review-button').click();

  await expect(page.locator('#ai-cleanup-review-modal')).toBeHidden();
  await expect(page.locator('#detail-ingredients')).toContainText('2 1/4 cups White Lily all-purpose flour');
  await expect(page.locator('#detail-ingredients')).toContainText('Dry Ingredients');

  const savedRecipe = await fetchRecipeFromList(page, recipeId);
  expect(savedRecipe.ingredients).toEqual(preview.ingredients);
});

test('saved AI cleanup review ignores suspicious single-letter unit fragments inside ingredient words', async ({ page }, testInfo) => {
  const log = (message: string) => console.log(`[ai-cleanup-review:${testInfo.title}] ${message}`);
  const recipe = buildFacebookTranscriptRecipe(`${testInfo.workerIndex}-${Date.now()}`);
  const recipeId = await createRecipe(page, recipe, log);
  const preview = {
    ...recipe,
    ingredient_groups: [
      {
        title: 'Vegetables',
        items: [
          { quantity: 1, unit: 'l', name: 'arge yellow onion, diced' },
          { quantity: 1, unit: 'g', name: 'reen bell pepper, diced' },
          { quantity: 3, unit: 'g', name: 'arlic cloves, minced' },
          { quantity: 2, name: 'green onions, thinly sliced' },
          { quantity: 2.25, unit: 'teaspoons', name: 'baking powder' },
          { quantity: 0.5, unit: 'teaspoon', name: 'baking soda' }
        ]
      }
    ]
  };

  await page.route(`**/api/recipes/${recipeId}/ai-cleanup`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'AI cleanup ready for review',
        payload_source: 'ai_cleanup',
        preview
      })
    });
  });

  await openRecipeCard(page, recipeId, log);
  await page.locator('#detail-ai-cleanup-button').click();

  await expect(page.locator('#ai-cleanup-review-modal')).toBeVisible();
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toContainText('1 large yellow onion, diced');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toContainText('1 green bell pepper, diced');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toContainText('3 garlic cloves, minced');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toContainText('2 green onions, thinly sliced');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toContainText('2 1/4 teaspoons baking powder');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).toContainText('1/2 teaspoon baking soda');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).not.toContainText('litre arge');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).not.toContainText('gram reen');
  await expect(page.locator('[data-ai-cleanup-field="ingredient_groups"]')).not.toContainText('grams arlic');

  await page.locator('#accept-ai-cleanup-review-button').click();

  await expect(page.locator('#ai-cleanup-review-modal')).toBeHidden();
  await expect(page.locator('#detail-ingredients')).toContainText('1 large yellow onion, diced');
  await expect(page.locator('#detail-ingredients')).toContainText('1 green bell pepper, diced');
  await expect(page.locator('#detail-ingredients')).toContainText('3 garlic cloves, minced');
  await expect(page.locator('#detail-ingredients')).toContainText('2 green onions, thinly sliced');
  await expect(page.locator('#detail-ingredients')).toContainText('2 1/4 teaspoons baking powder');
  await expect(page.locator('#detail-ingredients')).toContainText('1/2 teaspoon baking soda');

  const savedRecipe = await fetchRecipeFromList(page, recipeId);
  expect(savedRecipe.ingredient_groups).toEqual([
    {
      title: 'Vegetables',
      items: [
        '1 large yellow onion, diced',
        '1 green bell pepper, diced',
        '3 garlic cloves, minced',
        '2 green onions, thinly sliced',
        '2 1/4 teaspoons baking powder',
        '1/2 teaspoon baking soda'
      ]
    }
  ]);
});
