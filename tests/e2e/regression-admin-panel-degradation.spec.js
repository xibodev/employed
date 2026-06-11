// @ts-check
// BFS-003 regression for EMP-026b: when one admin request fails (the classic
// case being a 500 from GET /admin/reports), the moderation dashboard must
// degrade PER-PANEL — the jobs and users panels still render their data and
// only the failing panel shows an error banner. Before 592a0d4 a single
// rejected promise blanked the whole page.
//
// Like every journey spec in this suite, it requires the running local stack
// (frontend :3300, API :3301, the compose Postgres container for the admin
// grant). Run with: npx playwright test tests/e2e/regression-admin-panel-degradation.spec.js
const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { randomUUID } = require('node:crypto');

const API_URL = process.env.API_URL || 'http://localhost:3301';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');
const DOCKER = process.platform === 'win32' ? 'docker.exe' : 'docker';
const POSTGRES_CONTAINER = process.env.POSTGRES_CONTAINER || 'deploy-postgres-1';
const POSTGRES_USER = process.env.POSTGRES_USER || 'employed';
const POSTGRES_DB = process.env.POSTGRES_DB || 'employed';
const PASSWORD = 'Password123!';
const REPORTS_FAILURE_TEXT = 'Stubbed reports failure (BFS-003)';

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

function buildClientIp(testInfo) {
  const seed = Array.from(`${Date.now()}-${testInfo.project.name}`).reduce((total, char) => total + char.charCodeAt(0), 0);
  return `10.${(seed % 200) + 1}.${((seed * 7) % 200) + 1}.${((seed * 13) % 200) + 1}`;
}

function requestHeaders(clientIp, token) {
  return {
    'X-Forwarded-For': clientIp,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function sqlQuote(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

function runSql(sql) {
  return execFileSync(
    DOCKER,
    ['exec', POSTGRES_CONTAINER, 'psql', '-v', 'ON_ERROR_STOP=1', '-U', POSTGRES_USER, '-d', POSTGRES_DB, '-t', '-A', '-c', sql],
    { encoding: 'utf8' },
  ).trim();
}

async function registerUser(request, email, name, clientIp) {
  const response = await request.post(`${API_URL}/auth/register`, {
    data: { email, password: PASSWORD, name },
    headers: requestHeaders(clientIp),
  });
  expect(response.ok()).toBeTruthy();
}

async function grantAdminByDb(email) {
  runSql(`update users set email_verified = true, roles = ARRAY['admin'] where email = ${sqlQuote(email)};`);
}

async function apiLogin(request, email, clientIp) {
  const response = await request.post(`${API_URL}/auth/login`, {
    data: { email, password: PASSWORD },
    headers: requestHeaders(clientIp),
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  return payload.access_token || payload.accessToken || payload.token;
}

async function seedSession(page, token) {
  await page.goto('/');
  await page.evaluate((nextToken) => {
    window.localStorage.setItem('employed_token', nextToken);
    document.cookie = `employed_token=${encodeURIComponent(nextToken)}; Path=/; SameSite=Lax`;
  }, token);
}

async function createPendingJob(request, email, title, clientIp) {
  await registerUser(request, email, 'Panel Degradation Employer', clientIp);
  runSql(`update users set email_verified = true where email = ${sqlQuote(email)};`);
  const userId = runSql(`select id from users where email = ${sqlQuote(email)} limit 1;`);
  const jobId = randomUUID();
  runSql(`insert into jobs (id, user_id, title, company, country, location, url, contact, job_type, remote, description, html_description, status, created_at, updated_at) values (${sqlQuote(jobId)}, ${sqlQuote(userId)}, ${sqlQuote(title)}, 'Degradation Co', 'Mozambique', 'Maputo', 'https://example.com/degradation-role', ${sqlQuote(email)}, 'Full Time', false, '<p>Pending job for the per-panel regression.</p>', '<p>Pending job for the per-panel regression.</p>', 'pending', timezone('utc', now()), timezone('utc', now()));`);
  return { id: jobId, title };
}

test('Regression — admin dashboard degrades per-panel when /admin/reports 500s (BFS-003 / EMP-026b)', async ({ page, request }, testInfo) => {
  test.setTimeout(120000);

  const runId = `${Date.now()}-${testInfo.project.name}`;
  const adminEmail = `panel-degrade-${runId}@test.employed.co.mz`;
  const employerEmail = `panel-degrade-employer-${runId}@test.employed.co.mz`;
  const jobTitle = `Panel Degradation Job ${runId}`;
  const clientIp = buildClientIp(testInfo);

  await page.context().setExtraHTTPHeaders({ 'X-Forwarded-For': clientIp });

  const pendingJob = await createPendingJob(request, employerEmail, jobTitle, clientIp);
  expect(pendingJob.id).toBeTruthy();
  await registerUser(request, adminEmail, 'Panel Degradation Admin', clientIp);
  await grantAdminByDb(adminEmail);
  const adminToken = await apiLogin(request, adminEmail, clientIp);

  // Stub ONLY the reports endpoint with a 500; jobs/users pass through to the
  // real API. Registered before navigating so the dashboard's initial
  // Promise.allSettled load hits the stub.
  await page.route('**/admin/reports*', (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: REPORTS_FAILURE_TEXT }),
    }),
  );

  await seedSession(page, adminToken);
  await page.goto('/admin/jobs', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => undefined);

  // Jobs panel: renders heading, tabs, and the seeded pending row — not blank.
  await expect(page.locator('body')).toContainText('Admin job moderation', { timeout: 15000 });
  await expect(page.getByRole('button', { name: /^pending/i })).toBeVisible();
  await expect(page.locator('tr', { hasText: jobTitle }).first()).toBeVisible({ timeout: 15000 });

  // Users panel: renders its data (default listing shows admins).
  await expect(page.locator('body')).toContainText('Admin users');
  await expect(page.locator('body')).toContainText(adminEmail);

  // Reports panel: its own error banner appears with the stubbed failure...
  const panelBanners = page.locator('p.rounded-2xl[class*="bg-red-500/10"]');
  await expect(panelBanners).toHaveCount(1);
  await expect(panelBanners.first()).toContainText(REPORTS_FAILURE_TEXT);

  // ...while the panel itself still renders (empty state, not a blank page).
  await expect(page.locator('body')).toContainText('Reports queue');

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${testInfo.project.name}-regression-admin-panel-degradation.png`),
    fullPage: true,
  });
});
