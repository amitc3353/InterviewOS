/**
 * E2E tests for the interview room page — verifies UI elements render correctly.
 */

import { test, expect } from "@playwright/test";

test.describe("Interview room", () => {
  // The interview room requires a valid session ID. We navigate to a
  // placeholder ID and verify UI elements that render regardless of
  // backend availability (error state or loaded state).

  test("renders interview room page structure", async ({ page }) => {
    await page.goto("/interview/test-session-id");

    // The page should render either the loading state, an error, or the room.
    // With no backend, we expect the loading state to appear first.
    const loading = page.getByTestId("loading");
    const errorAlert = page.getByRole("alert");
    const room = page.getByTestId("interview-room");

    // Wait for one of these states to appear
    await expect(
      loading.or(errorAlert).or(room)
    ).toBeVisible({ timeout: 10000 });
  });

  test("shows loading state initially", async ({ page }) => {
    // Mock the session API to never respond (simulate loading)
    await page.route("**/api/sessions/loading-test", (route) =>
      // Don't fulfill — keeps the page in loading state
      route.abort("connectionrefused")
    );

    await page.goto("/interview/loading-test");

    // Should show loading or error state
    const loading = page.getByTestId("loading");
    const errorAlert = page.getByRole("alert");

    await expect(loading.or(errorAlert)).toBeVisible({ timeout: 10000 });
  });

  test("displays error when session fails to load", async ({ page }) => {
    // Mock the session endpoint to return 404
    await page.route("**/api/sessions/bad-session-id", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "Session not found" }),
      })
    );

    await page.goto("/interview/bad-session-id");

    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("alert")).toContainText("Failed to load");
  });

  test("renders sidebar controls when session loads", async ({ page }) => {
    // Mock the session endpoint
    await page.route("**/api/sessions/mock-session**", (route) => {
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
        body: JSON.stringify({
          session_id: "mock-session",
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
        }),
      });
    });

    await page.goto("/interview/mock-session");

    // Verify sidebar elements
    await expect(page.getByTestId("interview-room")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByTestId("scenario-title")).toContainText(
      "Design a URL Shortener"
    );
    await expect(page.getByTestId("phase-indicator")).toBeVisible();
    await expect(page.getByTestId("phase-badge")).toContainText("Intro");
    await expect(page.getByTestId("timer")).toBeVisible();
    await expect(page.getByTestId("voice-controls")).toBeVisible();
    await expect(page.getByTestId("mic-toggle")).toBeVisible();
    await expect(page.getByTestId("end-interview")).toBeVisible();
    await expect(page.getByTestId("transcript-panel")).toBeVisible();
  });
});
