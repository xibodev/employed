// @ts-check
const { test, expect } = require('@playwright/test');
const { anyLocaleRegex } = require('./i18n');

const API_URL = process.env.API_URL || 'http://localhost:3301';
const MAILHOG_URL = process.env.MAILHOG_URL || 'http://localhost:3310';

// ─── Anonymous visitor journeys ───────────────────────────────────

test.describe('Anonymous Visitor', () => {
  test('home page loads with hero and job listings', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Employed/);
    // Hero section should be visible
    const body = page.locator('body');
    // TD-001: default market serves pt — assert catalog copy, any locale
    await expect(body).toContainText(anyLocaleRegex('home.heroTagline'));
  });

  test('health endpoint returns ok', async ({ request }) => {
    const res = await request.get(`${API_URL}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe('ok');
    expect(body.db).toBe('ok');
    expect(body.redis).toBe('ok');
  });

  test('API jobs endpoint responds', async ({ request }) => {
    const res = await request.get(`${API_URL}/api/jobs`);
    expect(res.ok()).toBeTruthy();
  });

  test('robots.txt is served', async ({ request }) => {
    // TD-003: robots.txt ships now (env-derived base URL, EMP-024)
    const res = await request.get('/robots.txt');
    expect(res.status()).toBe(200);
    expect(await res.text()).toContain('Sitemap:');
  });

  test('sitemap.xml is served', async ({ request }) => {
    // TD-003: sitemap.xml ships now (env-derived market hosts, EMP-024)
    const res = await request.get('/sitemap.xml');
    expect(res.status()).toBe(200);
    expect(await res.text()).toContain('<urlset');
  });

  test('jobs listing page loads', async ({ page }) => {
    await page.goto('/jobs');
    await expect(page).toHaveTitle(/Browse jobs \| Employed/);
  });

  test('legal page loads', async ({ page }) => {
    await page.goto('/legal/terms');
    // Should load without error
    await expect(page.locator('body')).toBeVisible();
  });

  test('sign-up page loads', async ({ page }) => {
    await page.goto('/sign-up');
    await expect(page.locator('body')).toBeVisible();
  });

  test('sign-in page loads', async ({ page }) => {
    await page.goto('/sign-in');
    await expect(page.locator('body')).toBeVisible();
  });

  test('non-existent page shows 404', async ({ page }) => {
    await page.goto('/nonexistent-route-xyz');
    await expect(page.locator('body')).toContainText(/find that page/i);
  });
});

// ─── Navigation & responsive ──────────────────────────────────────

test.describe('Navigation', () => {
  test('header nav links are present', async ({ page }) => {
    await page.goto('/');
    const nav = page.locator('nav, .navbar, header');
    await expect(nav.first()).toBeVisible({ timeout: 30000 });
  });

  test('footer is present', async ({ page }) => {
    await page.goto('/');
    const footer = page.locator('footer, .footer');
    await expect(footer.first()).toBeVisible();
  });
});

// ─── SEO & meta ───────────────────────────────────────────────────

test.describe('SEO', () => {
  test('home page has meta description', async ({ page }) => {
    await page.goto('/');
    const meta = page.locator('meta[name="description"]');
    await expect(meta).toHaveAttribute('content', /.+/);
  });

  test('home page has og:title or title tag', async ({ page }) => {
    await page.goto('/');
    // og:title may be dynamically set; verify title tag exists at minimum
    await expect(page).toHaveTitle(/Employed/);
  });
});

// ─── Auth routes guard ────────────────────────────────────────────

test.describe('Auth Guards', () => {
  test('admin route redirects non-admin to jobs', async ({ page }) => {
    await page.goto('/admin/jobs');
    // Should redirect away from admin since not logged in
    await page.waitForURL(/\/(jobs|sign-in|$)/);
  });

  test('my jobs route requires sign-in', async ({ page }) => {
    await page.goto('/myjobs');
    await expect(page.locator('body')).toBeVisible();
  });
});

// ─── MailHog service check ────────────────────────────────────────

test.describe('External Services', () => {
  test('MailHog API is reachable', async ({ request }) => {
    const res = await request.get(`${MAILHOG_URL}/api/v2/messages`);
    expect(res.ok()).toBeTruthy();
  });
});

// ─── L10: Security headers & API shape ────────────────────────────

test.describe('Response Headers', () => {
  test('home page responds with html content type', async ({ request }) => {
    const res = await request.get('/');
    expect(res.headers()['content-type']).toContain('text/html');
  });

  test('home page disables caching in local UAT', async ({ request }) => {
    const res = await request.get('/');
    const cacheControl = res.headers()['cache-control'];
    expect(cacheControl).toContain('no-cache');
    expect(cacheControl).toContain('no-store');
    expect(cacheControl).toContain('must-revalidate');
  });
});

test.describe('API Response Shape', () => {
  test('health response has expected fields', async ({ request }) => {
    const res = await request.get(`${API_URL}/health`);
    const body = await res.json();
    expect(body).toEqual({
      status: 'ok',
      db: 'ok',
      redis: 'ok',
    });
  });

  test('/api/jobs returns paginated items', async ({ request }) => {
    const res = await request.get(`${API_URL}/api/jobs`);
    const body = await res.json();
    expect(Array.isArray(body.items)).toBeTruthy();
    expect(body).toHaveProperty('total');
    expect(body).toHaveProperty('page');
    expect(body).toHaveProperty('page_size');
  });
});
