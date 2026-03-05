/**
 * End-to-end test: complete interview flow from landing to feedback review.
 *
 * Tests the full user journey:
 * 1. Land on home → select scenario → start interview
 * 2. Interview room loads → LiveKit connects → transcript appears
 * 3. End interview → redirects to feedback → scores displayed
 * 4. Navigate to history → see session listed → click → view feedback
 *
 * All backend API calls are intercepted via Playwright request mocking.
 */

import { test, expect, Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_SCENARIOS = [
  {
    id: "url-shortener",
    name: "Design a URL Shortener",
    description: "Design a URL shortening service like bit.ly.",
    archetype: "crud-metadata",
    difficulty: "easy",
  },
  {
    id: "payment-gateway",
    name: "Design a Payment Gateway",
    description: "Build a payment processing system.",
    archetype: "transactional",
    difficulty: "hard",
  },
];

const MOCK_SESSION = {
  session_id: "e2e-session-001",
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

const MOCK_TOKEN = {
  token: "mock-livekit-token",
  url: "wss://mock-livekit.example.com",
};

const MOCK_FEEDBACK = {
  session_id: "e2e-session-001",
  scenario: "Design a URL Shortener",
  dimensions: {
    requirements_gathering: {
      dimension: "requirements_gathering",
      score: 4,
      label: "Strong",
      rationale: "Good requirements gathering.",
      strengths: ["Clarified constraints", "Asked about scale"],
      gaps: [],
    },
    system_architecture: {
      dimension: "system_architecture",
      score: 3,
      label: "Solid",
      rationale: "Decent architecture.",
      strengths: ["Clean API design"],
      gaps: ["Could improve caching strategy"],
    },
    technical_depth: {
      dimension: "technical_depth",
      score: 4,
      label: "Strong",
      rationale: "Deep knowledge demonstrated.",
      strengths: ["Database expertise", "Hashing knowledge"],
      gaps: [],
    },
    scalability_reliability: {
      dimension: "scalability_reliability",
      score: 3,
      label: "Solid",
      rationale: "Reasonable approach.",
      strengths: ["Mentioned replication"],
      gaps: ["Missing failover details"],
    },
    communication: {
      dimension: "communication",
      score: 5,
      label: "Exceptional",
      rationale: "Excellent communication throughout.",
      strengths: ["Clear explanations", "Structured thinking"],
      gaps: [],
    },
  },
  overall_score: 3.8,
  hire_signal: "Lean Yes",
  narrative:
    "Strong candidate with excellent communication skills and solid system design knowledge.",
  locked_constraints: { database: "PostgreSQL", cache: "Redis" },
  total_turns: 18,
  elapsed_minutes: 42,
  generated_at: "2026-02-15T11:12:00Z",
};

const MOCK_SESSION_COMPLETED = {
  ...MOCK_SESSION,
  phase: "wrap",
  conversation_history: [
    {
      role: "assistant",
      content: "[PHASE:intro] Welcome! Let's design a URL shortener.",
      timestamp: "2026-02-15T10:30:00Z",
    },
    {
      role: "user",
      content: "Sure, let me start with the requirements.",
      timestamp: "2026-02-15T10:31:00Z",
    },
    {
      role: "assistant",
      content:
        "[PHASE:scope] Great. What scale are we targeting?",
      timestamp: "2026-02-15T10:32:00Z",
    },
    {
      role: "user",
      content: "I would target around 100 million URLs per day.",
      timestamp: "2026-02-15T10:33:00Z",
    },
  ],
  elapsed_seconds: 2520,
  total_turns: 18,
};

const MOCK_SESSIONS_LIST = [
  {
    session_id: "e2e-session-001",
    scenario: "Design a URL Shortener",
    overall_score: 3.8,
    hire_signal: "Lean Yes",
    session_start_time: "2026-02-15T10:30:00Z",
    elapsed_minutes: 42,
    phase: "wrap",
  },
  {
    session_id: "e2e-session-002",
    scenario: "Design a Payment Gateway",
    overall_score: 4.2,
    hire_signal: "Strong Yes",
    session_start_time: "2026-02-14T14:00:00Z",
    elapsed_minutes: 38,
    phase: "wrap",
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Set up all API route mocks for the complete interview flow. */
async function setupAllApiMocks(page: Page) {
  // Scenarios endpoint
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SCENARIOS),
    })
  );

  // Create session endpoint
  await page.route("**/api/sessions", (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    // POST /api/sessions — create new session
    if (method === "POST") {
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(MOCK_SESSION),
      });
    }

    // GET /api/sessions — list all sessions
    if (url.pathname === "/api/sessions" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_SESSIONS_LIST),
      });
    }

    return route.continue();
  });

  // Session-specific endpoints
  await page.route("**/api/sessions/e2e-session-001**", (route) => {
    const url = route.request().url();

    if (url.includes("/token")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_TOKEN),
      });
    }

    if (url.includes("/feedback")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_FEEDBACK),
      });
    }

    if (url.includes("/state")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: MOCK_SESSION.session_id,
          phase: "intro",
          locked_constraints: {},
          conversation_history: [],
          phase_turn_count: 0,
          total_turn_count: 0,
          elapsed_seconds: 0,
        }),
      });
    }

    // GET /api/sessions/e2e-session-001
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SESSION),
    });
  });

  // Session 002 feedback (for history → feedback navigation)
  await page.route("**/api/sessions/e2e-session-002**", (route) => {
    const url = route.request().url();

    if (url.includes("/feedback")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...MOCK_FEEDBACK,
          session_id: "e2e-session-002",
          scenario: "Design a Payment Gateway",
          overall_score: 4.2,
          hire_signal: "Strong Yes",
          narrative: "Outstanding performance across all dimensions.",
        }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...MOCK_SESSION_COMPLETED,
        session_id: "e2e-session-002",
        scenario: "Design a Payment Gateway",
      }),
    });
  });
}

// ---------------------------------------------------------------------------
// Tests — Complete Interview Flow
// ---------------------------------------------------------------------------

test.describe("Complete interview flow", () => {
  test.beforeEach(async ({ page }) => {
    await setupAllApiMocks(page);
  });

  test("(1) Land on home → select scenario → start interview", async ({
    page,
  }) => {
    // Navigate to home
    await page.goto("/");

    // Verify landing page renders
    await expect(page.locator("h1")).toContainText("InterviewOS");
    await expect(page.locator("p").first()).toContainText(
      "system design interview"
    );

    // Wait for scenarios to load
    await expect(
      page.getByRole("button", { name: /start interview/i }).first()
    ).toBeVisible({ timeout: 10000 });

    // Verify scenario cards are displayed
    await expect(page.getByText("Design a URL Shortener")).toBeVisible();
    await expect(page.getByText("Design a Payment Gateway")).toBeVisible();

    // Click Start Interview on first scenario
    await page
      .getByRole("button", { name: /start interview/i })
      .first()
      .click();

    // Should navigate to interview room
    await expect(page).toHaveURL(/\/interview\/e2e-session-001/, {
      timeout: 10000,
    });
  });

  test("(2) Interview room loads → session details displayed → transcript visible", async ({
    page,
  }) => {
    // Navigate directly to interview room
    await page.goto("/interview/e2e-session-001");

    // Wait for interview room to load
    await expect(page.getByTestId("interview-room")).toBeVisible({
      timeout: 10000,
    });

    // Verify sidebar controls
    await expect(page.getByTestId("scenario-title")).toContainText(
      "Design a URL Shortener"
    );
    await expect(page.getByTestId("phase-indicator")).toBeVisible();
    await expect(page.getByTestId("phase-badge")).toContainText("Intro");
    await expect(page.getByTestId("timer")).toBeVisible();

    // Verify voice controls
    await expect(page.getByTestId("voice-controls")).toBeVisible();
    await expect(page.getByTestId("mic-toggle")).toBeVisible();
    await expect(page.getByTestId("end-interview")).toBeVisible();

    // Verify transcript panel
    await expect(page.getByTestId("transcript-panel")).toBeVisible();
  });

  test("(3) End interview → redirects to feedback → scores displayed", async ({
    page,
  }) => {
    // Navigate to interview room
    await page.goto("/interview/e2e-session-001");

    // Wait for room to fully load
    await expect(page.getByTestId("interview-room")).toBeVisible({
      timeout: 10000,
    });

    // Update the session route to return completed session for the feedback page
    await page.route("**/api/sessions/e2e-session-001", (route) => {
      const url = route.request().url();
      if (
        url.endsWith("/e2e-session-001") ||
        url.endsWith("/e2e-session-001/")
      ) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SESSION_COMPLETED),
        });
      }
      return route.continue();
    });

    // Click End Interview button
    await page.getByTestId("end-interview").click();

    // Should redirect to feedback page
    await expect(page).toHaveURL(/\/feedback\/e2e-session-001/, {
      timeout: 10000,
    });

    // Wait for feedback to load
    await expect(page.getByTestId("feedback-title")).toContainText(
      "Interview Feedback",
      { timeout: 10000 }
    );

    // Verify scenario name
    await expect(page.getByTestId("feedback-scenario")).toContainText(
      "Design a URL Shortener"
    );

    // Verify narrative summary
    await expect(page.getByTestId("feedback-narrative")).toContainText(
      "Strong candidate"
    );

    // Verify scoring rubric
    await expect(page.getByTestId("scoring-rubric")).toBeVisible();
    await expect(page.getByTestId("overall-score")).toContainText("3.8");
    await expect(page.getByTestId("hire-signal")).toContainText("Lean Yes");

    // Verify dimension cards are displayed (5 dimensions)
    const dimensionCards = page.getByTestId("dimension-card");
    expect(await dimensionCards.count()).toBe(5);

    // Verify transcript replay is shown (session has conversation history)
    await expect(page.getByTestId("transcript-replay")).toBeVisible();
    const replayMessages = page.getByTestId("replay-message");
    expect(await replayMessages.count()).toBe(4);
  });

  test("(4) Navigate to history → see sessions listed → click → view feedback", async ({
    page,
  }) => {
    // Navigate to history page
    await page.goto("/history");

    // Wait for session list to load
    await expect(page.getByTestId("session-list")).toBeVisible({
      timeout: 10000,
    });

    // Verify both sessions are displayed
    const sessionCards = page.getByTestId("session-card");
    expect(await sessionCards.count()).toBe(2);

    // Verify session details
    await expect(page.getByText("Design a URL Shortener")).toBeVisible();
    await expect(page.getByText("Design a Payment Gateway")).toBeVisible();

    // Click the first session card
    await sessionCards.first().click();

    // Should navigate to feedback page
    await expect(page).toHaveURL(/\/feedback\/e2e-session-001/, {
      timeout: 10000,
    });

    // Verify feedback page loads with scores
    await expect(page.getByTestId("feedback-title")).toContainText(
      "Interview Feedback",
      { timeout: 10000 }
    );
    await expect(page.getByTestId("overall-score")).toContainText("3.8");
    await expect(page.getByTestId("hire-signal")).toContainText("Lean Yes");
  });

  test("full journey: home → interview → feedback → history → feedback", async ({
    page,
  }) => {
    // Step 1: Start from home page
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("InterviewOS");

    // Wait for scenarios to load
    await expect(
      page.getByRole("button", { name: /start interview/i }).first()
    ).toBeVisible({ timeout: 10000 });

    // Select a scenario and start
    await page
      .getByRole("button", { name: /start interview/i })
      .first()
      .click();

    // Step 2: Interview room
    await expect(page).toHaveURL(/\/interview\/e2e-session-001/, {
      timeout: 10000,
    });
    await expect(page.getByTestId("interview-room")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByTestId("scenario-title")).toContainText(
      "Design a URL Shortener"
    );
    await expect(page.getByTestId("transcript-panel")).toBeVisible();

    // Update session route for completed state
    await page.route("**/api/sessions/e2e-session-001", (route) => {
      const url = route.request().url();
      if (
        url.endsWith("/e2e-session-001") ||
        url.endsWith("/e2e-session-001/")
      ) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SESSION_COMPLETED),
        });
      }
      return route.continue();
    });

    // Step 3: End interview → feedback
    await page.getByTestId("end-interview").click();
    await expect(page).toHaveURL(/\/feedback\/e2e-session-001/, {
      timeout: 10000,
    });
    await expect(page.getByTestId("feedback-title")).toContainText(
      "Interview Feedback",
      { timeout: 10000 }
    );
    await expect(page.getByTestId("overall-score")).toContainText("3.8");
    await expect(page.getByTestId("scoring-rubric")).toBeVisible();

    // Step 4: Navigate to history
    await page.getByTestId("back-to-history").click();
    await expect(page).toHaveURL(/\/history/, { timeout: 10000 });

    // Verify sessions listed
    await expect(page.getByTestId("session-list")).toBeVisible({
      timeout: 10000,
    });
    const cards = page.getByTestId("session-card");
    expect(await cards.count()).toBe(2);

    // Click second session to view its feedback
    await cards.nth(1).click();
    await expect(page).toHaveURL(/\/feedback\/e2e-session-002/, {
      timeout: 10000,
    });
    await expect(page.getByTestId("feedback-title")).toContainText(
      "Interview Feedback",
      { timeout: 10000 }
    );
    await expect(page.getByTestId("overall-score")).toContainText("4.2");
    await expect(page.getByTestId("hire-signal")).toContainText("Strong Yes");
  });
});

// ---------------------------------------------------------------------------
// Tests — Error handling during flow
// ---------------------------------------------------------------------------

test.describe("Complete flow error handling", () => {
  test("shows error when session creation fails during start", async ({
    page,
  }) => {
    // Mock scenarios to load successfully
    await page.route("**/api/scenarios", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_SCENARIOS),
      })
    );

    // Mock session creation to fail
    await page.route("**/api/sessions", (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "Internal server error" }),
        });
      }
      return route.continue();
    });

    await page.goto("/");

    // Wait for scenarios to load
    await expect(
      page.getByRole("button", { name: /start interview/i }).first()
    ).toBeVisible({ timeout: 10000 });

    // Try to start interview
    await page
      .getByRole("button", { name: /start interview/i })
      .first()
      .click();

    // Should show error alert
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("alert")).toContainText("Failed to create session");
  });

  test("shows error when interview session fails to load", async ({
    page,
  }) => {
    await page.route("**/api/sessions/nonexistent**", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "Session not found" }),
      })
    );

    await page.goto("/interview/nonexistent");

    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("alert")).toContainText("Failed to load");
  });

  test("shows error when feedback fails to load", async ({ page }) => {
    await page.route("**/api/sessions/broken-session**", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "Server error" }),
      })
    );

    await page.goto("/feedback/broken-session");

    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("alert")).toContainText(
      /Failed to load|not available/
    );
  });

  test("shows empty state when history has no sessions", async ({ page }) => {
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
