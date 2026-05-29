import { test, expect } from '@playwright/test';

test('dashboard loads backend-backed app without console errors', async ({ page }) => {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));
  await page.goto('http://localhost:8080/dashboard', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Power Desk')).toBeVisible();
  await expect(page.getByText('Syndicated Spread Notes')).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('Create an Operator account to save positions and PnL')).toBeVisible();
  await page.getByRole('button', { name: 'Portfolio' }).click();
  await expect(page.getByText('Account required')).toBeVisible();
  await page.getByRole('button', { name: 'Market Signal' }).click();
  await expect(page.getByText('Backend spread signal')).toBeVisible();
  await page.getByRole('button', { name: 'Account', exact: true }).click();
  await expect(page.getByText('Operator Account')).toBeVisible();
  expect(errors.filter(text => !text.includes('favicon'))).toEqual([]);
});
