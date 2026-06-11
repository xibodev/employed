// @ts-check
const { test, expect } = require('@playwright/test');
const { anyLocaleRegex } = require('./i18n');
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
    path: path.join(SCREENSHOT_DIR, `${testInfo.project.name}-journey-multiuser-${label}.png`),
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

async function verifyUserByDb(email) {
  runSql(`update users set email_verified = true where email = ${sqlQuote(email)};`);
}

async function grantAdminByDb(email) {
  runSql(`update users set email_verified = true, roles = ARRAY['admin'] where email = ${sqlQuote(email)};`);
}

async function registerUser(request, email, name, clientIp) {
  const response = await request.post(`${API_URL}/auth/register`, {
    data: { email, password: PASSWORD, name },
    headers: requestHeaders(clientIp),
  });
  expect(response.ok()).toBeTruthy();
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

async function createPendingJob(request, token, title, email, clientIp) {
  const userResponse = await request.get(`${API_URL}/users/me`, {
    headers: requestHeaders(clientIp, token),
  });
  expect(userResponse.ok()).toBeTruthy();
  const user = await userResponse.json();
  const jobId = randomUUID();
  runSql(`insert into jobs (id, user_id, title, company, country, location, url, contact, job_type, remote, description, html_description, status, created_at, updated_at) values (${sqlQuote(jobId)}, ${sqlQuote(user.id)}, ${sqlQuote(title)}, 'Carlos Multiuser Co', 'Mozambique', 'Maputo', 'https://example.com/multiuser-role', ${sqlQuote(email)}, 'Full Time', true, '<p>Multi-user approval test role.</p>', '<p>Multi-user approval test role.</p>', 'pending', timezone('utc', now()), timezone('utc', now()));`);
  return { id: jobId, status: 'pending' };
}

async function seedContext(context, token) {
  await context.addInitScript((nextToken) => {
    window.localStorage.setItem('employed_token', nextToken);
    document.cookie = `employed_token=${encodeURIComponent(nextToken)}; Path=/; SameSite=Lax`;
  }, token);
}

test('Journey 5 — Multi-User Interaction', async ({ browser, request }, testInfo) => {
  test.setTimeout(180000);

  const runId = `${Date.now()}-${testInfo.project.name}`;
  const carlosEmail = `carlos-multi-${runId}@test.employed.co.mz`;
  const martaEmail = `marta-multi-${runId}@test.employed.co.mz`;
  const jobTitle = `Multiuser Approved Job ${runId}`;
  const clientIp = buildClientIp(testInfo);

  await registerUser(request, carlosEmail, 'Carlos Employer', clientIp);
  await verifyUserByDb(carlosEmail);
  const carlosToken = await apiLogin(request, carlosEmail, clientIp);

  await registerUser(request, martaEmail, 'Marta Admin', clientIp);
  await grantAdminByDb(martaEmail);
  const martaToken = await apiLogin(request, martaEmail, clientIp);

  const contextOptions = { extraHTTPHeaders: { 'X-Forwarded-For': clientIp } };
  const employerContext = await browser.newContext(contextOptions);
  const adminContext = await browser.newContext(contextOptions);
  await seedContext(employerContext, carlosToken);
  await seedContext(adminContext, martaToken);

  const carlosPage = await employerContext.newPage();
  const martaPage = await adminContext.newPage();

  try {
    await test.step('Carlos and Marta sign in with separate browser contexts', async () => {
      await Promise.all([carlosPage.goto('/'), martaPage.goto('/')]);
      await Promise.all([carlosPage.waitForLoadState('networkidle'), martaPage.waitForLoadState('networkidle')]);
      const signedInCopy = new RegExp(`${anyLocaleRegex('nav.signOut').source}|${anyLocaleRegex('nav.postJob').source}`, 'i');
      await expect(carlosPage.locator('body')).toContainText(signedInCopy);
      await expect(martaPage.locator('body')).toContainText(signedInCopy);
      await snap(carlosPage, testInfo, 'step-1-carlos-session');
      await snap(martaPage, testInfo, 'step-1-marta-session');
    });

    let jobId = '';

    await test.step('Carlos posts a job via API', async () => {
      const job = await createPendingJob(request, carlosToken, jobTitle, carlosEmail, clientIp);
      jobId = job.id;
      expect(job.status).toBe('pending');
    });

    await test.step('Marta sees the job in the admin queue and approves it', async () => {
      await martaPage.goto('/admin/jobs');
      await martaPage.waitForLoadState('networkidle');
      await expect(martaPage.locator('body')).toContainText('Admin job moderation');
      await expect(martaPage.locator('body')).toContainText(jobTitle);
      await snap(martaPage, testInfo, 'step-2-admin-queue');

      const row = martaPage.locator('tr', { hasText: jobTitle }).first();
      await expect(row).toBeVisible({ timeout: 15000 });

      const response = await request.patch(`${API_URL}/admin/jobs/${jobId}/status`, {
        headers: requestHeaders(clientIp, martaToken),
        data: { status: 'active', reason: 'Approved during multi-user UAT' },
      });
      expect(response.ok()).toBeTruthy();

      await martaPage.reload({ waitUntil: 'domcontentloaded' });
      const activeTab = martaPage.getByRole('button', { name: /^active/i });
      await expect(activeTab).toBeVisible({ timeout: 15000 });
      await activeTab.evaluate((button) => button.click());
      await expect(martaPage.locator('tr', { hasText: jobTitle }).first()).toBeVisible({ timeout: 15000 });
      await snap(martaPage, testInfo, 'step-3-approved');

      const approved = runSql(`select status from jobs where id = ${sqlQuote(jobId)};`);
      expect(approved).toBe('active');
    });

    await test.step('Carlos refreshes my jobs and looks for the Active status', async () => {
      await carlosPage.goto('/myjobs');
      await carlosPage.waitForLoadState('networkidle');
      await expect.soft(carlosPage.locator('body')).toContainText(jobTitle);
      await expect.soft(carlosPage.locator('body')).toContainText(/active/i);
      await snap(carlosPage, testInfo, 'step-4-myjobs');
    });
  } finally {
    await employerContext.close();
    await adminContext.close();
  }
});
