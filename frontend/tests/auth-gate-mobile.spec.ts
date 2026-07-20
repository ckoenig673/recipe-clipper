import { expect, test } from '@playwright/test';

test('unauthenticated mobile session is locked to login screen', async ({ page, context }) => {
  await context.clearCookies();
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto('/');

  await expect(page.locator('#login-form')).toBeVisible();
  await expect(page.locator('.app-shell')).toHaveCount(0);
  await expect(page.locator('#mobile-bottom-nav')).toHaveCount(0);
  await expect(page.locator('#cookbooks-panel')).toHaveCount(0);
  await expect(page.locator('#dashboard-search-panel')).toHaveCount(0);
  await expect(page.locator('#meal-plan-view')).toHaveCount(0);
  await expect(page.locator('#shopping-list-view')).toHaveCount(0);
  await expect(page.locator('#add-recipe-modal')).toHaveCount(0);

  await expect(page.locator('#mobile-add-button')).toHaveCount(0);
});

test('share_target URL in shared_text routes to import mode and populates URL input', async ({ page, context }) => {
  const sharedUrl = 'https://sallysbakingaddiction.com/chewy-chocolate-chip-cookies/';
  await context.clearCookies();
  await page.addInitScript((url) => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.localStorage.setItem('shared_text', url);
  }, sharedUrl);

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, email: 'test@example.com' })
    });
  });
  await page.route('**/api/recipes', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });
  await page.route('**/api/cookbooks', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });

  await page.goto('/?share_target=1');

  await expect(page.locator('#add-recipe-modal')).toBeVisible();
  await expect(page.locator('#import-browser-panel')).toBeVisible();
  await expect(page.locator('#url')).toBeVisible();
  await expect(page.locator('#url')).toHaveValue(sharedUrl);
  await expect(page.locator('#paste-text-panel')).toBeHidden();
});

test('admin accounts access settings and admin users independently', async ({ page, context }) => {
  await context.clearCookies();
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 7, email: 'admin@example.com', is_admin: true })
    });
  });
  await page.route('**/api/recipes', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });
  await page.route('**/api/cookbooks', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });
  await page.route('**/api/settings/import', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        facebook_cookie_configured: true,
        facebook_cookie_preview: 'c_user=***',
        services: {}
      })
    });
  });
  await page.route('**/api/status/import-services', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        services: {
          social_downloader: {
            status: 'ok',
            url: 'http://social:80/health',
            last_checked_at: '2026-07-12T12:00:00Z'
          }
        }
      })
    });
  });
  await page.route('**/api/admin/security-settings', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        auth_lockout_enabled: true,
        auth_max_failed_attempts: 5,
        auth_lockout_minutes: 15
      })
    });
  });
  await page.route('**/api/admin/users', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 7,
          email: 'admin@example.com',
          display_name: 'Admin User',
          is_admin: true,
          is_active: true,
          is_locked_manual: false,
          locked_until: null,
          failed_login_attempts: 0,
          created_at: '2026-07-10T12:00:00Z',
          last_login: '2026-07-12T12:00:00Z'
        }
      ])
    });
  });

  await page.goto('/');

  await page.locator('#nav-settings-button').click();
  await expect(page.locator('#settings-panel')).toBeVisible();
  await expect(page.locator('#settings-panel')).toContainText('Facebook cookie');
  await expect(page.locator('#settings-panel')).toContainText('Import Services Status');

  await page.locator('#nav-admin-users-button').click();
  await expect(page.locator('#admin-users-panel')).toBeVisible();
  await expect(page.locator('#admin-users-panel')).toContainText('Security settings');
  await expect(page.locator('#admin-users-panel')).toContainText('Manage roles, lock state, and account access.');
  await expect(page.locator('#admin-users-panel')).not.toContainText('Facebook cookie');
  await expect(page.locator('#admin-users-panel')).not.toContainText('Import Services Status');

  await page.locator('#nav-settings-button').click();
  await expect(page.locator('#settings-panel')).toBeVisible();
  await expect(page.locator('#facebook-cookie-input')).toBeVisible();
});
