import { test, expect } from "@playwright/test";

test.describe("Feedback flow", () => {
  test("feedback page shows loading state then content", async ({ page }) => {
    // Mock the API responses
    await page.route("**/api/sessions/test-session/feedback", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "test-session",
          scenario: "Design a URL Shortener",
          dimensions: {
            requirements_gathering: {
              dimension: "requirements_gathering",
              score: 4,
              label: "Strong",
              rationale: "Good requirements.",
              strengths: ["Clarified constraints"],
              gaps: [],
            },
            system_architecture: {
              dimension: "system_architecture",
              score: 3,
              label: "Solid",
              rationale: "Decent architecture.",
              strengths: ["Clean API design"],
              gaps: ["Could improve caching"],
            },
            technical_depth: {
              dimension: "technical_depth",
              score: 4,
              label: "Strong",
              rationale: "Deep knowledge.",
              strengths: ["Database expertise"],
              gaps: [],
            },
            scalability_reliability: {
              dimension: "scalability_reliability",
              score: 3,
              label: "Solid",
              rationale: "Reasonable approach.",
              strengths: ["Mentioned replication"],
              gaps: ["Missing failover"],
            },
            communication: {
              dimension: "communication",
              score: 5,
              label: "Exceptional",
              rationale: "Excellent communication.",
              strengths: ["Clear explanations"],
              gaps: [],
            },
          },
          overall_score: 3.7,
          hire_signal: "Lean Yes",
          narrative: "Solid performance with good communication skills.",
          locked_constraints: {},
          total_turns: 18,
          elapsed_minutes: 40,
          generated_at: "2026-02-15T11:10:00Z",
        }),
      })
    );

    await page.route("**/api/sessions/test-session", (route) => {
      // Only match the exact path, not sub-paths
      const url = new URL(route.request().url());
      if (url.pathname === "/api/sessions/test-session") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: "test-session",
            scenario: "Design a URL Shortener",
            phase: "wrap",
            locked_constraints: {},
            conversation_history: [
              {
                role: "assistant",
                content:
                  "[PHASE:intro] Welcome! Let's design a URL shortener.",
                timestamp: "2026-02-15T10:30:00Z",
              },
              {
                role: "user",
                content: "Sure, let me start with the requirements.",
                timestamp: "2026-02-15T10:31:00Z",
              },
            ],
            transcript: [],
            metadata: {},
            scorecard: null,
            session_start_time: "2026-02-15T10:30:00Z",
            elapsed_seconds: 2400,
            total_turns: 18,
          }),
        });
      }
      return route.continue();
    });

    await page.goto("/feedback/test-session");

    // Should show feedback content
    await expect(page.getByTestId("feedback-title")).toContainText(
      "Interview Feedback"
    );
    await expect(page.getByTestId("feedback-scenario")).toContainText(
      "Design a URL Shortener"
    );
    await expect(page.getByTestId("feedback-narrative")).toContainText(
      "Solid performance"
    );

    // Should show scoring rubric
    await expect(page.getByTestId("scoring-rubric")).toBeVisible();
    await expect(page.getByTestId("overall-score")).toContainText("3.7");
    await expect(page.getByTestId("hire-signal")).toContainText("Lean Yes");

    // Should show dimension cards
    const dimensionCards = page.getByTestId("dimension-card");
    expect(await dimensionCards.count()).toBe(5);

    // Should show transcript replay
    await expect(page.getByTestId("transcript-replay")).toBeVisible();
    const messages = page.getByTestId("replay-message");
    expect(await messages.count()).toBe(2);
  });

  test("feedback page navigates to history via back button", async ({
    page,
  }) => {
    // Mock API to return feedback
    await page.route("**/api/sessions/test-session/feedback", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "test-session",
          scenario: "Design a URL Shortener",
          dimensions: {},
          overall_score: 3.5,
          hire_signal: "Lean Yes",
          narrative: "Good work.",
          locked_constraints: {},
          total_turns: 10,
          elapsed_minutes: 30,
          generated_at: "2026-02-15T11:00:00Z",
        }),
      })
    );

    await page.route("**/api/sessions/test-session", (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/sessions/test-session") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: "test-session",
            scenario: "Design a URL Shortener",
            phase: "wrap",
            locked_constraints: {},
            conversation_history: [],
            transcript: [],
            metadata: {},
            scorecard: null,
            session_start_time: "2026-02-15T10:30:00Z",
            elapsed_seconds: 1800,
            total_turns: 10,
          }),
        });
      }
      return route.continue();
    });

    await page.goto("/feedback/test-session");

    await expect(page.getByTestId("back-to-history")).toBeVisible();
    await page.getByTestId("back-to-history").click();

    await expect(page).toHaveURL(/\/history/);
  });

  test("history page lists sessions and navigates to feedback", async ({
    page,
  }) => {
    // Mock the sessions list API
    await page.route("**/api/sessions", (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/sessions") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              session_id: "session-1",
              scenario: "Design a URL Shortener",
              overall_score: 3.8,
              hire_signal: "Lean Yes",
              session_start_time: "2026-02-15T10:30:00Z",
              elapsed_minutes: 42,
              phase: "wrap",
            },
            {
              session_id: "session-2",
              scenario: "Design a Payment Gateway",
              overall_score: 4.2,
              hire_signal: "Strong Yes",
              session_start_time: "2026-02-14T14:00:00Z",
              elapsed_minutes: 38,
              phase: "wrap",
            },
          ]),
        });
      }
      return route.continue();
    });

    await page.goto("/history");

    // Should show session list
    await expect(page.getByTestId("session-list")).toBeVisible({
      timeout: 10000,
    });
    const cards = page.getByTestId("session-card");
    expect(await cards.count()).toBe(2);

    // Should show scenario names
    await expect(page.getByText("Design a URL Shortener")).toBeVisible();
    await expect(page.getByText("Design a Payment Gateway")).toBeVisible();

    // Click first card to navigate to feedback
    await cards.first().click();
    await expect(page).toHaveURL(/\/feedback\/session-1/);
  });

  test("history page shows empty state when no sessions", async ({ page }) => {
    await page.route("**/api/sessions", (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/sessions") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      }
      return route.continue();
    });

    await page.goto("/history");

    await expect(page.getByTestId("empty-state")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("No sessions yet.")).toBeVisible();
  });
});
