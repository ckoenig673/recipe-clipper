import { expect, type Page } from '@playwright/test';

type RecipeSummary = {
  id: number;
};

export async function fetchRecipeIds(page: Page): Promise<Set<number>> {
  const response = await page.request.get('/api/recipes');
  expect(response.ok()).toBeTruthy();
  const recipes = (await response.json()) as RecipeSummary[];
  return new Set(
    recipes
      .map((recipe) => Number(recipe.id))
      .filter((recipeId) => Number.isInteger(recipeId) && recipeId > 0)
  );
}

export async function cleanupRecipesAddedSince(page: Page, baselineRecipeIds: Set<number>, logPrefix: string) {
  const response = await page.request.get('/api/recipes');
  if (!response.ok()) {
    console.warn(`[${logPrefix}] cleanup skipped: unable to list recipes (${response.status()})`);
    return;
  }

  const recipes = (await response.json()) as RecipeSummary[];
  const createdRecipeIds = recipes
    .map((recipe) => Number(recipe.id))
    .filter((recipeId) => Number.isInteger(recipeId) && recipeId > 0 && !baselineRecipeIds.has(recipeId));

  for (const recipeId of createdRecipeIds) {
    const deleteResponse = await page.request.delete(`/api/recipes/${recipeId}`);
    if (!deleteResponse.ok() && deleteResponse.status() !== 404) {
      console.warn(`[${logPrefix}] cleanup failed for recipe ${recipeId}: ${deleteResponse.status()}`);
    }
  }
}
