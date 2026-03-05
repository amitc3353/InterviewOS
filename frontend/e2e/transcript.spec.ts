/**
 * E2E tests for the real-time transcript panel — verifies transcript UI renders
 * and displays messages within the interview room.
 */

import { test, expect } from "@playwright/test";

/** Mock session data returned by the API. */
const MOCK_SESSION = {
  session_id: "transcript-test-session",
  scenario: "Design a URL Shortener",
  phase: "intro",
  locked_constraints: {},
  conversation_history: [],
  transcript: [],
  metadata: {},
  scorecard: null,
  session_start_time: new Date().toISOString(),
  elapsed_seconds: 0,
  total_turns: 0,
};

test.describe("Transcript panel", () => {
  test.beforeEach(async ({ page }) => {
    // Mock session API
    await page.route("**/api/sessions/transcript-test-session**", (route) => {
      const url = route.request().url();

      if (url.includes("/token")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            token: "mock-token",
            url: "wss://mock-livekit.example.com",
          }),
        });
      }

      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_SESSION),
      });
    });
  });

  test("renders transcript panel in interview room", async ({ page }) => {
    await page.goto("/interview/transcript-test-session");

    await expect(page.getByTestId("interview-room")).toBeVisible({
      timeout: 10000,
    });

    await expect(page.getByTestId("transcript-panel")).toBeVisible();
  });

  test("shows empty transcript message initially", async ({ page }) => {
    await page.goto("/interview/transcript-test-session");

    await expect(page.getByTestId("interview-room")).toBeVisible({
      timeout: 10000,
    });

    await expect(page.getByTestId("transcript-empty")).toBeVisible();
    await expect(page.getByTestId("transcript-empty")).toContainText(
      "Transcript will appear here"
    );
  });

  test("shows connection status dot", async ({ page }) => {
    await page.goto("/interview/transcript-test-session");

    await expect(page.getByTestId("interview-room")).toBeVisible({
      timeout: 10000,
    });

    await expect(page.getByTestId("connection-dot")).toBeVisible();
  });

  test("shows Transcript heading", async ({ page }) => {
    await page.goto("/interview/transcript-test-session");

    await expect(page.getByTestId("interview-room")).toBeVisible({
      timeout: 10000,
    });

    await expect(page.getByText("Transcript")).toBeVisible();
  });
});
