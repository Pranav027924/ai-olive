/**
 * Playwright e2e for the five main UI flows (PRD §12.5), updated for the
 * ChatGPT-style UI:
 *   1. Create a chat (composer-first: the session is created on send)
 *   2. Send a message, see the streamed reply
 *   3. Cancel a stream
 *   4. Upload a PDF
 *   5. View the dashboard
 *
 * Preconditions (the suite skips early if these aren't met):
 *   - chat-service on 8000, dashboard-service on 8004 (see vite proxy)
 *   - postgres, redis, minio, clickhouse via `make up && make up-analytics`
 *   - migrations applied (`make migrate-all && make migrate-clickhouse`)
 *   - ANTHROPIC_API_KEY set so streamed replies actually come back
 */
import { expect, test } from "@playwright/test";

test.skip(
  !process.env.ANTHROPIC_API_KEY,
  "ANTHROPIC_API_KEY not set; skipping live UI e2e",
);

test("composing a message creates a chat and lands on the chat view", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("message-input").fill("Say hello in one short sentence.");
  await page.getByLabel("send").click();
  await expect(page).toHaveURL(/\/sessions\/[0-9a-f-]+/);
});

test("send a message and see a streamed reply", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("message-input").fill("Reply with exactly: hello-playwright");
  await page.getByLabel("send").click();
  await expect(page.getByTestId("stream-text")).toContainText(/hello-playwright/i, {
    timeout: 30_000,
  });
});

test("cancel button stops a long stream", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("message-input").fill("List every prime number under 1000, one per line.");
  await page.getByLabel("send").click();
  const cancel = page.getByLabel("cancel");
  await expect(cancel).toBeVisible({ timeout: 15_000 });
  await cancel.click();
  await expect(page.getByLabel("send")).toBeVisible({ timeout: 15_000 });
});

test("upload a PDF attachment", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("message-input").fill("Here is a document.");
  await page.getByLabel("send").click();
  await expect(page).toHaveURL(/\/sessions\/[0-9a-f-]+/);

  await page.getByLabel("attach").click();
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "hello.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(
      "%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<>>\nstartxref\n9\n%%EOF\n",
    ),
  });
  await expect(page.getByText(/hello\.pdf/)).toBeVisible({ timeout: 10_000 });
});

test("dashboard route renders the four headline stats", async ({ page }) => {
  await page.goto("/dashboard");
  for (const label of [/requests/i, /error rate/i, /p50 latency/i, /p99 latency/i]) {
    await expect(page.getByText(label)).toBeVisible();
  }
});
