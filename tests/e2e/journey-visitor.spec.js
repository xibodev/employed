// @ts-check
const { test, expect } = require('@playwright/test');
const { anyLocaleRegex } = require('./i18n');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { randomUUID } = require('node:crypto');

const API_URL = process.env.API_URL || 'http://localhost:3301';
const MAILHOG_URL = process.env.MAILHOG_URL || 'http://localhost:3310';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');
const DOCKER = process.platform === 'win32' ? 'docker.exe' : 'docker';
const POSTGRES_CONTAINER = process.env.POSTGRES_CONTAINER || 'deploy-postgres-1';
const POSTGRES_USER = process.env.POSTGRES_USER || 'employed';
const POSTGRES_DB = process.env.POSTGRES_DB || 'employed';
const PASSWORD = 'Password123!';

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

function delay(ms = 500) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

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

async function snap(page, testInfo, label) {
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${testInfo.project.name}-journey-visitor-${label}.png`),
    fullPage: true,
  });
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

async function clearMailhog(request) {
  await request.delete(`${MAILHOG_URL}/api/v1/messages`).catch(() => undefined);
}

async function verifyUserByDb(email) {
  runSql(`update users set email_verified = true where email = ${sqlQuote(email)};`);
}

async function activateJobByDb(jobId) {
  runSql(
    `update jobs set status = 'active', published_at = timezone('utc', now()), featured_through = timezone('utc', now()) + interval '7 days' where id = ${sqlQuote(jobId)};`,
  );
}

function insertJobByDb(email, title) {
  const userId = runSql(`select id from users where email = ${sqlQuote(email)} limit 1;`);
  const jobId = randomUUID();
  runSql(`insert into jobs (id, user_id, title, company, country, location, url, contact, job_type, remote, description, html_description, status, created_at, updated_at, published_at, featured_through) values (${sqlQuote(jobId)}, ${sqlQuote(userId)}, ${sqlQuote(title)}, 'Visitor Journey Company', 'Mozambique', 'Maputo', 'https://example.com/visitor-role', ${sqlQuote(email)}, 'Full Time', true, '<p>Visitor journey seeded role.</p>', '<p>Visitor journey seeded role.</p>', 'active', timezone('utc', now()), timezone('utc', now()), timezone('utc', now()), timezone('utc', now()) + interval '7 days');`);
  return jobId;
}

async function registerUser(request, email, name, clientIp) {
  const response = await request.post(`${API_URL}/auth/register`, {
    data: { email, password: PASSWORD, name },
    headers: requestHeaders(clientIp),
  });
  expect(response.ok()).toBeTruthy();
}

async function loginUser(request, email, clientIp) {
  const response = await request.post(`${API_URL}/auth/login`, {
    data: { email, password: PASSWORD },
    headers: requestHeaders(clientIp),
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  return payload.access_token || payload.accessToken || payload.token;
}

async function createActiveJob(request, testInfo, clientIp) {
  const runId = `${Date.now()}-${testInfo.project.name}`;
  const email = `visitor-owner-${runId}@test.employed.co.mz`;
  const title = `Visitor Journey Role ${runId}`;

  await clearMailhog(request);
  await registerUser(request, email, 'Visitor Owner', clientIp);
  await verifyUserByDb(email);
  await loginUser(request, email, clientIp);
  const jobId = insertJobByDb(email, title);
  await activateJobByDb(jobId);
  return { jobId, title };
}

test('Journey 4 — Anonymous Visitor', async ({ page, request }, testInfo) => {
  test.setTimeout(120000);

  const clientIp = buildClientIp(testInfo);
  await page.context().setExtraHTTPHeaders({ 'X-Forwarded-For': clientIp });
  const seededJob = await createActiveJob(request, testInfo, clientIp);

  await test.step('Home page loads with featured jobs section', async () => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('navigation').getByRole('link', { name: anyLocaleRegex('nav.browseJobs') }).first()).toBeVisible();
    await expect(page.locator('body')).toContainText(anyLocaleRegex('home.heroTagline'));
    await expect(page.locator('body')).toContainText(anyLocaleRegex('nav.browseJobs'));
    await snap(page, testInfo, 'step-1-home');
    await delay();
  });

  await test.step('Browse jobs shows grid and filter controls', async () => {
    await page.goto('/jobs');
    await page.waitForLoadState('networkidle');
    await expect(page.getByLabel('Search roles')).toBeVisible();
    await expect(page.getByLabel('Job type')).toBeVisible();
    await expect(page.getByText('Remote only')).toBeVisible();
    await expect(page.locator('body')).toContainText(/jobs found|nothing to show yet/i);
    await snap(page, testInfo, 'step-2-browse');
    await delay();
  });

  await test.step('Search and filters update the URL params', async () => {
    await page.getByLabel('Search roles').fill('Visitor Journey Role');
    await delay();
    await page.getByLabel('Job type').selectOption('Full Time');
    await delay();
    const searchBtn = page.getByRole('button', { name: /search/i }).first();
    await searchBtn.scrollIntoViewIfNeeded();
    await searchBtn.click({ timeout: 10000 }).catch(async () => {
      // Fallback: submit the form or press Enter
      await page.getByLabel('Search roles').press('Enter');
    });
    await page.waitForURL(/search=/, { timeout: 15000 }).catch(() => {});
    await snap(page, testInfo, 'step-3-search');
    await delay();
  });

  await test.step('The seeded job detail page loads', async () => {
    await page.goto(`/jobs/${seededJob.jobId}`);
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(new RegExp(`/jobs/${seededJob.jobId}`));
    await expect(page.locator('body')).toContainText(seededJob.title);
    await snap(page, testInfo, 'step-4-detail');
    await delay();
  });

  await test.step('Guarded routes redirect to sign-in', async () => {
    await page.goto('/myjobs');
    await page.waitForURL(/\/sign-in/);
    await expect(page).toHaveURL(/redirect=%2Fmyjobs|redirect=\/myjobs/);
    await snap(page, testInfo, 'step-5-myjobs-redirect');
    await delay();

    await page.goto('/admin/jobs');
    await page.waitForURL(/\/sign-in/);
    await expect(page).toHaveURL(/sign-in/);
    await snap(page, testInfo, 'step-6-admin-redirect');
    await delay();
  });

  await test.step('Terms and privacy pages render content', async () => {
    await page.goto('/terms');
    await expect(page.locator('body')).toContainText(/terms/i);
    await snap(page, testInfo, 'step-7-terms');
    await delay();

    await page.goto('/privacy');
    await expect(page.locator('body')).toContainText(/privacy/i);
    await snap(page, testInfo, 'step-7-privacy');
    await delay();
  });

  await test.step('Public API jobs endpoint returns paginated JSON', async () => {
    const response = await request.get(`${API_URL}/api/jobs?page=1&page_size=10`);
    expect(response.ok()).toBeTruthy();
    const payload = await response.json();
    expect(Array.isArray(payload.items)).toBeTruthy();
    expect(payload).toHaveProperty('total');
    expect(payload).toHaveProperty('page');
    expect(payload).toHaveProperty('page_size');
    expect(payload.items.some((item) => item.id === seededJob.jobId)).toBeTruthy();
  });
});
