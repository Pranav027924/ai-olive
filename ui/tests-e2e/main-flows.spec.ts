/**
 * Playwright e2e for the five main UI flows (PRD §12.5):
 *   1. Create session
 *   2. Send a message, see streamed reply
 *   3. Cancel a stream
 *   4. Upload a PDF
 *   5. View the dashboard
 *
 * Preconditions (the suite skips early if these aren't met):
 *   - chat-service on 8001, dashboard-service on 8004 (see vite proxy)
 *   - postgres, redis, minio, clickhouse via `make up && make up-analytics`
 *   - migrations applied (`make migrate-all && make migrate-clickhouse`)
 *   - ANTHROPIC_API_KEY set so streamed replies actually come back
 */
import { expect, test } from "@playwright/test";

const SHOULD_RUN = !!process.env.ANTHROPIC_API_KEY;
test.skip(!SHOULD_RUN, "ANTHROPIC_API_KEY not set; skipping live UI e2e");

test("create a session and land on the chat view", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Untitled").fill("playwright-create");
  await page.getByRole("button", { name: /create/i }).click();
  await expect(page).toHaveURL(/\/sessions\/[0-9a-f-]+/);
});

test("send a message and see a streamed reply", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Untitled").fill("playwright-stream");
  await page.getByRole("button", { name: /create/i }).click();
  await page.getByLabel("message-input").fill("Reply with exactly: hello-playwright");
  await page.getByRole("button", { name: /^send$/i }).click();

  const text = page.getByTestId("stream-text");
  await expect(text).toContainText(/hello-playwright/i, { timeout: 30_000 });
});

test("cancel button stops a long stream", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Untitled").fill("playwright-cancel");
  await page.getByRole("button", { name: /create/i }).click();
  await page.getByLabel("message-input").fill("List every prime number under 1000 line by line.");
  await page.getByRole("button", { name: /^send$/i }).click();
  // Wait until streaming starts (cancel button becomes enabled).
  const cancelBtn = page.getByRole("button", { name: /cancel/i });
  await expect(cancelBtn).toBeEnabled({ timeout: 10_000 });
  await cancelBtn.click();
  await expect(cancelBtn).toBeDisabled({ timeout: 10_000 });
});

test("upload a PDF attachment", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Untitled").fill("playwright-upload");
  await page.getByRole("button", { name: /create/i }).click();
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles({
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
