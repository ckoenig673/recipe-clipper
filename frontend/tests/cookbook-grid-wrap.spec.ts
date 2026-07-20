import { expect, test, type Page } from '@playwright/test';

type Cookbook = {
  id: number;
  name: string;
};

type Recipe = {
  id: number;
  title: string;
  cookbook_ids: number[];
  cookbooks: Cookbook[];
};

function buildCookbookFixtures(count: number) {
  const cookbooks: Cookbook[] = Array.from({ length: count }, (_, index) => ({
    id: index + 1,
    name: `Collection ${index + 1} with a longer title`,
  }));

  const recipes: Recipe[] = cookbooks.map((cookbook) => ({
    id: cookbook.id,
    title: `Recipe ${cookbook.id}`,
    cookbook_ids: [cookbook.id],
    cookbooks: [{ ...cookbook }],
  }));

  return { cookbooks, recipes };
}

async function bootstrapCookbookDashboard(page: Page, cookbookCount = 8) {
  const state = buildCookbookFixtures(cookbookCount);

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

  await page.route('**/api/recipes', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(state.recipes),
    });
  });

  await page.route('**/api/cookbooks', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(state.cookbooks),
    });
  });

  await page.goto('/');
  await expect(page.locator('.app-shell')).toHaveCount(1);
  await expect(page.locator('.cookbooks-header')).toBeVisible();
  await expect(page.locator('#cookbook-grid .cookbook-tile')).toHaveCount(cookbookCount + 1);
}

async function measureCookbookGrid(page: Page) {
  return page.locator('#cookbook-grid').evaluate((grid) => {
    const rounded = (value: number) => Math.round(value);
    const tiles = Array.from(grid.querySelectorAll<HTMLElement>('.cookbook-tile'));
    const tops = tiles.map((tile) => rounded(tile.getBoundingClientRect().top));
    const lefts = tiles.map((tile) => rounded(tile.getBoundingClientRect().left));
    const widths = tiles.map((tile) => rounded(tile.getBoundingClientRect().width));
    const contentOverflow = tiles.some((tile) => {
      const title = tile.querySelector<HTMLElement>('.cookbook-tile-title');
      const count = tile.querySelector<HTMLElement>('.cookbook-tile-count');
      const tileClipped = tile.scrollWidth > tile.clientWidth + 1;
      const titleClipped = title ? title.scrollWidth > title.clientWidth + 1 : false;
      const countClipped = count ? count.scrollWidth > count.clientWidth + 1 : false;
      return tileClipped || titleClipped || countClipped;
    });

    return {
      clientWidth: grid.clientWidth,
      scrollWidth: grid.scrollWidth,
      rowCount: new Set(tops).size,
      columnCount: new Set(lefts).size,
      minWidth: Math.min(...widths),
      maxWidth: Math.max(...widths),
      contentOverflow,
    };
  });
}

test('cookbook tiles wrap into multiple rows on desktop without horizontal scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await bootstrapCookbookDashboard(page, 9);

  const metrics = await measureCookbookGrid(page);

  expect(metrics.rowCount).toBeGreaterThan(1);
  expect(metrics.columnCount).toBeGreaterThan(2);
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
  expect(metrics.maxWidth - metrics.minWidth).toBeLessThanOrEqual(2);
  expect(metrics.contentOverflow).toBeFalsy();
});

test('cookbook tiles reduce to one or two columns on mobile without clipping', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await bootstrapCookbookDashboard(page, 7);

  const metrics = await measureCookbookGrid(page);

  expect(metrics.rowCount).toBeGreaterThan(1);
  expect(metrics.columnCount).toBeGreaterThanOrEqual(1);
  expect(metrics.columnCount).toBeLessThanOrEqual(2);
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
  expect(metrics.maxWidth - metrics.minWidth).toBeLessThanOrEqual(2);
  expect(metrics.contentOverflow).toBeFalsy();
});
