import { expect, test, type Page } from '@playwright/test';

type Cookbook = {
  id: number;
  name: string;
};

type Recipe = {
  id: number;
  title: string;
  image_url?: string | null;
  prep_time?: string;
  cook_time?: string;
  cookbook_ids: number[];
  cookbooks: Cookbook[];
};

function cloneRecipes(recipes: Recipe[]) {
  return recipes.map((recipe) => ({
    ...recipe,
    cookbook_ids: [...recipe.cookbook_ids],
    cookbooks: recipe.cookbooks.map((cookbook) => ({ ...cookbook })),
  }));
}

async function bootstrapRecipeApp(page: Page) {
  const state = {
    cookbooks: [
      { id: 11, name: 'Breakfast' },
      { id: 12, name: 'Dinner' },
    ] satisfies Cookbook[],
    recipes: cloneRecipes([
      { id: 1, title: 'Berry Pancakes', cookbook_ids: [11], cookbooks: [{ id: 11, name: 'Breakfast' }] },
      { id: 2, title: 'Cheese Omelet', cookbook_ids: [11], cookbooks: [{ id: 11, name: 'Breakfast' }] },
      { id: 3, title: 'Classic Waffles', cookbook_ids: [11], cookbooks: [{ id: 11, name: 'Breakfast' }] },
      { id: 4, title: 'Tomato Soup', cookbook_ids: [12], cookbooks: [{ id: 12, name: 'Dinner' }] },
    ] satisfies Recipe[]),
    groceryPreviewCalls: [] as number[][],
    moveCalls: [] as Array<{ recipeId: number; cookbookIds: number[] }>,
    deleteCalls: [] as number[],
    createCookbookCalls: [] as string[],
  };

  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, email: 'test@example.com', is_admin: false }),
    });
  });

  await page.route('**/api/grocery-list/preview', async (route) => {
    const body = route.request().postDataJSON() as { recipe_ids?: number[] };
    const recipeIds = Array.isArray(body.recipe_ids) ? body.recipe_ids.map(Number) : [];
    state.groceryPreviewCalls.push(recipeIds);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: recipeIds.map((recipeId) => ({
          name: `Item for ${recipeId}`,
          display_text: `Item for ${recipeId}`,
          source_recipe_id: recipeId,
          source_recipe_title: state.recipes.find((recipe) => recipe.id === recipeId)?.title || '',
        })),
      }),
    });
  });

  await page.route(/\/api\/recipes\/\d+\/cookbooks$/, async (route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/api\/recipes\/(\d+)\/cookbooks$/);
    const recipeId = Number(match?.[1] || 0);

    if (route.request().method() !== 'PUT') {
      await route.fulfill({ status: 405, contentType: 'application/json', body: '{}' });
      return;
    }

    const body = route.request().postDataJSON() as { cookbook_ids?: number[] };
    const cookbookIds = Array.isArray(body.cookbook_ids) ? body.cookbook_ids.map(Number).sort((a, b) => a - b) : [];
    const recipe = state.recipes.find((entry) => entry.id === recipeId);
    if (recipe) {
      recipe.cookbook_ids = cookbookIds;
      recipe.cookbooks = state.cookbooks.filter((cookbook) => cookbookIds.includes(cookbook.id)).map((cookbook) => ({ ...cookbook }));
    }
    state.moveCalls.push({ recipeId, cookbookIds });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(recipe?.cookbooks || []),
    });
  });

  await page.route(/\/api\/recipes\/\d+$/, async (route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/api\/recipes\/(\d+)$/);
    const recipeId = Number(match?.[1] || 0);

    if (route.request().method() !== 'DELETE') {
      await route.fallback();
      return;
    }

    state.recipes = state.recipes.filter((recipe) => recipe.id !== recipeId);
    state.deleteCalls.push(recipeId);
    await route.fulfill({ status: 204, body: '' });
  });

  await page.route('**/api/recipes', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(state.recipes),
    });
  });

  await page.route('**/api/cookbooks', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as { name?: string };
      const name = String(body.name || '').trim();
      const existing = state.cookbooks.find((cookbook) => cookbook.name.toLowerCase() === name.toLowerCase());
      if (existing) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(existing),
        });
        return;
      }

      const nextCookbook = { id: Math.max(...state.cookbooks.map((cookbook) => cookbook.id)) + 1, name };
      state.cookbooks.push(nextCookbook);
      state.createCookbookCalls.push(name);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(nextCookbook),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(state.cookbooks),
    });
  });

  await page.goto('/');
  await expect(page.locator('.app-shell')).toHaveCount(1);

  return state;
}

async function openCookbook(page: Page, name: string) {
  const dashboardTile = page.getByRole('button', { name: `Open ${name} cookbook`, exact: true });
  const sideNavButton = page.getByRole('button', { name: `Open ${name}`, exact: true });
  if (await dashboardTile.isVisible().catch(() => false)) {
    await dashboardTile.click();
  } else {
    await sideNavButton.click();
  }
  await expect(page.locator('#selected-cookbook-title')).toHaveText(name);
}

test('select all, clear selection, filtered selection, and grocery preview stay scoped to visible recipes', async ({ page }) => {
  const state = await bootstrapRecipeApp(page);
  await openCookbook(page, 'Breakfast');

  await page.locator('#shopping-selection-toggle').click();
  await expect(page.locator('#select-all-recipes-button')).toBeVisible();
  await expect(page.locator('#shopping-selection-count')).toHaveText('0 recipes selected');

  await page.locator('#select-all-recipes-button').click();
  await expect(page.locator('#shopping-selection-count')).toHaveText('3 recipes selected');
  await expect(page.locator('#select-all-recipes-button')).toHaveText('Clear Selection');
  await expect(page.locator('#generate-shopping-list-button')).toBeEnabled();
  await expect(page.locator('#move-selected-recipes-button')).toBeEnabled();
  await expect(page.locator('#delete-selected-recipes-button')).toBeEnabled();
  expect(state.groceryPreviewCalls).toEqual([]);
  expect(state.moveCalls).toEqual([]);
  expect(state.deleteCalls).toEqual([]);

  await page.locator('#cookbook-search-input').fill('Berry');
  await expect(page.locator('#shopping-selection-count')).toHaveText('1 recipe selected');
  await expect(page.locator('[data-card-open-id]')).toHaveCount(1);
  await expect(page.locator('#select-all-recipes-button')).toHaveText('Clear Selection');

  await page.locator('#select-all-recipes-button').click();
  await expect(page.locator('#shopping-selection-count')).toHaveText('0 recipes selected');
  await expect(page.locator('#generate-shopping-list-button')).toBeDisabled();
  expect(state.groceryPreviewCalls).toEqual([]);
  expect(state.moveCalls).toEqual([]);
  expect(state.deleteCalls).toEqual([]);

  await page.locator('[data-shopping-recipe-id="1"]').check();
  await expect(page.locator('#shopping-selection-count')).toHaveText('1 recipe selected');
  await page.locator('#generate-shopping-list-button').click();

  await expect(page.locator('#grocery-preview-modal')).toBeVisible();
  expect(state.groceryPreviewCalls).toEqual([[1]]);
  expect(state.moveCalls).toEqual([]);
  expect(state.deleteCalls).toEqual([]);
});

test('bulk move updates only the selected recipes', async ({ page }) => {
  const state = await bootstrapRecipeApp(page);
  await openCookbook(page, 'Breakfast');

  await page.locator('#shopping-selection-toggle').click();
  await expect(page.locator('#select-all-recipes-button')).toBeVisible();
  await page.locator('#cookbook-search-input').fill('Omelet');
  await expect(page.locator('[data-card-open-id]')).toHaveCount(1);

  await page.locator('#select-all-recipes-button').click();
  await expect(page.locator('#shopping-selection-count')).toHaveText('1 recipe selected');
  await page.locator('#move-selected-recipes-button').click();

  await expect(page.locator('#shopping-selection-toggle')).toHaveText('Select recipes');
  expect(state.moveCalls).toEqual([{ recipeId: 2, cookbookIds: [12] }]);
  expect(state.createCookbookCalls).toEqual([]);

  await expect(page.locator('#selected-cookbook-count')).toHaveText('2 recipes');
  await expect(page.locator('[data-card-open-id]')).toHaveCount(0);

  await page.locator('#cookbook-search-input').fill('');
  await expect(page.locator('[data-card-open-id]')).toHaveCount(2);
  await expect(page.locator('#recipes')).not.toContainText('Cheese Omelet');

  await openCookbook(page, 'Dinner');
  await expect(page.locator('#recipes')).toContainText('Cheese Omelet');
  await expect(page.locator('#selected-cookbook-count')).toHaveText('2 recipes');
});

test('individual checkbox selection still updates bulk actions without selecting other visible recipes', async ({ page }) => {
  const state = await bootstrapRecipeApp(page);
  await openCookbook(page, 'Breakfast');

  await page.locator('#shopping-selection-toggle').click();
  await expect(page.locator('#select-all-recipes-button')).toBeVisible();
  await expect(page.locator('#shopping-selection-count')).toHaveText('0 recipes selected');

  await page.locator('[data-shopping-recipe-id="2"]').check();
  await expect(page.locator('#shopping-selection-count')).toHaveText('1 recipe selected');
  await expect(page.locator('#select-all-recipes-button')).toHaveText('Select All');
  await expect(page.locator('#generate-shopping-list-button')).toBeEnabled();
  await expect(page.locator('#move-selected-recipes-button')).toBeEnabled();
  await expect(page.locator('#delete-selected-recipes-button')).toBeEnabled();

  await page.locator('#generate-shopping-list-button').click();
  await expect(page.locator('#grocery-preview-modal')).toBeVisible();
  expect(state.groceryPreviewCalls).toEqual([[2]]);
  expect(state.moveCalls).toEqual([]);
  expect(state.deleteCalls).toEqual([]);
});

test('bulk delete removes only the selected recipes', async ({ page }) => {
  const state = await bootstrapRecipeApp(page);
  await openCookbook(page, 'Breakfast');

  await page.locator('#shopping-selection-toggle').click();
  await page.locator('[data-shopping-recipe-id="1"]').check();
  await page.locator('[data-shopping-recipe-id="3"]').check();
  await expect(page.locator('#shopping-selection-count')).toHaveText('2 recipes selected');

  page.once('dialog', async (dialog) => {
    expect(dialog.type()).toBe('confirm');
    await dialog.accept();
  });
  await page.locator('#delete-selected-recipes-button').click();

  await expect(page.locator('#selected-cookbook-count')).toHaveText('1 recipe');
  await expect(page.locator('[data-card-open-id]')).toHaveCount(1);
  await expect(page.locator('[data-card-open-id]')).toContainText('Cheese Omelet');
  expect(state.deleteCalls.sort((a, b) => a - b)).toEqual([1, 3]);
});
