import { test, expect } from '@playwright/test';

test.setTimeout(90_000);

test('dashboard loads backend-backed app without console errors', async ({ page }) => {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));
  await page.goto('http://localhost:8080/dashboard', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Power Desk')).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('Loading backend state')).toBeHidden({ timeout: 60000 });
  await expect(page.getByText('Syndicated Spread Notes')).toBeVisible();
  await expect(page.getByText('Create an Operator account to save positions and PnL')).toBeVisible();
  await page.getByRole('button', { name: 'Portfolio' }).click();
  await expect(page.getByText('Account required')).toBeVisible();
  await page.getByRole('button', { name: 'Market Signal' }).click();
  await expect(page.getByText('Backend spread signal')).toBeVisible();
  await expect(page.getByText('Index coverage', { exact: true })).toBeVisible();
  await expect(page.getByText('Profitability ledger')).toBeVisible();
  await expect(page.getByText('How a user trades it')).toBeVisible();
  await page.getByRole('button', { name: 'Account', exact: true }).click();
  await expect(page.getByText('Operator Account')).toBeVisible();
  expect(errors.filter(text => !text.includes('favicon'))).toEqual([]);
});

test('telegram mini app renders backend mapped data without helper errors', async ({ page }) => {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));
  await page.goto('http://localhost:8080/tg', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Botozen Power')).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('My Portfolio')).toBeVisible();
  await expect(page.getByText('Mini App walkthrough')).toBeVisible();
  await page.getByText('What Changed').first().click();
  await expect(page.getByText('Screenshot map')).toBeVisible();
  await expect(page.getByText('Channel screenshot deck')).toBeVisible();
  await expect(page.getByText('npm run telegram:miniapp-release-post')).toBeVisible();
  await expect(page.getByText('Mock contract', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '← Back' }).click();
  await page.getByText('Mock Contract').first().click();
  await expect(page.getByText('Index catalog')).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('Profitability ledger')).toBeVisible();
  await expect(page.getByText('Account ticket')).toBeVisible();
  expect(errors.filter(text => !text.includes('favicon'))).toEqual([]);
});
