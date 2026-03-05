import { test, expect } from "@playwright/test";

test.describe("Smoke tests", () => {
  test("homepage renders with title", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("InterviewOS");
  });

  test("homepage has description text", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("p")).toContainText("system design interview");
  });

  test("page has dark background", async ({ page }) => {
    await page.goto("/");
    const html = page.locator("html");
    await expect(html).toHaveClass(/dark/);
  });
});
