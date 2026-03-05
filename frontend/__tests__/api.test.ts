/**
 * Tests for the API client — mock fetch, zero network calls.
 */

import { createApiClient, ApiClientError } from "@/lib/api";
import type { InterviewSession, SessionState, ScoringResult } from "@/lib/types";
import { InterviewPhase } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TEST_BASE_URL = "http://localhost:8000";

function mockFetchSuccess(data: unknown): jest.Mock {
  const mock = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => data,
  } as Response);
  global.fetch = mock;
  return mock;
}

function mockFetchError(status: number, body?: unknown): jest.Mock {
  const mock = jest.fn().mockResolvedValue({
    ok: false,
    status,
    json: async () => body,
  } as Response);
  global.fetch = mock;
  return mock;
}

function makeSession(overrides: Partial<InterviewSession> = {}): InterviewSession {
  return {
    session_id: "test-123",
    scenario: "Design a URL shortener",
    phase: InterviewPhase.INTRO,
    locked_constraints: {},
    conversation_history: [],
    transcript: [],
    metadata: {},
    scorecard: null,
    session_start_time: "2026-01-01T00:00:00Z",
    elapsed_seconds: 0,
    total_turns: 0,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
});

// ---------------------------------------------------------------------------
// Tests — createSession
// ---------------------------------------------------------------------------

describe("createSession", () => {
  it("sends POST with scenario and returns session", async () => {
    const session = makeSession();
    const fetchMock = mockFetchSuccess(session);

    const api = createApiClient({ baseUrl: TEST_BASE_URL });
    const result = await api.createSession("Design a URL shortener");

    expect(fetchMock).toHaveBeenCalledWith(
      `${TEST_BASE_URL}/api/sessions`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ scenario: "Design a URL shortener" }),
      })
    );
    expect(result.session_id).toBe("test-123");
    expect(result.scenario).toBe("Design a URL shortener");
  });
});

// ---------------------------------------------------------------------------
// Tests — getSession
// ---------------------------------------------------------------------------

describe("getSession", () => {
  it("sends GET and returns session data", async () => {
    const session = makeSession({ phase: InterviewPhase.ARCHITECTURE });
    const fetchMock = mockFetchSuccess(session);

    const api = createApiClient({ baseUrl: TEST_BASE_URL });
    const result = await api.getSession("test-123");

    expect(fetchMock).toHaveBeenCalledWith(
      `${TEST_BASE_URL}/api/sessions/test-123`,
      expect.objectContaining({ method: "GET" })
    );
    expect(result.phase).toBe(InterviewPhase.ARCHITECTURE);
  });
});

// ---------------------------------------------------------------------------
// Tests — getSessionState
// ---------------------------------------------------------------------------

describe("getSessionState", () => {
  it("returns current session state", async () => {
    const state: SessionState = {
      session_id: "test-123",
      phase: InterviewPhase.DEEP_DIVE,
      locked_constraints: { database: "PostgreSQL" },
      conversation_history: [],
      phase_turn_count: 3,
      total_turn_count: 10,
      elapsed_seconds: 600,
    };
    mockFetchSuccess(state);

    const api = createApiClient({ baseUrl: TEST_BASE_URL });
    const result = await api.getSessionState("test-123");

    expect(result.phase).toBe(InterviewPhase.DEEP_DIVE);
    expect(result.locked_constraints).toEqual({ database: "PostgreSQL" });
    expect(result.total_turn_count).toBe(10);
  });
});

// ---------------------------------------------------------------------------
// Tests — getScore
// ---------------------------------------------------------------------------

describe("getScore", () => {
  it("returns scoring result for completed session", async () => {
    const score: ScoringResult = {
      session_id: "test-123",
      scenario: "Design a URL shortener",
      dimensions: {
        system_architecture: {
          dimension: "system_architecture",
          score: 4,
          label: "Strong",
          rationale: "Good architecture design.",
          strengths: ["Clean separation of concerns"],
          gaps: ["Could improve caching strategy"],
        },
      },
      overall_score: 3.8,
      hire_signal: "Lean Yes",
      narrative: "Solid performance overall.",
      locked_constraints: {},
      total_turns: 20,
      elapsed_minutes: 42,
      generated_at: "2026-01-01T00:45:00Z",
    };
    mockFetchSuccess(score);

    const api = createApiClient({ baseUrl: TEST_BASE_URL });
    const result = await api.getScore("test-123");

    expect(result.overall_score).toBe(3.8);
    expect(result.hire_signal).toBe("Lean Yes");
    expect(result.dimensions.system_architecture.score).toBe(4);
  });
});

// ---------------------------------------------------------------------------
// Tests — healthCheck
// ---------------------------------------------------------------------------

describe("healthCheck", () => {
  it("returns status from health endpoint", async () => {
    const fetchMock = mockFetchSuccess({ status: "ok" });

    const api = createApiClient({ baseUrl: TEST_BASE_URL });
    const result = await api.healthCheck();

    expect(result.status).toBe("ok");
    expect(fetchMock).toHaveBeenCalledWith(
      `${TEST_BASE_URL}/api/health`,
      expect.objectContaining({ method: "GET" })
    );
  });
});

// ---------------------------------------------------------------------------
// Tests — Error handling
// ---------------------------------------------------------------------------

describe("error handling", () => {
  it("throws ApiClientError with status and body on 4xx", async () => {
    mockFetchError(404, { error: "Session not found" });

    const api = createApiClient({ baseUrl: TEST_BASE_URL });

    await expect(api.getSession("nonexistent")).rejects.toThrow(ApiClientError);

    try {
      await api.getSession("nonexistent");
    } catch (err) {
      const apiErr = err as ApiClientError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.body?.error).toBe("Session not found");
    }
  });

  it("throws ApiClientError with generic message on 500 without JSON body", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not JSON");
      },
    } as unknown as Response);

    const api = createApiClient({ baseUrl: TEST_BASE_URL });

    await expect(api.healthCheck()).rejects.toThrow(
      "Request failed with status 500"
    );
  });

  it("uses custom base URL without trailing slash issues", async () => {
    const fetchMock = mockFetchSuccess({ status: "ok" });

    const api = createApiClient({ baseUrl: "http://example.com/" });
    await api.healthCheck();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://example.com/api/health",
      expect.anything()
    );
  });

  it("merges custom headers", async () => {
    const fetchMock = mockFetchSuccess({ status: "ok" });

    const api = createApiClient({
      baseUrl: TEST_BASE_URL,
      headers: { Authorization: "Bearer test-token" },
    });
    await api.healthCheck();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
          "Content-Type": "application/json",
        }),
      })
    );
  });
});
