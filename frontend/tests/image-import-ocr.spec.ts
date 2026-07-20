import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';

const LOGIN_EMAIL = process.env.E2E_EMAIL;
const LOGIN_PASSWORD = process.env.E2E_PASSWORD;
const OCR_SAMPLE_IMAGE = path.resolve(process.cwd(), 'frontend/tests/fixtures/banana-crunch-cake.jpg');

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

async function waitForAuthenticatedShell(page: Page) {
  await expect(page.locator('.app-shell')).toHaveCount(1, { timeout: 30_000 });
  await getVisibleAddButton(page);
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
  await waitForAuthenticatedShell(page);
}

async function runImageImportAndAssert(page: Page) {
  await page.goto('/');
  await maybeLogin(page);
  const addButton = await getVisibleAddButton(page);
  await addButton.click();

  await expect(page.locator('#import-option-grid')).toBeVisible();
  await expect(page.locator('#image-upload-input')).toHaveCount(1);
  const ocrResponsePromise = page.waitForResponse(
    (response) => response.url().includes('/import/image') && response.status() === 200,
    { timeout: 180_000 }
  );
  const fileChooserPromise = page.waitForEvent('filechooser');
  await page.locator('#upload-photo-button').click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.setFiles(OCR_SAMPLE_IMAGE);
  await ocrResponsePromise;

  await expect(page.locator('#parsed-results')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('#edit-fields-panel')).toBeVisible();

  await expect(page.locator('#edit-title-input')).not.toHaveValue('');
  await expect
    .poll(async () => page.locator('[data-testid="parsed-ingredient-row"] input').count(), { timeout: 60_000 })
    .toBeGreaterThan(0);
  await expect
    .poll(async () => page.locator('[data-testid="parsed-instruction-row"] textarea').count(), { timeout: 60_000 })
    .toBeGreaterThan(0);
}

test('image OCR import transitions to parsed editor on desktop', async ({ page }) => {
  await runImageImportAndAssert(page);
});

test('image OCR import transitions to parsed editor on mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await runImageImportAndAssert(page);
});
