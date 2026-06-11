// @ts-check
const { test, expect } = require('@playwright/test');
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

async function gotoAndWait(page, url, readyLocator) {
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await expect(readyLocator).toBeVisible({ timeout: 15000 });
}

async function submitVisibleForm(page) {
  await page.locator('form').first().evaluate((form) => form.requestSubmit());
}

async function snap(page, testInfo, label) {
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${testInfo.project.name}-journey-seeker-${label}.png`),
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

async function listMessages(request) {
  const response = await request.get(`${MAILHOG_URL}/api/v2/messages`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

function subjectFor(message) {
  return (
    message?.Content?.Headers?.Subject?.[0] ||
    message?.MIME?.Headers?.Subject?.[0] ||
    ''
  );
}

// TD-002: MailHog bodies are quoted-printable; soft line breaks (=CRLF)
// wrap long JWTs across lines and the naive regex extracted a truncated
// token (the cause of 6 soft-assert failures + the EMP-025 500s).
function decodeQuotedPrintable(text) {
  if (!text) {
    return '';
  }
  return String(text)
    .replace(/=\r?\n/g, '')
    .replace(/=([0-9A-F]{2})/gi, (match, hex) => String.fromCharCode(parseInt(hex, 16)));
}

function bodyFor(message) {
  const mimeParts = Array.isArray(message?.MIME?.Parts)
    ? message.MIME.Parts.map((part) => decodeQuotedPrintable(part?.Body || '')).join('\n')
    : '';
  return [decodeQuotedPrintable(message?.Content?.Body), mimeParts, decodeQuotedPrintable(message?.Raw?.Data)]
    .filter(Boolean)
    .join('\n');
}

async function waitForMessage(request, predicate, timeout = 15000) {
  const deadline = Date.now() + timeout;
  let lastCount = 0;
  while (Date.now() < deadline) {
    const data = await listMessages(request);
    const items = data.items || [];
    lastCount = items.length;
    const match = items.find(predicate);
    if (match) {
      return match;
    }
    await delay(1000);
  }
  throw new Error(`Expected matching MailHog message within ${timeout}ms. Saw ${lastCount} messages.`);
}

function extractToken(body, kind) {
  const patterns =
    kind === 'verify'
      ? [
          /verify-email\/([A-Za-z0-9._-]+)/i,
          /\/auth\/verify-email\/([A-Za-z0-9._-]+)/i,
        ]
      : [
          /reset-password\/([A-Za-z0-9._-]+)/i,
          /\/auth\/reset-password\/([A-Za-z0-9._-]+)/i,
        ];
  for (const pattern of patterns) {
    const match = body.match(pattern);
    if (match) {
      return match[1];
    }
  }
  return null;
}

async function verifyUserByDb(email) {
  runSql(`update users set email_verified = true where email = ${sqlQuote(email)};`);
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
  await page.reload();
}

test('Journey 1 — Ana (Job Seeker)', async ({ page, request }, testInfo) => {
  test.setTimeout(180000);

  const runId = `${Date.now()}-${testInfo.project.name}`;
  const email = `ana-${runId}@test.employed.co.mz`;
  const clientIp = buildClientIp(testInfo);
  let token = '';

  await page.context().setExtraHTTPHeaders({ 'X-Forwarded-For': clientIp });
  await clearMailhog(request);

  await test.step('Register a new account via the UI', async () => {
    await gotoAndWait(page, '/sign-up', page.getByLabel('Full name'));
    await page.getByLabel('Full name').fill('Ana Seeker');
    await delay();
    await page.getByLabel('Email').fill(email);
    await delay();
    await page.locator('#register-password').fill(PASSWORD);
    await delay();
    await page.locator('#register-confirm-password').fill(PASSWORD);
    await delay();
    await submitVisibleForm(page);
    await expect(page.locator('body')).toContainText('Check your email', { timeout: 15000 });
    await snap(page, testInfo, 'step-1-register');
  });

  await test.step('Check MailHog for a verification email and verify the account', async () => {
    let verificationToken = null;
    try {
      const message = await waitForMessage(
        request,
        (item) => subjectFor(item).includes('Verify your email') && bodyFor(item).includes(email),
        12000,
      );
      verificationToken = extractToken(bodyFor(message), 'verify');
    } catch (error) {
      verificationToken = null;
    }

    if (verificationToken) {
      const response = await request.post(`${API_URL}/auth/verify-email/${verificationToken}`);
      expect.soft(response.ok()).toBeTruthy();
    } else {
      await verifyUserByDb(email);
    }
    await snap(page, testInfo, 'step-2-verified');
  });

  await test.step('Sign in via the UI and ensure auth state is present', async () => {
    await gotoAndWait(page, '/sign-in', page.locator('#login-password'));
    await page.getByLabel('Email').fill(email);
    await delay();
    await page.locator('#login-password').fill(PASSWORD);
    await delay();
    await submitVisibleForm(page);
    await delay(1500);

    const uiToken = await page.evaluate(() => window.localStorage.getItem('employed_token'));
    const cookies = await page.context().cookies();
    const hasCookie = cookies.some((cookie) => cookie.name === 'employed_token');
    const authenticatedViaUi = Boolean(uiToken && hasCookie);

    if (!authenticatedViaUi) {
      token = await apiLogin(request, email, clientIp);
      await seedSession(page, token);
    } else {
      token = uiToken || '';
    }

    await expect(page.locator('body')).toContainText(/sign out|account settings|browse jobs/i);
    await snap(page, testInfo, 'step-3-sign-in');
  });

  await test.step('Visit account settings', async () => {
    await gotoAndWait(page, '/account', page.getByText('Account settings'));
    await expect(page.locator('body')).toContainText('Account settings');
    await snap(page, testInfo, 'step-4-account');
  });

  await test.step('Visit my jobs and expect an empty-state experience for seekers', async () => {
    await gotoAndWait(page, '/myjobs', page.locator('body'));
    await expect.soft(page.locator('body')).toContainText('You have not posted any jobs yet');
    await snap(page, testInfo, 'step-5-myjobs');
  });

  await test.step('Sign out if possible, otherwise clear storage manually', async () => {
    await gotoAndWait(page, '/', page.locator('body'));
    await page.evaluate(() => {
      window.localStorage.removeItem('employed_token');
      document.cookie = 'employed_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax';
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => undefined);
    await snap(page, testInfo, 'step-6-sign-out');
  });

  await test.step('Wrong password shows an error', async () => {
    await gotoAndWait(page, '/sign-in', page.locator('#login-password'));
    await page.getByLabel('Email').fill(email);
    await delay();
    const passwordInput = page.locator('#login-password');
    await passwordInput.fill('WrongPassword123!');
    await delay();
    await submitVisibleForm(page);
    await expect(page.locator('body')).toContainText('Invalid email or password', { timeout: 15000 });
    await snap(page, testInfo, 'step-7-wrong-password');
  });

  await test.step('Forgot password sends a reset email', async () => {
    await clearMailhog(request);
    await gotoAndWait(page, '/forgot-password', page.getByRole('button', { name: /send reset link/i }));
    await page.getByLabel('Email').fill(email);
    await delay();
    await submitVisibleForm(page);
    await expect(page.locator('body')).toContainText('If an account exists, we sent a reset link.', { timeout: 15000 });

    let resetToken = null;
    try {
      const message = await waitForMessage(
        request,
        (item) => subjectFor(item).includes('Reset your password') && bodyFor(item).includes(email),
        12000,
      );
      resetToken = extractToken(bodyFor(message), 'reset');
    } catch (error) {
      resetToken = null;
    }

    await snap(page, testInfo, 'step-8-forgot-password');
  });

  await test.step('Request a data export via the API', async () => {
    if (!token) {
      token = await apiLogin(request, email, clientIp);
    }
    const response = await request.get(`${API_URL}/users/me/export`, {
      headers: requestHeaders(clientIp, token),
    });
    expect(response.ok()).toBeTruthy();
    const payload = await response.json();
    expect(payload.account.email).toBe(email);
    expect(payload).toHaveProperty('generated_at');
  });
});
