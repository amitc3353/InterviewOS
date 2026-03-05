/**
 * Integration tests for the landing page — scenario loading with mock API.
 */

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import type { Scenario } from "@/lib/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockPush = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockGetScenarios = jest.fn();
const mockCreateSession = jest.fn();

jest.mock("@/lib/api", () => ({
  api: {
    getScenarios: (...args: unknown[]) => mockGetScenarios(...args),
    createSession: (...args: unknown[]) => mockCreateSession(...args),
  },
}));

// Import after mocks are set up
import Home from "@/app/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TEST_SCENARIOS: Scenario[] = [
  {
    id: "url-shortener",
    name: "Design a URL Shortener",
    description: "Design a URL shortening service.",
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

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockPush.mockReset();
  mockGetScenarios.mockReset();
  mockCreateSession.mockReset();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Home page", () => {
  it("shows loading state initially", () => {
    mockGetScenarios.mockReturnValue(new Promise(() => {})); // never resolves
    render(<Home />);

    expect(screen.getByTestId("loading")).toHaveTextContent(
      "Loading scenarios..."
    );
  });

  it("renders scenarios after loading", async () => {
    mockGetScenarios.mockResolvedValue(TEST_SCENARIOS);
    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText("Design a URL Shortener")).toBeInTheDocument();
    });

    expect(screen.getByText("Design a Payment Gateway")).toBeInTheDocument();
    expect(screen.queryByTestId("loading")).not.toBeInTheDocument();
  });

  it("renders page header and subtitle", async () => {
    mockGetScenarios.mockResolvedValue([]);
    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText("InterviewOS")).toBeInTheDocument();
    });

    expect(
      screen.getByText(/system design interview simulator/i)
    ).toBeInTheDocument();
  });

  it("shows empty state when no scenarios", async () => {
    mockGetScenarios.mockResolvedValue([]);
    render(<Home />);

    await waitFor(() => {
      expect(screen.getByTestId("empty-state")).toHaveTextContent(
        "No scenarios available."
      );
    });
  });

  it("shows error when scenario loading fails", async () => {
    mockGetScenarios.mockRejectedValue(new Error("network error"));
    render(<Home />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Failed to load scenarios."
      );
    });
  });

  it("creates session and navigates on Start Interview click", async () => {
    mockGetScenarios.mockResolvedValue(TEST_SCENARIOS);
    mockCreateSession.mockResolvedValue({ session_id: "session-abc" });

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText("Design a URL Shortener")).toBeInTheDocument();
    });

    const buttons = screen.getAllByRole("button", {
      name: /start interview/i,
    });
    fireEvent.click(buttons[0]);

    await waitFor(() => {
      expect(mockCreateSession).toHaveBeenCalledWith("url-shortener");
    });

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/interview/session-abc");
    });
  });

  it("shows error when session creation fails", async () => {
    mockGetScenarios.mockResolvedValue(TEST_SCENARIOS);
    mockCreateSession.mockRejectedValue(new Error("server error"));

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText("Design a URL Shortener")).toBeInTheDocument();
    });

    const buttons = screen.getAllByRole("button", {
      name: /start interview/i,
    });
    fireEvent.click(buttons[0]);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Failed to create session"
      );
    });
  });
});
