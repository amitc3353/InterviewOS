/**
 * Tests for history page, SessionCard, and TranscriptReplay — mock API, zero network calls.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import type { SessionSummary } from "@/lib/types";
import { InterviewPhase } from "@/lib/types";
import SessionCard, { formatSessionDate } from "@/components/SessionCard";
import { formatRelativeTime, extractPhase } from "@/components/TranscriptReplay";

// ---------------------------------------------------------------------------
// Mock next/navigation
// ---------------------------------------------------------------------------

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ sessionId: "test-session-1" }),
}));

// ---------------------------------------------------------------------------
// Mock API
// ---------------------------------------------------------------------------

const mockGetSessions = jest.fn();
jest.mock("@/lib/api", () => ({
  api: {
    getSessions: (...args: unknown[]) => mockGetSessions(...args),
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSession(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    session_id: "session-1",
    scenario: "Design a URL Shortener",
    overall_score: 3.8,
    hire_signal: "Lean Yes",
    session_start_time: "2026-02-15T10:30:00Z",
    elapsed_minutes: 42,
    phase: InterviewPhase.WRAP,
    ...overrides,
  };
}

afterEach(() => {
  jest.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests — SessionCard
// ---------------------------------------------------------------------------

describe("SessionCard", () => {
  it("renders scenario name", () => {
    render(
      <SessionCard session={makeSession()} onClick={jest.fn()} />
    );

    expect(screen.getByTestId("session-scenario")).toHaveTextContent(
      "Design a URL Shortener"
    );
  });

  it("renders formatted date", () => {
    render(
      <SessionCard session={makeSession()} onClick={jest.fn()} />
    );

    const dateEl = screen.getByTestId("session-date");
    expect(dateEl.textContent).toBeTruthy();
    // Should contain "Feb" and "2026"
    expect(dateEl.textContent).toContain("2026");
  });

  it("renders overall score", () => {
    render(
      <SessionCard session={makeSession()} onClick={jest.fn()} />
    );

    expect(screen.getByTestId("session-score")).toHaveTextContent("3.8");
  });

  it("renders hire signal badge with correct styling", () => {
    render(
      <SessionCard
        session={makeSession({ hire_signal: "Strong Yes" })}
        onClick={jest.fn()}
      />
    );

    const badge = screen.getByTestId("session-hire-signal");
    expect(badge).toHaveTextContent("Strong Yes");
    expect(badge.className).toContain("green");
  });

  it("shows In Progress when score is null", () => {
    render(
      <SessionCard
        session={makeSession({ overall_score: null, hire_signal: null })}
        onClick={jest.fn()}
      />
    );

    expect(screen.getByTestId("session-in-progress")).toHaveTextContent(
      "In Progress"
    );
    expect(screen.queryByTestId("session-score")).not.toBeInTheDocument();
  });

  it("calls onClick with session_id when clicked", () => {
    const onClick = jest.fn();
    render(
      <SessionCard
        session={makeSession({ session_id: "abc-123" })}
        onClick={onClick}
      />
    );

    fireEvent.click(screen.getByTestId("session-card"));
    expect(onClick).toHaveBeenCalledWith("abc-123");
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// Tests — formatSessionDate
// ---------------------------------------------------------------------------

describe("formatSessionDate", () => {
  it("formats ISO date to readable format", () => {
    const formatted = formatSessionDate("2026-02-15T10:30:00Z");
    expect(formatted).toBeTruthy();
    // Should contain year
    expect(formatted).toContain("2026");
  });
});

// ---------------------------------------------------------------------------
// Tests — History Page
// ---------------------------------------------------------------------------

describe("HistoryPage", () => {
  // We need to dynamically import the page since it has hooks
  async function renderHistoryPage() {
    const HistoryPage = (await import("@/app/history/page")).default;
    return render(<HistoryPage />);
  }

  it("shows loading state initially", async () => {
    mockGetSessions.mockReturnValue(new Promise(() => {})); // never resolves
    await renderHistoryPage();

    expect(screen.getByTestId("loading")).toHaveTextContent("Loading sessions...");
  });

  it("renders session cards after loading", async () => {
    const sessions = [
      makeSession({ session_id: "s1", scenario: "URL Shortener" }),
      makeSession({ session_id: "s2", scenario: "Payment Gateway" }),
    ];
    mockGetSessions.mockResolvedValue(sessions);

    await renderHistoryPage();

    await waitFor(() => {
      expect(screen.getAllByTestId("session-card")).toHaveLength(2);
    });

    expect(screen.getByText("URL Shortener")).toBeInTheDocument();
    expect(screen.getByText("Payment Gateway")).toBeInTheDocument();
  });

  it("shows empty state when no sessions", async () => {
    mockGetSessions.mockResolvedValue([]);

    await renderHistoryPage();

    await waitFor(() => {
      expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    });

    expect(screen.getByText("No sessions yet.")).toBeInTheDocument();
  });

  it("shows error message on API failure", async () => {
    mockGetSessions.mockRejectedValue(new Error("Network error"));

    await renderHistoryPage();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Failed to load session history."
      );
    });
  });

  it("navigates to feedback page on card click", async () => {
    mockGetSessions.mockResolvedValue([
      makeSession({ session_id: "nav-test" }),
    ]);

    await renderHistoryPage();

    await waitFor(() => {
      expect(screen.getByTestId("session-card")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("session-card"));
    expect(mockPush).toHaveBeenCalledWith("/feedback/nav-test");
  });
});

// ---------------------------------------------------------------------------
// Tests — TranscriptReplay helpers
// ---------------------------------------------------------------------------

describe("formatRelativeTime", () => {
  it("formats time difference as MM:SS", () => {
    const result = formatRelativeTime(
      "2026-01-01T00:05:30Z",
      "2026-01-01T00:00:00Z"
    );
    expect(result).toBe("05:30");
  });

  it("handles zero difference", () => {
    const result = formatRelativeTime(
      "2026-01-01T00:00:00Z",
      "2026-01-01T00:00:00Z"
    );
    expect(result).toBe("00:00");
  });

  it("handles large time differences", () => {
    const result = formatRelativeTime(
      "2026-01-01T01:23:45Z",
      "2026-01-01T00:00:00Z"
    );
    expect(result).toBe("83:45");
  });
});

describe("extractPhase", () => {
  it("extracts phase from content with [PHASE:] marker", () => {
    expect(extractPhase("[PHASE:scope] Let's define the requirements.")).toBe(
      "scope"
    );
  });

  it("returns null when no phase marker present", () => {
    expect(extractPhase("Just a regular message.")).toBeNull();
  });

  it("is case-insensitive", () => {
    expect(extractPhase("[PHASE:ARCHITECTURE] Let's design.")).toBe(
      "architecture"
    );
  });

  it("returns null for invalid phase values", () => {
    expect(extractPhase("[PHASE:invalid_phase] Something.")).toBeNull();
  });
});
